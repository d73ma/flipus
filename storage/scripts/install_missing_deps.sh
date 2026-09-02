#!/bin/bash
# Install missing Python dependencies untuk FLIPUS backend.
# Dipanggil saat error "ModuleNotFoundError: No module named 'reportlab'"
# atau modul lain yang hilang di venv.

set -e

cd "$(dirname "$0")/.."

VENV_PYTHON=".venv/bin/python3"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ Venv not found di $VENV_PYTHON"
    echo "   Buat dulu: python3 -m venv .venv"
    exit 1
fi

echo "🔧 Installing missing dependencies..."
"$VENV_PYTHON" -m pip install --break-system-packages \
    "reportlab==4.2.5" \
    "Pillow==11.1.0"

echo ""
echo "✅ Verifikasi instalasi:"
"$VENV_PYTHON" -c "import reportlab; print(f'   reportlab: {reportlab.__version__}')"
"$VENV_PYTHON" -c "import PIL; print(f'   Pillow:     {PIL.__version__}')"

echo ""
echo "🚀 Sekarang restart backend:"
echo "   - Kalau pakai uvicorn langsung: Ctrl+C lalu 'uvicorn app.main:app --reload'"
echo "   - Kalau pakai docker:          docker compose restart backend"
echo "   - Kalau pakai supervisor:      sudo supervisorctl restart flipus-backend"
