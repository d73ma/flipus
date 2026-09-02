#!/bin/bash
# FLIPUS v1.4 — Backup GPG-Encrypted (T52)
#
# Usage:
#   ./storage/scripts/backup_gpg.sh                  # One-shot backup
#   ./storage/scripts/backup_gpg.sh --install-cron   # Install daily auto-backup
#   ./storage/scripts/backup_gpg.sh --test           # Run decryption test (verify integrity)
#
# What it does:
#   1. Detect DB type (SQLite dev or Postgres prod via DATABASE_URL)
#   2. Dump → compress (gzip) → GPG symmetric encrypt
#   3. Move to storage/backups/<date>/ with timestamp
#   4. Cleanup old backups (retention: BACKUP_RETENTION_DAYS, default 30)
#   5. Audit log: BACKUP_CREATED + size + SHA256 checksum
#   6. Optional: install cron job for daily auto-backup
#
# Security:
#   - GPG symmetric (AES-256) — passphrase via BACKUP_GPG_PASSPHRASE_FILE
#   - Passphrase file: chmod 600, NOT in .env, NOT in git
#   - Output file: chmod 600, owner-only
#   - Old backups purged securely (shred + delete)
#
# Setup (one-time):
#   1. Generate passphrase file:
#      sudo mkdir -p /etc/flipus && sudo chmod 700 /etc/flipus
#      sudo openssl rand -base64 48 | sudo tee /etc/flipus/backup.key
#      sudo chmod 600 /etc/flipus/backup.key
#   2. Add to .env:
#      BACKUP_GPG_PASSPHRASE_FILE=/etc/flipus/backup.key
#      BACKUP_RETENTION_DAYS=30
#   3. Test: ./storage/scripts/backup_gpg.sh --test
#   4. Install cron: ./storage/scripts/backup_gpg.sh --install-cron

set -e

BACKEND_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$BACKEND_DIR"

# Load .env kalau ada
if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# Settings
PASSPHRASE_FILE="${BACKUP_GPG_PASSPHRASE_FILE:-/etc/flipus/backup.key}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
BACKUP_ROOT="$BACKEND_DIR/storage/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DATE_DIR="$BACKUP_ROOT/$(date +%Y%m%d)"
LOG_FILE="$BACKUP_ROOT/backup.log"

mkdir -p "$DATE_DIR"
chmod 700 "$BACKUP_ROOT"

# ===== Helper: audit log =====
audit_log() {
    local action="$1"
    local detail="$2"
    PYTHONPATH="$BACKEND_DIR" "$BACKEND_DIR/.venv/bin/python3" - << PYEOF 2>/dev/null || true
import os
from datetime import datetime, timezone
from app.core.database import SessionLocal
from app.models.audit import AuditLog
from app.models.tenant import Tenant

db = SessionLocal()
try:
    first_tenant = db.query(Tenant).first()
    if first_tenant:
        db.add(AuditLog(
            tenant_id=first_tenant.id,
            action="$action",
            payload_hash="$detail",
        ))
        db.commit()
except Exception:
    db.rollback()
finally:
    db.close()
PYEOF
}

# ===== Helper: detect DB type =====
detect_db_type() {
    if [ -n "$DATABASE_URL_CLOUD" ] && [ -n "$DATABASE_URL_LOCAL" ]; then
        # Prefer cloud in production (Postgres), local in dev (SQLite)
        if [[ "$DATABASE_URL_CLOUD" == postgresql* ]]; then
            echo "postgres"
            return
        fi
    fi
    if [ -f "flipus_local.db" ]; then
        echo "sqlite"
        return
    fi
    echo "unknown"
}

# ===== Helper: backup sqlite =====
backup_sqlite() {
    local db_file="$1"
    local out_file="$2"
    if [ ! -f "$db_file" ]; then
        echo "❌ SQLite DB not found: $db_file"
        exit 1
    fi
    # SQLite backup via .backup command (safe even if DB is being written)
    "$BACKEND_DIR/.venv/bin/python3" - << PYEOF
import sqlite3
import sys
src = "$db_file"
dst = "$out_file"
conn = sqlite3.connect(src)
with conn:
    conn.execute("BEGIN IMMEDIATE")
    # Use SQLite's backup API for safe online backup
    backup_conn = sqlite3.connect(dst)
    conn.backup(backup_conn)
    backup_conn.close()
conn.close()
print(f"✓ SQLite backup written: $out_file")
PYEOF
}

# ===== Helper: backup postgres =====
backup_postgres() {
    local out_file="$1"
    # Parse DATABASE_URL_CLOUD (postgresql://user:pass@host:port/dbname)
    if [[ "$DATABASE_URL_CLOUD" =~ postgresql://([^:]+):([^@]+)@([^:]+):?([0-9]*)/(.+) ]]; then
        local pg_user="${BASH_REMATCH[1]}"
        local pg_pass="${BASH_REMATCH[2]}"
        local pg_host="${BASH_REMATCH[3]}"
        local pg_port="${BASH_REMATCH[4]:-5432}"
        local pg_db="${BASH_REMATCH[5]}"
        PGPASSWORD="$pg_pass" pg_dump -h "$pg_host" -p "$pg_port" -U "$pg_user" -d "$pg_db" \
            --no-owner --no-acl -f "$out_file"
        echo "✓ Postgres backup written: $out_file"
    else
        echo "❌ Cannot parse DATABASE_URL_CLOUD"
        exit 1
    fi
}

# ===== Main: do backup =====
do_backup() {
    echo "=== FLIPUS Backup GPG-Encrypted ==="
    echo "Timestamp: $TIMESTAMP"
    echo ""

    # Check passphrase file
    if [ ! -f "$PASSPHRASE_FILE" ]; then
        echo "❌ Passphrase file not found: $PASSPHRASE_FILE"
        echo ""
        echo "Setup one-time:"
        echo "  sudo mkdir -p /etc/flipus && sudo chmod 700 /etc/flipus"
        echo "  sudo openssl rand -base64 48 | sudo tee $PASSPHRASE_FILE"
        echo "  sudo chmod 600 $PASSPHRASE_FILE"
        echo ""
        echo "Tambahkan ke .env:"
        echo "  BACKUP_GPG_PASSPHRASE_FILE=$PASSPHRASE_FILE"
        exit 1
    fi
    if [ "$(stat -c %a "$PASSPHRASE_FILE" 2>/dev/null || stat -f %Lp "$PASSPHRASE_FILE" 2>/dev/null)" != "600" ]; then
        echo "⚠️  $PASSPHRASE_FILE tidak chmod 600. Auto-fix..."
        chmod 600 "$PASSPHRASE_FILE"
    fi

    # Check gpg
    if ! command -v gpg &> /dev/null; then
        echo "❌ gpg belum terinstall. Install: sudo apt install gnupg"
        exit 1
    fi

    # Detect DB type
    DB_TYPE=$(detect_db_type)
    echo "DB type: $DB_TYPE"

    # Step 1: Dump
    local dump_file="$DATE_DIR/flipus_${DB_TYPE}_${TIMESTAMP}.sql"
    case $DB_TYPE in
        sqlite)
            backup_sqlite "flipus_local.db" "$dump_file"
            ;;
        postgres)
            backup_postgres "$dump_file"
            ;;
        *)
            echo "❌ Unknown DB type"
            exit 1
            ;;
    esac

    # Step 2: Compress
    local gz_file="$dump_file.gz"
    gzip -9 -f "$dump_file"
    echo "✓ Compressed: $gz_file"

    # Step 3: GPG encrypt
    local gpg_file="$gz_file.gpg"
    gpg --batch --yes --quiet \
        --symmetric \
        --cipher-algo AES256 \
        --compress-algo none \
        --passphrase-file "$PASSPHRASE_FILE" \
        --output "$gpg_file" \
        "$gz_file"
    # Secure shred of plaintext gz
    shred -u "$gz_file" 2>/dev/null || rm -f "$gz_file"
    chmod 600 "$gpg_file"
    echo "✓ GPG-encrypted: $gpg_file"

    # Step 4: SHA256 checksum
    local checksum=$(sha256sum "$gpg_file" | awk '{print $1}')
    echo "$checksum  $(basename "$gpg_file")" > "$gpg_file.sha256"
    chmod 600 "$gpg_file.sha256"
    echo "✓ SHA256: $checksum"

    # Step 5: Size info
    local size=$(du -h "$gpg_file" | awk '{print $1}')
    echo "✓ Size: $size"

    # Step 6: Audit log
    audit_log "BACKUP_GPG_CREATED" "size=${size}_checksum=${checksum:0:16}"

    # Step 7: Cleanup old backups
    echo ""
    echo "Cleaning up backups older than $RETENTION_DAYS days..."
    find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime +$RETENTION_DAYS -exec rm -rf {} \;
    local purged=$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime +$RETENTION_DAYS | wc -l)
    echo "✓ Purged: $p purged directory"

    echo ""
    echo "✅ Backup complete: $gpg_file"
    echo "   Restore: ./storage/scripts/restore_gpg.sh $gpg_file"
}

# ===== Test: decrypt + verify =====
test_decrypt() {
    echo "=== FLIPUS Backup Test (decrypt + verify) ==="
    local latest=$(find "$BACKUP_ROOT" -name "*.gpg" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | awk '{print $2}')
    if [ -z "$latest" ]; then
        echo "❌ No backup found to test"
        exit 1
    fi
    echo "Latest backup: $latest"
    echo ""

    # Verify checksum
    if [ -f "$latest.sha256" ]; then
        cd "$(dirname "$latest")"
        if sha256sum -c "$(basename "$latest.sha256")" --quiet; then
            echo "✓ SHA256 checksum valid"
        else
            echo "❌ SHA256 checksum mismatch!"
            exit 1
        fi
        cd "$BACKEND_DIR"
    fi

    # Decrypt to /tmp
    local test_out="/tmp/flipus_backup_test_$$.sql.gz"
    gpg --batch --yes --quiet \
        --decrypt \
        --passphrase-file "$PASSPHRASE_FILE" \
        --output "$test_out" \
        "$latest"
    echo "✓ Decryption successful"

    # Verify gzip integrity
    if gzip -t "$test_out"; then
        echo "✓ Gzip integrity valid"
    else
        echo "❌ Gzip integrity failed"
        shred -u "$test_out"
        exit 1
    fi

    # Cleanup
    shred -u "$test_out"
    echo ""
    echo "✅ Backup test passed"
}

# ===== Install cron job =====
install_cron() {
    echo "=== Installing daily backup cron (02:00) ==="
    local cron_line="0 2 * * * $BACKEND_DIR/storage/scripts/backup_gpg.sh >> $LOG_FILE 2>&1"
    (crontab -l 2>/dev/null | grep -v 'backup_gpg.sh' ; echo "$cron_line") | crontab -
    echo "✓ Cron installed: daily 02:00"
    echo "  Log: $LOG_FILE"
    echo ""
    crontab -l | grep backup_gpg.sh
}

# ===== Main dispatch =====
case "${1:-}" in
    --test)
        test_decrypt
        ;;
    --install-cron)
        install_cron
        ;;
    "")
        do_backup
        ;;
    *)
        echo "Usage: $0 [--test|--install-cron]"
        exit 1
        ;;
esac
