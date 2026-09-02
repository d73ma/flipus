#!/bin/bash
# Extract traceback dari log file (binary-safe)
echo "=== WA checkpoint logs ==="
grep -a "WA-INBOUND-TOPLEVEL\|WA-BTN-SIMPAN\|WA-INBOUND-ENTRY" /tmp/flipus_backend.log | head -40
echo ""
echo "=== TOPLEVEL traceback (full, raw) ==="
grep -a "WA-INBOUND-TOPLEVEL" /tmp/flipus_backend.log | head -1
awk '/WA-INBOUND-TOPLEVEL/{found=1} found{print; if (++n > 60) exit}' /tmp/flipus_backend.log | tail -60
echo ""
echo "=== ASGI error trace ==="
awk '/Exception in ASGI/{found=1} found{print; if (++n > 60) exit}' /tmp/flipus_backend.log | tail -60