#!/bin/bash
# FLIPUS — Aktifkan bertahap: OCR + Input HP + Fix Perpuluhan.
# Setiap step terpisah, output ringkas. Stop otomatis kalau ada error.
#
# Usage: ./aktifkan_bertahap.sh
#
# 3 STEP:
#   [1/3] T101 — Fix perpuluhan (recompute Kuitansi existing)
#   [2/3] OCR — Gemini API key validation + Ollama check
#   [3/3] WA Input Bot — Fonnte device check + webhook URL setup

set -e
cd "$(dirname "$0")"

# ===== Warna =====
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ok() { printf "${GREEN}✓${NC} %s\n" "$1"; }
fail() { printf "${RED}✗${NC} %s\n" "$1"; }
warn() { printf "${YELLOW}⚠${NC} %s\n" "$1"; }
step() { printf "\n${CYAN}${BOLD}[%s]${NC} ${BOLD}%s${NC}\n" "$1" "$2"; }

PYTHON="/Users/jerrymauri/Flipus/.venv/bin/python3"
[ -x "$PYTHON" ] || PYTHON="python3"

echo "============================================================"
echo "  FLIPUS — Aktivasi Bertahap"
echo "============================================================"

# ============================================================
step "1/3" "FIX PERPULUHAN (T101 migration)"
# ============================================================
if [ ! -f scripts/fix_pct_x_jemaat_t101.py ]; then
    fail "scripts/fix_pct_x_jemaat_t101.py tidak ada"
    exit 1
fi
echo "  Menjalankan fix_pct_x_jemaat_t101.py..."
echo "  ────────────────────────────────────────────────────────"
$PYTHON scripts/fix_pct_x_jemaat_t101.py 2>&1 | grep -E "(INFO|WARN|✓|⚠|\[)" | head -30
echo "  ────────────────────────────────────────────────────────"
ok "T101 selesai — perpuluhan sekarang ke Misi (bukan Jemaat)"

# ============================================================
step "2/3" "AKTIFKAN OCR (Gemini + Ollama + Reportlab)"
# ============================================================

# 2a. Reportlab check (library untuk PDF Laporan Keuangan + Kuitansi)
echo "  Checking reportlab library..."
REPORTLAB=$($PYTHON -c "import reportlab; print(reportlab.__version__)" 2>&1)
if [[ "$REPORTLAB" == 4.* ]]; then
    ok "reportlab OK (v$REPORTLAB)"
elif [[ "$REPORTLAB" == *"ModuleNotFoundError"* ]]; then
    fail "reportlab TIDAK ADA di venv — Laporan Keuangan akan crash"
    warn "Auto-install sekarang..."
    /Users/jerrymauri/Flipus/.venv/bin/pip install reportlab==4.2.5 2>&1 | tail -3
    INSTALLED=$($PYTHON -c "import reportlab; print(reportlab.__version__)" 2>&1)
    if [[ "$INSTALLED" == 4.* ]]; then
        ok "reportlab terinstall (v$INSTALLED). Restart backend: ./start_dev.sh"
    else
        fail "reportlab gagal install. Manual: .venv/bin/pip install reportlab==4.2.5"
    fi
else
    warn "reportlab unexpected: $REPORTLAB"
fi

# 2b. Gemini API key format check
GEMINI_KEY=$(grep "^GEMINI_API_KEY=" .env 2>/dev/null | cut -d= -f2)
if [ -z "$GEMINI_KEY" ] || [ "${GEMINI_KEY:0:5}" = "GANTI" ]; then
    fail "GEMINI_API_KEY kosong di .env"
    warn "Dapat API key baru:"
    warn "  1. Buka https://aistudio.google.com/app/apikey"
    warn "  2. Create API key (format AIzaSy...)"
    warn "  3. Edit .env: GEMINI_API_KEY=AIzaSy..."
    warn "  4. Restart backend: ./start_dev.sh"
    GEMINI_OK=0
elif [[ "$GEMINI_KEY" == AQ.* ]]; then
    fail "GEMINI_API_KEY format AQ.* — bukan standard Google API key"
    warn "Gemini library butuh format AIzaSy..."
    warn "Dapat baru di https://aistudio.google.com/app/apikey"
    warn "Update .env lalu restart backend"
    GEMINI_OK=0
elif [[ "$GEMINI_KEY" == AIza* ]]; then
    ok "Gemini API key format OK (AIza...)"
    GEMINI_OK=1
else
    warn "Gemini API key format tidak dikenali: ${GEMINI_KEY:0:4}..."
    GEMINI_OK=0
fi

# 2c. Test Gemini API (kalau key OK)
if [ "$GEMINI_OK" = "1" ]; then
    echo "  Testing Gemini API connectivity..."
    GEMINI_RESP=$(curl -s --max-time 10 \
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${GEMINI_KEY}" \
        -H "Content-Type: application/json" \
        -d '{"contents":[{"parts":[{"text":"hi"}]}]}' 2>&1)
    if echo "$GEMINI_RESP" | grep -q '"candidates"'; then
        ok "Gemini API reachable + valid key"
    elif echo "$GEMINI_RESP" | grep -q "API_KEY_INVALID"; then
        fail "Gemini API key INVALID — generate ulang di AI Studio"
    else
        warn "Gemini API response aneh: ${GEMINI_RESP:0:200}"
    fi
fi

# 2d. Ollama check
echo "  Checking Ollama lokal..."
OLLAMA_RESP=$(curl -s --max-time 3 http://localhost:11434/api/tags 2>&1)
if echo "$OLLAMA_RESP" | grep -q "qwen2.5vl"; then
    ok "Ollama running + qwen2.5vl model installed"
else
    fail "Ollama tidak jalan atau model qwen2.5vl belum terinstall"
    warn "Fix:"
    warn "  1. ollama serve &  (terminal terpisah)"
    warn "  2. ollama pull qwen2.5vl:3b  (atau :7b)"
fi

# ============================================================
step "3/3" "AKTIFKAN WA INPUT BOT (Fonnte)"
# ============================================================

# 3a. Fonnte token + device check
FONNTE_TOKEN=$(grep "^FONNTE_TOKEN=" .env 2>/dev/null | cut -d= -f2)
if [ -z "$FONNTE_TOKEN" ] || [ "${FONNTE_TOKEN:0:5}" = "paste" ]; then
    fail "FONNTE_TOKEN kosong di .env"
    warn "Dapat di https://fonnte.com/app/settings"
else
    ok "FONNTE_TOKEN set (${#FONNTE_TOKEN} chars)"
    echo "  Checking device status..."
    DEV_RESP=$(curl -s -X POST --max-time 10 \
        -H "Authorization: $FONNTE_TOKEN" \
        https://api.fonnte.com/get-device 2>&1)
    DEV_STATUS=$(echo "$DEV_RESP" | $PYTHON -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null)
    if [ "$DEV_STATUS" = "True" ] || [ "$DEV_STATUS" = "true" ]; then
        PHONE=$(echo "$DEV_RESP" | $PYTHON -c "import json,sys; d=json.load(sys.stdin); print(d.get('phone','?'))" 2>/dev/null)
        QUOTA=$(echo "$DEV_RESP" | $PYTHON -c "import json,sys; d=json.load(sys.stdin); print(d.get('quota_remaining','?'))" 2>/dev/null)
        ok "Fonnte device CONNECTED"
        echo "    phone=$PHONE  quota_remaining=$QUOTA"
    else
        fail "Fonnte device DISCONNECTED"
        warn "Fix:"
        warn "  1. Buka https://fonnte.com/app/console"
        warn "  2. Pastikan HP terdaftar aktif + WhatsApp ON"
        warn "  3. Cek device status di sana"
    fi
fi

# 3b. Backend reachable?
echo "  Checking WA webhook endpoint..."
BACKEND_HEALTH=$(curl -s --max-time 3 http://localhost:8000/health 2>&1)
if [ -n "$BACKEND_HEALTH" ]; then
    WA_RESP=$(curl -s --max-time 3 http://localhost:8000/api/v1/wa/inbound 2>&1)
    if echo "$WA_RESP" | grep -q '"status":"ok"'; then
        ok "WA webhook endpoint hidup di backend"
        LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "localhost")
        echo "  ────────────────────────────────────────────────────────"
        echo "  Set webhook URL di Fonnte console:"
        echo "    http://${LAN_IP}:8000/api/v1/wa/inbound"
        echo "  ────────────────────────────────────────────────────────"
    else
        fail "WA webhook return: $WA_RESP"
    fi
else
    fail "Backend tidak jalan di port 8000"
    warn "Start dulu: ./start_dev.sh atau ./start_prod.sh"
fi

echo ""
echo "============================================================"
echo "  SELESAI"
echo "============================================================"
echo ""
echo "Summary:"
echo "  • T101 fix perpuluhan: sudah jalan (cek output di atas)"
echo "  • OCR: cek Gemini key + Ollama + reportlab di atas"
echo "  • WA Bot: cek Fonnte device + webhook URL di atas"
echo ""
echo "Catatan Dashboard timeout:"
echo "  • 'timeout 15000ms' / 'Memuat info sabat...' biasanya uvicorn auto-reload"
echo "  • Setelah edit file .py / install package, uvicorn restart butuh 5-15 detik"
echo "  • Refresh halaman setelah 30 detik. Atau restart manual: ./start_dev.sh"
echo ""
echo "Test:"
echo "  • OCR: buka /bendahara → OcrReview → upload foto kuitansi"
echo "  • WA Bot: dari HP, kirim pesan ke nomor Fonnte device"
echo "  • Perpuluhan: refresh dashboard, cek Porsi Misi X > 0"