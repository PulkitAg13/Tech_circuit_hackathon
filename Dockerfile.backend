FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/src /app/backend/src
COPY canons /app/canons

WORKDIR /app/backend
RUN uv pip install --system -e .

ENV CANONGATE_CANON_DIR=/app/canons
ENV CANONGATE_DB_URL=sqlite+aiosqlite:////data/canongate.db

EXPOSE 8000
CMD ["sh", "-c", "uvicorn canongate.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
