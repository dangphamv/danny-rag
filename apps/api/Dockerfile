# syntax=docker/dockerfile:1.7

# -------- builder stage --------
FROM python:3.12-slim-bookworm AS builder

# uv: fast Python package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Build-time system deps + the runtime deps unstructured needs.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libmagic1 \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first so this layer caches across source changes.
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project \
    || uv sync --no-dev --no-install-project

# Copy source.
COPY src/ ./src/

# Pre-download the cross-encoder model so cold starts on Railway's ephemeral
# filesystem don't pay the ~500 MB / ~30 s download cost on every restart.
ENV HF_HOME=/root/.cache/huggingface
RUN /app/.venv/bin/python -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-base')"

# -------- runtime stage --------
FROM python:3.12-slim-bookworm AS runtime

# Runtime-only system deps. Builder packages (build-essential, etc.) stay behind.
# libgl1 + libglib2.0-0 are transitively required by cv2 (opencv), which
# unstructured pulls in for PDF partitioning. Without them, any PDF upload
# crashes with `ImportError: libGL.so.1: cannot open shared object file`.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmagic1 \
        poppler-utils \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app

WORKDIR /app

# Copy the venv, source, and the pre-downloaded HF cache from the builder.
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/src /app/src
COPY --from=builder --chown=app:app /root/.cache/huggingface /home/app/.cache/huggingface

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HF_HOME=/home/app/.cache/huggingface \
    PORT=8000 \
    ENV=production

USER app
EXPOSE 8000

# Use python -m uvicorn so /app is reliably on sys.path. Railway sets $PORT.
CMD ["sh", "-c", "python -m uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
