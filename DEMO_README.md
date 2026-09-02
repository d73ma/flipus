# FLIPUS v1.3 — Panduan Demo Multi-Role

Dokumen ini untuk Jerry dan tim demo agar bisa trial-and-error dengan simulasi multi-role dan multi-tenant.

## Prasyarat

- Backend jalan: `cd /Users/jerrymauri/Flipus && .venv/bin/uvicorn app.main:app --reload --port 8000`
- Frontend jalan: `cd /Users/jerrymauri/Flipus/frontend && npm run dev` (default di `http://localhost:5173`)
- Database sudah di-seed: jalankan `.venv/bin/python3 scripts/seed_demo.py`

## Akun Demo (8 user, 2 jemaat, 2 misi)

| Username | Password | Role | Tenant |
|---|---|---|---|
| `bendahara_a` | `Bendahara123!` | Bendahara | Jemaat Nataan Ratahan |
| `ketua_a` | `Ketua123!` | Ketua Keuangan | Jemaat Nataan Ratahan |
| `pendeta_a` | `Pendeta123!` | Pendeta | Jemaat Nataan Ratahan |
| `bendahara_b` | `Bendahara123!` | Bendahara | Jemaat Sentrum Minahasa |
| `ketua_b` | `Ketua123!` | Ketua Keuangan | Jemaat Sentrum Minahasa |
| `pendeta_b` | `Pendeta123!` | Pendeta | Jemaat Sentrum Minahasa |
| `auditor_misi` | `AuditMisi123!` | Auditor Misi | DK Minahasa (lihat aggregate 2 jemaat) |
| `admin_uni` | `AdminUni123!` | Admin Uni | GMAHK UKIKT (lihat aggregate semua jemaat) |

## Cara Login Multi-Akun di Satu Laptop

Pakai browser Chrome / Safari + beberapa tab **incognito** (agar session/login tidak bentrok):

1. **Tab 1 (normal)**: login sebagai `bendahara_a` → lakukan input kuitansi
2. **Tab 2 (incognito)**: login sebagai `ketua_a` → approve kuitansi yang diinput tab 1
3. **Tab 3 (incognito)**: login sebagai `auditor_misi` → lihat aggregate 2 jemaat

Setiap tab punya session/token sendiri — tidak saling interfere.

> Tips: kalau pakai Firefox, dia punya "Container Tabs" yang lebih elegan. Tapi incognito cukup.

## Alur Demo per Role

### 1. Bendahara (`bendahara_a` atau `bendahara_b`)

Login → masuk ke **Dashboard Bendahara**.

Yang bisa dilakukan:
- **Upload & Review Foto Amplop** (menu OCR) → upload foto, OCR otomatis, edit manual X/PT/Khusus, simpan sebagai **draft**
- **Lihat Daftar Kuitansi** → filter status `draft` / `finalized` / `rejected`
- **Lihat Sabat Info** → cek apakah ada amplop yang sudah discan untuk minggu ini
- **Notifikasi** (bell icon) → cek apa ada approval yang ditolak atau alert

Yang **tidak** bisa:
- Approve kuitansi sendiri (harus Ketua)
- Lihat jemaat lain (cuma jemaat sendiri)

### 2. Ketua Keuangan (`ketua_a` atau `ketua_b`)

Login → masuk ke **Dashboard Ketua**.

Yang bisa dilakukan:
- **Approval Queue** → lihat daftar kuitansi `draft` dari jemaat sendiri
- Klik **Approve** → status jadi `finalized`, kuitansi resmi
- Klik **Reject** + alasan → status jadi `rejected`, Bendahara bisa revisi
- **Agregat Jemaat** → lihat total X, PT, Khusus minggu/bulan ini

### 3. Pendeta (`pendeta_a` atau `pendeta_b`)

Login → masuk ke **Dashboard Pendeta**.

Yang bisa dilakukan:
- **Agregat Jemaat** → ringkasan persembahan jemaat sendiri
- **Trend Mingguan** → grafik persembahan 12 minggu terakhir
- **Audit trail** → siapa input apa, kapan

Pendeta di FLIPUS adalah role **view + spiritual oversight**, bukan operator.

### 4. Auditor Misi (`auditor_misi`)

Login → masuk ke **Dashboard Auditor**.

Yang bisa dilakukan:
- **Pilih Misi** (DK.MIN) → lihat aggregate **2 jemaat** sekaligus
- **Compare Jemaat** → side-by-side stats
- **Export CSV/Excel** → download data untuk analisis offline
- **Lihat Audit Log** → transparansi transaksi
- **Set Persentase Pembagian** → config berapa % X/PT/Khusus yang dikirim ke Misi

Yang **penting**: auditor bisa lihat data **2 jemaat** (Nataan + Sentrum) walaupun tidak login di jemaat itu.

### 5. Admin Uni (`admin_uni`)

Login → masuk ke **Dashboard Admin Uni**.

Yang bisa dilakukan:
- **Pilih Jemaat** (dropdown di navbar) → lihat dashboard aggregate jemaat itu
- **Tenant Management** → list, edit, suspend, plan change
- **Branding** → upload logo, set warna primary/secondary
- **Lihat Audit Log** semua jemaat di uni

Admin Uni adalah **super-user** untuk scope GMAHK UKIKT.

## Skenario Demo Multi-Tenant

**Skenario 1: RBAC isolasi**
1. Login sebagai `bendahara_a` → coba buka `/bendahara/kuitansi/search?nama=test`
2. Login sebagai `auditor_misi` → buka halaman yang sama
3. Auditor lihat **lebih banyak data** (2 jemaat), Bendahara cuma 1

**Skenario 2: Approval workflow**
1. Login sebagai `bendahara_a` → input kuitansi via OCR (status: draft)
2. Logout, login sebagai `ketua_a` → approve kuitansi tsb (status: finalized)
3. Login sebagai `admin_uni` → Dashboard Admin Uni → jemaat A → lihat total persembahan minggu ini sudah include kuitansi tsb

**Skenario 3: Branding customization**
1. Login sebagai `admin_uni` → Tenant Management → pilih Jemaat B → Branding
2. Ubah primary color → simpan
3. Login sebagai `bendahara_b` → lihat header Dashboard → warna header berubah sesuai branding Jemaat B
4. Login sebagai `bendahara_a` → warna header tetap default (atau warna Jemaat A) → **terbukti branding terisolasi per tenant**

**Skenario 4: Notifikasi real-time**
1. Login `bendahara_a` (Tab 1) + `ketua_a` (Tab 2 incognito)
2. Bendahara input kuitansi draft
3. Ketua langsung lihat **bell icon** muncul notifikasi "Kuitansi baru menunggu approval"
4. Ketua approve
5. Bendahara lihat notifikasi "Kuitansi Anda sudah disetujui"

## Cara Reset DB kalau Kacau

Kalau saat demo ada yang sengaja iseng/jail (hapus user, ubah password, dll):

```bash
cd /Users/jerrymauri/Flipus
# Stop uvicorn (Ctrl+C)
rm -f flipus_local.db
.venv/bin/python3 scripts/seed_demo.py
# Start uvicorn lagi
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Semua kembali ke kondisi awal. Tidak ada yang terhapus dari DB backup `flipus_local.db.bak.YYYYMMDD_HHMMSS`.

## Yang Bisa Diakses dari Laptop Lain?

**Tidak bisa langsung** — `localhost:5173` dan `localhost:8000` adalah loopback ke mesin Jerry.

Kalau mau demo di laptop teman (via jaringan lokal):

```bash
# Backend di laptop Jerry — ubah host binding
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Cek IP laptop Jerry
ipconfig getifaddr en0   # di Mac

# Di laptop teman, buka:
# http://[IP-JERRY]:5173    (kalau Vite juga di --host 0.0.0.0)
# http://[IP-JERRY]:8000    (API)
```

Tapi untuk trial-and-error internal, **1 laptop + multi-tab incognito** sudah cukup.

## Pertanyaan Umum

**Q: Kenapa tidak ada tombol "Daftar" yang berfungsi?**
A: Endpoint `/register/pendeta` memang untuk jemaat baru. Untuk testing, langsung login pakai akun demo. Register hanya dipakai jemaat baru production nanti.

**Q: Apakah field edit X/PT/Khusus muncul di halaman OCR?**
A: Ya, tapi **setelah OCR selesai**. Klik "Jalankan OCR" dulu, baru section "2. Review & Edit" muncul dengan form editable.

**Q: Kenapa dropdown Misi kosong di form register?**
A: Karena harus pilih Uni dulu. Dropdown Misi auto-populate setelah Uni dipilih.

**Q: Bisa setup 2FA?**
A: Bisa, tapi opsional. Username demo default `is_2fa_enabled=False`. Untuk aktifkan: login → Settings → 2FA Setup → scan QR → confirm.

**Q: Audit log bisa dilihat siapa?**
A: Auditor Misi dan Admin Uni bisa. Bendahara/Ketua/Pendeta hanya lihat audit log jemaat sendiri (di menu Notification / Settings).

## Kontak

Kalau ada bug atau behaviour aneh saat demo, screenshot error + paste output terminal backend ke saya.