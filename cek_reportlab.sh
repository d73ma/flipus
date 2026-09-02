#!/bin/bash
# FLIPUS — Quick cek reportlab + auto-install kalau belum ada.
# Usage: ./cek_reportlab.sh

set -e
cd "$(dirname "$0")"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PYTHON="/Users/jerrymauri/Flipus/.venv/bin/python3"
[ -x "$PYTHON" ] || PYTHON="python3"

echo "============================================================"
echo "  Cek + Install reportlab"
echo "============================================================"
echo ""

VERSION=$($PYTHON -c "import reportlab; print(reportlab.__version__)" 2>&1)
if [[ "$VERSION" == 4.* ]]; then
    printf "${GREEN}✓${NC} reportlab OK (v$VERSION)\n"
    echo "  → Backend yang baru running sudah recognize library ini."
    echo "  → Coba: buka /bendahara → klik 'Buat Laporan Keuangan' → Generate"
    exit 0
fi

echo -e "${RED}✗${NC} reportlab BELUM ADA"
echo "  Error: $VERSION"
echo ""
echo "Installing reportlab==4.2.5 ..."
/Users/jerrymauri/Flipus/.venv/bin/pip install reportlab==4.2.5 2>&1 | tail -5
echo ""

VERSION2=$($PYTHON -c "import reportlab; print(reportlab.__version__)" 2>&1)
if [[ "$VERSION2" == 4.* ]]; then
    printf "${GREEN}✓${NC} reportlab terinstall (v$VERSION2)\n"
    echo ""
    echo -e "${YELLOW}⚠${NC} PENTING: Backend HARUS di-restart manual supaya recognize library baru."
    echo "  → Stop terminal yang ada start_dev.sh (Ctrl+C)"
    echo "  → Run ulang: ./start_dev.sh"
    echo "  → Tunggu 10 detik, refresh dashboard"
else
    printf "${RED}✗${NC} Install gagal: $VERSION2\n"
    echo "  → Coba manual: /Users/jerrymauri/Flipus/.venv/bin/pip install reportlab==4.2.5"
fi
echo ""
echo "============================================================"