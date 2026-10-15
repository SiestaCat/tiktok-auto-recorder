# TikTok MultiRecorder — Django + MySQL + Docker

Webservice para gestionar grabaciones de LIVE de TikTok. Reutiliza la **verificación de sala** y la prioridad de URLs de stream del grabador anterior. Cada comprobación usa **una instancia de `InvisiblePlaywright` nueva**, en modo `headless=True`, con un perfil distinto `data/profile_USERNAME_HASH` creado desde la sesión guardada en `data/profile`. FFmpeg puede grabar varios usuarios simultáneamente (hasta el límite del worker).

## Arquitectura

| Contenedor | Dockerfile / imagen | Función |
|---|---|---|
| `mysql` | `mysql:8.4` | Base de datos persistente |
| `api` | `backend/Dockerfile` → `tiktok-recorder-api:local` | API Django REST JSON bajo `/api/v1/` y carga de perfiles ZIP |
| `worker` | **misma imagen backend** | Worker independiente que comprueba directos y ejecuta FFmpeg |
| `web` | `web/Dockerfile` → `tiktok-recorder-web:local` | Panel Flask con contraseña; se comunica por HTTP con la API usando su propia configuración |

**Importante:** ejecutar **una sola réplica** del worker. Dentro de ella pueden correr varias comprobaciones y grabaciones en paralelo (`WORKER_CONCURRENCY`). No necesita Redis, Celery, cron externo ni yt-dlp.

## 1. Preparación de Debian (host)

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin python3-venv xvfb \
    libgtk-3-0 libnss3 libasound2 fonts-liberation
```

Si tu distribución proporciona Docker Compose por otro método, instala Docker Engine + el plugin Compose oficial. FFmpeg, Playwright, `invisible-playwright` y sus binarios **se instalan en la imagen backend**; no es necesario instalar pipx ni yt-dlp en el host para este proyecto. El script del host crea su propio virtualenv y descarga el navegador modificado.

Descomprime el proyecto, sitúate en su directorio raíz y crea el volumen de datos:

```bash
mkdir -p data
cp .env.example .env
chmod 600 .env
id -u
id -g
```

Edita `.env` antes de arrancar. Ajusta `APP_UID` y `APP_GID` con las salidas de `id -u` y `id -g` para que el worker pueda crear ficheros en `./data` sin usar root. Para generar valores aleatorios:

```bash
openssl rand -hex 32  # copiar a DJANGO_SECRET_KEY
openssl rand -hex 32  # copiar a API_KEY
openssl rand -hex 32  # copiar a WEB_SESSION_SECRET
```

También debes asignar contraseñas fuertes a `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD` y `WEB_PASSWORD`. Las contraseñas/API key están **en texto plano en variables de entorno**, como se solicitó; no subas `.env` a Git.

## 2. `--login` fuera de Docker: script interactivo

Con sesión gráfica de Debian abierta, ejecuta:

```bash
./scripts/login_debian.sh
```

El script pregunta:

- **Opción 1 — ruta absoluta del volumen de datos**: por ejemplo `/home/miusuario/tiktok_docker/data`. El login se abre en la máquina host y la sesión se guarda en `<ruta>/profile/`. Esa ruta debe coincidir con la carpeta `./data` montada como `/app/data` en Compose.
- **Opción 2 — generar ZIP**: solicita una **ruta absoluta** como `/home/miusuario/tiktok-profile.zip`, abre el navegador usando un perfil temporal y genera un ZIP importable desde la web o la API. Los datos temporales se eliminan al finalizar.

Abre TikTok e inicia sesión manualmente. Cuando acabes, vuelve a la terminal y pulsa Enter; el navegador se cierra y el perfil se consolida.

El script usa `headless=False` en el **host**. Dentro de Docker, todas las comprobaciones usan `headless=True`; **no existe** `--login` en los contenedores.

### Estructura del perfil

```text
data/
  profile/                         # sesión original, no se abre con Playwright dentro de Docker
    cookies.sqlite
    cookies.sqlite-wal             # si existe
    storage/
    storage.sqlite                # si existe
    .invisible-playwright-seed     # para mantener el fingerprint de la sesión
  profile_usuario1_9b3c1d2f.../   # copia independiente por intento (limpiada al acabar)
  profile_usuario2_7f38a3bd.../
  videos/usuario1/*.mkv
  logs/*.ffmpeg.log
```

Solo se copian **`cookies.sqlite`, `cookies.sqlite-wal`, `storage/`, `storage.sqlite`** a los perfiles por intento (los que existan). El seed se lee desde `data/profile/.invisible-playwright-seed`, pero no se copia; se proporciona al constructor de Playwright. Los perfiles de intento se borran automáticamente después del chequeo/grabación; para conservarlos pon `KEEP_ATTEMPT_PROFILES=1` (puede consumir mucho disco). El perfil `data/profile` permanece intacto durante las comprobaciones. Para actualizarlo, vuelve a ejecutar el script en el host o importa un ZIP desde la API.

**No ejecutes el login del host simultáneamente con verificaciones en curso contra la misma carpeta**; para actualizar una sesión activa, usa la importación ZIP.

## 3. Construir dos imágenes por separado

**Dockerfile 1 — API Django + worker:**

```bash
docker build -t tiktok-recorder-api:local -f backend/Dockerfile backend
```

**Dockerfile 2 — interfaz web:**

```bash
docker build -t tiktok-recorder-web:local -f web/Dockerfile web
```

La imagen API/worker ejecuta `python -m invisible_playwright fetch` en la **fase de build** (el navegador modificado puede ocupar varios cientos de MB). No es necesario ejecutar `python -m playwright install firefox` por separado para esta distribución de InvisiblePlaywright.

Arrancar los servicios:

```bash
docker compose up -d

docker compose ps
docker compose logs -f api worker web
```

El servicio `api` aplica migraciones Django al arrancar, después de que MySQL esté listo; `worker` arranca después de que `api` responda correctamente.

- Panel: **http://127.0.0.1:8080** (`WEB_PASSWORD` de `.env`).
- API: **http://127.0.0.1:8000/api/v1/**. Todas las rutas salvo `health/` requieren `X-API-Key`.
- MySQL solo accesible desde la red interna de Compose.
- Los volúmenes son `./data` para vídeos, logs y perfiles, y `mysql_data` para MySQL.

Por defecto el panel y la API solo escuchan en localhost del host. Si necesitas acceso remoto, configura un proxy HTTPS y controla el acceso; no publiques directamente el panel con contraseña de texto plano sobre HTTP en Internet. Para cookies seguras detrás de HTTPS usa `WEB_COOKIE_SECURE=1`.

## 4. Panel web

Desde el panel puedes:

1. Importar el ZIP del perfil (o usar el volumen de datos).
2. Añadir un usuario de TikTok.
3. Pulsar **Iniciar** para una comprobación inmediata. Si el LIVE está activo, FFmpeg comienza a grabar; de lo contrario finaliza el intento (modo manual).
4. Pulsar **Programar** y escoger el número de minutos entre **1 y 1440**. Mientras esté activado, si no hay LIVE se repite la comprobación pasado ese intervalo. Si un LIVE termina, la siguiente comprobación se programa pasado ese intervalo desde su finalización.
5. Pulsar **Detener** para cancelar el seguimiento y solicitar a FFmpeg que termine correctamente; las grabaciones parciales se conservan.
6. Consultar estados, próximas comprobaciones, historial de eventos y el log FFmpeg de cada grabación; descargar o eliminar archivos finalizados.

**Detalles:** el modo **Programar** activa el seguimiento recurrente. **Desprogramar** también solicita parar la grabación actual, si existe. Una comprobación manual iniciada sobre un usuario programado conserva la programación. El worker **no abre continuamente navegadores** mientras FFmpeg graba: el navegador solo se usa para obtener/validar la URL del LIVE y se cierra antes de grabar.

## 5. API: autenticación y endpoints

Todas las solicitudes autenticadas incluyen **el encabezado HTTP `X-API-Key: ...`**. La key se compara con `API_KEY` del entorno de la API. No se acepta en parámetros URL.

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/api/v1/health/` | Salud HTTP (sin autenticación) |
| `GET, POST` | `/api/v1/targets/` | Listar / crear usuarios |
| `GET, DELETE` | `/api/v1/targets/@usuario/` | Consultar / eliminar usuario sin grabaciones |
| `POST` | `/api/v1/targets/@usuario/start/` | Iniciar intento inmediato |
| `POST` | `/api/v1/targets/@usuario/stop/` | Detener comprobaciones y FFmpeg |
| `POST` | `/api/v1/targets/@usuario/schedule/` | Activar/desactivar comprobación recurrente |
| `GET` | `/api/v1/recordings/` | Lista de las últimas 200 grabaciones, filtro opcional `?username=...` |
| `GET` | `/api/v1/recordings/ID/download/` | Descargar archivo terminado |
| `DELETE` | `/api/v1/recordings/ID/` | Borrar grabación terminada y su log FFmpeg |
| `GET` | `/api/v1/recordings/ID/logs/` | Últimos 20 KB del log FFmpeg (URLs privadas redactadas) |
| `GET` | `/api/v1/logs/` | Eventos, filtro `?username=...&limit=100` (1–500) |
| `GET` | `/api/v1/profile/` | Consultar si hay sesión instalada |
| `POST` | `/api/v1/profile/` | Importar sesión en archivo ZIP (`multipart/form-data`, campo `file`) |

### Ejemplos con curl

```bash
export API_URL=http://127.0.0.1:8000/api/v1
export API_KEY='COPIA_AQUI_LA_API_KEY_DEL_ENV'

# Importar perfil desde ZIP (no hace falta --login en Docker)
curl -f -H "X-API-Key: $API_KEY" -F 'file=@/ruta/absoluta/tiktok-profile.zip' "$API_URL/profile/"

# Añadir usuario
curl -f -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"username":"usuario1","check_interval_minutes":5}' "$API_URL/targets/"

# Activar comprobaciones automáticas cada 3 minutos
curl -f -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"enabled":true,"check_interval_minutes":3}' "$API_URL/targets/usuario1/schedule/"

# Iniciar una comprobación ahora (conserva si ya tiene modo automático)
curl -f -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{}' "$API_URL/targets/usuario1/start/"

# Ver estado
curl -f -H "X-API-Key: $API_KEY" "$API_URL/targets/"

# Consultar logs
curl -f -H "X-API-Key: $API_KEY" "$API_URL/logs/?username=usuario1&limit=50"

# Listar grabaciones
curl -f -H "X-API-Key: $API_KEY" "$API_URL/recordings/?username=usuario1"

# Descargar grabación con id=1
curl -fL -H "X-API-Key: $API_KEY" -OJ "$API_URL/recordings/1/download/"

# Eliminar grabación con id=1
curl -f -X DELETE -H "X-API-Key: $API_KEY" "$API_URL/recordings/1/"

# Detener comprobación/grabación
curl -f -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{}' "$API_URL/targets/usuario1/stop/"

# Cancelar programación
curl -f -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"enabled":false}' "$API_URL/targets/usuario1/schedule/"
```

### Seguridad de perfiles ZIP

Se aceptan ZIP con la raíz `profile/`, `data/profile/` o los archivos directamente en la raíz. Solo se importan las entradas `cookies.sqlite`, `cookies.sqlite-wal`, `storage.sqlite`, `.invisible-playwright-seed` y los archivos bajo `storage/`. Los ZIP con rutas ascendentes, enlaces simbólicos, archivos extraños o entradas duplicadas son rechazados. Límites: **256 MiB comprimidos, 512 MiB descomprimidos, 2000 entradas**. El nuevo perfil se prepara aparte y sustituye al original bajo un bloqueo de ficheros compartido con la copia de perfiles del worker.

**Cuidado:** el ZIP es un secreto de autenticación. Trátalo igual que una sesión iniciada. No lo publiques ni lo compartas. La API key y la contraseña de interfaz también son secretos, aunque se configuren en texto plano.

## 6. Logs y operaciones

```bash
docker compose logs -f worker
docker compose logs -f api
docker compose logs -f web
docker compose exec api python manage.py showmigrations
```

Las grabaciones usan `-c copy`, sin recodificar. Archivos bajo `data/videos/<usuario>/`; salida de FFmpeg bajo `data/logs/`. Errores de las comprobaciones se registran en MySQL (`EventLog`), consultables vía `/logs/` y el panel. Las grabaciones no se pueden descargar ni borrar mientras figuran como `recording`.

`WORKER_CONCURRENCY` limita los usuarios simultáneamente **activos** (una tarea ocupa plaza mientras FFmpeg graba). No escales el servicio `worker` a más de una réplica sin añadir antes una estrategia de bloqueo distribuido. Un reinicio del worker reprograma los objetivos activos y conserva los vídeos y registros previos. Un reinicio brusco podría dejar un archivo MKV parcial; al iniciar, el worker reconcilia esas grabaciones incompletas.

## 7. Pruebas y limitaciones

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q backend web scripts
```

El proyecto incluye pruebas sin conectarse a TikTok. Se debe validar la descarga real, el login y el comportamiento del navegador con las versiones actuales en el host final, y realizar un `docker build` en una máquina que disponga de Docker y acceso a los paquetes. TikTok puede cambiar la estructura de su API privada o restringir la reproducción. Respeta las condiciones del servicio y los derechos de las personas que transmiten.
