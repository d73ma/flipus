# FLIPUS — Security Procedures

## 🔄 SECRET_KEY Rotation

### Kapan Rotate?
- **Rutin**: setiap 6 bulan
- **Insiden**: kalau `.env` pernah terexpose (lupa commit ke repo, server compromised, dsb)

### Prosedur

#### 1. Standalone (Quick — pakai script otomatis)

```bash
cd /path/to/Flipus

# Standard: rotate + restart backend
./storage/scripts/rotate_secret_key.sh

# Tanpa restart (manual restart setelahnya)
./storage/scripts/rotate_secret_key.sh --no-restart
```

Script akan otomatis:
1. Generate `SECRET_KEY` baru (64 char URL-safe)
2. Backup `.env` → `.env.bak.<timestamp>`
3. Update `.env`: `SECRET_KEY` = new, `SECRET_KEY_PREVIOUS` = old (24 jam grace window)
4. Audit log: `SECRET_KEY_ROTATED`
5. Cron job: drop `SECRET_KEY_PREVIOUS` setelah 24 jam
6. (Default) Restart backend

#### 2. Manual (kalau script tidak bisa dipakai)

```bash
# Generate new key
python3 -c "import secrets; print(secrets.token_urlsafe(64))"

# Backup .env
cp .env .env.bak.$(date +%Y%m%d_%H%M%S)

# Edit .env:
#   SECRET_KEY=<new_key>
#   SECRET_KEY_PREVIOUS=<old_key_value>

# Restart backend
bash restart_backend.sh
```

### Grace Window (24 jam)

Saat rotasi, JWT lama masih valid via fallback ke `SECRET_KEY_PREVIOUS`. Ini supaya user yang sedang aktif tidak tiba-tiba ter-logout.

Setelah 24 jam:
- Cron job otomatis hapus `SECRET_KEY_PREVIOUS` dari `.env`
- JWT lama jadi invalid (user harus re-login)
- Hanya JWT baru (signed dengan `SECRET_KEY`) yang valid

### Verifikasi Rotation Berhasil

```bash
# 1. Cek .env (jangan tampilkan key-nya!)
grep "SECRET_KEY" .env

# 2. Cek audit log
sqlite3 flipus_local.db "SELECT created_at, action FROM audit_logs WHERE action='SECRET_KEY_ROTATED' ORDER BY id DESC LIMIT 5;"

# 3. Test JWT lama masih valid (grace window test)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"pendeta_a","password":"..."}'  # Dapat token baru (signed new key)

# 4. Test JWT baru works
curl -H "Authorization: Bearer <new_token>" http://localhost:8000/api/v1/dashboard/data
```

### Force Re-Login (Optional)

Kalau curiga `.env` pernah terexpose, mau force semua user re-login segera:

```bash
# Hapus SECRET_KEY_PREVIOUS manual (skip 24 jam grace)
sed -i.bak '/^SECRET_KEY_PREVIOUS=/d' .env
bash restart_backend.sh
```

Semua user dengan JWT lama akan ter-logout otomatis (perlu login ulang).

### Backup & Disaster Recovery

**PENTING**: Setiap backup `.env.bak.<timestamp>` adalah SECURITY-CRITICAL.
- Simpan di lokasi terenkripsi (GPG/encrypted volume)
- **JANGAN** commit ke git
- **JANGAN** upload ke cloud storage tanpa enkripsi
- `.env*` harus sudah di-`.gitignore` (verify!)

---

## 💾 GPG-Encrypted Backup (T52)

### Overview
Semua backup database FLIPUS di-encrypt dengan **GPG AES-256 symmetric** sebelum disimpan. Passphrase disimpan di file terpisah dengan chmod 600, **tidak di `.env`**. Cocok untuk **GDPR/UU PDP compliance** — backup at rest terekripsi.

### Setup (One-Time)

#### 1. Generate Passphrase File (di server production)

```bash
# Buat directory ter-restrict
sudo mkdir -p /etc/flipus
sudo chmod 700 /etc/flipus

# Generate passphrase random (48 byte = 64 char base64)
sudo openssl rand -base64 48 | sudo tee /etc/flipus/backup.key
sudo chmod 600 /etc/flipus/backup.key
sudo chown root:root /etc/flipus/backup.key

# Verify
ls -la /etc/flipus/backup.key
# -rw------- 1 root root 64 ... /etc/flipus/backup.key
```

#### 2. Add to `.env`

```bash
BACKUP_GPG_PASSPHRASE_FILE=/etc/flipus/backup.key
BACKUP_RETENTION_DAYS=30
```

⚠️ **PENTING**: Passphrase file ini **TIDAK boleh**:
- Di-commit ke git
- Di-backup ke tempat biasa (gunakan secret manager atau offline storage)
- Dibagikan via Slack/email

🛡️ **Best practice**: Simpan passphrase **offline** (printed di kertas, disimpan di safe) sebagai backup recovery. Kalau server hilang total, Anda perlu passphrase untuk restore.

#### 3. Install GPG

```bash
sudo apt install gnupg  # Ubuntu/Debian
# atau
sudo yum install gnupg2  # CentOS/RHEL
```

### Cara Pakai

#### Backup Manual (One-Shot)

```bash
cd /path/to/Flipus
./storage/scripts/backup_gpg.sh
```

Output:
```
=== FLIPUS Backup GPG-Encrypted ===
Timestamp: 20260821_143000

✓ SQLite backup written: .../flipus_20260821_143000.sql
✓ Compressed: .../flipus_20260821_143000.sql.gz
✓ GPG-encrypted: .../flipus_20260821_143000.sql.gz.gpg
✓ SHA256: a1b2c3d4...
✓ Size: 1.2M
✓ Purged: 0 old backups

✅ Backup complete
```

#### Test Decryption (Integrity Check)

```bash
./storage/scripts/backup_gpg.sh --test
```

Verifikasi:
- SHA256 checksum valid
- GPG decryption sukses
- Gzip integrity check
- Otomatis cleanup plaintext

#### Install Auto-Backup (Cron)

```bash
./storage/scripts/backup_gpg.sh --install-cron
```

Install cron job: **daily 02:00 AM**. Output: `storage/backups/backup.log`.

#### List Backups

```bash
./storage/scripts/backup_gpg.sh           # List semua backup
# atau
./storage/scripts/restore_gpg.sh --list
```

Output:
```
=== Available GPG Backups ===
2026-08-21 14:30:00  1234567 bytes  .../flipus_20260821_143000.sql.gz.gpg
2026-08-20 02:00:00  1198234 bytes  .../flipus_20260820_020000.sql.gz.gpg
Total: 2 backup(s)
```

#### Restore dari Backup

```bash
# Restore ke /tmp/flipus_restored_<timestamp>.sql
./storage/scripts/restore_gpg.sh storage/backups/20260821/flipus_20260821_143000.sql.gz.gpg

# Restore ke path tertentu
./storage/scripts/restore_gpg.sh <backup.gpg> --target /tmp/my_restore.sql

# Decrypt ke stdout (untuk pipe)
./storage/scripts/restore_gpg.sh <backup.gpg> --stdout | less
```

⚠️ **Setelah selesai restore, hapus plaintext**:
```bash
shred -u /tmp/flipus_restored_*.sql
```

### Audit Trail

Setiap backup event di-log ke `AuditLog`:

| Action | Detail |
|---|---|
| `BACKUP_GPG_CREATED` | size + checksum partial |
| `BACKUP_GPG_RESTORE_INITIATED` | filename + checksum |
| `BACKUP_GPG_RESTORED` | target path + size |

Query untuk monitoring:
```sql
SELECT created_at, action, payload_hash
FROM audit_logs
WHERE action LIKE 'BACKUP_GPG%'
ORDER BY id DESC
LIMIT 20;
```

### Security Properties

| Aspek | Implementasi |
|---|---|
| **Encryption** | GPG AES-256 symmetric |
| **Passphrase storage** | File terpisah di `/etc/flipus/`, chmod 600, owner root |
| **Plaintext handling** | shred -u (3-pass overwrite) sebelum delete |
| **Output file mode** | chmod 600 (owner-only read/write) |
| **Backup directory** | chmod 700 (owner-only access) |
| **Retention** | Auto-purge >30 days (configurable) |
| **Integrity** | SHA256 checksum per backup file |
| **Audit trail** | AuditLog entry setiap event |

### Compliance

✅ **GDPR Art. 32** ("appropriate technical measures") — backup at rest encrypted
✅ **UU PDP Pasal 35** (perlindungan data pribadi) — enkripsi sebagai langkah proteksi
✅ **ISO 27001 A.10.5** (backup) — encrypted backup + retention policy

---

## 🚨 Security Event Response

### LICENSE_TAMPER_DETECTED (clone attack)

**Trigger**: Tenant signature mismatch (database di-clone/di-edit di luar FLIPUS).

**Tanda**:
- User complain tidak bisa login dengan pesan "Tenant signature invalid"
- Audit log: `LICENSE_TAMPER_DETECTED`
- WA alert otomatis ke ADMIN_UNI

**Response**:
1. JANGAN panik — sistem mendeteksi tamper, ini fitur yang working as intended
2. Investigasi: cek `storage/logs/`, kapan akses terakhir normal?
3. Restore dari backup terakhir yang trusted (verify signature dulu)
4. Rotate `SECRET_KEY` + `PII_ENCRYPTION_KEY` (kalau backup bocor)
5. Audit semua AuditLog dalam window — cari anomali

### CROSS_TENANT_BLOCKED (probing)

**Trigger**: User mencoba akses tenant bukan haknya.

**Tanda**: WA alert "Cross-tenant access diblokir" dengan detail username + tenant attempted vs actual.

**Response**:
- Single occurrence: biasanya user salah klik/typo — monitor
- Burst: kemungkinan probing → consider rotate user password + lock account temporarily

---

## 📊 Audit Log Reference

Critical events yang di-monitor:

| Event | Severity | Auto Alert |
|---|---|---|
| `LICENSE_TAMPER_DETECTED` | CRITICAL | WA ke ADMIN_UNI |
| `CROSS_TENANT_BLOCKED_*` | CRITICAL | WA ke ADMIN_UNI |
| `LOGIN_BLOCKED_LOCKOUT` | INFO | — |
| `LOGIN_FAILED` | INFO | — |
| `LOGIN_SUCCESS` | INFO | — |
| `2FA_ENABLED` | INFO | — |
| `2FA_DISABLED` | WARNING | — |
| `2FA_DISABLED_REJECTED` | WARNING | — |
| `PASSWORD_RESET_REQUESTED` | INFO | — |
| `PASSWORD_RESET_SENT` | INFO | — |
| `REGISTER_SELF_SERVICE_*` | INFO | — |
| `SECRET_KEY_ROTATED` | INFO | — |
| `TENANT_STATUS_CHANGED` | WARNING | — |
| `BRANDING_CHANGED` | INFO | — |

Query untuk cek recent events:

```sql
SELECT created_at, tenant_id, action, payload_hash
FROM audit_logs
WHERE created_at >= datetime('now', '-7 days')
ORDER BY created_at DESC
LIMIT 100;
```

---

_Last updated: 2026-08-21 (v1.4 hardening phase)_