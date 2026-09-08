# FLIPUS v2 — Single-container Dockerfile (Railway/PAAS deployment).
#
# Menggabungkan frontend (Vite build) + backend (FastAPI/uvicorn) dalam SATU
# container. Frontend di-serve LANGSUNG oleh FastAPI (lihat app/main.py),
# sehingga TIDAK butuh nginx/supervisord — satu proses uvicorn saja:
#   uvicorn app.main:app --host 0.0.0.0 --port $PORT

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

# ============ Stage 3: Runtime ============
FROM python:3.11-slim

WORKDIR /app

# curl untuk healthcheck; libpq5 kalau pakai PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Python packages dari builder
COPY --from=backend-builder /install /usr/local

# Backend app + storage
COPY app /app/app
COPY storage /app/storage
RUN mkdir -p storage/temp storage/amplop_records storage/backups

# Frontend static build → /app/frontend_dist (path yang diharapkan main.py)
COPY --from=frontend-builder /build/dist /app/frontend_dist

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_URL_LOCAL="sqlite:///./flipus_local.db"

EXPOSE 8000

# Uvicorn bind 0.0.0.0:$PORT (Railway inject PORT). Frontend SPA di-serve
# oleh FastAPI (StaticFiles mount + catch-all), bukan nginx.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
