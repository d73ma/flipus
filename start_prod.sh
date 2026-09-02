#!/bin/bash
# FLIPUS prod start — bypass Vite dev server, pakai static build + Python http.server.
#
# LATAR BELAKANG:
# Vite dev server kadang "ready" tapi tidak serve HTTP (curl return EMPTY).
# Root cause masih misterius — kemungkinan optimizeDeps hang atau port-bind race.
# Untuk demo Officers Uni yang harus reliable, pakai production build static
# yang dilayani Python HTTP server (stdlib only, tidak ada deps).
#
# Usage: ./start_prod.sh
# Stop:  Ctrl+C
#
# --host 0.0.0.0 agar device lain di Wi-Fi yang sama bisa akses
# (untuk demo offline multi-device Officers Uni).

set -e
cd "$(dirname "$0")"

echo "===== FLIPUS PROD Startup ====="
echo ""

# Kill existing
pkill -f uvicorn 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
pkill -f "http.server" 2>/dev/null || true
sleep 1

# ===== DETECT LAN IP =====
# en0 = Wi-Fi (umum), en1 = kadang Wi-Fi juga di Mac tertentu.
# Prioritas: en0 → en1 → fallback ke ifconfig broad scan → localhost.
detect_lan_ip() {
  local ip
  ip=$(ipconfig getifaddr en0 2>/dev/null)
  if [ -z "$ip" ]; then
    ip=$(ipconfig getifaddr en1 2>/dev/null)
  fi
  if [ -z "$ip" ]; then
    # Last resort: pakai ipconfig parse
    ip=$(ifconfig | grep -E "inet " | grep -v "127.0.0.1" | head -1 | awk '{print $2}')
  fi
  echo "${ip:-localhost}"
}

LAN_IP=$(detect_lan_ip)

# ===== BACKEND =====
echo "[1/3] Starting backend di port 8000 (listen 0.0.0.0)..."
/Users/jerrymauri/Flipus/.venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > /tmp/flipus_backend.log 2>&1 &
BACKEND_PID=$!
echo "  → backend PID=$BACKEND_PID, log=/tmp/flipus_backend.log"

# ===== BUILD STATIC FRONTEND =====
echo "[2/3] Building static frontend (npm run build)..."
cd frontend
# Export VITE_API_URL ke absolute URL dengan LAN IP host.
# api.ts baca VITE_API_URL → axios baseURL jadi absolute.
# Alasan: Python http.server TIDAK support proxy. Frontend call backend langsung.
export VITE_API_URL="http://${LAN_IP}:8000/api"
echo "  → VITE_API_URL=$VITE_API_URL"
npm run build > /tmp/flipus_frontend_build.log 2>&1
echo "  → build selesai, log=/tmp/flipus_frontend_build.log"

# ===== SERVE STATIC =====
echo "[3/3] Serving dist/ via Python http.server di port 5173 (listen 0.0.0.0)..."
cd dist
/Users/jerrymauri/Flipus/.venv/bin/python3 -m http.server 5173 --bind 0.0.0.0 > /tmp/flipus_frontend.log 2>&1 &
FRONTEND_PID=$!
echo "  → frontend PID=$FRONTEND_PID, log=/tmp/flipus_frontend.log"

# Cleanup on exit
trap "echo ''; echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true; exit" INT TERM

echo ""
echo "===== READY (PRODUCTION MODE) ====="
echo "  Backend (lokal):   http://localhost:8000"
echo "  Frontend (lokal):  http://localhost:5173"
echo "  Backend (LAN):     http://${LAN_IP}:8000"
echo "  Frontend (LAN):    http://${LAN_IP}:5173"
echo "  API docs:          http://localhost:8000/docs"
echo ""
echo "Untuk demo ke device lain di Wi-Fi yang sama, share URL LAN di atas."
echo "Tekan Ctrl+C untuk stop keduanya."
echo "Logs: tail -f /tmp/flipus_backend.log /tmp/flipus_frontend.log /tmp/flipus_frontend_build.log"

# Wait both processes
wait $BACKEND_PID $FRONTEND_PID
