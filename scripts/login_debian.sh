#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
VENV="$ROOT_DIR/.host-venv"
TMPDIR_PROFILE=''
cleanup() { if [[ -n "$TMPDIR_PROFILE" ]]; then rm -rf -- "$TMPDIR_PROFILE"; fi; }
trap cleanup EXIT

echo 'Inicio de sesión TikTok fuera de Docker (requiere sesión gráfica en Debian).'
echo '1) Guardar directamente en la ruta absoluta del volumen de datos'
echo '2) Crear un ZIP con el perfil para importarlo desde la API'
read -r -p 'Selecciona 1 o 2: ' MODE
case "$MODE" in
  1)
    read -r -p 'Ruta ABSOLUTA del volumen de datos (ej. /home/user/tiktok_docker/data): ' DATA_DEST
    if [[ "$DATA_DEST" != /* || "$DATA_DEST" == '/' ]]; then echo 'La ruta debe ser absoluta y distinta de /'; exit 1; fi
    mkdir -p -- "$DATA_DEST/profile"
    PROFILE_DIR="$DATA_DEST/profile"
    echo "El perfil se guardará en $PROFILE_DIR"
    ;;
  2)
    read -r -p 'Ruta ABSOLUTA del ZIP a generar (ej. /home/user/tiktok-profile.zip): ' ZIP_DEST
    if [[ "$ZIP_DEST" != /* || "$ZIP_DEST" == '/' ]]; then echo 'La ruta debe ser absoluta'; exit 1; fi
    TMPDIR_PROFILE="$(mktemp -d)"
    PROFILE_DIR="$TMPDIR_PROFILE/profile"
    mkdir -p "$PROFILE_DIR"
    ;;
  *) echo 'Opción no válida'; exit 1 ;;
esac

if [[ ! -x "$VENV/bin/python" ]]; then
  echo 'Creando entorno Python del host...'
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --disable-pip-version-check 'playwright>=1.55,<2' 'invisible-playwright>=0.22,<1'
"$VENV/bin/python" -m invisible_playwright fetch
export PYTHONPATH="$ROOT_DIR/backend"
if [[ "$MODE" == '2' ]]; then
  "$VENV/bin/python" "$SCRIPT_DIR/hostLogin.py" "$PROFILE_DIR" --zip-output "$ZIP_DEST"
  echo 'Para importar el ZIP usa la interfaz web o POST /api/v1/profile/.'
else
  "$VENV/bin/python" "$SCRIPT_DIR/hostLogin.py" "$PROFILE_DIR"
  echo 'El perfil está disponible para los contenedores que monten ese volumen como /app/data.'
fi
