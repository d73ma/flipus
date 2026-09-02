#!/bin/bash
# FLIPUS dev start — jalanin backend + frontend bareng
# Usage: ./start_dev.sh
# Stop: Ctrl+C
#
# Catatan: --host 0.0.0.0 agar device lain di Wi-Fi yang sama bisa akses
# (untuk demo offline multi-device). Akses dari IP MacBook, bukan localhost.

set -e
cd "$(dirname "$0")"

echo "===== FLIPUS Dev Startup ====="
echo ""

# Kill existing
pkill -f uvicorn 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
sleep 1

# Backend
echo "[1/2] Starting backend di port 8000 (listen 0.0.0.0)..."
/Users/jerrymauri/Flipus/.venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > /tmp/flipus_backend.log 2>&1 &
BACKEND_PID=$!
echo "  → backend PID=$BACKEND_PID, log=/tmp/flipus_backend.log"

# Frontend
echo "[2/2] Starting frontend di port 5173 (listen 0.0.0.0)..."
cd frontend
npm run dev > /tmp/flipus_frontend.log 2>&1 &
FRONTEND_PID=$!
echo "  → frontend PID=$FRONTEND_PID, log=/tmp/flipus_frontend.log"

# Cleanup on exit
trap "echo ''; echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true; exit" INT TERM

echo ""
echo "===== READY ====="
echo "  Backend (lokal):   http://localhost:8000"
echo "  Frontend (lokal):  http://localhost:5173"
echo "  Backend (LAN):     http://$(ipconfig getifaddr en0 2>/dev/null || echo "<IP_MACBOOK>"):8000"
echo "  Frontend (LAN):    http://$(ipconfig getifaddr en0 2>/dev/null || echo "<IP_MACBOOK>"):5173"
echo "  API docs:          http://localhost:8000/docs"
echo ""
echo "Untuk demo ke device lain di Wi-Fi yang sama, share URL LAN di atas."
echo "Tekan Ctrl+C untuk stop keduanya."
echo "Logs: tail -f /tmp/flipus_backend.log /tmp/flipus_frontend.log"

# Wait both processes
wait $BACKEND_PID $FRONTEND_PID