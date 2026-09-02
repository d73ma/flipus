"""
FLIPUS v1.1 — Admin endpoint (Jerry-only).

Endpoint manual untuk testing / recovery:
- POST /admin/trigger-reset — manual trigger reset scheduler
- POST /admin/backup-db — backup DB ke storage/backups/
- GET  /admin/backups — list semua backup files
- POST /admin/restore-db — restore DB dari backup file
- POST /admin/recompute-porsi — recompute porsi_kantor_misi/porsi_kas_jemaat kuitansi existing
                                (pakai PersentaseConfig yang sekarang aktif). Berguna setelah Auditor
                                ubah persentase dan ingin apply ke data lama juga.
"""

from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.audit import AuditLog
from app.models.master import PersentaseConfig, MisiKonferens
from app.models.tenant import Tenant
from app.models.transaction import Kuitansi
from app.models.user import User
from app.services import backup_service
# FASE 2 S4/R3: migrasi dari legacy calculate_distribution (Layer 1+2) ke Jerry Model B (compute_porsi).
# Single source of truth: semua call site yang recompute porsi harus pakai compute_porsi.
from app.utils.porsi_calculator import compute_porsi
from app.services.notification_service import create_notification, EventType
from app.services.whatsapp import get_device_status

router = APIRouter()


def _now() -> datetime:
    """FASE 2 S6/R5: helper UTC timestamp untuk porsi_recomputed_at & audit logs."""
    return datetime.now(timezone.utc)


# ===== Fonnte Device Status (v1.5-F) =====

class FonnteDeviceStatusOut(BaseModel):
    status: str  # 'connected' | 'disconnected' | 'disabled' | 'no_token' | 'error'
    device: Optional[str] = None
    phone: Optional[str] = None
    quota: Optional[int] = None
    quota_remaining: Optional[int] = None
    expired: Optional[str] = None
    reason: Optional[str] = None
    checked_at: str


@router.get("/fonnte/device-status", tags=['Admin'], response_model=FonnteDeviceStatusOut)
def get_fonnte_device_status(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    v1.5-F: Cek status device Fonnte (connected/disconnected/quota).

    RBAC: ADMIN_UNI only.
    Tujuannya biar Admin Uni bisa lihat apakah Fonnte device masih nyala
    sebelum blast WA — menghindari blast gagal karena device offline.
    """
    if current_user["role"] != "ADMIN_UNI":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Admin Uni yang boleh cek device Fonnte")

    info = get_device_status()
    from datetime import datetime, timezone
    info["checked_at"] = datetime.now(timezone.utc).isoformat()
    return info


# ===== Manual Reset =====

class ManualResetOut(BaseModel):
    status: str
    triggered_by: str
    note: str


@router.post("/trigger-reset", tags=['Admin'], response_model=ManualResetOut)
def trigger_manual_reset(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Manual trigger reset scheduler (Jerry-only).

    RBAC: ADMIN_UNI only (sebagai super-user Jerry).
    Trigger counter sequence reset & kirim notifikasi ke Jerry via WA.

    Untuk testing atau recovery, BUKAN untuk routine use.
    """
    if current_user["role"] != "ADMIN_UNI":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Admin Uni (Jerry)")

    from app.services.reset_scheduler import trigger_reset_now
    try:
        trigger_reset_now()
    except Exception as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Reset gagal: {e}")

    db.add(AuditLog(
        tenant_id=current_user["tenant_id"],
        action=f"MANUAL_RESET_user_{current_user['id']}",
        payload_hash="manual_reset",
    ))
    db.commit()

    return ManualResetOut(
        status="triggered",
        triggered_by=current_user["role"],
        note="Reset scheduler dipicu manual. Cek WA Jerry untuk notifikasi.",
    )


# ===== Backup DB =====

class BackupOut(BaseModel):
    status: str
    path: str
    filename: str
    size_bytes: int
    created_at: str
    old_backups_deleted: List[str] = []
    method: str


@router.post("/backup-db", tags=['Admin'], response_model=BackupOut)
def backup_db(
    method: str = "binary",
    retention: int = 7,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Backup DB ke storage/backups/.

    Args:
        method: 'binary' (default, cepat) atau 'sql' (portable, lebih lambat)
        retention: berapa backup terakhir yang disimpan (default 7)

    Returns:
        BackupOut dengan path, filename, size_bytes, dll
    """
    if current_user["role"] != "ADMIN_UNI":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Admin Uni (Jerry)")

    try:
        if method == "sql":
            result = backup_service.backup_database_sql(retention=retention)
        else:
            result = backup_service.backup_database(retention=retention)
    except FileNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except Exception as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Backup gagal: {e}")

    db.add(AuditLog(
        tenant_id=current_user["tenant_id"],
        action=f"BACKUP_DB_user_{current_user['id']}_{method}",
        payload_hash=result["filename"],
    ))
    db.commit()

    # T24: Notify ALL ADMIN_UNI users about backup completion
    all_admins = (
        db.query(User)
        .filter(User.role == "ADMIN_UNI", User.is_active == True)  # noqa: E712
        .all()
    )
    size_mb = round(result["size_bytes"] / 1024 / 1024, 2)
    for admin in all_admins:
        create_notification(
            db,
            user_id=admin.id,
            tenant_id=admin.tenant_id,
            event_type=EventType.BACKUP_COMPLETED,
            title=f"Backup {method.upper()} selesai",
            message=(
                f"Backup {result['filename']} ({size_mb} MB) berhasil dibuat. "
                f"Retention: {retention} file, {len(result.get('old_backups_deleted', []))} "
                f"backup lama dihapus."
            ),
            link="/admin",
            related_entity_type="backup",
            related_entity_id=result["filename"],
            extra_data={
                "method": method,
                "size_bytes": result["size_bytes"],
                "retention": retention,
                "deleted_count": len(result.get("old_backups_deleted", [])),
            },
            actor_user_id=current_user["id"],
            commit=False,
        )
    db.commit()

    return BackupOut(**result)


class BackupItemOut(BaseModel):
    filename: str
    path: str
    size_bytes: int
    created_at: str
    kind: str


class BackupListOut(BaseModel):
    backups: List[BackupItemOut]
    count: int


@router.get("/backups", tags=['Admin'], response_model=BackupListOut)
def list_backups(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List semua backup files di storage/backups/. READ ONLY."""
    if current_user["role"] != "ADMIN_UNI":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Admin Uni (Jerry)")

    items = backup_service.list_backups()
    return BackupListOut(
        backups=[BackupItemOut(**i) for i in items],
        count=len(items),
    )


# ===== Restore DB =====

class RestoreIn(BaseModel):
    filename: str
    auto_backup_before: bool = True


class RestoreOut(BaseModel):
    status: str
    restored_from: str
    filename: str
    auto_backup_path: str = None
    restored_at: str
    method: str


@router.post("/restore-db", tags=['Admin'], response_model=RestoreOut)
def restore_db(
    payload: RestoreIn,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Restore DB dari backup file.

    Safety:
    - Auto-backup DB sekarang sebelum restore (kalau auto_backup_before=True)
    - Validasi file exists + format
    - Overwrite file DB asli

    ⚠️ PERINGATAN: Restore akan menggandakan session Bendahara yang sedang
    aktif. User harus login ulang setelah restore.
    """
    if current_user["role"] != "ADMIN_UNI":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Admin Uni (Jerry)")

    try:
        result = backup_service.restore_database(
            filename=payload.filename,
            auto_backup_before=payload.auto_backup_before,
        )
    except FileNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except Exception as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Restore gagal: {e}")

    db.add(AuditLog(
        tenant_id=current_user["tenant_id"],
        action=f"RESTORE_DB_user_{current_user['id']}_from_{payload.filename}",
        payload_hash=payload.filename,
    ))
    db.commit()

    return RestoreOut(**result)


# ===== Manual Backup Trigger =====

@router.post("/trigger-backup", tags=['Admin'], response_model=BackupOut)
def trigger_manual_backup(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Manual trigger auto-backup (Jerry-only).
    Untuk testing atau backup ad-hoc.
    """
    if current_user["role"] != "ADMIN_UNI":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Admin Uni (Jerry)")

    from app.services.reset_scheduler import trigger_backup_now
    try:
        result = trigger_backup_now()
    except Exception as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Backup gagal: {e}")

    db.add(AuditLog(
        tenant_id=current_user["tenant_id"],
        action=f"MANUAL_BACKUP_user_{current_user['id']}",
        payload_hash=result["filename"],
    ))
    db.commit()

    # T24: Notify all admins about manual backup
    all_admins = (
        db.query(User)
        .filter(User.role == "ADMIN_UNI", User.is_active == True)  # noqa: E712
        .all()
    )
    size_mb = round(result["size_bytes"] / 1024 / 1024, 2)
    for admin in all_admins:
        create_notification(
            db,
            user_id=admin.id,
            tenant_id=admin.tenant_id,
            event_type=EventType.BACKUP_COMPLETED,
            title="Manual backup selesai",
            message=f"Backup manual {result['filename']} ({size_mb} MB) berhasil dibuat.",
            link="/admin",
            related_entity_type="backup",
            related_entity_id=result["filename"],
            actor_user_id=current_user["id"],
            commit=False,
        )
    db.commit()

    return BackupOut(**result)


# ===== Recompute Porsi =====

class RecomputePorsiOut(BaseModel):
    status: str
    kuitansi_processed: int
    kuitansi_updated: int
    note: str


@router.post("/recompute-porsi", tags=['Admin'], response_model=RecomputePorsiOut)
def recompute_porsi_all(
    tenant_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Recompute porsi_kantor_misi + porsi_kas_jemaat + porsi_khusus_* untuk semua kuitansi existing,
    pakai PersentaseConfig yang sekarang aktif di Misi tenant tersebut.

    Berguna setelah Auditor/Admin Ubah persentase pembagian dan ingin apply ke data historis juga.

    Args:
        tenant_id: optional — kalau None, recompute semua tenant di Uni caller.
                   Kalau diisi, recompute cuma tenant tsb (harus dalam Uni caller).

    RBAC: ADMIN_UNI only.
    """
    if current_user["role"] != "ADMIN_UNI":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Admin Uni (Jerry)")

    # Determine tenant scope
    if tenant_id is not None:
        target = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not target:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
        caller = db.query(Tenant).filter(Tenant.id == current_user["tenant_id"]).first()
        if not caller or target.nama_uni != caller.nama_uni:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant di luar Uni Anda")
        tenant_ids = [tenant_id]
    else:
        caller = db.query(Tenant).filter(Tenant.id == current_user["tenant_id"]).first()
        if not caller or not caller.nama_uni:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Caller belum terkait Uni")
        tenant_ids = [
            t.id for t in db.query(Tenant).filter(Tenant.nama_uni == caller.nama_uni).all()
        ]

    processed = 0
    updated = 0

    for tid in tenant_ids:
        tenant = db.query(Tenant).filter(Tenant.id == tid).first()
        if not tenant or not tenant.misi_konferens_id:
            continue

        # Get PersentaseConfig MISI scope
        cfg = (
            db.query(PersentaseConfig)
            .filter(PersentaseConfig.scope == "MISI", PersentaseConfig.ref_id == tenant.misi_konferens_id)
            .first()
        )
        if not cfg:
            # Fallback default (SDA doctrine T101: pct_x_jemaat=0.0, 100% X ke Misi)
            cfg_x, cfg_pt, cfg_kh = 0.0, 0.5, 0.5
            cfg_xu, cfg_ptu, cfg_khu = 0.0, 0.0, 0.0
        else:
            cfg_x = cfg.pct_x_jemaat
            cfg_pt = cfg.pct_pt_jemaat
            cfg_kh = cfg.pct_khusus_jemaat
            cfg_xu = cfg.pct_x_uni
            cfg_ptu = cfg.pct_pt_uni
            cfg_khu = cfg.pct_khusus_uni

        # Get all kuitansi non-purged for this tenant
        kuitansis = (
            db.query(Kuitansi)
            .filter(Kuitansi.tenant_id == tid, Kuitansi.is_purged == False)  # noqa: E712
            .all()
        )
        for k in kuitansis:
            processed += 1
            # FASE 2 S4/R3: pakai Jerry Model B (compute_porsi), bukan legacy calculate_distribution
            porsi = compute_porsi(
                x=k.perpuluhan_x_angka,
                pt=k.pt_angka,
                kh=k.khusus_angka,
                pct_x_jemaat=cfg_x,
                pct_pt_jemaat=cfg_pt,
                pct_khusus_jemaat=cfg_kh,
                pct_x_uni=cfg_xu,
                pct_pt_uni=cfg_ptu,
                pct_khusus_uni=cfg_khu,
            )
            new_kantor_misi = porsi["pm_x"] + porsi["pm_pt"] + porsi["pm_kh"]
            new_kas_jemaat = porsi["pj_x"] + porsi["pj_pt"] + porsi["pj_kh"]
            old_misi = k.porsi_kantor_misi
            old_jemaat = k.porsi_kas_jemaat
            k.porsi_kantor_misi = new_kantor_misi
            k.porsi_kas_jemaat = new_kas_jemaat
            k.porsi_khusus_misi = porsi["pm_kh"]
            k.porsi_khusus_jemaat = porsi["pj_kh"]
            # FASE 2 S5/R4: simpan porsi Uni juga
            k.porsi_x_uni = porsi["pu_x"]
            k.porsi_pt_uni = porsi["pu_pt"]
            k.porsi_khusus_uni = porsi["pu_kh"]
            # FASE 2 S6/R5: timestamp recompute + audit log per-kuitansi (sebelum commit)
            k.porsi_recomputed_at = _now()
            if old_misi != new_kantor_misi or old_jemaat != new_kas_jemaat:
                updated += 1
            # Audit log per-kuitansi (untuk trace before/after snapshot)
            db.add(AuditLog(
                tenant_id=tid,
                id_rekap_mingguan=k.id_rekap_mingguan,
                nomor_kuitansi_token=k.nomor_kuitansi,
                action="recompute_porsi",
                porsi_dana_misi=new_kantor_misi,
                payload_hash=(
                    f"user={current_user['id']}|"
                    f"old_misi={old_misi}|old_jemaat={old_jemaat}|"
                    f"new_misi={new_kantor_misi}|new_jemaat={new_kas_jemaat}|"
                    f"cfg=pct_x_j={cfg_x},pct_pt_j={cfg_pt},pct_kh_j={cfg_kh},"
                    f"pct_x_u={cfg_xu},pct_pt_u={cfg_ptu},pct_kh_u={cfg_khu}|"
                    f"changed={old_misi != new_kantor_misi or old_jemaat != new_kas_jemaat}"
                ),
            ))

    # FASE 2 S6/R5: per-kuitansi audit log sudah ditulis di dalam loop.
    # Summary batch log tetap dicatat agar mudah difilter di AuditLog page.
    db.add(AuditLog(
        tenant_id=current_user["tenant_id"],
        action=f"RECOMPUTE_PORSI_BATCH_user_{current_user['id']}",
        payload_hash=(
            f"batch|processed={processed}|updated={updated}|"
            f"tenants={tenant_ids}"
        ),
    ))
    db.commit()

    return RecomputePorsiOut(
        status="ok",
        kuitansi_processed=processed,
        kuitansi_updated=updated,
        note=(
            f"Recompute selesai. {updated} dari {processed} kuitansi ter-update. "
            f"Audit log per-kuitansi sudah dicatat."
        ),
    )

