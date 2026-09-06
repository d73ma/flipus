# FLIPUS — Push to GitHub & Tag v2.2.0

**Status:** Repo lokal sudah commit sampai Sprint 5 + cleanup. Tidak ada git remote
di-set. Langkah-langkah ini menyiapkan GitHub repo + push + tag v2.2.0.

**Asumsi:** Jerry memiliki akun GitHub di `jmauri01@gmail.com` (sesuai
`git config user.email` di repo ini).

---

## Step 1 — Buat GitHub repo

Buka <https://github.com/new> dan buat repo baru:

- **Owner:** jmauri01 (atau organisasi Jerry)
- **Repository name:** `flipus` (atau nama lain yang Jerry pilih)
- **Description:** `FLIPUS — Financial Ledger & Integrated Perpuluhan Umbrella System`
- **Visibility:** Private (recommended, contains church financial data architecture)
- **Initialize:** JANGAN centang "Add README", "Add .gitignore", atau "Choose license"
  (repo lokal sudah punya semua ini)

Klik **Create repository**.

## Step 2 — Tambahkan SSH key ke GitHub

SSH key baru sudah di-generate:

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFcF/Ap0fGys1QnX6PxcX17U+uua5R3yMcj+VOnU9w8L jmauri01@gmail.com
```

1. Buka <https://github.com/settings/keys>
2. Klik **New SSH key**
3. **Title:** `MacBook FLIPUS dev` (atau nama machine)
4. **Key type:** Authentication Key
5. **Key:** Paste seluruh baris di atas
6. Klik **Add SSH key**

Verifikasi SSH connection:

```bash
ssh -T git@github.com
# Expected: Hi <username>! You've successfully authenticated...
```

## Step 3 — Setup remote + push

Ganti `<OWNER>` dan `<REPO>` dengan nilai dari Step 1:

```bash
cd /Users/jerrymauri/Flipus

git remote add origin git@github.com:<OWNER>/<REPO>.git

# Verify
git remote -v
# Expected:
# origin  git@github.com:<OWNER>/<REPO>.git (fetch)
# origin  git@github.com:<OWNER>/<REPO>.git (push)

# Push current branch (audit/comprehensive-review)
git push -u origin audit/comprehensive-review

# Switch to main branch
git checkout main

# Merge Sprint 4 + 5 work (8 commits since Roo Code lock)
git merge audit/comprehensive-review --no-ff -m "Merge: FASE 5 Sprint 4 + 5 (CI gate closure + coverage lift + cleanup)"

# Push main
git push -u origin main

# Tag v2.2.0
git tag -a v2.2.0 -m "FLIPUS v2.2.0 — FASE 5 Sprint 4 + 5

Sprint 4: CI gate closure (bandit, pip-audit 37→0, alembic baseline).
Sprint 5: Coverage lift 53.5% → 61.1% + gate raised to 60%.

632 tests passing. 0 bandit HIGH findings. 1 pip-audit residual
suppressed (ecdsa no-fix, FLIPUS uses HS256 JWT).

See FASE5_SPRINT4_SUMMARY.md and FASE5_SPRINT5_SUMMARY.md for details."

git push origin v2.2.0
```

## Step 4 — Update README badges

Edit `README.md` (line 15-17) dan ganti `<OWNER>/<REPO>` placeholder dengan
nilai sebenarnya:

```markdown
[![CI](https://github.com/<OWNER>/<REPO>/actions/workflows/ci.yml/badge.svg)](...)
```

Commit fix ini sebagai `docs: update README badges with real GitHub path`.

## Step 5 — Opsional: GitHub Actions secrets

Untuk menjalankan CI penuh di GitHub, set repository secrets:

- `SECRET_KEY` — random 32-byte URL-safe string
- `PII_ENCRYPTION_KEY` — Fernet key (lihat `python3 -c "from cryptography.fernet
  import Fernet; print(Fernet.generate_key().decode())"`)
- `FONNTE_TOKEN` — Fonnte WA token (atau dummy untuk CI)
- `GEMINI_API_KEY` — Google Gemini API key (atau dummy)

Settings: <https://github.com/<OWNER>/<REPO>/settings/secrets/actions>

---

## Cleanup jika perlu

Jika Jerry ingin remove SSH key nanti (mis. ganti machine):

```bash
ssh-keygen -R git@github.com
# Hapus manual di https://github.com/settings/keys
```

---

## Expected result

Setelah Step 3, GitHub repo akan menampilkan:

- 8 new commits di branch `main` (dari `3a62d95` → `03b6ca1`)
- Tag `v2.2.0` dengan release notes otomatis (kalau GitHub Release dipakai)
- Branch `audit/comprehensive-review` tersedia untuk review/PR-style diff
- README badges hijau (kalau CI pass)

---

## Troubleshooting

**"Permission denied (publickey)":** SSH key belum ditambahkan ke GitHub, atau
salah akun. Ulang Step 2.

**"Repository not found":** Repo belum dibuat atau nama salah. Ulang Step 1.

**"Updates were rejected":** Remote `main` punya commit lain (mungkin dari
push sebelumnya). Jerry perlu `git pull --rebase` atau `git push --force`
(setelah konfirmasi).

**"Tag already exists":** Tag `v2.2.0` sudah ada. Delete dengan
`git push origin :refs/tags/v2.2.0` lalu ulangi.