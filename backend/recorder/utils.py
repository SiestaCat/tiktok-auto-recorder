import re
from django.core.exceptions import ValidationError
from .models import EventLog

USERNAME_RE = re.compile(r'^[a-zA-Z0-9._]{1,32}$')


def normalizeUsername(value):
    username = str(value or '').strip().lstrip('@').lower()
    if not USERNAME_RE.fullmatch(username):
        raise ValidationError('Usuario no válido (1-32 caracteres: letras, números, . o _)')
    return username


def validateInterval(value):
    if isinstance(value, bool):
        raise ValidationError('Intervalo no válido')
    try:
        minutes = int(value)
    except (ValueError, TypeError):
        raise ValidationError('El intervalo debe ser un entero')
    if not 1 <= minutes <= 1440:
        raise ValidationError('El intervalo debe estar entre 1 y 1440 minutos')
    return minutes


def logEvent(target, message, level='info'):
    EventLog.objects.create(target=target, message=str(message)[:2000], level=level)
    print(f'[{level}] @{target.username if target else "system"}: {message}', flush=True)
