"""
FLIPUS v1.1 — Test script untuk register endpoints.

Jalankan SETELAH backend running di Mac (port 8000) dan master data sudah di-seed.

    /Users/jerrymauri/Flipus/.venv/bin/python3 -m storage.scripts.test_register

Test 3 endpoint register + verifikasi user created di DB.
"""

import os
import sys

sys.path.insert(0, os.getcwd())

import requests

BASE = "http://localhost:8000/api/v1"


def get_first_uni(db_or_engine=None):
    """Ambil Uni pertama via API."""
    r = requests.get(f"{BASE}/master/uni")
    r.raise_for_status()
    return r.json()[0]


def get_first_misi(uni_id):
    r = requests.get(f"{BASE}/master/misi", params={"uni_id": uni_id})
    r.raise_for_status()
    return r.json()[0]


def test_register_pendeta():
    print("\n=== TEST: Register Pendeta ===")
    uni = get_first_uni()
    misi = get_first_misi(uni["id"])
    payload = {
        "uni_id": uni["id"],
        "misi_konferens_id": misi["id"],
        "nama_jemaat": "Jemaat Tes Nataan",
        "initial_jemaat": "TN",
        "nama_pendeta": "Pdt. Tes Pendeta",
        "wa_pendeta": "628123456789",
        "nama_ketua": "Bpk. Tes Ketua",
        "wa_ketua": None,
        "nama_bendahara": "Ibu Tes Bendahara",
        "wa_bendahara": None,
    }
    r = requests.post(f"{BASE}/register/pendeta", json=payload)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"  user_id: {data['user_id']}")
        print(f"  username: {data['credentials']['username']}")
        print(f"  password: {data['credentials']['password']}")
        print(f"  password_masked: {data['credentials']['password_masked']}")
        print(f"  wa_sent: {data['credentials']['wa_sent']}")
        print(f"  message: {data['message']}")
        return data["credentials"]["username"], data["credentials"]["password"]
    else:
        print(f"  ERROR: {r.json()}")
        return None, None


def test_register_auditor():
    print("\n=== TEST: Register Auditor ===")
    uni = get_first_uni()
    misi = get_first_misi(uni["id"])
    payload = {
        "uni_id": uni["id"],
        "misi_konferens_id": misi["id"],
        "nama_bendahara_misi": "Bpk. Tes Bendahara Misi",
        "wa_bendahara_misi": None,
        "nama_auditor": "Ibu Tes Auditor",
        "wa_auditor": "628123456789",
        "pct_x_jemaat": 1.0,
        "pct_pt_jemaat": 0.5,
        "pct_khusus_jemaat": 0.5,
    }
    r = requests.post(f"{BASE}/register/auditor", json=payload)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"  username: {data['credentials']['username']}")
        print(f"  password: {data['credentials']['password']}")
        return data["credentials"]["username"], data["credentials"]["password"]
    else:
        print(f"  ERROR: {r.json()}")
        return None, None


def test_register_admin():
    print("\n=== TEST: Register Admin Uni ===")
    uni = get_first_uni()
    payload = {
        "uni_id": uni["id"],
        "nama_bendahara_uni": "Bpk. Tes Bendahara Uni",
        "wa_bendahara_uni": None,
        "nama_admin_uni": "Ibu Tes Admin Uni",
        "wa_admin_uni": "628123456789",
        "pct_x_uni": 0.5,
        "pct_pt_uni": 0.3,
        "pct_khusus_uni": 0.3,
    }
    r = requests.post(f"{BASE}/register/admin", json=payload)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"  username: {data['credentials']['username']}")
        print(f"  password: {data['credentials']['password']}")
        return data["credentials"]["username"], data["credentials"]["password"]
    else:
        print(f"  ERROR: {r.json()}")
        return None, None


def test_login(username, password):
    print(f"\n=== TEST: Login as {username} ===")
    r = requests.post(f"{BASE}/auth/login", json={"username": username, "password": password})
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"  role: {data['role']}")
        print(f"  tenant_id: {data['tenant_id']}")
        print(f"  token: {data['access_token'][:30]}...")
    else:
        print(f"  ERROR: {r.json()}")


def main():
    print("=== FLIPUS v1.1 — Register Endpoint Tests ===")
    print("Pastikan backend running di http://localhost:8000")
    print("Pastikan master data sudah di-seed (run seed_master_data.py)")

    # Step 1: Seed master (kalau belum)
    print("\n=== STEP 0: Seed master data ===")
    r = requests.post(f"{BASE}/master/seed")
    print(f"Status: {r.status_code}, Response: {r.json()}")

    # Step 2: Test register
    p_user, p_pass = test_register_pendeta()
    a_user, a_pass = test_register_auditor()
    ad_user, ad_pass = test_register_admin()

    # Step 3: Test login dengan kredensial baru
    if p_user:
        test_login(p_user, p_pass)
    if a_user:
        test_login(a_user, a_pass)
    if ad_user:
        test_login(ad_user, ad_pass)

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()
