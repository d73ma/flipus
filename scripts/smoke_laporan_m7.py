"""v2.0 M7 smoke test — Laporan Gabungan + PDF + Send-to-Auditor.

Skenario:
1. Login Bendahara_a → token
2. GET /laporan/gabungan/{id_rekap_mingguan} → verify Kuitansi+Pengeluaran totals
3. GET /laporan/gabungan/{id_rekap_mingguan}/pdf → verify PDF binary
4. POST /laporan/gabungan/{id_rekap_mingguan}/send-to-auditor
   - Set dummy WA untuk auditor_misi (id=4) → trigger Fonnte call
   - Restore WA ke None setelah selesai
5. Verify PDF di storage/temp/

Usage:
    python3 scripts/smoke_laporan_m7.py
"""
import os
import sys
import json
import sqlite3
import requests

BASE = os.environ.get("FLIPUS_BASE", "http://localhost:8000")
DB_PATH = os.environ.get("FLIPUS_DB", "flipus_local.db")


def login(username: str, password: str) -> str:
    r = requests.post(f"{BASE}/api/v1/auth/login", json={"username": username, "password": password}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def find_latest_rekap(token: str) -> str:
    """Ambil id_rekap_mingguan yang ada Kuitansi finalized."""
    r = requests.get(
        f"{BASE}/api/v1/kuitansi/search?status_filter=finalized&per_page=500",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json().get("items", [])
    if not data:
        raise RuntimeError("Tidak ada kuitansi finalized")
    # Group by id_rekap_mingguan, ambil yang paling baru (by max tanggal_sabat)
    by_rekap = {}
    for k in data:
        rid = k.get("id_rekap_mingguan")
        tgl = k.get("tanggal_sabat", "")
        if rid not in by_rekap or tgl > by_rekap[rid]:
            by_rekap[rid] = tgl
    return max(by_rekap.keys(), key=lambda x: by_rekap[x])


def step(title: str):
    print(f"\n=== {title} ===")


def main():
    print(f"BASE={BASE}  DB={DB_PATH}")
    print("FLIPUS v2.0 M7 smoke test — Laporan Gabungan + PDF + Send-to-Auditor\n")

    # === 1. Login Bendahara_a ===
    step("1. Login Bendahara_a")
    try:
        token = login("bendahara_a", "Bendahara123!")
    except Exception as exc:
        print(f"❌ Login gagal: {exc}")
        sys.exit(1)
    print(f"✅ token (40 chars): {token[:40]}…")

    headers = {"Authorization": f"Bearer {token}"}

    # === 2. Find rekap with Kuitansi ===
    step("2. Cari id_rekap_mingguan dengan Kuitansi finalized")
    try:
        id_rekap = find_latest_rekap(token)
    except Exception as exc:
        print(f"❌ Gagal cari rekap: {exc}")
        sys.exit(1)
    print(f"✅ id_rekap_mingguan = {id_rekap}")

    # === 3. GET JSON gabungan ===
    step("3. GET /laporan/gabungan/{id_rekap_mingguan}")
    try:
        r = requests.get(
            f"{BASE}/api/v1/laporan/gabungan/{id_rekap}",
            headers=headers,
            timeout=15,
        )
    except Exception as exc:
        print(f"❌ Request error: {exc}")
        sys.exit(1)
    print(f"   HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"❌ Response: {r.text[:300]}")
        sys.exit(1)
    data = r.json()
    print(f"   tanggal_sabat     : {data['tanggal_sabat']}")
    print(f"   nama_jemaat       : {data['nama_jemaat']}")
    print(f"   count_kuitansi    : {data['count_kuitansi']}")
    print(f"   count_peng_approved: {data['count_pengeluaran_approved']}")
    print(f"   count_peng_pending: {data['count_pengeluaran_pending']}")
    print(f"   total_penerimaan  : Rp {data['total_penerimaan']:,}")
    print(f"   total_peng_approved: Rp {data['total_pengeluaran_approved']:,}")
    print(f"   net_saldo         : Rp {data['net_saldo']:,}")
    print(f"   porsi_misi        : Rp {data['porsi_misi']:,}")
    print(f"   porsi_jemaat      : Rp {data['porsi_jemaat']:,}")
    print(f"   terima_huruf      : {data['total_penerimaan_huruf'][:60]}")
    if data["count_kuitansi"] == 0:
        print("⚠️  Tidak ada kuitansi finalized di rekap ini. Test minimal.")
    else:
        print(f"✅ Response OK ({data['count_kuitansi']} kuitansi + {data['count_pengeluaran_approved']} pengeluaran approved)")

    # === 4. GET PDF ===
    step("4. GET /laporan/gabungan/{id_rekap_mingguan}/pdf")
    try:
        r = requests.get(
            f"{BASE}/api/v1/laporan/gabungan/{id_rekap}/pdf",
            headers=headers,
            timeout=30,
        )
    except Exception as exc:
        print(f"❌ Request error: {exc}")
        sys.exit(1)
    print(f"   HTTP {r.status_code}")
    print(f"   Content-Type: {r.headers.get('Content-Type')}")
    if r.status_code != 200:
        print(f"❌ Response: {r.text[:300]}")
        sys.exit(1)
    if "pdf" not in r.headers.get("Content-Type", "").lower():
        print(f"❌ Content-Type bukan PDF: {r.headers.get('Content-Type')}")
        sys.exit(1)
    pdf_size = len(r.content)
    if pdf_size < 1000:
        print(f"❌ PDF terlalu kecil: {pdf_size} bytes")
        sys.exit(1)
    print(f"✅ PDF size: {pdf_size:,} bytes")
    # Save sample for visual inspection
    sample_path = os.path.join("storage", "temp", f"smoke_m7_{id_rekap.replace('/', '_')}.pdf")
    os.makedirs(os.path.dirname(sample_path), exist_ok=True)
    with open(sample_path, "wb") as f:
        f.write(r.content)
    print(f"   Sample saved: {sample_path}")

    # === 5. POST send-to-auditor (pakai dummy WA) ===
    step("5. POST /laporan/gabungan/{id_rekap_mingguan}/send-to-auditor")

    # Set dummy WA untuk auditor_misi dulu (id=4, tenant 1)
    dummy_wa = "6281234567890"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    original_wa = c.execute("SELECT nomor_whatsapp FROM users WHERE id=4").fetchone()
    original_wa = original_wa[0] if original_wa else None
    c.execute("UPDATE users SET nomor_whatsapp=? WHERE id=4", (dummy_wa,))
    conn.commit()
    print(f"   [setup] auditor_misi (id=4) WA: {original_wa} → {dummy_wa}")

    try:
        r = requests.post(
            f"{BASE}/api/v1/laporan/gabungan/{id_rekap}/send-to-auditor",
            headers=headers,
            timeout=60,
        )
    except Exception as exc:
        print(f"❌ Request error: {exc}")
        # restore
        c.execute("UPDATE users SET nomor_whatsapp=? WHERE id=4", (original_wa,))
        conn.commit()
        conn.close()
        sys.exit(1)
    finally:
        # always restore
        c.execute("UPDATE users SET nomor_whatsapp=? WHERE id=4", (original_wa,))
        conn.commit()
        conn.close()
        print(f"   [restore] auditor_misi (id=4) WA: {dummy_wa} → {original_wa}")

    print(f"   HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"❌ Response: {r.text[:500]}")
        sys.exit(1)
    blast = r.json()
    print(f"   status           : {blast['status']}")
    print(f"   auditors_found   : {blast['auditors_found']}")
    print(f"   auditors_notified: {blast['auditors_notified']}")
    print(f"   auditors_skipped : {len(blast['auditors_skipped'])}")
    for sk in blast['auditors_skipped']:
        print(f"      - {sk}")
    print(f"   pdf_filename     : {blast['pdf_filename']}")
    if blast["auditors_found"] < 1:
        print("❌ Tidak ada auditor ditemukan (seharusnya 1)")
        sys.exit(1)
    print(f"✅ send-to-auditor OK ({blast['auditors_notified']} notified, {len(blast['auditors_skipped'])} skipped)")

    # === Final summary ===
    print("\n" + "=" * 60)
    print("✅ v2.0 M7 SMOKE TEST COMPLETE")
    print(f"   • JSON gabungan: {data['count_kuitansi']} kuitansi + {data['count_pengeluaran_approved']} pengeluaran")
    print(f"   • PDF generated: {pdf_size:,} bytes")
    print(f"   • Auditor blast: {blast['auditors_found']} found, {blast['auditors_notified']} notified, {len(blast['auditors_skipped'])} skipped")
    print("=" * 60)


if __name__ == "__main__":
    main()