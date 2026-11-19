# Studio backend: one Dockerfile, two images.
#   docker build -f webapp/deploy/backend.Dockerfile --target api    -t studio-api .
#   docker build -f webapp/deploy/backend.Dockerfile --target worker -t studio-worker .
# Build context: the repository root (the worker needs plugins/video-studio, the engine).

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN useradd --create-home --uid 10001 studio
WORKDIR /srv/api
COPY webapp/api/pyproject.toml ./
RUN python -c 'import tomllib; print("\n".join(tomllib.load(open("pyproject.toml", "rb"))["project"]["dependencies"]))' > requirements.txt \
 && pip install --upgrade pip && pip install -r requirements.txt
# the engine: the API uses its lesson logic in-process, the worker runs `vs`
COPY plugins/video-studio /opt/video-studio
ENV VS_BIN=/opt/video-studio/bin/vs AGENT_PLUGIN_DIR=/opt/video-studio
COPY webapp/api/app ./app
COPY webapp/api/worker ./worker
COPY webapp/api/migrations ./migrations
COPY webapp/api/alembic.ini ./

# --- API: FastAPI behind uvicorn ------------------------------------------------------------------------------------
FROM base AS api
USER studio
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/healthz')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

# --- Worker: ffmpeg + the vs engine + faster-whisper + Claude Code (Agent SDK, bundled CLI) ---------------------------
# Node 22 and Chromium are for the plugin's HyperFrames (HTML -> video) and media scripts that Claude runs.
FROM base AS worker
ARG WHISPER_MODELS="small"
ARG NODE_MAJOR=22
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core fontconfig ca-certificates \
      curl gnupg git chromium \
 && curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium CHROME_PATH=/usr/bin/chromium
ENV VS_VENV=/opt/vs-venv WHISPER_MODEL_DIR=/models WORKER_ROOT=/work
RUN python -m venv /opt/vs-venv \
 && /opt/vs-venv/bin/pip install "faster-whisper>=1.0" "numpy>=1.26" "gdown>=5" "yt-dlp" "huggingface_hub>=0.23" \
 && for m in $WHISPER_MODELS; do /opt/vs-venv/bin/python -c "from huggingface_hub import snapshot_download as d; d('Systran/faster-whisper-$m', local_dir='/models/faster-whisper-$m')"; done \
 && mkdir -p /work && chown studio /work
USER studio
CMD ["python", "-m", "worker.main"]
