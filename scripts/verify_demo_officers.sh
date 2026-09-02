#!/bin/bash
cd /Users/jerrymauri/Flipus
> /tmp/flipus_m8.log
pkill -9 -f "uvicorn app.main" 2>/dev/null
sleep 3
nohup .venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/flipus_m8.log 2>&1 &
disown
sleep 8
echo "=== HEALTH ==="
curl -s http://127.0.0.1:8000/health
echo ""
echo ""
echo "=== LOGIN: Bendahara_a ==="
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"bendahara_a","password":"Bendahara123!"}' | head -c 200
echo ""
echo ""
echo "=== LOGIN: AuditMisi_a ==="
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"auditmisi_a","password":"AuditMisi123!"}' | head -c 200
echo ""
echo ""
echo "=== LOGIN: AdminUni_a ==="
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"adminuni_a","password":"AdminUni123!"}' | head -c 200
echo ""
echo ""
echo "=== SMOKE M7 (laporan gabungan) ==="
.venv/bin/python3 scripts/smoke_laporan_m7.py
echo ""
echo "=== SMOKE M8 (managed users + void) ==="
FLIPUS_WA_UNIQUE=88 .venv/bin/python3 scripts/smoke_m8.py
echo ""
echo "=== SMOKE PENGELUARAN (M4-M6) ==="
.venv/bin/python3 scripts/smoke_pengeluaran.py
