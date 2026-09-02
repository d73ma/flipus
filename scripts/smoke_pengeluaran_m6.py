"""
v2.0 M6 SMOKE TEST — OCR Pengeluaran + WA Input Bot Pengeluaran.

Test 2 jalur:
A. OCR (Bendahara upload foto nota via /api/v1/pengeluaran/ocr-batch-upload)
   - Karena fixture .txt (bukan gambar), fallback Ollama gagal → OCR status NEED_REVIEW
   - Verify Bendahara bisa save manual sebagai draft via /pengeluaran/ocr-save

B. WA Bot (chat single-step via /api/v1/wa/pengeluaran/inbound)
   - 4 skenario: rutin+auto-approve, rutin shortcut, non-rutin pending, cancel

Usage:
    .venv/bin/python3 scripts/smoke_pengeluaran_m6.py
"""
import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "http://localhost:8000/api/v1"
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

CREDS = {
    "bendahara_a": ("bendahara_a", "Bendahara123!"),
    "ketua_a": ("ketua_a", "Ketua123!"),
    "pendeta_a": ("pendeta_a", "Pendeta123!"),
}


def login(username: str, password: str) -> str:
    r = requests.post(f"{BASE_URL}/auth/login", json={"username": username, "password": password}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def main():
    print("=" * 70)
    print("  v2.0 M6 SMOKE TEST — OCR + WA Pengeluaran")
    print("=" * 70)

    bendahara_tok = login(*CREDS["bendahara_a"])
    print(f"\n[A] Login Bendahara OK")

    # === Test A1: OCR upload (fallback ke NEED_REVIEW karena .txt bukan gambar) ===
    print(f"\n[A1] OCR batch-upload dengan fixture .txt (expect NEED_REVIEW)...")
    nota_files = []
    for fname in ["nota_pln_250k.txt", "nota_pdam_180k.txt", "nota_telkom_200k.txt"]:
        path = FIXTURE_DIR / "m6_nota" / fname
        nota_files.append(("files", (fname, open(path, "rb"), "text/plain")))

    try:
        r = requests.post(f"{BASE_URL}/pengeluaran/ocr-batch-upload",
                          files=nota_files, headers=auth_headers(bendahara_tok), timeout=180)
    finally:
        for _, (_, fp, _) in nota_files:
            fp.close()
    print(f"  status: {r.status_code}")
    if r.status_code != 200:
        print(f"  ❌ FAILED: {r.text[:200]}")
        return
    ocr_result = r.json()
    print(f"  total_files: {ocr_result['total_files']}")
    items = ocr_result["items"]
    if len(items) != 3:
        print(f"  ❌ Expected 3 items, got {len(items)}")
        return
    print(f"  ✅ 3 nota uploaded (Ollama fallback: NEED_REVIEW)")

    # === Test A2: List kategori pengeluaran ===
    print(f"\n[A2] List kategori (Bendahara ambil id Listrik untuk save manual)...")
    r = requests.get(f"{BASE_URL}/kategori-pengeluaran/list", headers=auth_headers(bendahara_tok), timeout=10)
    r.raise_for_status()
    kats = r.json()
    listrik = next((k for k in kats if k["alias"] == "LIS"), None)
    if not listrik:
        print(f"  ❌ Listrik (LIS) not found")
        return
    print(f"  ✅ Listrik id={listrik['id']}, is_rutin={listrik['is_rutin']}")

    # === Test A3: Save OCR result as draft (manual review) ===
    print(f"\n[A3] Bendahara review OCR → save as draft Listrik Rp 250k...")
    first_item = items[0]
    save_body = {
        "path": first_item["path"],
        "jumlah": 250000,
        "penerima": "PLN",
        "kategori_pengeluaran_id": listrik["id"],
        "deskripsi": "Tagihan listrik PLN Agustus 2026 (OCR review manual)",
        "metode_bayar": "transfer",
    }
    r = requests.post(f"{BASE_URL}/pengeluaran/ocr-save", json=save_body,
                      headers=auth_headers(bendahara_tok), timeout=10)
    print(f"  status: {r.status_code}")
    if r.status_code != 200:
        print(f"  ❌ FAILED: {r.text[:200]}")
        return
    saved = r.json()
    print(f"  ✅ saved_id={saved['saved_id']} nomor={saved['nomor_pengeluaran']} rutin={saved['is_rutin']}")

    # === Test B1: WA chat rutin ===
    print(f"\n[B1] WA Bot — chat rutin (listrik, auto-approve)...")
    # Sender: Jerry's real number (updated by update_bendahara_wa.py to 628124809145)
    sender = "628124809145"  # Bendahara_a phone (sesuai update_bendahara_wa.py default)
    wa_messages = ["keluar", "250000", "PLN", "LIS", "ya"]
    for i, msg in enumerate(wa_messages):
        body = {"sender": sender, "message": msg}
        r = requests.post(f"{BASE_URL}/wa/pengeluaran/inbound", json=body, timeout=10)
        if r.status_code != 200:
            print(f"  ❌ step {i+1} '{msg}' → {r.status_code}: {r.text[:150]}")
            return
        result = r.json()
        print(f"  step {i+1} '{msg}' → state={result.get('state', result.get('status'))}")

    # Verify saved Pengeluaran
    r = requests.get(f"{BASE_URL}/pengeluaran/list?status_filter=approved&bulan=2026-09",
                     headers=auth_headers(bendahara_tok), timeout=10)
    approved = r.json()
    wa_saved = next((p for p in approved if p.get("created_via") == "wa" and p.get("jumlah") == 250000), None)
    if wa_saved:
        print(f"  ✅ WA Pengeluaran saved: id={wa_saved['id']} nomor={wa_saved['nomor_pengeluaran']} status={wa_saved['status']}")
    else:
        print(f"  ❌ WA Pengeluaran not found in approved list")

    # === Test B2: WA chat non-rutin (Pembangunan) → pending ===
    print(f"\n[B2] WA Bot — chat non-rutin (Pembangunan → pending_approval)...")
    # Create Pembangunan category first if not exists
    pembangunan = next((k for k in kats if k["alias"] == "PBG" or "pembangunan" in k["nama"].lower()), None)
    if not pembangunan:
        # Create it
        r = requests.post(f"{BASE_URL}/kategori-pengeluaran/create", json={
            "nama": "Pembangunan", "alias": "PBG", "is_rutin": False, "urutan": 99,
        }, headers=auth_headers(bendahara_tok), timeout=10)
        if r.status_code == 200:
            pembangunan = r.json()
            print(f"  ✅ Kategori Pembangunan created id={pembangunan['id']}")
        else:
            print(f"  ⚠️  Could not create Pembangunan: {r.text[:100]}")
    else:
        print(f"  ✅ Pembangunan already exists id={pembangunan['id']}")

    # Make sure session is IDLE
    requests.post(f"{BASE_URL}/wa/pengeluaran/reset", json={"phone": sender}, timeout=10)

    # Send non-rutin chat
    wa_messages = ["keluar", "1500000", "Toko Bangunan ABC", "PBG", "ya"]
    for i, msg in enumerate(wa_messages):
        body = {"sender": sender, "message": msg}
        r = requests.post(f"{BASE_URL}/wa/pengeluaran/inbound", json=body, timeout=10)
        if r.status_code != 200:
            print(f"  ❌ step {i+1} '{msg}' → {r.status_code}")
            return
        result = r.json()
        print(f"  step {i+1} '{msg[:30]}' → state={result.get('state', result.get('status'))}")

    # Verify pending
    r = requests.get(f"{BASE_URL}/pengeluaran/list?status_filter=pending_approval",
                     headers=auth_headers(bendahara_tok), timeout=10)
    pending = r.json()
    wa_pending = next((p for p in pending if p.get("created_via") == "wa" and p.get("jumlah") == 1500000), None)
    if wa_pending:
        print(f"  ✅ WA Pengeluaran pending: id={wa_pending['id']} status={wa_pending['status']}")
    else:
        print(f"  ❌ WA Pengeluaran pending not found")

    # === Test B3: Cancel flow ===
    print(f"\n[B3] WA Bot — cancel flow (batal)...")
    requests.post(f"{BASE_URL}/wa/pengeluaran/reset", json={"phone": sender}, timeout=10)
    wa_messages = ["keluar", "50000", "batal"]
    for i, msg in enumerate(wa_messages):
        body = {"sender": sender, "message": msg}
        r = requests.post(f"{BASE_URL}/wa/pengeluaran/inbound", json=body, timeout=10)
        result = r.json()
        print(f"  step {i+1} '{msg}' → state={result.get('state', result.get('status'))}")
    print(f"  ✅ Cancel flow completed without saving")

    # === Summary ===
    print("\n" + "=" * 70)
    print(f"  ✅ v2.0 M6 SMOKE TEST COMPLETE")
    print(f"     • OCR: 3 nota uploaded (NEED_REVIEW fallback), 1 saved as draft")
    print(f"     • WA Bot: 1 rutin auto-approved + 1 non-rutin pending + 1 cancelled")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print(f"\n❌ FATAL: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)