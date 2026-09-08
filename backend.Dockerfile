# FLIPUS v1.2 — Backend Dockerfile.
#
# Multi-stage build untuk produksi:
# - Stage 1 (builder): install dependencies + compile
# - Stage 2 (runtime): copy only what's needed, run uvicorn
#
# Usage:
#     docker build -f backend.Dockerfile -t flipus-backend .
#     docker run -p 8000:8000 flipus-backend

# ---------- Builder stage ----------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools + system deps untuk reportlab wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements dulu (Docker cache)
COPY requirements.txt .

# Install Python deps ke prefix yang nanti akan di-copy
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ---------- Runtime stage ----------
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages dari builder
COPY --from=builder /install /usr/local

# Copy aplikasi
COPY app/ ./app/
COPY storage/ ./storage/

# Create storage dirs (mounted as volumes in production)
RUN mkdir -p storage/temp storage/amplop_records storage/backups

# Non-root user untuk security
RUN useradd -m -u 1000 flipus && chown -R flipus:flipus /app
USER flipus

# Environment defaults (override di docker-compose)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_URL_LOCAL="sqlite:///./flipus_local.db"

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default: 4 uvicorn workers
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]