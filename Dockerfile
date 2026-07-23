FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/app /app/backend/app
COPY frontend/dist /app/frontend/dist
COPY sample-assets /app/sample-assets
COPY sample-briefs /app/sample-briefs

WORKDIR /app/backend
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

ENV HOSTED=1 \
    ROOT_PATH=/pipeline \
    DATA_ROOT=/data \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN mkdir -p /data/campaigns

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
