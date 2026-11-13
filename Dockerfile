# syntax=docker/dockerfile:1

# ---------------------------------------------------------------- builder ----
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# A virtualenv keeps the build tooling separate from the runtime filesystem.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements first so this layer is cached until dependencies change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------- runtime ----
FROM python:3.12-slim AS runtime

ARG GIT_SHA=dev
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    GIT_SHA=${GIT_SHA} \
    APP_ENV=production \
    DATABASE_URL=sqlite:////data/expenses.db \
    LOG_LEVEL=INFO

# Non-root runtime user (never ship a container that runs as root).
RUN groupadd --gid 1001 app \
 && useradd --uid 1001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app app ./app
COPY --chown=app:app wsgi.py ./

RUN mkdir -p /data /app/logs && chown -R app:app /data /app

USER app

EXPOSE 8000

# Docker itself can now report container health (docker ps shows healthy).
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

CMD ["gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--threads", "2", \
     "--timeout", "30", \
     "--graceful-timeout", "25", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "wsgi:app"]
