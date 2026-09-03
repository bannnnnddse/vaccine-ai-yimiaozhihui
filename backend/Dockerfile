FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

WORKDIR /app/backend

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system --gid 10001 app \
    && adduser --system --uid 10001 --ingroup app app \
    && mkdir -p /data/runtime /data/generated_images /data/rag_index /data/model_cache \
    && chown -R app:app /data

COPY backend/pyproject.toml backend/README.md ./

# Runtime RAG is CPU-only. Pin the CPU wheel before resolving
# sentence-transformers so pip does not pull the Linux CUDA distribution.
# Keep this before application sources: ordinary code changes must not force
# a 192 MB Torch download during a production rebuild.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.13.0+cpu

# Install third-party dependencies before copying application sources. Hatchling
# needs the declared package to exist, but dependency resolution only depends on
# pyproject.toml, so a minimal package marker keeps this layer reusable across
# ordinary app changes.
RUN mkdir -p app
COPY backend/app/__init__.py ./app/__init__.py
RUN pip install --no-cache-dir .

COPY backend/app ./app
COPY backend/assets ./assets
COPY skills /app/skills

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
