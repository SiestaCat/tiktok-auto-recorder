"""Isolate the saved authenticated Firefox profile for every LIVE check."""
import fcntl
import hashlib
import secrets
import shutil
from contextlib import contextmanager
from pathlib import Path

from .config import getProfileSeed

PROFILE_FILES = ("cookies.sqlite", "cookies.sqlite-wal", "storage", "storage.sqlite")


@contextmanager
def profileLock(dataDir, exclusive=False):
    """Serialize imports against copies; shared for concurrent profile copies."""
    dataDir = Path(dataDir)
    dataDir.mkdir(parents=True, exist_ok=True)
    with (dataDir / "profile.lock").open("a+b") as lockFile:
        fcntl.flock(lockFile, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(lockFile, fcntl.LOCK_UN)


def cloneProfile(profileDir, username, seedHolder=None):
    profileDir = Path(profileDir)
    with profileLock(profileDir.parent):
        if not (profileDir / "cookies.sqlite").is_file():
            raise FileNotFoundError("Falta data/profile/cookies.sqlite. Importa primero un perfil desde el host.")
        profileSeed = getProfileSeed(profileDir)
        while True:
            profileHash = hashlib.sha256(f"{username.lower()}:{secrets.token_hex(16)}".encode()).hexdigest()[:12]
            profileCopy = profileDir.parent / f"profile_{username.lower()}_{profileHash}"
            try:
                profileCopy.mkdir(mode=0o700)
                break
            except FileExistsError:
                continue
        try:
            for name in PROFILE_FILES:
                source = profileDir / name
                target = profileCopy / name
                if not source.exists():
                    continue
                if source.is_symlink():
                    raise ValueError(f"Enlace simbólico prohibido: {name}")
                if source.is_dir():
                    if any(p.is_symlink() for p in source.rglob('*')):
                        raise ValueError(f'Enlace simbólico prohibido bajo {name}')
                    shutil.copytree(source, target, symlinks=False)
                else:
                    shutil.copy2(source, target)
                    target.chmod(0o600)
            if seedHolder is not None:
                seedHolder.append(profileSeed)
            return profileCopy
        except Exception:
            shutil.rmtree(profileCopy, ignore_errors=True)
            raise


def createBrowserFactory(profileDir, username, createdCopies=None, playwrightClass=None):
    profileDir = Path(profileDir)
    if playwrightClass is None:
        from invisible_playwright import InvisiblePlaywright
        playwrightClass = InvisiblePlaywright

    def browserFactory():
        seeds = []
        profileCopy = cloneProfile(profileDir, username, seedHolder=seeds)
        if createdCopies is not None:
            createdCopies.append(profileCopy)
        return playwrightClass(profile_dir=profileCopy, seed=seeds[0], headless=True)

    return browserFactory
