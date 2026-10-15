from django.db import models


class Target(models.Model):
    username = models.CharField(max_length=32, unique=True)
    active = models.BooleanField(default=False)
    auto_check = models.BooleanField(default=False)
    check_interval_minutes = models.PositiveIntegerField(default=5)
    status = models.CharField(max_length=24, default='stopped')
    next_check_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Recording(models.Model):
    target = models.ForeignKey(Target, on_delete=models.PROTECT, related_name='recordings')
    file_path = models.CharField(max_length=512, unique=True)
    ffmpeg_log = models.CharField(max_length=512, blank=True, default='')
    status = models.CharField(max_length=24, default='recording')
    size_bytes = models.BigIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)


class EventLog(models.Model):
    target = models.ForeignKey(Target, on_delete=models.SET_NULL, null=True, blank=True)
    level = models.CharField(max_length=12, default='info')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
