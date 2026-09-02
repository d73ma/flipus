"""
FLIPUS v1.2 — Frontend Dockerfile.

Multi-stage build:
- Stage 1 (builder): install Node deps + build Vite production bundle
- Stage 2 (runtime): nginx serve static files dari /usr/share/nginx/html

Usage:
    docker build -f frontend.Dockerfile -t flipus-frontend ./frontend
    docker run -p 80:80 flipus-frontend
"""

# ---------- Builder stage ----------
FROM node:18-alpine AS builder

WORKDIR /build

# Copy package files dulu (cache layer)
COPY frontend/package*.json ./

# Install deps
RUN npm ci --no-audit --no-fund

# Copy source
COPY frontend/ ./

# Build production bundle
RUN npm run build


# ---------- Runtime stage ----------
FROM nginx:1.25-alpine AS runtime

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built static files dari builder
COPY --from=builder /build/dist /usr/share/nginx/html

# Health check via wget
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q --spider http://localhost/ || exit 1

EXPOSE 80

# nginx default CMD sudah ada di base image
CMD ["nginx", "-g", "daemon off;"]