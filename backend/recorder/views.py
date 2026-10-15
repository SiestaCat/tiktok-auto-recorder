"""JSON API with one constant-time X-API-Key authenticator."""
import json
import re
import secrets
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import FileResponse, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import EventLog, Recording, Target
from .profileImport import importProfile, MAX_ZIP_BYTES
from .utils import logEvent, normalizeUsername, validateInterval

from datetime import timedelta

def responseError(message, status=400):
    return JsonResponse({'error': str(message)}, status=status)


def withApiKey(handler):
    @wraps(handler)
    @csrf_exempt
    def wrapper(request, *args, **kwargs):
        key = request.headers.get('X-API-Key', '')
        if not key or not secrets.compare_digest(key, settings.API_KEY):
            return responseError('API key inválida', 401)
        try:
            return handler(request, *args, **kwargs)
        except (ValidationError, ValueError) as error:
            message = '; '.join(error.messages) if isinstance(error, ValidationError) else str(error)
            return responseError(message)
    return wrapper


def requestJson(request):
    if request.content_type != 'application/json':
        raise ValidationError('Content-Type debe ser application/json')
    try:
        value = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        raise ValidationError('JSON inválido')
    if not isinstance(value, dict):
        raise ValidationError('Se esperaba un objeto JSON')
    return value


def iso(value):
    return value.isoformat() if value else None


def targetJson(target):
    return dict(username=target.username, active=target.active, auto_check=target.auto_check,
                check_interval_minutes=target.check_interval_minutes, status=target.status,
                last_checked_at=iso(target.last_checked_at), next_check_at=iso(target.next_check_at),
                last_error=target.last_error)


def recordingJson(item):
    sizeBytes = item.size_bytes

    if item.status == 'recording':
        path = validPath(settings.DATA_DIR / 'videos', item.file_path)
        try:
            sizeBytes = path.stat().st_size
        except FileNotFoundError:
            pass

    return dict(id=item.pk, username=item.target.username,
                filename=Path(item.file_path).name, status=item.status,
                size_bytes=sizeBytes, started_at=iso(item.started_at), ended_at=iso(item.ended_at),
                download_url=f'/api/v1/recordings/{item.pk}/download/',
                logs_url=f'/api/v1/recordings/{item.pk}/logs/')


def findTarget(username):
    return Target.objects.filter(username=normalizeUsername(username)).first()


def validPath(basePath, relativePath):
    root = Path(basePath).resolve()
    candidate = (settings.DATA_DIR / relativePath).resolve()
    if not candidate.is_relative_to(root):
        raise ValidationError('Ruta de archivo inválida')
    return candidate


def health(request):
    return JsonResponse({'ok': True})


@withApiKey
@require_http_methods(['GET', 'POST'])
def targets(request):
    if request.method == 'GET':
        return JsonResponse({'results': [targetJson(t) for t in Target.objects.order_by('username')]})
    data = requestJson(request)
    username = normalizeUsername(data.get('username'))
    interval = validateInterval(data.get('check_interval_minutes', 5))
    obj, created = Target.objects.get_or_create(username=username, defaults={'check_interval_minutes': interval})
    if not created:
        return responseError('Ese usuario ya existe', 409)
    logEvent(obj, 'Usuario creado')
    return JsonResponse(targetJson(obj), status=201)


@withApiKey
@require_http_methods(['GET', 'DELETE'])
def targetDetail(request, username):
    obj = findTarget(username)
    if not obj:
        return responseError('Usuario no encontrado', 404)
    if request.method == 'GET':
        return JsonResponse(targetJson(obj))
    if obj.active or obj.status in ('checking', 'recording', 'stopping'):
        return responseError('Detén el usuario antes de borrarlo', 409)
    if obj.recordings.exists():
        return responseError('Elimina primero sus grabaciones', 409)
    logEvent(obj, 'Usuario eliminado')
    obj.delete()
    return HttpResponse(status=204)


@withApiKey
@require_http_methods(['POST'])
def startTarget(request, username):
    obj = findTarget(username)
    if not obj:
        return responseError('Usuario no encontrado', 404)
    data = requestJson(request)
    if 'auto_check' in data:
        if not isinstance(data['auto_check'], bool):
            return responseError('auto_check debe ser booleano')
        obj.auto_check = data['auto_check']
    if 'check_interval_minutes' in data:
        obj.check_interval_minutes = validateInterval(data['check_interval_minutes'])
    obj.active = True
    obj.status = 'waiting' if obj.status not in ('recording', 'checking') else obj.status
    obj.next_check_at = timezone.now()
    obj.last_error = ''
    obj.save()
    logEvent(obj, f'Activado (automático={obj.auto_check}, cada {obj.check_interval_minutes} min)')
    return JsonResponse(targetJson(obj))


@withApiKey
@require_http_methods(['POST'])
def stopTarget(request, username):
    obj = findTarget(username)
    if not obj:
        return responseError('Usuario no encontrado', 404)

    busy = obj.status in ('recording', 'checking', 'stopping')

    if busy:
        obj.active = False
        obj.next_check_at = None
        obj.status = 'stopping'
    elif obj.auto_check:
        obj.active = True
        obj.next_check_at = timezone.now() + timedelta(minutes=obj.check_interval_minutes)
        obj.status = 'waiting'
    else:
        obj.active = False
        obj.next_check_at = None
        obj.status = 'stopped'

    obj.save()
    logEvent(obj, 'Parada solicitada; programación automática conservada')
    return JsonResponse(targetJson(obj))


@withApiKey
@require_http_methods(['POST'])
def scheduleTarget(request, username):
    obj = findTarget(username)
    if not obj:
        return responseError('Usuario no encontrado', 404)
    data = requestJson(request)
    if not isinstance(data.get('enabled'), bool):
        return responseError('enabled debe ser booleano')
    obj.auto_check = data['enabled']
    if 'check_interval_minutes' in data:
        obj.check_interval_minutes = validateInterval(data['check_interval_minutes'])
    if obj.auto_check:
        obj.active = True
        obj.next_check_at = timezone.now()
        if obj.status not in ('recording', 'checking'):
            obj.status = 'waiting'
    else:
        obj.active = False
        obj.next_check_at = None
        obj.status = 'stopping' if obj.status in ('recording', 'checking') else 'stopped'
    obj.save()
    logEvent(obj, f'Programación {"activada" if obj.auto_check else "desactivada"}; intervalo {obj.check_interval_minutes} min')
    return JsonResponse(targetJson(obj))


@withApiKey
@require_http_methods(['GET'])
def recordings(request):
    qs = Recording.objects.select_related('target').order_by('-started_at')
    if request.GET.get('username'):
        qs = qs.filter(target__username=normalizeUsername(request.GET['username']))
    return JsonResponse({'results': [recordingJson(item) for item in qs[:200]]})


@withApiKey
@require_http_methods(['GET'])
def downloadRecording(request, recordingId):
    rec = Recording.objects.filter(pk=recordingId).first()
    if not rec:
        return responseError('Grabación no encontrada', 404)
    if rec.status == 'recording':
        return responseError('La grabación sigue en curso', 409)
    path = validPath(settings.DATA_DIR / 'videos', rec.file_path)
    if not path.is_file():
        return responseError('Archivo no encontrado en disco', 404)
    return FileResponse(path.open('rb'), as_attachment=True, filename=path.name)


@withApiKey
@require_http_methods(['DELETE'])
def deleteRecording(request, recordingId):
    rec = Recording.objects.select_related('target').filter(pk=recordingId).first()
    if not rec:
        return responseError('Grabación no encontrada', 404)
    if rec.status == 'recording':
        return responseError('Detén la grabación antes de borrarla', 409)
    for path in (validPath(settings.DATA_DIR / 'videos', rec.file_path),
                 validPath(settings.DATA_DIR / 'logs', rec.ffmpeg_log) if rec.ffmpeg_log else None):
        if path:
            path.unlink(missing_ok=True)
    logEvent(rec.target, f'Grabación eliminada: {Path(rec.file_path).name}')
    rec.delete()
    return HttpResponse(status=204)


URL_RE = re.compile(r'https?://[^\s\]<>\"\']+')


def redactUrls(text):
    def redact(match):
        split = urlsplit(match.group(0))
        return urlunsplit((split.scheme, split.netloc, split.path, '', '')) + ('?[REDACTED]' if split.query else '')
    return URL_RE.sub(redact, text)


@withApiKey
@require_http_methods(['GET'])
def recordingLogs(request, recordingId):
    rec = Recording.objects.filter(pk=recordingId).first()
    if not rec:
        return responseError('Grabación no encontrada', 404)
    if not rec.ffmpeg_log:
        return JsonResponse({'text': ''})
    path = validPath(settings.DATA_DIR / 'logs', rec.ffmpeg_log)
    if not path.is_file():
        return JsonResponse({'text': ''})
    # Read only the last 64 KiB, even for multi-day recordings.
    with path.open('rb') as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 65536))
        text = f.read().decode('utf-8', errors='replace')
    return JsonResponse({'text': redactUrls(text[-20000:])})


@withApiKey
@require_http_methods(['GET'])
def logs(request):
    qs = EventLog.objects.select_related('target').order_by('-created_at')
    if request.GET.get('username'):
        qs = qs.filter(target__username=normalizeUsername(request.GET['username']))
    try:
        limit = max(1, min(500, int(request.GET.get('limit', 100))))
    except ValueError:
        raise ValidationError('limit no válido')
    return JsonResponse({'results': [dict(id=x.pk, username=x.target.username if x.target else None,
                                          level=x.level, message=x.message, created_at=iso(x.created_at)) for x in qs[:limit]]})


@withApiKey
@require_http_methods(['GET', 'POST'])
def profile(request):
    if request.method == 'GET':
        directory = settings.DATA_DIR / 'profile'
        return JsonResponse({'installed': (directory / 'cookies.sqlite').is_file()})
    upload = request.FILES.get('file')
    if upload is None:
        return responseError('Se requiere el archivo ZIP en el campo file')
    if upload.size > MAX_ZIP_BYTES:
        return responseError('ZIP demasiado grande', 413)
    count = importProfile(upload, settings.DATA_DIR)
    logEvent(None, f'Perfil importado desde ZIP: {count} archivos')
    return JsonResponse({'installed': True, 'imported_files': count})
