FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 INVISIBLE_PLAYWRIGHT_CACHE_DIR=/opt/invisible-browser
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg xvfb libmariadb-dev build-essential pkg-config \
    libasound2 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdbus-1-3 libdbus-glib-1-2 \
    libdrm2 libgbm1 libgtk-3-0 libnss3 libx11-xcb1 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libxshmfence1 libxtst6 \
    libfontconfig1 libfreetype6 fonts-liberation ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m invisible_playwright fetch
COPY . .
RUN mkdir -p /app/data /opt/invisible-browser \
    && groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid 1000 --create-home appuser \
    && chown -R appuser:appuser /app /opt/invisible-browser \
    && chmod -R a+rX /opt/invisible-browser
USER appuser
EXPOSE 8000
CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
