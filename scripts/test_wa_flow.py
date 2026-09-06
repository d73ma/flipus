"""
T112 test (2026-08-26): Simulasi full state machine WA Input Bot via curl-like calls.
Jerry bisa pakai ini untuk verify backend tanpa harus kirim WA asli dari HP.

Jalankan step by step, masing-masing 2-3 detik jeda (untuk simulasi sender typing).
Sender harus match dengan nomor_whatsapp user BENDAHARA di tenant target.

Usage:
    cd /Users/jerrymauri/Flipus
    .venv/bin/python3 scripts/test_wa_flow.py

Default: sender=628124809145 (nomor asli Jerry, = bendahara_a Jemaat Nataan Ratahan)
        X=500000, PT=100000, KH=0, nama='Budi Santoso'
Override sender lewat env var, contoh:
    SENDER=628123450001 .venv/bin/python3 scripts/test_wa_flow.py   # bendahara_b
"""
import os
import time

import requests

BACKEND = os.environ.get("BACKEND", "http://localhost:8000")
SENDER = os.environ.get("SENDER", "628124809145")  # match dengan bendahara_a (Jemaat Nataan Ratahan) - nomor Jerry


def post_inbound(message: str, button_id: str | None = None) -> dict:
    """Simulate Fonnte inbound webhook POST."""
    data = {
        "sender": SENDER,
        "message": message,
        "device": "FLIPUS-DEMO",
    }
    if button_id:
        data["button_id"] = button_id
    r = requests.post(f"{BACKEND}/api/v1/wa/inbound", data=data, timeout=10)
    r.raise_for_status()
    return r.json()


def main():
    print("=== Simulasi WA Input Bot ===")
    print(f"Sender: {SENDER}")
    print(f"Backend: {BACKEND}\n")

    # Step 1: Kirim "Input" → dapat menu
    print(">>> Step 1: Kirim 'Input' (atau tap tombol)")
    r = post_inbound("Input")
    print(f"<<< {r}\n")
    time.sleep(1)

    # Step 2: Kirim nominal X (bisa langsung numeric atau pakai shortcut)
    print(">>> Step 2: Kirim nominal X = 500000")
    r = post_inbound("500000")
    print(f"<<< {r}\n")
    time.sleep(1)

    # Step 3: Kirim nominal PT
    print(">>> Step 3: Kirim nominal PT = 100000")
    r = post_inbound("100000")
    print(f"<<< {r}\n")
    time.sleep(1)

    # Step 4: Kirim nominal KH (atau 'Lewati')
    print(">>> Step 4: Kirim 'Lewati' untuk skip KH")
    r = post_inbound("Lewati", button_id="btn_lewati")
    print(f"<<< {r}\n")
    time.sleep(1)

    # Step 5: Kirim nama pemberi
    print(">>> Step 5: Kirim nama 'Budi Santoso'")
    r = post_inbound("Budi Santoso")
    print(f"<<< {r}\n")
    time.sleep(1)

    # Step 6: Tap Simpan
    print(">>> Step 6: Tap tombol 'Simpan'")
    r = post_inbound("Simpan", button_id="btn_simpan")
    print(f"<<< {r}\n")

    print("\n=== Verifikasi di DB ===")
    print("Login sebagai Bendahara → cek tabel '📥 Dari WA — Item Staging'")
    print("Row baru dengan nama_pemberi='Budi Santoso', tanggal_sabat=2026-08-22")
    print("Lalu klik 'Simpan yang Dipilih' untuk finalize → row masuk kuitansi final.")


if __name__ == "__main__":
    main()
