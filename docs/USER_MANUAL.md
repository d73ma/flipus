# FLIPUS v1.2 — User Manual

> Sistem Akuntansi Jemaat Otomatis — GMAHK Uni Konferens Indonesia Kawasan Timur (UKIKT)

---

## Daftar Isi

1. [Pengenalan](#1-pengenalan)
2. [Login & Logout](#2-login--logout)
3. [Panduan per Role](#3-panduan-per-role)
   - [Bendahara](#31-bendahara)
   - [Ketua Keuangan](#32-ketua-keuangan)
   - [Pendeta](#33-pendeta)
   - [Auditor Misi](#34-auditor-misi)
   - [Admin Uni](#35-admin-uni)
4. [Reset Password](#4-reset-password)
5. [Pendaftaran Akun Baru](#5-pendaftaran-akun-baru)
6. [Backup & Restore](#6-backup--restore)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Pengenalan

FLIPUS (**F**inancial **L**edger & **I**ntegrated **P**erpuluhan **U**mbrella **S**ystem) adalah sistem digital untuk mengelola perpuluhan dan persembahan jemaat GMAHK UKIKT. Sistem ini:

- ✅ **Otomatis** — Baca nominal amplop dari foto (OCR)
- ✅ **Aman** — Enkripsi PII, JWT auth, audit log lengkap
- ✅ **Terintegrasi** — WhatsApp ke Pendeta, mobil ke Auditor Misi
- ✅ **Offline-first** — SQLite untuk jemaat lokal

---

## 2. Login & Logout

### Login
1. Buka `http://localhost:5173/login`
2. Masukkan **username** dan **password** yang diberikan Admin
3. Klik **Login**

### Logout
Klik tombol **Logout** di pojok kanan atas.

### Lupa Password
1. Klik **Lupa password?** di halaman login
2. Masukkan username atau nomor WhatsApp
3. Password baru akan dikirim via WhatsApp

---

## 3. Panduan per Role

### 3.1 Bendahara

**Login sebagai:** `bendahara` / `Bendahara123!`

#### Upload Foto Amplop
1. Klik **Upload Foto Amplop** di pojok kanan atas Dashboard
2. Pilih 1 atau lebih foto amplop (JPG/PNG)
3. Klik **Jalankan OCR**
4. Tunggu proses selesai (~10-30 detik per foto)
5. **Review** nama & nominal per kuitansi (bisa edit)
6. Isi **nomor WhatsApp** pemberi (opsional, untuk auto-thanks)
7. Klik **Simpan ke Database**

#### Lihat Laporan Mingguan
1. Di Dashboard, masukkan **ID Rekap Mingguan** (mis. `FLIPUS-2026-DEMO-001`)
2. Klik **Cari**
3. Tabel akan menampilkan semua kuitansi pada minggu tersebut

#### Kirim Laporan ke Pendeta
1. Setelah报表 muncul, klik **Blast WA ke Pendeta**
2. Konfirmasi: **Ya, Kirim Sekarang**
3. Laporan PDF akan terkirim via WhatsApp Pendeta

#### Counter Sabat
- Pojok kanan atas menampilkan **Sabat ke-N, tanggal X** (auto-update harian)

---

### 3.2 Ketua Keuangan

**Login sebagai:** `ketua_keuang` / `Ketua123!`

#### Lihat Ringkasan Bulanan
1. Pilih **Bulan** (input type month)
2. Klik **Cari**
3. 4 card metrik akan tampil:
   - **Perpuluhan (X)** — total X jemaat
   - **Persembahan (PT)** — total PT
   - **Porsi Misi** — jatah Kantor Misi
   - **Porsi Jemaat** — kas jemaat
4. Tabel per minggu + Grand Total + Terbilang

---

### 3.3 Pendeta

**Login sebagai:** `pendeta` / `Pendeta123!`

#### Lihat Agregat Jemaat (Read-only)
- Dashboard menampilkan tabel perpuluhan per minggu
- Pilih bulan untuk filter
- Lihat Grand Total + Terbilang
- **Tidak bisa edit** — read-only view

---

### 3.4 Auditor Misi

**Login sebagai:** `auditor_misi` / `AuditMisi123!`

#### Lihat Agregat Semua Jemaat di Misi
1. Pilih bulan
2. Lihat total + per-jemaat breakdown
3. Tab **Daftar Jemaat di Misi Ini** — list jemaat + kontak

#### Nonaktifkan Jemaat
1. Di card jemaat, klik **Nonaktifkan**
2. Akun jemaat tidak bisa login (data tetap ada untuk audit)

---

### 3.5 Admin Uni

**Login sebagai:** `admin_uni` / `AdminUni123!` (Jerry-only)

#### Lihat Agregat Semua Misi di Uni
1. Pilih bulan
2. Lihat total Uni + per-misi breakdown
3. Metric cards + tabel per minggu

#### Backup Database
1. Klik **Backup Binary** (cepat, .db) atau **Backup SQL** (portable, .sql)
2. File tersimpan di `storage/backups/`
3. Auto-cleanup: simpan 7 backup terakhir

#### Restore Database
1. Pilih file backup dari list
2. Klik **Restore**
3. Auto-backup dulu sebelum restore
4. **Catatan:** User harus login ulang setelah restore

#### Lihat Audit Log
1. Filter by **action** (e.g., "BLAST", "REGISTER", "RESTORE")
2. Pagination: 50 logs per page
3. Color-coded by action type

---

## 4. Reset Password

1. Buka `/forgot-password`
2. Masukkan username atau nomor WA
3. Password baru akan dikirim via WhatsApp dalam beberapa detik
4. Login dengan password baru

> ⚠️ Rate limit: 1 request / 5 menit per user

---

## 5. Pendaftaran Akun Baru

Sistem ini mendukung **self-service registrasi** untuk role struktural:

### Daftar Pendeta / Jemaat
1. Buka `/register`
2. Pilih **Pendeta**
3. Isi form (Uni, Misi, nama jemaat, dll)
4. Submit → kredensial muncul di success page
5. Screenshot/save kredensial (muncul sekali!)
6. Login

### Daftar Auditor Misi
1. Pilih **Auditor Misi**
2. Isi form + tentukan persentase (default 100% X, 50% PT)

### Daftar Admin Uni
1. Pilih **Admin Uni**
2. Isi form + persentase (default 0%)

> Admin Uni khusus Jerry (super-user)

---

## 6. Backup & Restore

### Auto-Backup
- Sistem auto-backup database **setiap hari jam 02:00 UTC** (= 10:00 WITA)
- Disimpan di `storage/backups/`
- Retention: 7 file terakhir (older auto-deleted)

### Manual Backup
1. Login sebagai **Admin Uni**
2. Pilih **Backup Binary** atau **Backup SQL**
3. File akan muncul di list

### Restore
1. Pilih file backup
2. Klik **Restore**
3. Konfirmasi
4. Sistem auto-backup db sekarang sebelum restore
5. **Semua user harus login ulang** setelah restore

### Manual Backup (CLI)
```bash
# Backup SQLite manually
cd /Users/jerrymauri/Flipus
cp flipus_local.db storage/backups/flipus_manual_$(date +%Y%m%d).db
```

---

## 7. Troubleshooting

### Login gagal
- ✅ Pastikan username/password benar
- ✅ Coba **Lupa Password** untuk reset
- ✅ Cek JWT expiry (default 8 jam)

### OCR tidak akurat
- ✅ Foto harus jelas, tidak blur
- ✅ Tulisan nominal visible
- ✅ Hindari foto miring

### WA Blast tidak terkirim
- ✅ Cek `FONNTE_TOKEN` di `.env`
- ✅ Cek nomor WA Pendeta (bisa diupdate via Admin)
- ✅ Cek log Fonnte

### Database error
- ✅ Restore dari backup terbaru
- ✅ Cek storage/backups/ untuk list file

### 403 License invalid
- ✅ Tenant signature corrupt
- ✅ Hubungi Jerry untuk re-issue license

---

## Kontak Support

**Jerry Mauri** — Admin Uni FLIPUS
- WhatsApp: 6285750113010
- Email: support@flipus.local

---

*FLIPUS v1.2 — UKIKT 2026*