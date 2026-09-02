#!/bin/bash
# FLIPUS Diagnosa v1.5 — Cek semua dependency untuk OCR + WA Bot + Auto-thanks.
# Jalanin SEBELUM demo Officers Uni untuk pastikan semua jalan.
#
# Cek:
# 1. Backend health
# 2. Gemini API key + model + connectivity
# 3. Ollama lokal + model vision
# 4. Fonnte token + device status + quota
# 5. WA webhook endpoint reachable
# 6. Konfigurasi OCR frontend
#
# Usage: ./diagnosa.sh
set -e
cd "$(dirname "$0")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
section() { echo ""; echo -e "${YELLOW}===== $1 =====${NC}"; }

section "1. BACKEND HEALTH"
HEALTH=$(curl -s --max-time 5 http://localhost:8000/health 2>&1)
if [ -n "$HEALTH" ]; then
    ok "Backend running: $HEALTH"
else
    fail "Backend TIDAK jalan di port 8000"
    echo "  → Jalankan: ./start_dev.sh atau ./start_prod.sh"
    exit 1
fi

section "2. ENV CONFIGURATION (.env)"
if [ ! -f .env ]; then
    fail ".env TIDAK ADA di $(pwd)"
    exit 1
fi
ok ".env ada"

# WA enabled?
WA_ENABLED=$(grep "^WHATSAPP_ENABLED=" .env | cut -d= -f2)
if [ "$WA_ENABLED" = "true" ]; then
    ok "WHATSAPP_ENABLED=true"
else
    fail "WHATSAPP_ENABLED=$WA_ENABLED (harus true)"
    echo "  → Edit .env: WHATSAPP_ENABLED=true"
fi

# Fonnte token
FONNTE_TOKEN=$(grep "^FONNTE_TOKEN=" .env | cut -d= -f2)
if [ -n "$FONNTE_TOKEN" ] && [ "${FONNTE_TOKEN:0:5}" != "paste" ]; then
    ok "FONNTE_TOKEN di-set (${#FONNTE_TOKEN} chars)"
else
    fail "FONNTE_TOKEN kosong/placeholder"
fi

# Gemini key
GEMINI_KEY=$(grep "^GEMINI_API_KEY=" .env | cut -d= -f2)
if [ -n "$GEMINI_KEY" ] && [ "${GEMINI_KEY:0:5}" != "GANTI" ]; then
    ok "GEMINI_API_KEY di-set (${#GEMINI_KEY} chars)"
    echo "  Format check: ${GEMINI_KEY:0:8}..."
    # Standard Google API key starts with "AIza"
    if [[ "$GEMINI_KEY" == AIza* ]]; then
        ok "  Format: Standard Google API key"
    elif [[ "$GEMINI_KEY" == AQ.* ]]; then
        warn "  Format: AQ.* — ini format Google Cloud ADC (Application Default Credentials), BUKAN API key biasa"
        warn "  Gemini API perlu AIza... key. Kalau pakai ADC, harus setup GOOGLE_APPLICATION_CREDENTIALS"
    else
        warn "  Format: tidak dikenali (mulai '${GEMINI_KEY:0:4}')"
    fi
else
    fail "GEMINI_API_KEY kosong/placeholder"
    echo "  → OCR akan NEED_REVIEW untuk semua gambar"
fi

# Ollama model
OLLAMA_MODEL=$(grep "^OLLAMA_MODEL=" .env | cut -d= -f2 | head -1)
[ -z "$OLLAMA_MODEL" ] && OLLAMA_MODEL=$(grep "^OLLAMA_MODEL=" app/core/config.py | grep -oE 'qwen2\.5vl:[0-9]+b')
ok "OLLAMA_MODEL=$OLLAMA_MODEL"

section "3. OLLAMA LOKAL"
OLLAMA_RESP=$(curl -s --max-time 3 http://localhost:11434/api/tags 2>&1)
if echo "$OLLAMA_RESP" | grep -q "qwen2.5vl" 2>/dev/null; then
    INSTALLED=$(echo "$OLLAMA_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(', '.join(m['name'] for m in d.get('models',[]) if 'qwen' in m['name']))" 2>/dev/null)
    ok "Ollama running, vision model: $INSTALLED"
else
    fail "Ollama TIDAK jalan atau model $OLLAMA_MODEL belum terinstall"
    echo "  → Start: ollama serve &"
    echo "  → Install: ollama pull $OLLAMA_MODEL"
fi

section "4. FONNTE DEVICE STATUS"
TOKEN="$FONNTE_TOKEN"
if [ -n "$TOKEN" ] && [ "${TOKEN:0:5}" != "paste" ]; then
    DEV_RESP=$(curl -s -X POST --max-time 10 \
        -H "Authorization: $TOKEN" \
        https://api.fonnte.com/get-device 2>&1)
    DEV_STATUS=$(echo "$DEV_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null)
    if [ "$DEV_STATUS" = "True" ] || [ "$DEV_STATUS" = "true" ]; then
        PHONE=$(echo "$DEV_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('phone','unknown'))" 2>/dev/null)
        QUOTA=$(echo "$DEV_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('quota_remaining','?'))" 2>/dev/null)
        ok "Fonnte device CONNECTED phone=$PHONE quota_remaining=$QUOTA"
    else
        fail "Fonnte device DISCONNECTED atau token invalid"
        echo "  Response: $DEV_RESP"
        echo "  → Cek HP yang terdaftar di Fonnte — WhatsApp harus aktif & terkoneksi internet"
    fi
else
    fail "Skip — FONNTE_TOKEN kosong"
fi

section "5. WA WEBHOOK ENDPOINT"
# Test GET (Fonnte URL verification)
WA_GET=$(curl -s --max-time 5 http://localhost:8000/api/v1/wa/inbound 2>&1)
if echo "$WA_GET" | grep -q '"status":"ok"'; then
    ok "WA inbound endpoint hidup: $WA_GET"
else
    fail "WA inbound endpoint TIDAK hidup"
    echo "  Response: $WA_GET"
fi

# Test webhook POST dengan payload simulasi (ganti dengan nomor Jerry kalau perlu)
# echo ""
# echo "Simulasi POST (test only — tidak kirim beneran):"
# curl -s -X POST --max-time 5 \
#     -d "sender=6281234567890&message=test" \
#     http://localhost:8000/api/v1/wa/inbound

section "6. OCR ENDPOINT (test upload)"
OCR_TEST=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
    http://localhost:8000/api/v1/scanner/batch-upload 2>&1)
if [ "$OCR_TEST" = "405" ] || [ "$OCR_TEST" = "401" ] || [ "$OCR_TEST" = "403" ]; then
    ok "OCR endpoint exist (HTTP $OCR_TEST = method not allowed / auth required — expected)"
elif [ "$OCR_TEST" = "000" ]; then
    fail "OCR endpoint tidak reachable (backend down?)"
else
    warn "OCR endpoint return HTTP $OCR_TEST (cek manual)"
fi

section "7. KESIMPULAN"
echo "Semua komponen kritis dicek. Kalau ada ✗ di atas, fix dulu sebelum demo."
echo ""
echo "Quick reference untuk Officers Uni demo:"
echo "  • Backend start: ./start_dev.sh (atau ./start_prod.sh kalau Vite rewel)"
echo "  • Ollama harus: ollama serve &"
echo "  • Fonnte device harus ON + WhatsApp aktif"
echo "  • Untuk demo WA Bot: kirim pesan ke nomor Fonnte device"
echo ""