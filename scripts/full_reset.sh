#!/bin/bash
# Full reset: kill backend + clear ALL Python caches + restart
set -e
cd "$(dirname "$0")/.."

echo "===== FULL RESET ====="
echo ""

echo "[1/4] Kill all uvicorn processes"
pkill -9 -f uvicorn || true
sleep 2

echo "[2/4] Clear ALL Python bytecode caches"
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null
find . -name "*.pyo" -delete 2>/dev/null
echo "  Caches cleared"

echo "[3/4] Clear wa_sessions table (paksa IDLE fresh start)"
.venv/bin/python3 -c "
import sys, os
sys.path.insert(0, '.')
os.chdir('.')
from app.core.database import SessionLocal
from app.models.wa_session import WaSession
db = SessionLocal()
deleted = db.query(WaSession).delete()
db.commit()
print(f'  Deleted {deleted} wa_sessions rows')
db.close()
"

echo "[4/4] Start backend fresh"
nohup .venv/bin/python3 -m uvicorn app.main:app --port 8000 --reload > /tmp/flipus_backend.log 2>&1 &
sleep 6
curl -s -o /dev/null -w "  /docs → HTTP %{http_code}\n" http://localhost:8000/docs
echo ""
echo "===== READY ====="
echo "Now run: bash scripts/diag_btn_simpan.sh"