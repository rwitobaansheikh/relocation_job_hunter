# syntax=docker/dockerfile:1

# ---- Stage 1: build the React/Vite frontend ----
FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python backend that also serves the built frontend ----
# Python 3.11 has prebuilt wheels for reportlab 3.6.x (pinned via xhtml2pdf
# <4). The native libs below let reportlab's _renderPM compile from source as
# a fallback (needs FreeType/JPEG/zlib headers) if a wheel isn't available.
FROM python:3.11-slim AS backend
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    STATIC_DIR=/app/static \
    DATABASE_URL=sqlite:////data/job_hunter.db \
    UPLOADS_DIR=/data/uploads \
    GENERATED_DIR=/data/generated

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libfreetype6-dev \
        libjpeg-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# Built static assets from the frontend stage.
COPY --from=frontend /frontend/dist ./static

# Persistent data (SQLite DB, uploads, generated PDFs) lives on a mounted volume.
RUN mkdir -p /data/uploads /data/generated

EXPOSE 8000

# Single worker on purpose: SQLite + local-file storage are not safe to share
# across multiple worker processes.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
