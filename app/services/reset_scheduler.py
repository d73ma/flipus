"""
FLIPUS v1.1 — Auto-reset scheduler.

Tugas: deteksi "Sabat pertama di bulan Januari" → trigger reset counter urutan.
Counter urutan di sini ditangani oleh generator (auto increment per bulan),
jadi reset yang sebenarnya = LOG event + opsional purge old audit data.

Untuk v1.1: scheduler cukup LOG event + kirim notifikasi ke Jerry via WA.

Jalankan: scheduler.start() dari app/main.py saat startup, atau sebagai
standalone script: `python -m app.services.reset_scheduler`
"""

from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.utils.sabat_counter import get_sabat_info
from app.services.whatsapp import send_simple_message
from app.services import backup_service
from app.core.config import settings


def _is_first_saturday_of_january(tgl: datetime) -> bool:
    """Cek apakah tgl adalah Sabtu pertama di bulan Januari."""
    return tgl.month == 1 and tgl.weekday() == 5 and tgl.day <= 7


def _is_first_saturday_of_month(tgl: datetime) -> bool:
    """Cek apakah tgl adalah Sabtu pertama di bulan apapun."""
    return tgl.weekday() == 5 and tgl.day <= 7


def reset_counter_sequences():
    """
    Action yang dijalankan tiap Sabtu pertama di bulan Januari.

    Untuk v1.1: cukup LOG + kirim notifikasi ke Jerry.
    Counter urutan otomatis reset tiap bulan Romawi via generator_new_nomor_kuitansi
    (counter increment per (bulan, jemaat), jadi naturally reset tiap bulan).
    """
    tgl = datetime.now()
    if not _is_first_saturday_of_january(tgl):
        return

    sabat_info = get_sabat_info(tgl)
    msg = (
        f"[FLIPUS RESET SCHEDULER]\n\n"
        f"Tanggal: {sabat_info['tanggal_sabat']}\n"
        f"Sabat ke-{sabat_info['sabat_ke']} tahun {sabat_info['tahun']}\n\n"
        f"Ini adalah Sabtu pertama di bulan Januari.\n"
        f"Counter urutan kuitansi untuk semua jemaat AKAN RESET ke 1\n"
        f"untuk bulan Januari {sabat_info['tahun']}.\n\n"
        f"Audit log akan otomatis mencatat event ini."
    )

    # Kirim WA ke Jerry (nomor hardcoded untuk v1.1)
    jerry_wa = "6285750113010"  # dari memory
    try:
        send_simple_message(jerry_wa, msg)
    except Exception:
        pass

    print(f"[RESET SCHEDULER] {msg}")


def start_scheduler():
    """
    Start background scheduler. Dipanggil sekali saat app startup.

    Jobs:
    1. Auto-backup DB — setiap hari jam 02:00 UTC
    2. Reset counter — setiap Sabtu jam 08:00 UTC (filter Sabtu pertama Januari)
    3. Notification cleanup — setiap hari jam 03:00 UTC (T24: cleanup >90 days old)
    """
    scheduler = BackgroundScheduler(timezone="UTC")

    # Auto-backup harian
    scheduler.add_job(
        auto_backup_daily,
        trigger=CronTrigger(hour=2, minute=0),
        id="auto_backup_daily",
        name="Auto-backup DB (daily 02:00 UTC)",
        replace_existing=True,
    )

    # Reset counter (Sabtu pertama Januari only)
    scheduler.add_job(
        reset_counter_sequences,
        trigger=CronTrigger(day_of_week="sat", hour=8, minute=0),
        id="reset_first_saturday_january",
        name="Auto-reset on first Saturday of January",
        replace_existing=True,
    )

    # T24: Notification cleanup (delete >90 days old) — daily 03:00 UTC
    scheduler.add_job(
        cleanup_notifications_daily,
        trigger=CronTrigger(hour=3, minute=0),
        id="notification_cleanup_daily",
        name="Notification cleanup (daily 03:00 UTC, retention 90 days)",
        replace_existing=True,
    )

    scheduler.start()
    print("[SCHEDULER] Started — backup 02:00, reset Sat 08:00, notif cleanup 03:00 UTC")
    return scheduler


def cleanup_notifications_daily():
    """
    T24: Daily cleanup of notifications older than retention period.
    Called by APScheduler. Retention default: 90 days (configurable via env).
    """
    import os
    from app.core.database import SessionLocal
    from app.services.notification_service import cleanup_old_notifications

    retention_days = int(os.getenv("NOTIFICATION_RETENTION_DAYS", "90"))

    db = SessionLocal()
    try:
        deleted = cleanup_old_notifications(db, retention_days=retention_days)
        print(f"[NOTIFICATION CLEANUP] Deleted {deleted} notifications (>{retention_days} days)")
    except Exception as e:
        print(f"[NOTIFICATION CLEANUP] Error: {e}")
    finally:
        db.close()


# ===== Manual trigger (untuk testing) =====

def trigger_reset_now():
    """Trigger reset langsung (untuk testing atau recovery oleh Jerry)."""
    print("[MANUAL RESET] Triggered")
    reset_counter_sequences()


# ===== Auto-backup =====

def auto_backup_daily():
    """
    Auto-backup DB tiap hari jam 02:00 UTC (= 10:00 WITA, 09:00 WIB).

    Strategy:
    - Binary copy (cepat, ratusan KB)
    - Retention 7 hari (cleanup yang lebih lama)
    - Notifikasi ke Jerry kalau backup gagal
    """
    try:
        result = backup_service.backup_database(retention=7)
        print(f"[AUTO-BACKUP] {result['filename']} ({result['size_bytes']:,} bytes)")
        return result
    except Exception as e:
        # Notifikasi Jerry kalau gagal
        jerry_wa = "6285750113010"
        msg = f"[FLIPUS AUTO-BACKUP GAGAL]\n\n{str(e)}\n\nCek DB & storage/backups/ segera."
        try:
            send_simple_message(jerry_wa, msg)
        except Exception:
            pass
        print(f"[AUTO-BACKUP] GAGAL: {e}")
        raise


def trigger_backup_now():
    """Trigger backup langsung (untuk testing atau recovery)."""
    print("[MANUAL BACKUP] Triggered")
    return auto_backup_daily()


if __name__ == "__main__":
    # Standalone: jalan sebagai script
    print("=== Reset Scheduler — Manual Run ===")
    trigger_reset_now()
