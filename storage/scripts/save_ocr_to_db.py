"""Tahap #5: Save OCR result ke DB."""

import os

import sys

from datetime import datetime

sys.path.insert(0, os.getcwd())

from app.core.database import SessionLocal, Base, engine

from app.models.transaction import Kuitansi

from app.ai_engine.cloud_parser import validate_with_gemini

from app.core.security import encrypt_pii

from app.utils.number_to_words import terbilang

Base.metadata.create_all(bind=engine)

db = SessionLocal()

foto_dir = "/Users/jerrymauri/Flipus/storage/temp/"

fotos = [os.path.join(foto_dir, f) for f in os.listdir(foto_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]

print("Found photos:", fotos)

if not fotos:

    print("Tidak ada foto di storage/temp/")

    sys.exit(0)

img = fotos[0]

print("Processing:", img)

res = validate_with_gemini({}, img)

ocr = res.get("ocr", {}) if isinstance(res, dict) else {}

nama = ocr.get("nama", "Tidak Terbaca")

x_val = int(ocr.get("perpuluhan_X_angka") or 0)

pt_val = int(ocr.get("PT_angka") or 0)

total = x_val + pt_val

porsi_misi = x_val + (pt_val // 2)

porsi_jemaat = pt_val // 2

if pt_val % 2 == 1:

    porsi_jemaat += 1

today = datetime.utcnow().strftime("%Y%m%d")

nomor_kuitansi = f"KPT-{today}-{int(datetime.utcnow().timestamp())}"

id_rekap = f"RK-{today}"

k = Kuitansi(

    tenant_id=2,

    id_rekap_mingguan=id_rekap,

    nomor_kuitansi=nomor_kuitansi,

    tanggal_sabat=datetime.utcnow().strftime("%Y-%m-%d"),

    nama_umat_encrypted=encrypt_pii(nama),

    nomor_whatsapp_encrypted=encrypt_pii("081234567890"),

    foto_amplop_path=img,

    perpuluhan_x_angka=x_val,

    pt_angka=pt_val,

    total_pemberian_angka=total,

    total_pemberian_huruf=terbilang(total),

    porsi_kantor_misi=porsi_misi,

    porsi_kas_jemaat=porsi_jemaat,

)

db.add(k)

db.commit()

db.refresh(k)

print(f"SAVED kuitansi ID={k.id}")

print(f"nomor: {nomor_kuitansi}")

print(f"nama: {nama} | X: {x_val} | PT: {pt_val} | total: {total}")

print(f"porsi_misi: {porsi_misi} | porsi_jemaat: {porsi_jemaat}")

db.close()

print("DONE")