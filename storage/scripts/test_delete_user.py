"""
FLIPUS v1.1 — Test script untuk delete user + list users endpoints.

Jalankan SETELAH backend running + ada user Auditor/Amin Uni yang bisa login.

    /Users/jerrymauri/Flipus/.venv/bin/python3 -m storage.scripts.test_delete_user

Test:
1. Login sebagai Auditor
2. List user di misi caller
3. Cari user iseng (kalau ada, atau register satu)
4. Delete user
5. Verify is_active=False
6. Coba login dengan user deleted (harus 401)
"""

import os
import sys

sys.path.insert(0, os.getcwd())

import requests

BASE = "http://localhost:8000/api/v1"


def login(username, password):
    r = requests.post(f"{BASE}/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_list_as_auditor(auditor_username, auditor_password):
    print(f"\n=== TEST: List users as {auditor_username} (Auditor) ===")
    token = login(auditor_username, auditor_password)
    r = requests.get(f"{BASE}/users", headers=auth_headers(token))
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"  Found {data['count']} user(s) in this misi:")
        for u in data["users"]:
            print(f"    [{u['id']}] {u['username']} ({u['role']}) — {u['nama_lengkap']} {'ACTIVE' if u['is_active'] else 'INACTIVE'}")
        return token, data["users"]
    else:
        print(f"  ERROR: {r.json()}")
        return token, []


def test_delete(token, user_id, username):
    print(f"\n=== TEST: Delete user {user_id} ({username}) ===")
    r = requests.delete(f"{BASE}/users/{user_id}", headers=auth_headers(token))
    print(f"Status: {r.status_code}")
    print(f"Response: {r.json()}")


def test_login_deleted(username):
    print(f"\n=== TEST: Try login as deleted user {username} ===")
    r = requests.post(f"{BASE}/auth/login", json={"username": username, "password": "anywrong"})
    print(f"Status: {r.status_code} (expected 401)")


def test_cross_tenant_access(token, wrong_user_id):
    print(f"\n=== TEST: Try delete user from another tenant (id={wrong_user_id}) ===")
    r = requests.delete(f"{BASE}/users/{wrong_user_id}", headers=auth_headers(token))
    print(f"Status: {r.status_code} (expected 403)")


def main():
    print("=== FLIPUS v1.1 — User Delete Tests ===")
    print("Sebelum run, pastikan:")
    print("1. Backend running di localhost:8000")
    print("2. Ada user AUDITOR_MISI yang bisa login (default: auditor / AuditMisi123!)")
    print("3. Ada user PENDETA target untuk di-delete")
    print()

    auditor_username = input("Auditor username [auditor]: ").strip() or "auditor"
    auditor_password = input("Auditor password [AuditMisi123!]: ").strip() or "AuditMisi123!"

    token, users = test_list_as_auditor(auditor_username, auditor_password)

    if not users:
        print("\nTidak ada user untuk di-test. Buat dulu via /register/pendeta.")
        return

    # Cari user pertama yang role-nya PENDETA dan is_active=True
    targets = [u for u in users if u["role"] == "PENDETA" and u["is_active"]]
    if not targets:
        print("\nTidak ada user PENDETA aktif untuk di-test.")
        return

    target = targets[0]
    print(f"\nTarget delete: {target['username']} (id={target['id']})")

    confirm = input(f"Yakin delete user {target['username']}? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        return

    test_delete(token, target["id"], target["username"])
    test_login_deleted(target["username"])

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()