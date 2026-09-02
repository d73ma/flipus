#!/bin/bash
# FLIPUS v1.4 — Restore GPG-Encrypted Backup
#
# Usage:
#   ./storage/scripts/restore_gpg.sh <backup.gpg>                  # Restore to /tmp/flipus_restored.<ext>
#   ./storage/scripts/restore_gpg.sh <backup.gpg> --stdout         # Output to stdout (pipe)
#   ./storage/scripts/restore_gpg.sh <backup.gpg> --target <path>  # Restore to specific path
#   ./storage/scripts/restore_gpg.sh --list                        # List all available backups
#
# Recovery workflow:
#   1. Verify backup file exists and is GPG-encrypted
#   2. Verify SHA256 checksum
#   3. Decrypt with passphrase
#   4. Decompress gzip
#   5. Output to specified location (default: /tmp/flipus_restored.<ext>)
#   6. Audit log: BACKUP_GPG_RESTORED
#
# ⚠️  PENTING: Setelah restore, JANGAN lupa hapus file plaintext dari /tmp!
#     Gunakan: shred -u /tmp/flipus_restored.*

set -e

BACKEND_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$BACKEND_DIR"

if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

PASSPHRASE_FILE="${BACKUP_GPG_PASSPHRASE_FILE:-/etc/flipus/backup.key}"
BACKUP_ROOT="$BACKEND_DIR/storage/backups"

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

# ===== List backups =====
list_backups() {
    echo "=== Available GPG Backups ==="
    find "$BACKUP_ROOT" -name "*.gpg" -type f -printf '%T+ %s %p\n' 2>/dev/null | \
        sort -r | \
        awk '{
            cmd = "date -d \"" $1 "\" \"+%Y-%m-%d %H:%M:%S\""
            cmd | getline dt
            close(cmd)
            printf "%s  %s bytes  %s\n", dt, $2, $3
        }'
    echo ""
    echo "Total: $(find "$BACKUP_ROOT" -name "*.gpg" -type f | wc -l) backup(s)"
}

# ===== Restore =====
do_restore() {
    local backup_file="$1"
    local target="$2"
    local stdout_mode="$3"

    if [ ! -f "$backup_file" ]; then
        echo "❌ Backup file not found: $backup_file"
        exit 1
    fi

    if [ ! -f "$PASSPHRASE_FILE" ]; then
        echo "❌ Passphrase file not found: $PASSPHRASE_FILE"
        exit 1
    fi

    # Verify SHA256
    if [ -f "$backup_file.sha256" ]; then
        echo "Verifying SHA256 checksum..."
        local checksum_dir=$(dirname "$backup_file")
        cd "$checksum_dir"
        if sha256sum -c "$(basename "$backup_file.sha256")" --quiet; then
            echo "✓ SHA256 valid"
        else
            echo "❌ SHA256 mismatch — backup corrupted!"
            cd "$BACKEND_DIR"
            exit 1
        fi
        cd "$BACKEND_DIR"
    else
        echo "⚠️  No .sha256 file — skipping integrity check"
    fi

    # Audit log
    local checksum=$(sha256sum "$backup_file" | awk '{print $1}')
    audit_log "BACKUP_GPG_RESTORE_INITIATED" "file=$(basename "$backup_file")_checksum=${checksum:0:16}"

    if [ "$stdout_mode" = true ]; then
        # Decrypt + decompress → stdout
        gpg --batch --yes --quiet \
            --decrypt \
            --passphrase-file "$PASSPHRASE_FILE" \
            "$backup_file" | \
        gunzip
    else
        # Decrypt to target
        local temp_gz="/tmp/flipus_restore_$$.gz"
        if [ -z "$target" ]; then
            target="/tmp/flipus_restored_$(date +%Y%m%d_%H%M%S).sql"
        fi
        # Ensure target dir exists
        mkdir -p "$(dirname "$target")"

        gpg --batch --yes --quiet \
            --decrypt \
            --passphrase-file "$PASSPHRASE_FILE" \
            --output "$temp_gz" \
            "$backup_file"
        echo "✓ Decrypted to $temp_gz"

        # Decompress
        gunzip -c "$temp_gz" > "$target"
        chmod 600 "$target"
        shred -u "$temp_gz"
        echo "✓ Restored to: $target"

        # Audit log
        audit_log "BACKUP_GPG_RESTORED" "target=$target_size=$(du -h "$target" | awk '{print $1}')"
    fi

    echo ""
    echo "✅ Restore complete"
    echo ""
    echo "⚠️  PENTING: Hapus plaintext file setelah selesai:"
    echo "   shred -u $target"
}

# ===== Main dispatch =====
case "${1:-}" in
    --list|"")
        list_backups
        echo ""
        echo "Usage: $0 <backup.gpg> [--stdout | --target <path>]"
        ;;
    *)
        BACKUP_FILE="$1"
        shift
        if [ "$1" = "--stdout" ]; then
            do_restore "$BACKUP_FILE" "" true
        elif [ "$1" = "--target" ]; then
            do_restore "$BACKUP_FILE" "$2" false
        else
            do_restore "$BACKUP_FILE" "" false
        fi
        ;;
esac
