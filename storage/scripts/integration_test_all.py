"""
FLIPUS v1.2 — Integration test suite.

Run: storage/scripts/integration_test_all.py

Tests all major E2E flows:
1. Login (admin, bendahara, ketua, pendeta, auditor)
2. List master data (Uni, Misi)
3. Create kuitansi (Bendahara)
4. Get agregat tenant (Ketua/Pendeta)
5. Get agregat misi (Auditor)
6. Backup DB (Admin)
7. List backups
8. List audit logs

Returns: pass/fail per test, exit code 0 kalau semua pass.
"""

import sys
import time
import json
import httpx
from typing import Dict, List, Tuple


BASE_URL = "http://localhost:8000/api/v1"
TIMEOUT = 30.0

# Default credentials (dari rehash_passwords.py)
USERS = {
    "admin_uni":   "AdminUni123!",
    "bendahara":   "Bendahara123!",
    "ketua_keuang": "Ketua123!",
    "pendeta":     "Pendeta123!",
    "auditor_misi": "AuditMisi123!",
}


class TestResult:
    def __init__(self):
        self.passed: List[str] = []
        self.failed: List[Tuple[str, str]] = []

    def ok(self, name: str):
        self.passed.append(name)
        print(f"  ✓ {name}")

    def fail(self, name: str, reason: str):
        self.failed.append((name, reason))
        print(f"  ✗ {name}: {reason}")

    def summary(self) -> int:
        total = len(self.passed) + len(self.failed)
        print(f"\n=== Summary ===")
        print(f"Passed: {len(self.passed)}/{total}")
        print(f"Failed: {len(self.failed)}/{total}")
        if self.failed:
            print("\nFailed tests:")
            for name, reason in self.failed:
                print(f"  - {name}: {reason}")
            return 1
        print("\n✅ All tests passed!")
        return 0


def login(client: httpx.Client, username: str, password: str) -> str:
    """Login dan return JWT."""
    resp = client.post(f"{BASE_URL}/auth/login", json={"username": username, "password": password})
    resp.raise_for_status()
    return resp.json()["access_token"]


def test_login_all_users(client: httpx.Client) -> Dict[str, str]:
    """Login semua user default, return map username → token."""
    print("\n[1] Login all users")
    tokens = {}
    for username, password in USERS.items():
        try:
            tokens[username] = login(client, username, password)
            print(f"  ✓ {username}: login OK")
        except Exception as e:
            print(f"  ✗ {username}: {e}")
    return tokens


def test_master_data(client: httpx.Client, token: str, result: TestResult):
    """Test master data endpoints."""
    print("\n[2] Master data (Uni, Misi)")
    headers = {"Authorization": f"Bearer {token}"}

    # GET /uni
    try:
        r = client.get(f"{BASE_URL}/master/uni", headers=headers, timeout=TIMEOUT)
        if r.status_code == 200 and len(r.json()) >= 3:
            result.ok("GET /master/uni (returns ≥3 Uni)")
        else:
            result.fail("GET /master/uni", f"Got {r.status_code}: {r.text[:100]}")
    except Exception as e:
        result.fail("GET /master/uni", str(e))

    # GET /misi
    try:
        r = client.get(f"{BASE_URL}/master/misi", headers=headers, timeout=TIMEOUT)
        if r.status_code == 200 and len(r.json()) >= 10:
            result.ok(f"GET /master/misi (returns {len(r.json())} Misi)")
        else:
            result.fail("GET /master/misi", f"Got {r.status_code}: {r.text[:100]}")
    except Exception as e:
        result.fail("GET /master/misi", str(e))


def test_agregat_tenant(client: httpx.Client, token: str, result: TestResult):
    """Test agregat tenant endpoint (Bendahara/Ketua)."""
    print("\n[3] Agregat tenant (Bendahara/Ketua)")
    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = client.get(f"{BASE_URL}/agregat/tenant", headers=headers, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            required = {"nama_jemaat", "minggu_items", "grand_total_semua", "grand_total_huruf"}
            if required.issubset(data.keys()):
                result.ok(f"GET /agregat/tenant (jemaat={data['nama_jemaat']})")
            else:
                result.fail("GET /agregat/tenant", f"Missing fields: {required - data.keys()}")
        else:
            result.fail("GET /agregat/tenant", f"Got {r.status_code}: {r.text[:100]}")
    except Exception as e:
        result.fail("GET /agregat/tenant", str(e))


def test_create_kuitansi(client: httpx.Client, token: str, result: TestResult):
    """Test create kuitansi (Bendahara)."""
    print("\n[4] Create kuitansi (Bendahara)")
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "nama_umat": "Test Umat Integration",
        "nomor_whatsapp": "628123456789",
        "perpuluhan_x_angka": 500000,
        "pt_angka": 200000,
        "khusus_angka": 0,
    }

    try:
        r = client.post(f"{BASE_URL}/dashboard/kuitansi", json=payload, headers=headers, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            if data.get("nomor_kuitansi") and data.get("total_pemberian_angka") == 700000:
                result.ok(f"POST /dashboard/kuitansi (nomor={data['nomor_kuitansi']})")
            else:
                result.fail("POST /dashboard/kuitansi", f"Unexpected response: {data}")
        else:
            result.fail("POST /dashboard/kuitansi", f"Got {r.status_code}: {r.text[:100]}")
    except Exception as e:
        result.fail("POST /dashboard/kuitansi", str(e))


def test_agregat_misi(client: httpx.Client, token: str, result: TestResult):
    """Test agregat misi (Auditor)."""
    print("\n[5] Agregat misi (Auditor)")
    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = client.get(f"{BASE_URL}/agregat/misi", headers=headers, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            if "nama_misi" in data and "jemaat_summary" in data:
                result.ok(f"GET /agregat/misi (misi={data['nama_misi']}, jemaat={data['jemaat_count']})")
            else:
                result.fail("GET /agregat/misi", f"Missing fields")
        else:
            result.fail("GET /agregat/misi", f"Got {r.status_code}: {r.text[:100]}")
    except Exception as e:
        result.fail("GET /agregat/misi", str(e))


def test_admin_backup(client: httpx.Client, token: str, result: TestResult):
    """Test backup endpoint (Admin)."""
    print("\n[6] Admin backup + list + audit logs")
    headers = {"Authorization": f"Bearer {token}"}

    # POST /backup-db
    try:
        r = client.post(f"{BASE_URL}/admin/backup-db?method=binary&retention=7", headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            if data.get("filename") and data.get("size_bytes"):
                result.ok(f"POST /admin/backup-db ({data['filename']}, {data['size_bytes']} bytes)")
            else:
                result.fail("POST /admin/backup-db", "Missing filename/size_bytes")
        else:
            result.fail("POST /admin/backup-db", f"Got {r.status_code}: {r.text[:100]}")
    except Exception as e:
        result.fail("POST /admin/backup-db", str(e))

    # GET /backups
    try:
        r = client.get(f"{BASE_URL}/admin/backups", headers=headers, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data.get("backups"), list) and data["count"] > 0:
                result.ok(f"GET /admin/backups (count={data['count']})")
            else:
                result.fail("GET /admin/backups", "No backups returned")
        else:
            result.fail("GET /admin/backups", f"Got {r.status_code}: {r.text[:100]}")
    except Exception as e:
        result.fail("GET /admin/backups", str(e))

    # GET /audit-logs
    try:
        r = client.get(f"{BASE_URL}/admin/audit-logs?page=1&per_page=10", headers=headers, timeout=TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            if "logs" in data and "count" in data:
                result.ok(f"GET /admin/audit-logs (count={data['count']})")
            else:
                result.fail("GET /admin/audit-logs", "Missing fields")
        else:
            result.fail("GET /admin/audit-logs", f"Got {r.status_code}: {r.text[:100]}")
    except Exception as e:
        result.fail("GET /admin/audit-logs", str(e))


def test_rbac(client: httpx.Client, tokens: Dict[str, str], result: TestResult):
    """Test RBAC: Bendahara tidak bisa akses admin endpoint."""
    print("\n[7] RBAC enforcement")
    headers = {"Authorization": f"Bearer {tokens['bendahara']}"}

    try:
        r = client.get(f"{BASE_URL}/admin/backups", headers=headers, timeout=TIMEOUT)
        if r.status_code == 403:
            result.ok("RBAC: Bendahara → /admin/backups = 403")
        else:
            result.fail("RBAC: Bendahara", f"Expected 403, got {r.status_code}")
    except Exception as e:
        result.fail("RBAC: Bendahara", str(e))


def main():
    print("=== FLIPUS v1.2 — Integration Test Suite ===")
    print(f"Target: {BASE_URL}\n")

    result = TestResult()

    with httpx.Client() as client:
        # 1) Login semua user
        tokens = test_login_all_users(client)
        if len(tokens) < 5:
            print(f"⚠ Only {len(tokens)}/5 users logged in. Some tests may skip.")

        if not tokens:
            print("❌ Tidak bisa login. Cek apakah backend running.")
            return 1

        # 2-3) Master data + Agregat (Bendahara)
        test_master_data(client, tokens["bendahara"], result)
        test_agregat_tenant(client, tokens["bendahara"], result)
        test_create_kuitansi(client, tokens["bendahara"], result)

        # 4-5) Ketua + Pendeta + Auditor
        test_agregat_tenant(client, tokens["ketua_keuang"], result)
        test_agregat_tenant(client, tokens["pendeta"], result)
        test_agregat_misi(client, tokens["auditor_misi"], result)

        # 6) Admin
        test_admin_backup(client, tokens["admin_uni"], result)

        # 7) RBAC
        test_rbac(client, tokens, result)

    return result.summary()


if __name__ == "__main__":
    sys.exit(main())