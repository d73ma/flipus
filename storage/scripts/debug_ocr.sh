#!/bin/bash
# FLIPUS v1.4 — OCR Debug Script (T53-T57 verification)
#
# Purpose: Verify Gemini OCR benar-benar baca image (vs cache/hallucinate).
# Usage: ./storage/scripts/debug_ocr.sh
#
# Apa yang dilakukan:
#   1. Scan semua file di storage/temp/
#   2. Untuk setiap file, print MD5 hash + size + Gemini raw response
#   3. Highlight kalau hash sama (kemungkinan cached) atau response mirip (hallucination)
#
# Expected: beda image → beda MD5 → beda response
# Kalau hasilnya semua SAMA → bug Gemini API cache/auth/key

set -e

BACKEND_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$BACKEND_DIR"

TEMP_DIR="$BACKEND_DIR/storage/temp"

echo "=== FLIPUS OCR Debug ==="
echo "Scanning: $TEMP_DIR"
echo ""

# Collect all image files (skip backups/encrypted)
mapfile -t FILES < <(find "$TEMP_DIR" -maxdepth 1 -type f \
    \( -iname "*.jpg" -o -iname "*.jpeg" -o -iname "*.png" \) \
    -printf '%T@ %s %p\n' | sort -rn | awk '{print $3}')

if [ ${#FILES[@]} -eq 0 ]; then
    echo "❌ No image files found in $TEMP_DIR"
    exit 1
fi

echo "Found ${#FILES[@]} file(s). Computing hashes..."
echo ""

# Compute hash for each unique file
declare -A HASH_MAP
for f in "${FILES[@]}"; do
    HASH=$(md5 -q "$f" 2>/dev/null || md5sum "$f" | awk '{print $1}')
    BASENAME=$(basename "$f")
    SIZE=$(du -h "$f" | awk '{print $1}')
    echo "  $BASENAME  →  $HASH  ($SIZE)"
    HASH_MAP["$HASH"]="${HASH_MAP[$HASH]:-} $BASENAME"
done

echo ""
echo "=== Hash uniqueness check ==="
UNIQUE_HASHES=$(printf '%s\n' "${FILES[@]}" | xargs -I {} md5 -q {} 2>/dev/null | sort -u | wc -l)
TOTAL_FILES=${#FILES[@]}
echo "Total files: $TOTAL_FILES"
echo "Unique hashes: $UNIQUE_HASHES"
if [ "$UNIQUE_HASHES" -lt "$TOTAL_FILES" ]; then
    echo "⚠️  Ada file dengan hash sama (kemungkinan duplicate upload)"
else
    echo "✓ Semua file punya hash unik (tidak ada duplicate)"
fi
echo ""

echo "=== Calling Gemini OCR untuk SEMUA file (batch) ==="
echo ""

# Build JSON list of paths for Python call
PYTHON_PATHS=$(printf '"%s",' "${FILES[@]}" | sed 's/,$//')

PYTHONPATH="$BACKEND_DIR" "$BACKEND_DIR/.venv/bin/python3" - << PYEOF
import os, hashlib, json
from pathlib import Path

paths = [${PYTHON_PATHS}]

print(f"Processing {len(paths)} files via process_batch...")
print("")

from app.ai_engine.batch_processor import process_batch

result = process_batch(paths)
print(f"total_amplop: {result['total_amplop']}")
print(f"need_review_count: {result.get('need_review_count', 0)}")
print("")
print(f"{'Idx':<4} {'img_hash':<14} {'Nama':<25} {'X':<12} {'PT':<12} {'Status':<14} {'Source':<18}")
print("-" * 110)

for it in result['items']:
    idx = it.get('index', '?')
    ih = it.get('img_hash') or '-'
    nama = (it.get('nama_umat') or '')[:23]
    x = it.get('perpuluhan_X_angka', 0)
    pt = it.get('PT_angka', 0)
    status = it.get('ocr_status', '?')
    source = it.get('ocr_source', '?')
    print(f"{idx:<4} {ih:<14} {nama:<25} {x:<12} {pt:<12} {status:<14} {source:<18}")

print("")
print("=== ANALISIS ===")
hashes = [it.get('img_hash') for it in result['items']]
if len(set(hashes)) < len(hashes):
    print("⚠️  Ada item dengan img_hash sama — kemungkinan Gemini return CACHED response untuk image berbeda")
else:
    print("✓ Semua img_hash unik")

# Check apakah OCR results identik despite different images
seen_responses = {}
for it in result['items']:
    key = (it.get('nama_umat', ''), it.get('perpuluhan_X_angka', 0), it.get('PT_angka', 0))
    if key not in seen_responses:
        seen_responses[key] = []
    seen_responses[key].append(it.get('img_hash', '?'))

dup_count = sum(1 for v in seen_responses.values() if len(v) > 1)
if dup_count > 0:
    print(f"⚠️  {dup_count} OCR response DUPLICATE untuk image berbeda → kemungkinan HALLUCINATION/CACHE")
    for k, v in seen_responses.items():
        if len(v) > 1:
            print(f"   Response: nama={k[0]!r} X={k[1]} PT={k[2]} → hashes: {v}")
else:
    print("✓ Semua OCR response unik per image")
PYEOF