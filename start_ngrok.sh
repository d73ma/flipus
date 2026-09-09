#!/bin/bash
# FLIPUS — start ngrok tunnel untuk expose backend (yang serve frontend + API)
# di satu port :8000 ke URL publik yang STABIL (ngrok-free.app).
#
# Usage:
#   export NGROK_AUTHTOKEN=ngrok_xxxxxxxx
#   export NGROK_DOMAIN=flipus-demo.ngrok-free.app    # (opsional, kalau ada)
#   ./start_ngrok.sh
#
# Kalau NGROK_DOMAIN tidak di-set, ngrok pakai random subdomain.

set -euo pipefail

PORT="${FLIPUS_PORT:-8000}"

# 1. Require authtoken
if [ -z "${NGROK_AUTHTOKEN:-}" ]; then
  echo "❌ NGROK_AUTHTOKEN belum di-set." >&2
  echo "   Dapatkan di https://dashboard.ngrok.com/get-started/your-authtoken" >&2
  echo "   Lalu jalankan:" >&2
  echo "   export NGROK_AUTHTOKEN=ngrok_xxxxxxxx" >&2
  exit 1
fi

# 2. Konfigurasi authtoken (idempotent)
ngrok config add-authtoken "$NGROK_AUTHTOKEN"

# 3. Cek backend lokal hidup
if ! curl -sf "http://localhost:${PORT}/health" > /dev/null 2>&1; then
  echo "⚠️  Backend di http://localhost:${PORT} belum hidup." >&2
  echo "   Mulai dulu: PYTHONPATH=. .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT}" >&2
  exit 1
fi

# 4. Jalankan ngrok tunnel
if [ -n "${NGROK_DOMAIN:-}" ]; then
  echo "🌐 Membuka https://${NGROK_DOMAIN} → http://localhost:${PORT}"
  exec ngrok http --domain="${NGROK_DOMAIN}" "${PORT}"
else
  echo "🌐 Membuka ngrok tunnel (random subdomain) → http://localhost:${PORT}"
  exec ngrok http "${PORT}"
fi
