from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(name='Target', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('username', models.CharField(max_length=32, unique=True)),
            ('active', models.BooleanField(default=False)),
            ('auto_check', models.BooleanField(default=False)),
            ('check_interval_minutes', models.PositiveIntegerField(default=5)),
            ('status', models.CharField(default='stopped', max_length=24)),
            ('next_check_at', models.DateTimeField(blank=True, null=True)),
            ('last_checked_at', models.DateTimeField(blank=True, null=True)),
            ('last_error', models.TextField(blank=True, default='')),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
        ]),
        migrations.CreateModel(name='Recording', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('file_path', models.CharField(max_length=512, unique=True)),
            ('ffmpeg_log', models.CharField(blank=True, default='', max_length=512)),
            ('status', models.CharField(default='recording', max_length=24)),
            ('size_bytes', models.BigIntegerField(default=0)),
            ('started_at', models.DateTimeField(auto_now_add=True)),
            ('ended_at', models.DateTimeField(blank=True, null=True)),
            ('target', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='recordings', to='recorder.target')),
        ]),
        migrations.CreateModel(name='EventLog', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('level', models.CharField(default='info', max_length=12)),
            ('message', models.TextField()),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('target', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='recorder.target')),
        ]),
    ]
