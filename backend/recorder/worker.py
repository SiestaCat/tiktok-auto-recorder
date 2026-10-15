"""Single worker service with concurrent independent Playwright/FFmpeg jobs."""
import os
import shutil
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from .models import Recording, Target
from .utils import logEvent
from tiktokRecorder.browser import BrowserSession, checkLiveWithRecovery
from tiktokRecorder.profile import createBrowserFactory
from tiktokRecorder.streams import getLiveStreams

STOP = threading.Event()


def shouldContinue(pk):
    close_old_connections()
    return Target.objects.filter(pk=pk, active=True).exists() and not STOP.is_set()


def updateTarget(pk, **fields):
    close_old_connections()
    Target.objects.filter(pk=pk).update(**fields)


def stopFfmpeg(process):
    if process.poll() is not None:
        return
    try:
        process.stdin.write(b'q\n')
        process.stdin.flush()
        process.wait(timeout=12)
    except (OSError, subprocess.TimeoutExpired):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=6)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def runFfmpeg(target, streams, userAgent):
    videosDir = settings.DATA_DIR / 'videos' / target.username
    logDir = settings.DATA_DIR / 'logs'
    videosDir.mkdir(parents=True, exist_ok=True)
    logDir.mkdir(parents=True, exist_ok=True)
    # UUID avoids collisions when a new stream starts within the same second.
    import uuid
    filename = f'{target.username}_{timezone.now():%Y-%m-%d_%H-%M-%S}_{uuid.uuid4().hex[:8]}.mkv'
    outputFile = videosDir / filename
    logFile = logDir / f'{filename}.ffmpeg.log'
    rec = Recording.objects.create(target=target,
        file_path=str(outputFile.relative_to(settings.DATA_DIR)),
        ffmpeg_log=str(logFile.relative_to(settings.DATA_DIR)), status='recording')
    logEvent(target, f'Iniciando grabación: {filename}')
    updateTarget(target.pk, status='recording')
    status = 'failed'
    try:
        for streamUrl in streams:
            if not shouldContinue(target.pk):
                status = 'stopped'
                break
            command = [
                'ffmpeg', '-hide_banner', '-loglevel', 'warning',
                '-user_agent', userAgent,
                '-referer', f'https://www.tiktok.com/@{target.username}/live',
                '-analyzeduration', '30000000', '-probesize', '50000000',
                '-i', streamUrl, '-map', '0:v:0', '-map', '0:a:0?',
                '-c', 'copy', '-y', str(outputFile),
            ]
            with logFile.open('ab') as stderr:
                proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=stderr)
                try:
                    while proc.poll() is None:
                        if not shouldContinue(target.pk):
                            stopFfmpeg(proc)
                            status = 'stopped'
                            break
                        time.sleep(1)
                    code = proc.wait()
                finally:
                    if proc.poll() is None:
                        stopFfmpeg(proc)
                    if proc.stdin:
                        proc.stdin.close()
            if outputFile.exists() and outputFile.stat().st_size > 0:
                if status != 'stopped':
                    status = 'completed' if code == 0 else 'partial'
                break
            outputFile.unlink(missing_ok=True)
            if status == 'stopped':
                break
        return status
    finally:
        size = outputFile.stat().st_size if outputFile.is_file() else 0
        rec.status = status
        rec.size_bytes = size
        rec.ended_at = timezone.now()
        rec.save(update_fields=['status', 'size_bytes', 'ended_at'])
        logEvent(target, f'Grabación {status}: {filename} ({size} bytes)', 'error' if status == 'failed' else 'info')


def checkTarget(pk):
    """One attempt per task: clone profile, launch browser, then independent FFmpeg."""
    close_old_connections()
    clones = []
    try:
        target = Target.objects.get(pk=pk)
        if not target.active:
            return
        updateTarget(pk, status='checking', last_checked_at=timezone.now(), last_error='')
        logEvent(target, 'Comprobando LIVE mediante Playwright aislado')
        profileDir = settings.DATA_DIR / 'profile'
        factory = createBrowserFactory(profileDir, target.username, createdCopies=clones)
        with BrowserSession(factory) as session:
            streams, userAgent = checkLiveWithRecovery(session, target.username, getLiveStreams)
        # Browser is now closed. FFmpeg is independent of the Playwright session.
        if not shouldContinue(pk):
            return
        if not streams:
            logEvent(target, 'El LIVE no está activo')
        else:
            runFfmpeg(target, streams, userAgent)
    except Exception as error:
        close_old_connections()
        updateTarget(pk, last_error=str(error)[:2000])
        target = Target.objects.filter(pk=pk).first()
        logEvent(target, f'Error comprobando/grabando LIVE: {error}', level='error')
    finally:
        for profile in clones:
            if os.environ.get('KEEP_ATTEMPT_PROFILES', '0') != '1':
                shutil.rmtree(profile, ignore_errors=True)
        close_old_connections()
        target = Target.objects.filter(pk=pk).first()
        if target:
            if target.auto_check and not STOP.is_set():
                updateTarget(pk, status='waiting', active=True, next_check_at=timezone.now() + timedelta(minutes=target.check_interval_minutes))
            else:
                updateTarget(pk, status='stopped', active=False, next_check_at=None)
        close_old_connections()


def runWorker():
    concurrency = max(1, min(32, int(os.environ.get('WORKER_CONCURRENCY', '4'))))

    def shutdown(signum, frame):
        STOP.set()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    # Exactly ONE worker replica must run. Recover interrupted recordings after a crash.
    # This runs before any new checks are submitted.
    for rec in Recording.objects.filter(status='recording'):
        path = (settings.DATA_DIR / rec.file_path).resolve()
        root = (settings.DATA_DIR / 'videos').resolve()
        size = path.stat().st_size if path.is_relative_to(root) and path.is_file() else 0
        rec.status = 'partial' if size else 'failed'
        rec.size_bytes = size
        rec.ended_at = timezone.now()
        rec.save(update_fields=['status', 'size_bytes', 'ended_at'])
        logEvent(rec.target, f'Recuperada grabación interrumpida: {path.name} ({rec.status})', 'warning')
    Target.objects.filter(active=True).update(status='waiting', next_check_at=timezone.now())
    Target.objects.filter(active=False).update(status='stopped', next_check_at=None)
    pool = ThreadPoolExecutor(max_workers=concurrency)
    tasks = {}
    print(f'Worker iniciado; concurrencia={concurrency}', flush=True)
    try:
        while not STOP.is_set():
            close_old_connections()
            for pk, future in list(tasks.items()):
                if future.done():
                    try:
                        future.result()
                    except Exception as error:
                        print(f'Excepción inesperada en tarea {pk}: {error}', flush=True)
                    del tasks[pk]
            if len(tasks) < concurrency:
                now = timezone.now()
                ready = Target.objects.filter(active=True, next_check_at__lte=now).exclude(pk__in=tasks).order_by('next_check_at')
                for target in ready[:concurrency - len(tasks)]:
                    # Reserve until task has finished; prevents duplicate dispatch in this worker.
                    tasks[target.pk] = pool.submit(checkTarget, target.pk)
            STOP.wait(2)
    finally:
        STOP.set()
        print('Deteniendo worker y FFmpeg; esperando cierre limpio...', flush=True)
        pool.shutdown(wait=True)
        close_old_connections()
