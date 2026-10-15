#!/usr/bin/env python3
"""Interactive Debian host login; never run from the Docker containers."""
import argparse
import zipfile
from pathlib import Path

from invisible_playwright import InvisiblePlaywright
from tiktokRecorder.config import getProfileSeed
from tiktokRecorder.profile import PROFILE_FILES


def archiveProfile(profileDir, filename):
    if not (profileDir / 'cookies.sqlite').is_file():
        raise SystemExit('No se encontró cookies.sqlite; ¿se ha completado el inicio de sesión?')
    archivePaths = ['.invisible-playwright-seed', *PROFILE_FILES]
    filename.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(filename, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in archivePaths:
            path = profileDir / name
            if path.is_symlink():
                raise SystemExit('No se admiten enlaces simbólicos en el perfil')
            if path.is_file():
                archive.write(path, arcname=f'profile/{name}')
            elif path.is_dir():
                for item in path.rglob('*'):
                    if item.is_symlink():
                        raise SystemExit('No se admiten enlaces simbólicos dentro del perfil')
                    if item.is_file():
                        archive.write(item, arcname=f'profile/{item.relative_to(profileDir).as_posix()}')
    print(f'ZIP creado: {filename}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('profile_path')
    parser.add_argument('--zip-output')
    args = parser.parse_args()
    profileDir = Path(args.profile_path).resolve()
    profileDir.mkdir(parents=True, exist_ok=True)
    profileDir.chmod(0o700)
    seed = getProfileSeed(profileDir)
    with InvisiblePlaywright(profile_dir=profileDir, seed=seed, headless=False) as context:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto('https://www.tiktok.com', wait_until='domcontentloaded', timeout=60000)
        input('Inicia sesión en TikTok en la ventana y pulsa Enter aquí cuando termines... ')
    if not (profileDir / 'cookies.sqlite').is_file():
        raise SystemExit('No existe cookies.sqlite después de cerrar el navegador. No se exporta un perfil vacío.')
    print(f'Perfil guardado en: {profileDir}')
    if args.zip_output:
        archiveProfile(profileDir, Path(args.zip_output).resolve())


if __name__ == '__main__':
    main()
