#!/bin/bash
set -e
cd /Users/jerrymauri/Flipus
pkill -f uvicorn 2>/dev/null || true
sleep 2
exec /Users/jerrymauri/Flipus/.venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
