"""
v2.0 M1 — Smoke test endpoint /kuitansi/quick-input.

Usage:
  Terminal A: cd /Users/jerrymauri/Flipus && .venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
  Terminal B: .venv/bin/python3 /tmp/test_quick_input.py
"""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8000"

def post(path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")

print("=" * 60)
print("  v2.0 M1 — Quick Input Endpoint Smoke Test")
print("=" * 60)

# Step 1: Login sebagai Bendahara_a
print("\n[1] Login Bendahara_a...")
status, resp = post("/api/v1/auth/login", {"username": "bendahara_a", "password": "Bendahara123!"})
print(f"    HTTP {status}")
print(f"    Response keys: {list(resp.keys())}")
if status != 200:
    print(f"    FULL RESPONSE: {json.dumps(resp, indent=2)}")
    sys.exit(1)

if "access_token" not in resp:
    print(f"    WARN: No access_token — got {resp}")
    print(f"    Maybe 2FA required? Got: {resp.keys()}")
    sys.exit(1)

token = resp["access_token"]
role = resp.get("role", "?")
tenant_id = resp.get("tenant_id", "?")
print(f"    OK: role={role}, tenant_id={tenant_id}, token_len={len(token)}")

# Step 2: Quick input kategori existing (X)
print("\n[2] Test kategori EXISTING (Perpuluhan)...")
status, resp = post(
    "/api/v1/kuitansi/quick-input",
    {"nama_pemberi": "Bpk. Test PWA X", "items": [{"kategori_nama": "Perpuluhan", "nominal": 150000}]},
    token=token,
)
print(f"    HTTP {status}")
print(f"    {json.dumps(resp, indent=2, ensure_ascii=False)}")
if status != 200:
    sys.exit(1)

# Step 3: Quick input kategori BARU (auto-create)
print("\n[3] Test kategori BARU (Persembahan Pembangunan - auto-create)...")
status, resp = post(
    "/api/v1/kuitansi/quick-input",
    {"nama_pemberi": "Ibu. Test Pembangunan", "items": [{"kategori_nama": "Persembahan Pembangunan", "nominal": 250000}]},
    token=token,
)
print(f"    HTTP {status}")
print(f"    {json.dumps(resp, indent=2, ensure_ascii=False)}")
if status != 200:
    sys.exit(1)

# Step 4: Quick input multi-item
print("\n[4] Test MULTI-ITEM (PT + Ulang Tahun)...")
status, resp = post(
    "/api/v1/kuitansi/quick-input",
    {"nama_pemberi": "Keluarga Test Multi", "items": [
        {"kategori_nama": "Persembahan Terpadu", "nominal": 100000},
        {"kategori_nama": "Persembahan Ulang Tahun", "nominal": 50000},
    ]},
    token=token,
)
print(f"    HTTP {status}")
print(f"    {json.dumps(resp, indent=2, ensure_ascii=False)}")
if status != 200:
    sys.exit(1)

# Step 5: Verify kategori baru sudah ter-create di DB
print("\n[5] Verify kategori baru ada di DB...")
import sqlite3  # noqa: E402

db = sqlite3.connect("/Users/jerrymauri/Flipus/flipus_local.db")
kat = db.execute("SELECT id, nama, alias, is_rutin FROM kategori_pemasukan WHERE tenant_id = ? ORDER BY id",
                 (tenant_id,)).fetchall()
print(f"    Total kategori tenant {tenant_id}: {len(kat)}")
for k in kat:
    print(f"      id={k[0]} nama={k[1]!r} alias={k[2]!r} rutin={bool(k[3])}")
db.close()

print("\n" + "=" * 60)
print("  ALL TESTS PASSED ✓")
print("=" * 60)
