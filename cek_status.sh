#!/bin/bash
# FLIPUS — Cek status T101 Recompute + Fonnte device.
# Usage: ./cek_status.sh

set -e
cd "$(dirname "$0")"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PYTHON="/Users/jerrymauri/Flipus/.venv/bin/python3"
[ -x "$PYTHON" ] || PYTHON="python3"

echo "============================================================"
echo "  Cek Status"
echo "============================================================"

# ===== A. T101 Recompute audit =====
printf "\n${CYAN}[A]${NC} T101 — Cek Kuitansi X>0 dan porsi-nya:\n"
$PYTHON -c "
import sys
sys.path.insert(0, '.')
from app.core.database import SessionLocal
from app.models.transaction import Kuitansi
from app.models.tenant import Tenant
from app.utils.porsi_calculator import compute_porsi
from app.models.master import PersentaseConfig

db = SessionLocal()
ks = db.query(Kuitansi).filter(Kuitansi.perpuluhan_x_angka > 0).all()
print(f'  Total Kuitansi dengan X>0: {len(ks)}')
if not ks:
    print('  (tidak ada)')
    sys.exit(0)

# Build config map
cfg_map = {}
for c in db.query(PersentaseConfig).filter(PersentaseConfig.scope == 'MISI').all():
    cfg_map[c.ref_id] = {
        'pct_x_jemaat': c.pct_x_jemaat,
        'pct_pt_jemaat': c.pct_pt_jemaat,
        'pct_khusus_jemaat': c.pct_khusus_jemaat,
        'pct_x_uni': c.pct_x_uni or 0.0,
        'pct_pt_uni': c.pct_pt_uni or 0.0,
        'pct_khusus_uni': c.pct_khusus_uni or 0.0,
    }

tenant_cache = {}
def tenant_of(tid):
    if tid not in tenant_cache:
        tenant_cache[tid] = db.query(Tenant).filter(Tenant.id == tid).first()
    return tenant_cache[tid]

print()
for k in ks:
    t = tenant_of(k.tenant_id)
    jemaat = t.nama_jemaat_lokal if t else '?'
    cfg = cfg_map.get(t.misi_konferens_id) if t else None
    pct_x_j = cfg['pct_x_jemaat'] if cfg else '?'
    pct_x_u = cfg['pct_x_uni'] if cfg else '?'
    marker = '✓' if (cfg and cfg['pct_x_jemaat'] == 0.0) else '⚠'
    print(f'  {marker} {k.nomor_kuitansi} | {jemaat} | X={k.perpuluhan_x_angka:,} | pct_x_jemaat={pct_x_j} pct_x_uni={pct_x_u} | stored: jemaat={k.porsi_kas_jemaat:,} misi={k.porsi_kantor_misi:,}')
" 2>&1 | grep -v "^DEBUG\|^$"

# ===== B. Fonnte device =====
printf "\n${CYAN}[B]${NC} Fonnte device status:\n"
TOKEN=$(grep "^FONNTE_TOKEN=" .env 2>/dev/null | cut -d= -f2)
if [ -z "$TOKEN" ]; then
    printf "  ${RED}✗${NC} FONNTE_TOKEN kosong\n"
else
    # Simpan raw response ke temp file + capture HTTP code
    RAW=/tmp/fonnte_resp.txt
    HTTP_CODE=$(curl -s -o "$RAW" -w "%{http_code}" -X POST --max-time 15 \
        -H "Authorization: $TOKEN" \
        https://api.fonnte.com/get-device 2>&1)
    BODY=$(cat "$RAW" 2>/dev/null | head -c 300)
    STATUS=$($PYTHON -c "
import json
http_code = '$HTTP_CODE'
try:
    with open('$RAW') as f:
        body = f.read().strip()
    # Short-circuit untuk endpoint deprecated
    if http_code == '404':
        print(f\"Fonnte /get-device deprecated (HTTP 404). Cek device manual di https://fonnte.com/app/console. /send untuk kirim WA masih jalan.\")
    elif not body:
        print(f'EMPTY_RESPONSE (HTTP {http_code}) — token invalid atau Fonnte API down')
    else:
        d = json.loads(body)
        if d.get('status'):
            print(f\"CONNECTED phone={d.get('phone','?')} quota={d.get('quota_remaining','?')}/{d.get('quota','?')}\")
        else:
            print(f\"DISCONNECTED reason={d.get('reason','?')}\")
except json.JSONDecodeError as e:
    print(f'PARSE_ERROR (HTTP {http_code}): {str(e)[:60]} | body[:100]={body[:100]}')
except Exception as e:
    print(f'ERROR (HTTP {http_code}): {str(e)[:80]}')
" 2>&1)
    if echo "$STATUS" | grep -q "CONNECTED"; then
        printf "  ${GREEN}✓${NC} %s\n" "$STATUS"
    elif echo "$STATUS" | grep -q "deprecated\|unknown\|DISCONNECTED"; then
        printf "  ${YELLOW}⚠${NC} %s\n" "$STATUS"
    else
        printf "  ${RED}✗${NC} %s\n" "$STATUS"
    fi
    if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "000" ]; then
        printf "  ${YELLOW}→${NC} HTTP=%s. Cek Fonnte console: https://fonnte.com/app/console\n" "$HTTP_CODE"
    fi
fi

# ===== C. WA webhook reachable? =====
printf "\n${CYAN}[C]${NC} WA webhook endpoint:\n"
WA_RESP=$(curl -s --max-time 3 http://localhost:8000/api/v1/wa/inbound 2>&1)
if echo "$WA_RESP" | grep -q '"status":"ok"'; then
    LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "localhost")
    printf "  ${GREEN}✓${NC} Reachable. Webhook URL set di Fonnte:\n"
    printf "      http://%s:8000/api/v1/wa/inbound\n" "$LAN_IP"
else
    printf "  ${RED}✗${NC} %s\n" "$WA_RESP"
fi

echo ""
echo "============================================================"