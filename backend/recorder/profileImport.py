"""Strict ZIP import: only known profile files, no symlinks or traversal."""
import secrets
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from django.core.exceptions import ValidationError
from tiktokRecorder.profile import profileLock
from tiktokRecorder.config import getProfileSeed

MAX_ZIP_BYTES = 256 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_FILES = 2000


def allowedPath(name):
    path = PurePosixPath(name)
    parts = path.parts
    if not parts or name.startswith('/') or '\\' in name or '..' in parts or ':' in name:
        raise ValidationError('Ruta no permitida dentro del ZIP')
    if parts[:2] == ('data', 'profile'):
        parts = parts[2:]
    elif parts[:1] == ('profile',):
        parts = parts[1:]
    if not parts:
        return None
    if parts[0] in ('cookies.sqlite', 'cookies.sqlite-wal', 'storage.sqlite', '.invisible-playwright-seed') and len(parts) == 1:
        return Path(*parts)
    if parts[0] == 'storage' and len(parts) > 1:
        return Path(*parts)
    if parts == ('storage',):
        return Path('storage')
    raise ValidationError('El ZIP contiene archivos ajenos al perfil permitido')


def importProfile(uploadedFile, dataDir):
    if uploadedFile.size > MAX_ZIP_BYTES:
        raise ValidationError('ZIP demasiado grande (máx. 256 MiB)')
    dataDir = Path(dataDir)
    dataDir.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.profile-import-', dir=dataDir))
    backup = dataDir / f'.profile-backup-{secrets.token_hex(8)}'
    count = 0
    try:
        try:
            with zipfile.ZipFile(uploadedFile) as archive:
                members = archive.infolist()
                if len(members) > MAX_FILES:
                    raise ValidationError('Demasiados archivos dentro del ZIP')
                if sum(info.file_size for info in members) > MAX_UNCOMPRESSED_BYTES:
                    raise ValidationError('ZIP descomprimido demasiado grande')
                filesSeen = set()
                for info in members:
                    # Symlinks / device entries are not regular files.
                    unixMode = (info.external_attr >> 16) & 0xffff
                    fileType = stat.S_IFMT(unixMode)
                    if fileType not in (0, stat.S_IFREG, stat.S_IFDIR):
                        raise ValidationError('El ZIP contiene entradas no regulares')
                    relative = allowedPath(info.filename)
                    if relative is None:
                        continue
                    if relative == Path('storage') and not info.is_dir():
                        raise ValidationError('storage debe ser un directorio')
                    if info.is_dir() and relative.name != 'storage' and relative.parts[0] != 'storage':
                        raise ValidationError('Directorio fuera de storage')
                    if info.is_dir():
                        (stage / relative).mkdir(parents=True, exist_ok=True)
                        continue
                    if relative in filesSeen:
                        raise ValidationError('El ZIP contiene entradas duplicadas')
                    filesSeen.add(relative)
                    destination = stage / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as src, destination.open('xb') as dst:
                        shutil.copyfileobj(src, dst, length=1024 * 1024)
                    destination.chmod(0o600)
                    count += 1
        except (zipfile.BadZipFile, OSError) as error:
            raise ValidationError(f'ZIP inválido: {error}')
        if not (stage / 'cookies.sqlite').is_file():
            raise ValidationError('El ZIP debe incluir cookies.sqlite')
        # Generate/validate stable fingerprint seed inside the imported profile.
        try:
            getProfileSeed(stage)
        except (ValueError, OSError) as error:
            raise ValidationError(f'Seed de perfil inválido: {error}')
        with profileLock(dataDir, exclusive=True):
            profileDir = dataDir / 'profile'
            if profileDir.exists():
                profileDir.rename(backup)
            try:
                stage.rename(profileDir)
            except Exception:
                if backup.exists():
                    backup.rename(profileDir)
                raise
        return count
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)
