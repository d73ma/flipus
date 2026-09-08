# FLIPUS — Deploy ke Railway (URL permanen + auto-restart)

Railway menyelesaikan 2 masalah yang kita alami dengan quick tunnel:
1. **Auto-restart** saat crash (backend tidak lagi mati-mati)
2. **URL permanen** (`*.up.railway.app`) — tidak berubah/expire

Repo sudah disiapkan dengan config berikut (Kilo 2026-09-08):
- `Dockerfile` — single container (frontend nginx + backend uvicorn via supervisord)
- `nginx.railway.conf` — reverse proxy /api → uvicorn, port dinamis
- `supervisord.conf` — jalankan nginx + uvicorn bareng, auto-restart
- `docker-entrypoint.sh` — substitusi $PORT
- `railway.json` — build DOCKERFILE + healthcheck /health
- `.dockerignore` — exclude .venv/node_modules/.git

---

## Langkah Deploy (Jerry di browser, ≈10 menit)

### 1. Buat akun Railway
Buka <https://railway.app> → klik **Login** → pilih **Login with GitHub**
(pakai akun `d73ma` yang sudah connect ke repo flipus).

### 2. Deploy dari repo GitHub
1. Klik **New Project**
2. Pilih **Deploy from GitHub repo**
3. Cari & pilih repo **`d73ma/flipus`**
4. Railway auto-deteksi `Dockerfile` di root → mulai build (≈3-5 menit pertama)

### 3. Set Environment Variables
Buka project → tab **Variables** → tambahkan ini (nilai salin dari `.env` lokal):

| Key | Nilai | Wajib |
|---|---|---|
| `SECRET_KEY` | random string 32+ char | ✅ |
| `PII_ENCRYPTION_KEY` | Fernet key | ✅ |
| `DATABASE_URL_LOCAL` | `sqlite:///./flipus_local.db` | ✅ |
| `LICENSE_TENANT_SIGNATURE_SALT` | dari `.env` | ✅ |
| `DEFAULT_UNI` | `Uni Konferens Indonesia Kawasan Timur (UKIKT)` | ✅ |
| `FONNTE_TOKEN` | token Fonnte (atau dummy) | opsional |
| `GEMINI_API_KEY` | Gemini API key (atau dummy) | opsional |
| `WA_API_TOKEN` | (sama dengan FONNTE_TOKEN) | opsional |
| `WHATSAPP_ENABLED` | `false` | opsional |

> **Catatan SQLite:** filesystem Railway **ephemeral** (reset tiap deploy).
> Untuk data persisten, di tab **Volumes**: attach volume ke path `/app/storage`.
> Untuk produksi nyata, pakai PostgreSQL (lihat catatan bawah).

### 4. Deploy & dapatkan URL
- Setelah env vars ter-set, Railway auto-redeploy.
- Buka tab **Settings** → **Networking** → **Generate Domain** → dapat URL `https://flipus.up.railway.app` (atau nama custom).

### 5. Seed data demo (opsional, sekali)
Buka **Deployments** → terbaru → **Open shell** → jalankan:
```bash
python scripts/seed_demo.py
python scripts/seed_demo_full.py
```

### 6. Login
Buka URL → login `bendahara_a` / `Bendahara123!` (atau user yang di-seed).

---

## Troubleshooting

**Build gagal** → cek **Deployments → build logs**. Umumnya Dockerfile build
berhasil karena frontend `npm run build` sudah diverifikasi lokal.

**Healthcheck fail** → pastikan `DATABASE_URL_LOCAL` & secrets di-set, bukan
kosong. Cek logs shell.

**Data hilang setelah redeploy** → belum attach volume. Tambah volume ke
`/app/storage` (dan pastikan `DATABASE_URL_LOCAL` menunjuk ke dalam volume).

**URL 404 di /api** → nginx proxy ke `127.0.0.1:8000`; pastikan uvicorn naik
(lihat `supervisord` logs via shell).

---

## PostgreSQL (produksi nyata, opsional)

Untuk produksi multi-jemaat, SQLite (single-file) kurang ideal. Railway punya
PostgreSQL plugin:
1. Tab **New** → **Database** → **PostgreSQL** → provisikan
2. Railway inject `DATABASE_URL` public
3. Set env `DATABASE_URL_LOCAL=${DATABASE_URL}` di service backend
4. Jalankan migrasi alembic: `alembic upgrade head` (via shell)
5. Seed demo data

---

## Menutup Quick Tunnel

Setelah Railway jalan, quick tunnel lokal (`trycloudflare.com`) tidak
diperlukan lagi. Cukup stop `cloudflared` di mesin Jerry.
