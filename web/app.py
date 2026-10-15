"""Server-side web UI. API key never reaches the browser."""
import os
import secrets
from functools import wraps
from urllib.parse import quote

import requests
from flask import Flask, Response, flash, redirect, render_template, request, session, stream_with_context, url_for

API_BASE_URL = os.environ.get('WEB_API_BASE_URL', '').rstrip('/')
API_KEY = os.environ.get('WEB_API_KEY', '')
PASSWORD = os.environ.get('WEB_PASSWORD', '')
SESSION_SECRET = os.environ.get('WEB_SESSION_SECRET', '')
if not API_BASE_URL.startswith(('http://', 'https://')) or not API_KEY or not PASSWORD or len(SESSION_SECRET) < 32:
    raise RuntimeError('Configura WEB_API_BASE_URL, WEB_API_KEY, WEB_PASSWORD y WEB_SESSION_SECRET (>=32 caracteres)')

app = Flask(__name__)
app.secret_key = SESSION_SECRET
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                  SESSION_COOKIE_SECURE=os.environ.get('WEB_COOKIE_SECURE', '0') == '1',
                  MAX_CONTENT_LENGTH=256 * 1024 * 1024)


def api(method, path, **kwargs):
    headers = {'X-API-Key': API_KEY}
    result = requests.request(method, f'{API_BASE_URL}/api/v1/{path.lstrip("/")}',
                              headers=headers, timeout=(10, 125), **kwargs)
    if result.status_code >= 400:
        try:
            message = result.json().get('error', result.text[:200])
        except ValueError:
            message = result.text[:200]
        raise RuntimeError(f'API {result.status_code}: {message}')
    if result.status_code == 204:
        return {}
    return result.json()


def loginRequired(func):
    @wraps(func)
    def inner(*args, **kwargs):
        if session.get('authenticated') is not True:
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    return inner


@app.before_request
def csrfGuard():
    if request.method == 'POST' and request.endpoint != 'login':
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        received = request.form.get('_csrf', '')
        if not received or not secrets.compare_digest(received, session.get('csrf', '')):
            return Response('Token CSRF inválido', status=403)


@app.context_processor
def csrf():
    return {'csrf_token': session.get('csrf', '')}


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if secrets.compare_digest(request.form.get('password', ''), PASSWORD):
            session.clear()
            session['authenticated'] = True
            session['csrf'] = secrets.token_urlsafe(32)
            return redirect(url_for('dashboard'))
        flash('Contraseña incorrecta', 'error')
    return render_template('login.html')


@app.post('/logout')
@loginRequired
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@loginRequired
def dashboard():
    try:
        targets = api('GET', 'targets/')['results']
        recordings = api('GET', 'recordings/')['results']
        profile = api('GET', 'profile/')
        logs = api('GET', 'logs/?limit=30')['results']
    except (requests.RequestException, RuntimeError) as error:
        flash(str(error), 'error')
        targets, recordings, profile, logs = [], [], {'installed': False}, []
    return render_template('dashboard.html', targets=targets, recordings=recordings,
                           profile=profile, logs=logs)


def act(callback):
    try:
        callback()
        flash('Operación completada', 'ok')
    except (RuntimeError, requests.RequestException, ValueError) as error:
        flash(str(error), 'error')
    return redirect(url_for('dashboard'))


@app.post('/targets')
@loginRequired
def addTarget():
    return act(lambda: api('POST', 'targets/', json={
        'username': request.form.get('username', ''),
        'check_interval_minutes': request.form.get('interval', '5'),
    }))


@app.post('/targets/<username>/start')
@loginRequired
def start(username):
    return act(lambda: api('POST', f'targets/{quote(username, safe="")}/start/', json={}))


@app.post('/targets/<username>/stop')
@loginRequired
def stop(username):
    return act(lambda: api('POST', f'targets/{quote(username, safe="")}/stop/', json={}))


@app.post('/targets/<username>/schedule')
@loginRequired
def schedule(username):
    return act(lambda: api('POST', f'targets/{quote(username, safe="")}/schedule/', json={
        'enabled': request.form.get('enabled') == 'true',
        'check_interval_minutes': request.form.get('interval', '5'),
    }))


@app.post('/targets/<username>/delete')
@loginRequired
def deleteTarget(username):
    return act(lambda: api('DELETE', f'targets/{quote(username, safe="")}/'))


@app.post('/profile/upload')
@loginRequired
def uploadProfile():
    def upload():
        file = request.files.get('file')
        if file is None or not file.filename.lower().endswith('.zip'):
            raise ValueError('Selecciona un archivo .zip')
        api('POST', 'profile/', files={'file': (file.filename, file.stream, 'application/zip')})
    return act(upload)


@app.get('/recordings/<int:recId>/download')
@loginRequired
def download(recId):
    try:
        upstream = requests.get(f'{API_BASE_URL}/api/v1/recordings/{recId}/download/',
                                headers={'X-API-Key': API_KEY}, stream=True, timeout=(10, 125))
        if not upstream.ok:
            upstream.close()
            flash('La grabación no está disponible para descarga', 'error')
            return redirect(url_for('dashboard'))

        def chunks():
            try:
                yield from upstream.iter_content(chunk_size=256 * 1024)
            finally:
                upstream.close()

        response = Response(stream_with_context(chunks()), content_type='application/octet-stream')
        response.headers['Content-Disposition'] = upstream.headers.get('Content-Disposition', 'attachment')
        if upstream.headers.get('Content-Length'):
            response.headers['Content-Length'] = upstream.headers['Content-Length']
        return response
    except requests.RequestException as error:
        flash(str(error), 'error')
        return redirect(url_for('dashboard'))


@app.post('/recordings/<int:recId>/delete')
@loginRequired
def deleteRecording(recId):
    return act(lambda: api('DELETE', f'recordings/{recId}/'))


@app.get('/recordings/<int:recId>/logs')
@loginRequired
def recordingLogs(recId):
    try:
        text = api('GET', f'recordings/{recId}/logs/')['text']
    except (RuntimeError, requests.RequestException) as error:
        text = str(error)
    return render_template('logs.html', text=text, recId=recId)


if __name__ == '__main__':
    app.run(port=8080)
