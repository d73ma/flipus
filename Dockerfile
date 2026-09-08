# FLIPUS v2 — Single-container Dockerfile (Railway/PAAS deployment).
#
# Menggabungkan frontend (Vite build) + backend (FastAPI/uvicorn) dalam SATU
# container, dijalankan bersama via supervisord:
#   - nginx: serve frontend static + reverse-proxy /api ke uvicorn
#   - uvicorn: FastAPI backend di 127.0.0.1:8000
#
# Berlawanan dgn docker-compose.yml (2 service terpisah), ini 1 container
# supaya Railway/Render bisa deploy langsung dari repo ini.

# ============ Stage 1: Build frontend ============
FROM node:18-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ============ Stage 2: Build backend deps ============
FROM python:3.11-slim AS backend-builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============ Stage 3: Runtime (combined) ============
FROM python:3.11-slim

WORKDIR /app

# Runtime system deps: nginx (frontend+proxy), supervisor (process mgmt),
# curl (healthcheck), libpq5 (kalau pakai PostgreSQL).
RUN apt-get update && apt-get install -y --no-install-recommends \
        nginx supervisor curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Python packages dari builder
COPY --from=backend-builder /install /usr/local

# Backend app
COPY app/ ./app/
COPY storage/ ./storage/
RUN mkdir -p storage/temp storage/amplop_records storage/backups

# Frontend static build + nginx config
COPY --from=frontend-builder /build/dist /usr/share/nginx/html
COPY nginx.railway.conf /etc/nginx/conf.d/default.conf
RUN rm -f /etc/nginx/sites-enabled/default

# Supervisor config
COPY supervisord.conf /etc/supervisor/conf.d/flipus.conf

# Entrypoint (PORT substitution)
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_URL_LOCAL="sqlite:///./flipus_local.db"

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
