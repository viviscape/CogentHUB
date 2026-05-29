# Standalone (non-add-on) image — runs the connector as a plain Docker container
# anywhere, reading config from environment variables (see config.py env fallback).
# Build context is the repo root: docker build -f docker/Dockerfile .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /usr/src

COPY cogent_hub/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY cogent_hub/app ./app
RUN mkdir -p /data

# Spool/store-and-forward lives in /data (mount a volume to persist across restarts).
VOLUME ["/data"]

CMD ["python", "-m", "app.main"]
