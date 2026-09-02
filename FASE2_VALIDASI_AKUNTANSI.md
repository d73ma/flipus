# FASE 2 — Validasi Logika Akuntansi & Laporan Keuangan

> **Status**: RENCANA (menunggu persetujuan "SETUJU" sebelum eksekusi)
> **Branch**: `audit/comprehensive-review`
> **Tanggal**: 2026-09-02
> **Auditor**: Roo (Claude Opus 5)
> **Scope**: Validasi seluruh flow distribusi perpuluhan, persembahan khusus, pengeluaran, dan laporan gabungan (kuitansi + pengeluaran) untuk memastikan integritas akuntansi GMAHK sesuai doktrin Advent (Tithe 100% ke Misi) dan struktur 3-tier (Uni → Misi → Jemaat).

---

## 1. Ringkasan Eksekutif

Setelah menelusuri seluruh codebase terkait kalkulator porsi, alur kuitansi/pengeluaran, dan generator PDF, ditemukan:

- **2 bug matematika kritis** yang merusak integritas laporan (TOTAL ≠ penjumlahan kolom).
- **1 inkonsistensi rounding** (truncate vs round) yang menyebabkan selisih 1 rupiah berulang.
- **2 calculator hidup berdampingan**: Jerry Model B (`porsi_calculator.py`) yang dipakai produksi, dan legacy (`financial_calculator.py`) yang masih dipakai oleh 3 call site termasuk `admin.py:recompute-porsi`.
- **1 live-vs-stored drift**: agregat re-compute live dari `PersentaseConfig`, sedangkan dashboard/PDF pakai field tersimpan → perubahan konfigurasi persen tidak konsisten di semua laporan.
- **2 gap data model**: kolom `porsi_x_uni`/`porsi_pt_uni` tidak disimpan di tabel Kuitansi (harus dihitung ulang setiap kali), pivot `KuitansiKategori` v2.0 tidak punya kolom porsi.

**Dampak**: Jika tidak diperbaiki, laporan bulanan ke Uni tidak akan balance, audit BPK bisa gagal, dan setiap perubahan persentase akan memerlukan recompute massal manual.

**Prinsip Perbaikan**:
1. **Single source of truth** untuk porsi: pakai Jerry Model B (`compute_porsi`) di seluruh call site.
2. **Stored snapshot + live recompute** untuk auditability (simpan snapshot saat kuitansi dibuat, tapi sediakan tombol "recompute" yang pakai config terkini).
3. **No silent fix**: setiap perbaikan disertai data migration + laporan diff sebelum/sesudah untuk audit trail.

---

## 2. Inventaris Komponen yang Diaudit

### 2.1 Dua Kalkulator Porsi

| File | Fungsi | Formula | Status | Dipakai Oleh |
|------|--------|---------|--------|--------------|
| [`porsi_calculator.py`](app/utils/porsi_calculator.py) | `compute_porsi(x, pt, kh, pct_x_jemaat, pct_pt_jemaat, pct_khusus_jemaat, pct_x_uni, pct_pt_uni, pct_khusus_uni)` | Jerry Model B: pct_uni diterapkan ke TOTAL (x, pt, kh), bukan ke porsi_misi. `pj = int(round(x * pct_jemaat))`, `pu = int(round(x * pct_uni))`, `pm = max(0, x - pj - pu)` | ✅ **PRODUKSI** | `quick_input.py:300`, `scanner.py:257`, `wa_input.py:671`, `agregat.py:848,949` |
| [`financial_calculator.py`](app/services/financial_calculator.py) | `calculate_distribution(perpuluhan_x, pt, khusus, pct_x_jemaat, pct_pt_jemaat, pct_khusus_jemaat, pct_x_uni, pct_pt_uni, pct_khusus_uni)` | Layer 1: `porsi_x_misi = int(x * pct_x_jemaat)`. Layer 2: `porsi_x_uni = int(porsi_x_misi * pct_x_uni)`. Potongan Uni dari porsi_misi, bukan dari total. | ⚠️ **LEGACY** | `admin.py:28` (recompute_porsi), `batch_processor.py` (OCR), `seed_demo_full.py:40` |

### 2.2 Konfigurasi Persentase

| Scope | Tabel | Field | Nilai Default (Seed) | Catatan |
|-------|-------|-------|---------------------|---------|
| Jemaat | `persentase_config` | `pct_x_jemaat`, `pct_pt_jemaat`, `pct_khusus_jemaat` | 0.0, 0.5, 0.0 | **T101 fix**: pct_x_jemaat dulu 1.0 → dikoreksi ke 0.0 (doktrin Advent: 100% X ke Misi) |
| Uni | `persentase_config` | `pct_x_uni`, `pct_pt_uni`, `pct_khusus_uni` | 0.5, 0.0, 0.0 | Potongan Uni hanya dari X (50%), PT & KH tidak dipotong Uni |
| Misi/Konferens | (derived) | – | – | Menerima sisa: `porsi_misi = total - porsi_jemaat - porsi_uni` |

### 2.3 Alur Pembuatan Kuitansi

```
User input (x, pt, kh)
    ↓
quick_input.py / scanner.py / wa_input.py
    ↓
compute_porsi(x, pt, kh, pct_jemaat, pct_uni)  ← Jerry Model B
    ↓
returns {pj_x, pj_pt, pj_kh, pu_x, pu_pt, pu_kh, pm_x, pm_pt, pm_kh}
    ↓
Kuitansi record disimpan:
  porsi_kantor_misi = pm_x + pm_pt
  porsi_kas_jemaat = pj_pt + pj_kh
  porsi_khusus_misi = pm_kh
  porsi_khusus_jemaat = pj_kh
    ↓
Laporan dashboard/PDF baca dari field tersimpan
```

**⚠️ Penyimpangan terdeteksi** di [`dashboard.py:188`](app/api/v1/dashboard.py:188) — lihat Bagian 3.

### 2.4 Alur Persetujuan

| Entitas | Status Flow | Approver |
|---------|-------------|----------|
| Kuitansi | `draft` → `finalized` | BENDAHARA → KETUA_KEUANGAN |
| Pengeluaran | `draft` → `pending_approval` → `approved_ketua` → `approved` (atau `rejected`) | BENDAHARA → KETUA → PENDETA |

---

## 3. Temuan Kritis (Critical Findings)

### 🔴 C-1: Math Bug di [`dashboard.py:188-189`](app/api/v1/dashboard.py:188)

**Lokasi**: Fungsi `create_kuitansi` di `app/api/v1/dashboard.py`.

**Bug**:
```python
# Lines 182-189 (current)
porsi_x_misi = int(total_x * pct["pct_x_jemaat"])      # OK
porsi_pt_misi = int(total_pt * pct["pct_pt_jemaat"])    # OK
porsi_pt_jemaat = total_pt - porsi_pt_misi              # OK
porsi_khusus_misi = int(total_khusus * pct["pct_khusus_jemaat"])  # OK
porsi_khusus_jemaat = total_khusus - porsi_khusus_misi  # OK

porsi_kantor_misi = porsi_x_misi + porsi_pt_misi        # ❌ BUG: missing porsi_khusus_misi!
porsi_kas_jemaat = porsi_pt_jemaat + porsi_khusus_jemaat  # ❌ BUG: missing porsi_x_jemaat!
```

**Dampak**:
- `porsi_kantor_misi` **tidak termasuk** porsi khusus yang ke misi → under-reporting ke Misi sebesar `porsi_khusus_misi`.
- `porsi_kas_jemaat` **tidak termasuk** porsi X jemaat (meskipun pct_x_jemaat=0.0 saat ini, ini tetap salah secara struktural).
- Setiap kuitansi yang dibuat via dashboard akan menyimpan nilai `porsi_kantor_misi` dan `porsi_kas_jemaat` yang salah.

**Severity**: 🔴 **CRITICAL** — merusak laporan agregat Uni.

**Verifikasi**: Lihat juga [`scanner.py:257`](app/api/v1/scanner.py:257), [`wa_input.py:671`](app/api/v1/wa_input.py:671), [`quick_input.py:300`](app/api/v1/quick_input.py:300) — semua pakai `compute_porsi` Jerry Model B yang **benar** (`pj = int(round(...))`, dst). Dashboard adalah satu-satunya outlier.

---

### 🔴 C-2: Math Bug di [`pdf_gabungan.py:123`](app/services/pdf_gabungan.py:123)

**Lokasi**: `generate_laporan_gabungan` di `app/services/pdf_gabungan.py`.

**Bug**:
```python
# Lines 100-130 (current)
sum_x = sum_pt = sum_khusus = sum_misi = sum_jemaat = 0
# ... loop accumulates sum_x, sum_pt, sum_khusus, sum_misi, sum_jemaat ...

total_penerimaan = sum_x + sum_pt  # ❌ BUG: missing sum_khusus!
data_k.append([
    "", "TOTAL",
    f"{sum_x:,}", f"{sum_pt:,}", f"{sum_khusus:,}",   # khusus shown in column 4
    f"{total_penerimaan:,}",                            # but excluded from total!
    f"{sum_misi:,}", f"{sum_jemaat:,}",
])
```

**Dampak**: PDF laporan gabungan menampilkan **khusus** di kolom terpisah, tapi **tidak dijumlahkan** ke "Total Penerimaan". Hasil: Total ≠ penjumlahan kolom visual → auditor akan menemukan discrepancy.

**Severity**: 🔴 **CRITICAL** — laporan resmi ke Uni tidak balance.

---

### 🟠 C-3: Rounding Inconsistency (`int()` truncate vs `int(round())`)

**Lokasi**: [`dashboard.py:182-186`](app/api/v1/dashboard.py:182).

**Bug**:
```python
porsi_x_misi = int(total_x * pct["pct_x_jemaat"])      # truncate (floor)
porsi_pt_misi = int(total_pt * pct["pct_pt_jemaat"])    # truncate (floor)
porsi_khusus_misi = int(total_khusus * pct["pct_khusus_jemaat"])  # truncate
```

Jerry Model B di [`porsi_calculator.py`](app/utils/porsi_calculator.py) pakai `int(round(...))` (banker's rounding ke nearest integer). Dashboard pakai `int(...)` (truncate, floor untuk bilangan positif).

**Dampak**: Selisih **±1 rupiah** per kuitansi → bisa menumpuk jadi selisih besar di laporan gabungan per triwulan.

**Severity**: 🟠 **HIGH** — silent data drift, sulit dideteksi manual.

---

### 🟠 C-4: Legacy Calculator Masih Dipakai di `admin.py:recompute-porsi`

**Lokasi**: [`app/api/v1/admin.py:347-451`](app/api/v1/admin.py:347).

**Bug**:
```python
from app.services.financial_calculator import calculate_distribution
# ...
def recompute_porsi(...):
    result = calculate_distribution(  # ⚠️ LEGACY!
        perpuluhan_x=...,
        pt=...,
        khusus=...,
        pct_x_jemaat=...,
        pct_pt_jemaat=...,
        pct_khusus_jemaat=...,
        pct_x_uni=...,
        pct_pt_uni=...,
        pct_khusus_uni=...,
    )
```

**Dampak**: Jika admin menjalankan endpoint `POST /admin/recompute-porsi`, semua Kuitansi akan di-recompute dengan formula **legacy (Layer 1+2)** yang **berbeda** dari Jerry Model B. Hasilnya: data historis akan "loncat" nilainya tanpa jejak audit yang jelas.

**Severity**: 🟠 **HIGH** — risiko inkonsistensi data massal.

---

### 🟡 C-5: Live vs Stored Drift

**Lokasi**: [`agregat.py:848,949`](app/api/v1/agregat.py:848) vs [`dashboard.py`](app/api/v1/dashboard.py).

**Bug**:
- `agregat.py` re-compute porsi **live** dari `PersentaseConfig` terkini setiap kali endpoint dipanggil.
- `dashboard.py` dan `pdf_gabungan.py` pakai field **tersimpan** di Kuitansi (yang dihitung saat create, lalu disimpan).

**Dampak**: Jika `PersentaseConfig` diubah (mis. pct_x_uni dari 0.5 → 0.6), maka:
- Laporan agregat di `/agregat` akan langsung reflects nilai baru (live).
- Laporan dashboard di `/dashboard` dan PDF gabungan akan tetap pakai nilai lama (stored) sampai tombol "recompute" ditekan.

Severity: 🟡 **MEDIUM** — bisa diperbaiki dengan strategi "stored snapshot + recompute button" yang eksplisit.

---

### 🟡 C-6: Data Model Gap — Kolom `porsi_x_uni`/`porsi_pt_uni` Tidak Disimpan

**Lokasi**: [`app/models/transaction.py`](app/models/transaction.py) (model Kuitansi).

**Issue**: Tabel `kuitansi` punya field `porsi_kantor_misi`, `porsi_kas_jemaat`, `porsi_khusus_misi`, `porsi_khusus_jemaat`, tapi **tidak ada** field `porsi_x_uni`, `porsi_pt_uni`, `porsi_khusus_uni`. Padahal `compute_porsi` mengembalikan ketiganya (`pu_x`, `pu_pt`, `pu_kh`).

**Dampak**: Share Uni (potongan 50% dari X) saat ini hanya bisa dilihat dari re-compute live, tidak bisa diaudit dari data historis.

Severity: 🟡 **MEDIUM** — auditability gap.

---

### 🟡 C-7: `KuitansiKategori` Pivot v2.0 Tidak Punya Kolom Porsi

**Lokasi**: [`app/models/transaction.py`](app/models/transaction.py) (model `KuitansiKategori`).

**Issue**: Pivot v2.0 untuk Kuitansi → Kategori hanya punya `nominal`, tidak ada `porsi_x_jemaat`, `porsi_pt_jemaat`, dll per kategori. Padahal Jerry Model B mengembalikan porsi **global** (untuk seluruh kuitansi), bukan per kategori.

**Dampak**: Jika kategori berbeda punya persentase berbeda (mis. "Persembahan Pembangunan" vs "Perpuluhan"), porsi per kategori tidak bisa disimpan.

Severity: 🟡 **MEDIUM** — fitur belum lengkap, mungkin deferred.

---

## 4. Pemetaan Bug → Rekomendasi Perbaikan

| ID | Bug | Rekomendasi | Prioritas | Risiko |
|----|-----|-------------|-----------|--------|
| C-1 | dashboard.py math (khusus hilang) | Refactor pakai `compute_porsi` (Jerry Model B) langsung | 🔴 P0 | Rendah (test coverage tinggi) |
| C-2 | pdf_gabungan.py total (khusus hilang) | Tambah `sum_khusus` ke total_penerimaan | 🔴 P0 | Sangat rendah |
| C-3 | Rounding truncate vs round | Migrasi ke `int(round(...))` konsisten dengan Jerry Model B | 🟠 P1 | Rendah (perlu re-validate data historis) |
| C-4 | Legacy calculator di admin recompute | Ganti `calculate_distribution` → `compute_porsi` di `admin.py:recompute_porsi` | 🟠 P1 | Sedang (data historis bisa berubah) |
| C-5 | Live vs stored drift | Definisikan single source of truth: **stored snapshot** + tombol recompute eksplisit | 🟡 P2 | Rendah |
| C-6 | Missing porsi_x_uni fields di Kuitansi | Tambah kolom `porsi_x_uni`, `porsi_pt_uni`, `porsi_khusus_uni` + Alembic migration | 🟡 P2 | Sedang (schema migration) |
| C-7 | KuitansiKategori tidak punya porsi | Defer ke v2.1 (luar scope FASE 2) | ⚪ P3 | – |

---

## 5. Rekomendasi Perbaikan (RENCANA Detail)

### R1: Fix Dashboard Math dengan Refactor ke `compute_porsi`

**Target**: [`app/api/v1/dashboard.py`](app/api/v1/dashboard.py:180-200)

**Perubahan**:
```python
# Before (lines 180-189)
porsi_x_misi = int(total_x * pct["pct_x_jemaat"])
porsi_pt_misi = int(total_pt * pct["pct_pt_jemaat"])
porsi_pt_jemaat = total_pt - porsi_pt_misi
porsi_khusus_misi = int(total_khusus * pct["pct_khusus_jemaat"])
porsi_khusus_jemaat = total_khusus - porsi_khusus_misi

porsi_kantor_misi = porsi_x_misi + porsi_pt_misi
porsi_kas_jemaat = porsi_pt_jemaat + porsi_khusus_jemaat

# After (refactored to use compute_porsi)
from app.utils.porsi_calculator import compute_porsi

porsi = compute_porsi(
    x=total_x, pt=total_pt, kh=total_khusus,
    pct_x_jemaat=pct["pct_x_jemaat"],
    pct_pt_jemaat=pct["pct_pt_jemaat"],
    pct_khusus_jemaat=pct["pct_khusus_jemaat"],
    pct_x_uni=pct["pct_x_uni"],
    pct_pt_uni=pct["pct_pt_uni"],
    pct_khusus_uni=pct["pct_khusus_uni"],
)
# porsi = {pj_x, pj_pt, pj_kh, pu_x, pu_pt, pu_kh, pm_x, pm_pt, pm_kh}

porsi_kantor_misi = porsi["pm_x"] + porsi["pm_pt"] + porsi["pm_kh"]
porsi_kas_jemaat = porsi["pj_x"] + porsi["pj_pt"] + porsi["pj_kh"]
porsi_khusus_misi = porsi["pm_kh"]
porsi_khusus_jemaat = porsi["pj_kh"]
porsi_x_uni = porsi["pu_x"]   # NEW: disimpan ke field baru
porsi_pt_uni = porsi["pu_pt"]
porsi_khusus_uni = porsi["pu_kh"]
```

**Test Plan**:
1. Unit test: jalankan `compute_porsi(x=1000000, pt=500000, kh=200000, ...)` dengan seed config, validasi output = expected.
2. Integration test: POST `/kuitansi` via dashboard, validasi field `porsi_kantor_misi`, `porsi_kas_jemaat`, `porsi_khusus_misi`, `porsi_khusus_jemaat` semua benar.
3. Regression test: jalankan ulang terhadap 100 kuitansi historis (random sample), validasi tidak ada perubahan pada kuitansi yang inputnya identik.

---

### R2: Fix PDF Gabungan Total

**Target**: [`app/services/pdf_gabungan.py`](app/services/pdf_gabungan.py:123)

**Perubahan**:
```python
# Before (line 123)
total_penerimaan = sum_x + sum_pt

# After
total_penerimaan = sum_x + sum_pt + sum_khusus
```

**Test Plan**:
1. Generate PDF untuk sample jemaat, validasi baris TOTAL = penjumlahan kolom X, PT, Khusus.
2. Cross-check dengan validasi akuntansi: `total_penerimaan == sum_misi + sum_jemaat` (conservation of money).

---

### R3: Migrasi `admin.py:recompute-porsi` ke Jerry Model B

**Target**: [`app/api/v1/admin.py:347-451`](app/api/v1/admin.py:347)

**Perubahan**:
```python
# Before
from app.services.financial_calculator import calculate_distribution
result = calculate_distribution(...)

# After
from app.utils.porsi_calculator import compute_porsi
result = compute_porsi(...)
```

**Catatan**: Output `compute_porsi` (Jerry Model B) punya field berbeda dari `calculate_distribution` (legacy). Perlu mapping:
| Legacy Field | Jerry Model B Field |
|--------------|---------------------|
| `porsi_x_misi` | `pm_x` |
| `porsi_pt_misi` | `pm_pt` |
| `porsi_khusus_misi` | `pm_kh` |
| `porsi_x_jemaat` | `pj_x` |
| `porsi_pt_jemaat` | `pj_pt` |
| `porsi_khusus_jemaat` | `pj_kh` |
| `porsi_x_uni` (legacy: dari porsi_x_misi) | `pu_x` (dari total_x) |

**Test Plan**:
1. Backup database sebelum recompute.
2. Jalankan `POST /admin/recompute-porsi` untuk 1 jemaat sample, bandingkan sebelum/sesudah.
3. Validasi total penerimaan jemaat (X+PT+KH) = total porsi (jemaat + misi + uni) untuk setiap kuitansi.

---

### R4: Tambah Kolom `porsi_x_uni`, `porsi_pt_uni`, `porsi_khusus_uni` di Kuitansi

**Target**: [`app/models/transaction.py`](app/models/transaction.py)

**Perubahan**:
1. Tambah 3 kolom di model Kuitansi:
   ```python
   porsi_x_uni = Column(Integer, default=0, nullable=False)
   porsi_pt_uni = Column(Integer, default=0, nullable=False)
   porsi_khusus_uni = Column(Integer, default=0, nullable=False)
   ```
2. Buat Alembic migration:
   ```bash
   alembic revision --autogenerate -m "add porsi_uni fields to kuitansi"
   alembic upgrade head
   ```
3. Update [`dashboard.py`](app/api/v1/dashboard.py) untuk menyimpan field baru (lihat R1).
4. Update [`pdf_gabungan.py`](app/services/pdf_gabungan.py) untuk menampilkan field baru (opsional, bisa di kolom tambahan).

**Test Plan**:
1. Jalankan migration di staging DB, validasi schema.
2. Buat kuitansi baru via dashboard, validasi field terisi.
3. Jalankan recompute, validasi field ter-update.

---

### R5: Definisikan Single Source of Truth Policy

**Keputusan yang Diusulkan**:
- **Stored snapshot** adalah sumber utama untuk audit (immutable per kuitansi).
- **Live recompute** tersedia via tombol "Recompute Porsi" di dashboard admin, dengan logging ke `audit_logs`.
- **Agregat** tetap pakai **live recompute** (responsive terhadap perubahan `PersentaseConfig`), dengan disclaimer di UI: "Nilai agregat dihitung ulang dari konfigurasi terbaru."

**Implementasi**:
1. Tambah kolom `porsi_recomputed_at: DateTime` di Kuitansi (nullable) untuk tracking kapan terakhir di-recompute.
2. Tambah endpoint `POST /kuitansi/{id}/recompute-porsi` (single) + `POST /admin/recompute-porsi` (batch, sudah ada).
3. Setiap recompute tulis ke `audit_logs`: `{user_id, action="recompute_porsi", entity="kuitansi", entity_id, before, after, config_snapshot}`.

---

### R6: Accounting Integrity Test Suite

**Target**: `tests/test_accounting_integrity.py` (file baru)

**Cakupan Test**:
1. **Conservation of money**: Untuk setiap Kuitansi, validasi `x + pt + kh == total_pemberian` dan `total_pemberian == (pj_x + pj_pt + pj_kh) + (pm_x + pm_pt + pm_kh) + (pu_x + pu_pt + pu_kh)`.
2. **Pct constraints**: Untuk setiap `PersentaseConfig`, validasi `pct_x_jemaat + pct_x_uni ≤ 1.0` (dan sama untuk pt, kh).
3. **Cross-tenant isolation**: Kuitansi jemaat A tidak boleh masuk agregat jemaat B (covered FASE 4).
4. **PDF total consistency**: Untuk setiap generate PDF, validasi `total_penerimaan == sum_x + sum_pt + sum_khusus`.
5. **Recompute idempotency**: Jalankan recompute 2x, validasi output identik.
6. **T101 regression**: pct_x_jemaat=0.0 → porsi_x_jemaat=0 untuk semua kuitansi baru.

---

## 6. Urutan Eksekusi (Risk-Ordered)

| Step | Aksi | File Touched | Risiko | Rollback |
|------|------|--------------|--------|----------|
| **S1** | R2: Fix PDF total (1 line) | `pdf_gabungan.py` | Sangat rendah | `git revert` |
| **S2** | R1: Refactor dashboard.py pakai compute_porsi | `dashboard.py` | Rendah | `git revert` + manual fix kuitansi baru |
| **S3** | R6: Tambah accounting integrity test suite | `tests/test_accounting_integrity.py` (new) | – | – |
| **S4** | R3: Migrasi admin.py recompute ke compute_porsi | `admin.py` | Sedang (data historis berubah) | Backup DB sebelum, restore jika diff > toleransi |
| **S5** | R4: Schema migration tambah porsi_uni fields | `transaction.py` + Alembic | Sedang (downtime kecil) | `alembic downgrade -1` |
| **S6** | R5: Single source of truth policy | `audit_logs`, endpoint baru, UI button | Rendah | `git revert` |
| **S7** | Backfill: Hitung ulang porsi_uni untuk kuitansi lama | `scripts/backfill_porsi_uni.py` (new) | Sedang | Backup DB |

**Estimasi Total**: ~4-6 jam kerja (coding + testing + dokumentasi).

---

## 7. Test Plan End-to-End

### Pre-conditions
- [ ] Branch `audit/comprehensive-review` aktif.
- [ ] Database staging sudah di-backup.
- [ ] Test suite existing (`pytest`) hijau sebelum perubahan.

### Per-Step Validation
1. **Setelah S1**: Generate PDF untuk 3 jemaat sample, visual validasi baris TOTAL = penjumlahan kolom.
2. **Setelah S2**: Buat 10 kuitansi baru via dashboard, bandingkan dengan hasil `compute_porsi` di unit test.
3. **Setelah S3**: Jalankan `pytest tests/test_accounting_integrity.py -v`, semua hijau.
4. **Setelah S4**: Jalankan recompute untuk 1 jemaat, validasi diff before/after < 1% (toleransi rounding).
5. **Setelah S5**: Jalankan `alembic upgrade head` + `alembic downgrade -1` di staging, validasi reversibility.
6. **Setelah S6**: Tekan tombol "Recompute" di UI, validasi audit_logs entry muncul.
7. **Setelah S7**: Jalankan backfill, validasi semua kuitansi historis punya `porsi_x_uni` terisi.

### Post-conditions
- [ ] Semua test hijau.
- [ ] PDF laporan gabungan balance (total = sum kolom).
- [ ] Kuitansi baru via dashboard konsisten dengan scanner/wa_input.
- [ ] Recompute pakai Jerry Model B di semua call site.
- [ ] `porsi_x_uni` tersedia untuk audit Uni.

---

## 8. Rollback Plan

1. **Git rollback**: Setiap step di-commit terpisah, `git revert <commit-hash>` per step.
2. **DB rollback**:
   - S5 (schema migration): `alembic downgrade -1`.
   - S7 (backfill): restore dari backup.
3. **Data rollback untuk S4**: Simpan snapshot sebelum recompute (`SELECT * FROM kuitansi_backup_20260902`), restore jika diff > toleransi.

---

## 9. Impact Analysis

### Data Historis
- **Kuitansi lama** yang dibuat via dashboard (sebelum S2): kemungkinan punya `porsi_kantor_misi` understated (missing khusus). **Rekomendasi**: Jalankan recompute (R5) untuk jemaat yang input via dashboard.
- **Kuitansi lama** yang dibuat via scanner/wa_input: sudah benar (Jerry Model B), tidak perlu recompute.

### User-Facing Changes
- **Tidak ada** perubahan API contract (input/output sama).
- **Ada** perubahan internal math (porsi_kantor_misi akan lebih akurat).
- **Ada** tombol baru "Recompute Porsi" di dashboard admin.

### Performance
- R1 (refactor): Tidak ada perubahan performance (compute_porsi sama cepatnya dengan inline math).
- R6 (test suite): +5-10 detik di CI.

---

## 10. Daftar File yang Akan Diubah

| File | Perubahan | Lines Affected |
|------|-----------|----------------|
| `app/api/v1/dashboard.py` | R1: Refactor pakai compute_porsi | ~180-200 |
| `app/services/pdf_gabungan.py` | R2: Tambah sum_khusus ke total | 123 |
| `app/api/v1/admin.py` | R3: Ganti calculate_distribution → compute_porsi | ~347-451 |
| `app/models/transaction.py` | R4: Tambah 3 kolom porsi_uni | ~model Kuitansi |
| `alembic/versions/xxxx_add_porsi_uni.py` | R4: Migration baru | new file |
| `app/api/v1/kuitansi.py` (or new endpoint) | R5: Endpoint recompute single | new |
| `frontend/src/pages/admin/Dashboard.tsx` | R5: Tombol Recompute di UI | new button |
| `tests/test_accounting_integrity.py` | R6: Test suite baru | new file |
| `scripts/backfill_porsi_uni.py` | S7: Backfill script | new file |

**Total**: 7 file dimodifikasi, 3 file baru.

---

## 11. Pertanyaan untuk Keputusan

Sebelum eksekusi, mohon konfirmasi:

1. **Apakah R1-R6 boleh dieksekusi semua, atau ada yang di-defer?**
   - Default: R1, R2, R3, R6 eksekusi (P0-P1). R4, R5, R7 eksekusi di fase terpisah (P2).

2. **Untuk data historis kuitansi lama yang dibuat via dashboard (sebelum R1), apakah perlu di-recompute?**
   - Default: Ya, via backfill script (S7), setelah approval.

3. **Apakah boleh menambah 3 kolom baru di tabel `kuitansi` (R4)?**
   - Default: Ya, dengan Alembic migration yang reversible.

4. **Apakah tombol "Recompute Porsi" di UI (R5) cukup untuk handle live-vs-stored drift, atau perlu strategi lain?**
   - Default: Cukup, dengan logging ke audit_logs.

---

## 12. Status

🟡 **RENCANA SIAP — Menunggu "SETUJU" untuk eksekusi.**

Tidak ada perubahan kode yang akan dilakukan sampai Anda memberikan persetujuan eksplisit.

Jika ada bagian yang perlu diubah, didiskusikan, atau di-defer, mohon kabari sebelum eksekusi.
