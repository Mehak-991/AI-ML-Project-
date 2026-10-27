# syntax=docker/dockerfile:1
#
# Production image for the AIProject API.
#   docker build -t aiproject:latest .
#   docker build --build-arg INSTALL_LLM=true -t aiproject:llm .              # + OpenAI/LangGraph
#   docker build --build-arg INSTALL_LLM=true --build-arg INSTALL_NLP=true .  # + CPU PyTorch NLP
#
# No secrets are copied or baked in: configuration comes from environment variables
# at runtime (.env and .env.* are excluded by .dockerignore).

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------- build stage --
FROM python:${PYTHON_VERSION}-slim AS builder

ARG INSTALL_LLM=false
ARG INSTALL_NLP=false

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.txt requirements-llm.txt requirements-nlp.txt ./
RUN pip install -r requirements.txt \
    && if [ "$INSTALL_LLM" = "true" ]; then pip install -r requirements-llm.txt; fi \
    && if [ "$INSTALL_NLP" = "true" ]; then \
         pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu \
         && pip install -r requirements-nlp.txt; \
       fi

# -------------------------------------------------------------- runtime stage --
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production \
    LOG_FORMAT=json \
    UPLOAD_DIR=/data/uploads \
    MODEL_DIR=/data/trained_models \
    AI_MODEL_CACHE_DIR=/data/model_cache \
    MPLCONFIGDIR=/tmp/matplotlib \
    TIKTOKEN_CACHE_DIR=/data/model_cache/tiktoken \
    FORWARDED_ALLOW_IPS=127.0.0.1
# FORWARDED_ALLOW_IPS: proxies trusted to set X-Forwarded-For (read by uvicorn). Set it to
# your reverse proxy's address so logs and rate limits see real client IPs.

# Unprivileged user; /data holds everything the app writes (mounted as volumes).
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /data/uploads /data/trained_models /data/model_cache \
    && chown -R app:app /data

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app app ./app
COPY --chown=app:app scripts ./scripts

USER app
EXPOSE 8000

# Liveness only (no DB): the orchestrator restarts the process if this fails.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

# Validates config, runs `alembic upgrade head` (RUN_MIGRATIONS=true, with retries),
# then execs the command below.
ENTRYPOINT ["python", "scripts/docker_entrypoint.py"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--no-access-log", \
     "--workers", "2", "--timeout-graceful-shutdown", "20"]
