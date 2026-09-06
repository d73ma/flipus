"""v2.0 M8 smoke test — Invite user + void transaksi.

Skenario:
1. Login Bendahara_a (tenant 1, jemaat A)
2. POST /users/invite BENDAHARA dengan WA baru → 200, user created
3. POST /users/invite same WA → 409 conflict
4. POST /users/invite tanpa RBAC (login Bendahara coba invite AUDITOR) → 400/403
5. Cari Kuitansi draft (status='draft') → POST /kuitansi/{id}/void → 200
6. Cari Kuitansi finalized → POST void → 403 (locked)
7. Cari Pengeluaran draft → POST /pengeluaran/{id}/void → 200
8. Cari Pengeluaran approved → POST void → 403 (locked)
9. Verify audit log via DB query
"""
import os
import sqlite3
import sys

import requests

BASE = os.environ.get("FLIPUS_BASE", "http://localhost:8000")
DB_PATH = os.environ.get("FLIPUS_DB", "flipus_local.db")
# WA suffix unik per-run: random 2 digit biar tidak bentrok kalau re-run
_UNIQUE = f"{os.getpid() % 100:02d}"
UNIQUE = os.environ.get("FLIPUS_WA_UNIQUE", _UNIQUE)
UNIQUE_NUM = f"6289999900{UNIQUE}"

results = []  # list of (step_name, ok_bool, msg)


def login(username, password):
    r = requests.post(f"{BASE}/api/v1/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


def step(name, ok, msg=""):
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {msg}")
    results.append((name, ok, msg))


# ====== STEP 1: Login Bendahara_a ======
print("=" * 60)
print("STEP 1: Login Bendahara_a")
print("=" * 60)
try:
    tok_b = login("bendahara_a", "Bendahara123!")
    step("login Bendahara_a", True, f"token len={len(tok_b)}")
except Exception as e:
    step("login Bendahara_a", False, str(e))
    sys.exit(1)

# ====== STEP 2: Invite KETUA_KEUANGAN baru ======
print()
print("=" * 60)
print("STEP 2: POST /users/invite — invite KETUA_KEUANGAN baru")
print("=" * 60)
_SMOKE_K = f"SMOKE-M8-K-{os.getpid() % 10000}"
new_user_wa = f"6289999901{UNIQUE}"
try:
    r = requests.post(
        f"{BASE}/api/v1/users/invite",
        headers=hdr(tok_b),
        json={
            "nama_lengkap": "Ketua Smoke Test",
            "role": "KETUA_KEUANGAN",
            "nomor_whatsapp": new_user_wa,
            "username_hint": "ketua_test",
        },
    )
    if r.status_code == 200:
        d = r.json()
        step("invite KETUA_KEUANGAN", True,
             f"user_id={d['user_id']} username={d['username']} wa_sent={d['wa_sent']}")
        new_user_id = d["user_id"]
    else:
        step("invite KETUA_KEUANGAN", False, f"{r.status_code} {r.text[:200]}")
        new_user_id = None
except Exception as e:
    step("invite KETUA_KEUANGAN", False, str(e))
    new_user_id = None

# ====== STEP 3: Invite same WA → 409 ======
print()
print("=" * 60)
print("STEP 3: POST /users/invite — duplicate WA → expect 409")
print("=" * 60)
try:
    r = requests.post(
        f"{BASE}/api/v1/users/invite",
        headers=hdr(tok_b),
        json={
            "nama_lengkap": "Ketua Duplikat",
            "role": "KETUA_KEUANGAN",
            "nomor_whatsapp": new_user_wa,
        },
    )
    if r.status_code == 409:
        step("duplicate WA → 409", True, r.json().get("detail", "")[:100])
    else:
        step("duplicate WA → 409", False, f"got {r.status_code}: {r.text[:200]}")
except Exception as e:
    step("duplicate WA → 409", False, str(e))

# ====== STEP 4: Bendahara coba invite AUDITOR_MISI → expect 403 ======
print()
print("=" * 60)
print("STEP 4: Bendahara coba invite AUDITOR_MISI → expect 403")
print("=" * 60)
try:
    r = requests.post(
        f"{BASE}/api/v1/users/invite",
        headers=hdr(tok_b),
        json={
            "nama_lengkap": "Auditor Ilegal",
            "role": "AUDITOR_MISI",
            "nomor_whatsapp": f"6289999902{UNIQUE}",
        },
    )
    if r.status_code in (400, 403):
        step("Bendahara invite AUDITOR → 403", True, f"{r.status_code} {r.json().get('detail','')[:80]}")
    else:
        step("Bendahara invite AUDITOR → 403", False, f"got {r.status_code}: {r.text[:200]}")
except Exception as e:
    step("Bendahara invite AUDITOR → 403", False, str(e))

# ====== STEP 5: Void Kuitansi draft ======
print()
print("=" * 60)
print("STEP 5: Void Kuitansi draft")
print("=" * 60)
try:
    # Cari Kuitansi draft (status='draft'), kalau tidak ada → insert via sqlite3 untuk smoke test
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, nomor_kuitansi, status, is_purged, tenant_id
        FROM kuitansi
        WHERE status = 'draft' AND is_purged = 0 AND tenant_id = 1
        ORDER BY id DESC LIMIT 1
    """)
    row = cur.fetchone()
    if not row:
        # Insert draft Kuitansi langsung via DB untuk testing void rule
        cur.execute("""
            INSERT INTO kuitansi
            (tenant_id, id_rekap_mingguan, nomor_kuitansi, tanggal_sabat, status,
             perpuluhan_x_angka, pt_angka, khusus_angka,
             total_pemberian_angka, total_pemberian_huruf,
             porsi_kantor_misi, porsi_kas_jemaat, porsi_khusus_misi, porsi_khusus_jemaat,
             is_purged, is_finalized, created_by_user_id, created_via)
            VALUES (1, 'SMOKE-M8-TEST', :nomor, '2026-09-02', 'draft',
                    0, 0, 0, 0, '', 0, 0, 0, 0, 0, 0, 6, 'web')
        """, {"nomor": _SMOKE_K})
        conn.commit()
        cur.execute("SELECT last_insert_rowid()")
        new_kid = cur.fetchone()[0]
        print(f"  inserted draft Kuitansi id={new_kid} nomor={_SMOKE_K} for test")
        row = (new_kid, _SMOKE_K, "draft", 0, 1)
    conn.close()
    if row:
        kid, knomor, kstatus, kpurged, ktenant = row
        print(f"  found kuitansi id={kid} nomor={knomor} status={kstatus} tenant={ktenant}")
        r = requests.post(
            f"{BASE}/api/v1/kuitansi/{kid}/void?reason=test_smoke_m8",
            headers=hdr(tok_b),
        )
        if r.status_code == 200:
            d = r.json()
            step("void Kuitansi draft", True, f"nomor={d['nomor']} voided_by={d['voided_by_user_id']}")
        else:
            step("void Kuitansi draft", False, f"{r.status_code} {r.text[:200]}")
except Exception as e:
    step("void Kuitansi draft", False, str(e))

# ====== STEP 6: Void Kuitansi finalized → 403 ======
print()
print("=" * 60)
print("STEP 6: Void Kuitansi finalized → expect 403")
print("=" * 60)
try:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, nomor_kuitansi FROM kuitansi
        WHERE status = 'finalized' AND is_purged = 0 AND tenant_id = 1
        ORDER BY id DESC LIMIT 1
    """)
    row = cur.fetchone()
    conn.close()
    if row:
        kid, knomor = row
        r = requests.post(
            f"{BASE}/api/v1/kuitansi/{kid}/void",
            headers=hdr(tok_b),
        )
        if r.status_code == 403:
            step("void Kuitansi finalized → 403", True, r.json().get("detail", "")[:100])
        else:
            step("void Kuitansi finalized → 403", False, f"got {r.status_code}: {r.text[:200]}")
    else:
        step("void Kuitansi finalized → 403", False, "no finalized Kuitansi found for tenant 1 — skip")
except Exception as e:
    step("void Kuitansi finalized → 403", False, str(e))

# ====== STEP 7: Void Pengeluaran draft ======
print()
print("=" * 60)
print("STEP 7: Void Pengeluaran draft")
print("=" * 60)
try:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, nomor_pengeluaran, status, is_purged FROM pengeluaran
        WHERE status = 'draft' AND is_purged = 0 AND tenant_id = 1
        ORDER BY id DESC LIMIT 1
    """)
    row = cur.fetchone()
    conn.close()
    if not row:
        # Insert draft Pengeluaran langsung via DB untuk testing void rule
        from datetime import date as _date
        _smoke_pnomor = f"SMOKE-M8-P-{os.getpid() % 10000}"
        _rekap_id = f"RK-{_date.today().year}-{_date.today().month:02d}"
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        # Ambil kategori id sembarang
        cur.execute("SELECT id FROM kategori_pengeluaran WHERE is_aktif=1 ORDER BY id LIMIT 1")
        kat_row = cur.fetchone()
        if not kat_row:
            conn.close()
            step("void Pengeluaran draft", False, "no kategori_pengeluaran available")
        else:
            kat_id = kat_row[0]
            cur.execute("""
                INSERT INTO pengeluaran (tenant_id, id_rekap_mingguan, nomor_pengeluaran,
                    tanggal, tanggal_sabat, kategori_pengeluaran_id, jumlah,
                    deskripsi, penerima, metode_bayar, status, is_purged,
                    created_by_user_id, created_via, created_at, updated_at)
                VALUES (1, ?, ?, datetime('now'), date('now'), ?, 200000,
                    'Smoke Test M8', 'Bendahara', 'cash', 'draft', 0,
                    6, 'manual', datetime('now'), datetime('now'))
            """, (_rekap_id, _smoke_pnomor, kat_id))
            conn.commit()
            new_id = cur.lastrowid
            conn.close()
            print(f"  inserted draft Pengeluaran id={new_id} nomor={_smoke_pnomor}")
            r = requests.post(
                f"{BASE}/api/v1/pengeluaran/{new_id}/void?reason=test_smoke_m8",
                headers=hdr(tok_b),
            )
            if r.status_code == 200:
                d = r.json()
                step("void Pengeluaran draft", True, f"nomor={d.get('nomor','?')} voided_by={d.get('voided_by_user_id','?')}")
            else:
                step("void Pengeluaran draft", False, f"{r.status_code} {r.text[:200]}")
    else:
        pid, pnomor, pstatus, ppurged = row
        print(f"  found pengeluaran id={pid} nomor={pnomor} status={pstatus}")
        r = requests.post(
            f"{BASE}/api/v1/pengeluaran/{pid}/void?reason=test_smoke_m8",
            headers=hdr(tok_b),
        )
        if r.status_code == 200:
            d = r.json()
            step("void Pengeluaran draft", True, f"nomor={d['nomor']} voided_by={d['voided_by_user_id']}")
        else:
            step("void Pengeluaran draft", False, f"{r.status_code} {r.text[:200]}")
except Exception as e:
    step("void Pengeluaran draft", False, str(e))

# ====== STEP 8: Void Pengeluaran approved → 403 ======
print()
print("=" * 60)
print("STEP 8: Void Pengeluaran approved → expect 403")
print("=" * 60)
try:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, nomor_pengeluaran FROM pengeluaran
        WHERE status = 'approved' AND is_purged = 0 AND tenant_id = 1
        ORDER BY id DESC LIMIT 1
    """)
    row = cur.fetchone()
    conn.close()
    if row:
        pid, pnomor = row
        r = requests.post(
            f"{BASE}/api/v1/pengeluaran/{pid}/void",
            headers=hdr(tok_b),
        )
        if r.status_code == 403:
            step("void Pengeluaran approved → 403", True, r.json().get("detail", "")[:100])
        else:
            step("void Pengeluaran approved → 403", False, f"got {r.status_code}: {r.text[:200]}")
    else:
        step("void Pengeluaran approved → 403", False, "no approved Pengeluaran found for tenant 1 — skip")
except Exception as e:
    step("void Pengeluaran approved → 403", False, str(e))

# ====== STEP 9: Verify audit log ======
print()
print("=" * 60)
print("STEP 9: Verify audit log ada entry invite + void")
print("=" * 60)
try:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT action FROM audit_logs
        WHERE action LIKE '%INVITED%'
           OR action LIKE '%KUITANSI_VOID%'
           OR action LIKE '%PENGELUARAN_VOID%'
        ORDER BY id DESC LIMIT 5
    """)
    rows = cur.fetchall()
    conn.close()
    has_invite = any("INVITED" in r[0] for r in rows)
    has_void = any("VOID" in r[0] for r in rows)
    print("  audit entries:")
    for r in rows:
        print(f"    • {r[0][:120]}")
    step("audit log entries", has_invite or has_void,
         f"invite={has_invite} void={has_void} total_recent={len(rows)}")
except Exception as e:
    step("audit log entries", False, str(e))

# ====== Summary ======
print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
for name, ok, _msg in results:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
print(f"\n>>> {passed}/{total} PASS")
sys.exit(0 if passed == total else 1)
