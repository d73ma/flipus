#!/bin/bash
# Script debug btn_simpan 500 error — restart fresh lalu trigger + lihat log.
# Jalankan dari folder Flipus: bash scripts/diag_btn_simpan.sh

set -e
cd "$(dirname "$0")/.."

echo "============================================="
echo "[1/5] Kill backend lama"
echo "============================================="
pkill -9 -f uvicorn || true
sleep 2

echo ""
echo "============================================="
echo "[2/5] Start backend baru"
echo "============================================="
nohup .venv/bin/python3 -m uvicorn app.main:app --port 8000 --reload > /tmp/flipus_backend.log 2>&1 &
BACKEND_PID=$!
echo "  PID=$BACKEND_PID, log=/tmp/flipus_backend.log"
echo "  Tunggu 6 detik untuk startup..."
sleep 6

echo ""
echo "============================================="
echo "[3/5] Test endpoint ready"
echo "============================================="
curl -s -o /dev/null -w "  /docs → HTTP %{http_code}\n" http://localhost:8000/docs

echo ""
echo "============================================="
echo "[4/5] Trigger shortcut (X 100rb, PT 50rb, KH 25rb)"
echo "============================================="
RESP1=$(curl -s -X POST http://localhost:8000/api/v1/wa/inbound \
  -H "Content-Type: application/json" \
  -d '{"sender":"628124809145","message":"X 100rb, PT 50rb, KH 25rb","id":"diag-1"}')
echo "  Response: $RESP1"

sleep 2

echo ""
echo "  Trigger btn_simpan..."
RESP2=$(curl -s -X POST http://localhost:8000/api/v1/wa/inbound \
  -H "Content-Type: application/json" \
  -d '{"sender":"628124809145","button_id":"btn_simpan","id":"diag-2"}')
echo "  Response: $RESP2"

echo ""
echo "============================================="
echo "[5/5] Lihat checkpoint log (binary-safe)"
echo "============================================="
echo "  --- WA-INBOUND-ENTRY (body masuk) ---"
grep -a "WA-INBOUND-ENTRY" /tmp/flipus_backend.log | tail -5
echo ""
echo "  --- DBG impl (checkpoint impl) ---"
grep -a "DBG impl" /tmp/flipus_backend.log | tail -20
echo ""
echo "  --- DBG get_or_create_session (checkpoint) ---"
grep -a "DBG get_or_create_session" /tmp/flipus_backend.log | tail -15
echo ""
echo "  --- WA-INBOUND-TOPLEVEL (errors) ---"
grep -a "WA-INBOUND-TOPLEVEL" /tmp/flipus_backend.log | tail -5
echo ""
echo "  --- TOPLEVEL full traceback ---"
awk '/WA-INBOUND-TOPLEVEL/{found=1} found{print; if (++n > 80) exit}' /tmp/flipus_backend.log | tail -80

echo ""
echo "Done."