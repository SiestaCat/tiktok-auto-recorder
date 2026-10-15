import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get('DATA_DIR', str(BASE_DIR / 'data'))).resolve()
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
API_KEY = os.environ.get('API_KEY', '')
if not SECRET_KEY or len(SECRET_KEY) < 32:
    raise ImproperlyConfigured('DJANGO_SECRET_KEY debe tener al menos 32 caracteres')
if not API_KEY or len(API_KEY) < 20:
    raise ImproperlyConfigured('API_KEY debe tener al menos 20 caracteres')
DEBUG = False
ALLOWED_HOSTS = [x.strip() for x in os.environ.get('DJANGO_ALLOWED_HOSTS', 'api,localhost,127.0.0.1').split(',') if x.strip()]
INSTALLED_APPS = ['django.contrib.contenttypes', 'recorder']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware']
ROOT_URLCONF = 'core.urls'
TEMPLATES = []
WSGI_APPLICATION = 'core.wsgi.application'
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('MYSQL_DATABASE', 'tiktok'),
        'USER': os.environ.get('MYSQL_USER', 'tiktok'),
        'PASSWORD': os.environ.get('MYSQL_PASSWORD', ''),
        'HOST': os.environ.get('MYSQL_HOST', 'mysql'),
        'PORT': int(os.environ.get('MYSQL_PORT', '3306')),
        'OPTIONS': {'charset': 'utf8mb4', 'init_command': "SET sql_mode='STRICT_TRANS_TABLES'"},
        'CONN_MAX_AGE': 0,
    },
}
USE_TZ = True
TIME_ZONE = 'UTC'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
SECURE_CONTENT_TYPE_NOSNIFF = True
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
