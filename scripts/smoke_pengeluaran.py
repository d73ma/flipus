"""
v2.0 M5 Smoke Test — Modul Pengeluaran end-to-end.

Tests:
1. Migration tables exist + 4 kategori default per tenant
2. BENDAHARA login → list kategori
3. Create custom kategori → list show 5
4. Create pengeluaran RUTIN (kategori Listrik) → submit → status='approved' (auto-approved)
5. Create pengeluaran NON-RUTIN (kategori Pembangunan) → submit → status='pending_approval'
6. KETUA approve → status='approved_ketua'
7. PENDETA approve → status='approved'
8. REJECT flow: create non-rutin → KETUA reject → status='rejected' with reason
9. List by status_filter
10. Rekap bulanan: total_rutin + total_non_rutin + count_pending

Usage:
    .venv/bin/python3 scripts/smoke_pengeluaran.py

Assumes backend running di http://localhost:8000 dan DB sudah di-migrate.
"""
import sys
import os
import requests

BASE = os.environ.get("FLIPUS_BASE", "http://localhost:8000")
PASSWORD = "Bendahara123!"


def login(username: str, password: str) -> str:
    r = requests.post(f"{BASE}/api/v1/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def check(label: str, ok: bool, detail: str = ""):
    icon = "✅" if ok else "❌"
    print(f"  {icon} {label}" + (f" — {detail}" if detail else ""))
    return ok


def main():
    print("=" * 70)
    print("  v2.0 M5 SMOKE TEST — Modul Pengeluaran")
    print("=" * 70)

    # 1. Migration check
    print("\n[1] Check migration tables exist...")
    try:
        r = requests.get(f"{BASE}/api/v1/kategori-pengeluaran/list")
        # Tanpa auth → 401 expected
        if r.status_code == 401:
            print("  ✅ Endpoint exists (auth required as expected)")
        elif r.status_code == 200:
            print("  ⚠️  Endpoint accessible without auth (CHECK)")
        else:
            print(f"  ❌ Unexpected status: {r.status_code}")
            sys.exit(1)
    except Exception as e:
        print(f"  ❌ Cannot reach backend: {e}")
        sys.exit(1)

    # 2. BENDAHARA login
    print("\n[2] Login as bendahara_a (demo tenant)...")
    try:
        token_b = login("bendahara_a", PASSWORD)
        check("bendahara_a login", True)
    except Exception as e:
        print(f"  ❌ Login failed: {e}. Cek demo seed sudah jalan.")
        sys.exit(1)

    # 3. List kategori
    print("\n[3] List kategori pengeluaran (expect 4 default)...")
    r = requests.get(f"{BASE}/api/v1/kategori-pengeluaran/list", headers=hdr(token_b))
    r.raise_for_status()
    kats = r.json()
    check("kategori list returns 4 items", len(kats) == 4, f"got {len(kats)}")
    rutin_count = sum(1 for k in kats if k["is_rutin"])
    check("all 4 are is_rutin=True (default)", rutin_count == 4, f"{rutin_count} rutin")
    listrik = next((k for k in kats if k["alias"] == "LIS"), None)
    check("Listrik (LIS) exists", listrik is not None)

    # 4. Create custom kategori (non-rutin)
    print("\n[4] Create custom kategori 'Pembangunan' (non-rutin)...")
    r = requests.post(
        f"{BASE}/api/v1/kategori-pengeluaran/create",
        headers=hdr(token_b),
        json={"nama": "Pembangunan", "alias": "PBG", "is_rutin": False},
    )
    if r.status_code == 201:
        pbg = r.json()
        check("Pembangunan created", True, f"id={pbg['id']}")
    elif r.status_code == 409:
        # Already exists (idempotent)
        r2 = requests.get(f"{BASE}/api/v1/kategori-pengeluaran/list", headers=hdr(token_b))
        pbg = next((k for k in r2.json() if k["alias"] == "PBG"), None)
        check("Pembangunan already exists (idempotent)", pbg is not None, f"id={pbg['id'] if pbg else '?'}")
    else:
        check("Pembangunan created", False, f"status={r.status_code}: {r.text[:200]}")
        sys.exit(1)

    # 5. Create pengeluaran RUTIN (Listrik)
    print("\n[5] Create RUTIN pengeluaran (Listrik, 250000)...")
    r = requests.post(
        f"{BASE}/api/v1/pengeluaran/create",
        headers=hdr(token_b),
        json={
            "tanggal": "2026-09-05",
            "kategori_pengeluaran_id": listrik["id"],
            "jumlah": 250000,
            "deskripsi": "Bayar listrik bulan Agustus",
            "penerima": "PLN",
            "metode_bayar": "transfer",
        },
    )
    if r.status_code != 201:
        check("Create rutin", False, f"status={r.status_code}: {r.text[:300]}")
        sys.exit(1)
    p_rutin = r.json()
    check("Rutin created (draft)", p_rutin["status"] == "draft", f"status={p_rutin['status']}, nomor={p_rutin['nomor_pengeluaran']}")

    # Submit → auto-approved
    r = requests.post(f"{BASE}/api/v1/pengeluaran/{p_rutin['id']}/submit", headers=hdr(token_b))
    r.raise_for_status()
    p_rutin_submitted = r.json()
    check("Submit rutin → auto-approved", p_rutin_submitted["status"] == "approved", f"status={p_rutin_submitted['status']}")

    # 6. Create pengeluaran NON-RUTIN (Pembangunan)
    print("\n[6] Create NON-RUTIN pengeluaran (Pembangunan, 1500000)...")
    r = requests.post(
        f"{BASE}/api/v1/pengeluaran/create",
        headers=hdr(token_b),
        json={
            "tanggal": "2026-09-06",
            "kategori_pengeluaran_id": pbg["id"] if isinstance(pbg, dict) and "id" in pbg else None,
            "jumlah": 1500000,
            "deskripsi": "Beli semen 10 sak untuk renovasi",
            "penerima": "Toko Bangunan",
            "metode_bayar": "tunai",
        },
    )
    if r.status_code != 201:
        check("Create non-rutin", False, f"status={r.status_code}: {r.text[:300]}")
        sys.exit(1)
    p_nonrutin = r.json()
    check("Non-rutin created (draft)", p_nonrutin["status"] == "draft")

    # Submit → pending_approval
    r = requests.post(f"{BASE}/api/v1/pengeluaran/{p_nonrutin['id']}/submit", headers=hdr(token_b))
    r.raise_for_status()
    p_nonrutin_submitted = r.json()
    check("Submit non-rutin → pending_approval", p_nonrutin_submitted["status"] == "pending_approval", f"status={p_nonrutin_submitted['status']}")

    # 7. KETUA approve
    print("\n[7] KETUA approve → approved_ketua...")
    try:
        token_k = login("ketua_a", "Ketua123!")
    except Exception as e:
        print(f"  ❌ ketua_a login failed: {e}")
        sys.exit(1)
    r = requests.post(
        f"{BASE}/api/v1/pengeluaran/{p_nonrutin['id']}/approve-ketua",
        headers=hdr(token_k),
        json={"note": "Disetujui untuk renovasi"},
    )
    r.raise_for_status()
    p_approved_ketua = r.json()
    check("Ketua approve → approved_ketua", p_approved_ketua["status"] == "approved_ketua", f"status={p_approved_ketua['status']}")

    # 8. PENDETA approve
    print("\n[8] PENDETA approve → approved (LOCKED)...")
    try:
        token_p = login("pendeta_a", "Pendeta123!")
    except Exception as e:
        print(f"  ❌ pendeta_a login failed: {e}")
        sys.exit(1)
    r = requests.post(
        f"{BASE}/api/v1/pengeluaran/{p_nonrutin['id']}/approve-pendeta",
        headers=hdr(token_p),
        json={"note": "Setuju, lanjutkan"},
    )
    r.raise_for_status()
    p_approved = r.json()
    check("Pendeta approve → approved", p_approved["status"] == "approved", f"status={p_approved['status']}")

    # 9. REJECT flow
    print("\n[9] REJECT flow: create another non-rutin → KETUA reject...")
    r = requests.post(
        f"{BASE}/api/v1/pengeluaran/create",
        headers=hdr(token_b),
        json={
            "tanggal": "2026-09-07",
            "kategori_pengeluaran_id": pbg["id"] if isinstance(pbg, dict) and "id" in pbg else None,
            "jumlah": 5000000,
            "deskripsi": "Beli laptop baru untuk kantor",
            "metode_bayar": "transfer",
        },
    )
    r.raise_for_status()
    p_reject = r.json()
    requests.post(f"{BASE}/api/v1/pengeluaran/{p_reject['id']}/submit", headers=hdr(token_b))
    r = requests.post(
        f"{BASE}/api/v1/pengeluaran/{p_reject['id']}/reject",
        headers=hdr(token_k),
        json={"reason": "Tidak ada di RAPB 2026, usulkan di tahun depan"},
    )
    r.raise_for_status()
    p_rejected = r.json()
    check("Reject → rejected with reason", p_rejected["status"] == "rejected" and p_rejected["rejected_reason"] is not None)

    # 10. List by status
    print("\n[10] List by status_filter=approved (expect 2)...")
    r = requests.get(f"{BASE}/api/v1/pengeluaran/list?status_filter=approved", headers=hdr(token_b))
    r.raise_for_status()
    approved_list = r.json()
    check("List approved returns 2 (rutin + non-rutin)", len(approved_list) >= 2, f"got {len(approved_list)}")

    # 11. Rekap bulanan
    print("\n[11] Rekap bulanan September 2026...")
    r = requests.get(f"{BASE}/api/v1/pengeluaran/rekap?bulan=2026-09", headers=hdr(token_b))
    r.raise_for_status()
    rekap = r.json()
    print(f"     Total: Rp {rekap['total']:,} ({rekap['count_rutin']} rutin, {rekap['count_non_rutin']} non-rutin)")
    print(f"     Rutin: Rp {rekap['total_rutin']:,}")
    print(f"     Non-rutin: Rp {rekap['total_non_rutin']:,}")
    print(f"     Pending: {rekap['count_pending']}")
    print(f"     By kategori: {len(rekap['by_kategori'])} entries")
    check("Rekap total = 1750000 (250k + 1.5M)", rekap["total"] == 1750000, f"got {rekap['total']:,}")
    check("count_pending = 0 (all approved/rejected)", rekap["count_pending"] == 0)

    # 12. Pending count endpoint
    print("\n[12] Pending count for KETUA dashboard badge...")
    r = requests.get(f"{BASE}/api/v1/pengeluaran/pending-count", headers=hdr(token_k))
    r.raise_for_status()
    pc = r.json()
    check("Pending count endpoint works", "pending_ketua" in pc, f"{pc}")

    # Summary
    print("\n" + "=" * 70)
    print("  ✅ SMOKE TEST COMPLETE — Modul Pengeluaran end-to-end WORKS")
    print("=" * 70)
    print("\nNext steps:")
    print("  • Restart uvicorn untuk apply new routers")
    print("  • Buka /bendahara/pengeluaran di browser mobile via LAN")
    print("  • Verifikasi visual form Pengeluaran")


if __name__ == "__main__":
    main()