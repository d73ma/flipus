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
from app.services.financial_calculator import calculate_distribution
from app.services.notification_service import create_notification, EventType
from app.services.whatsapp import get_device_status

router = APIRouter()


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


@router.get("/fonnte/device-status", response_model=FonnteDeviceStatusOut)
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


@router.post("/trigger-reset", response_model=ManualResetOut)
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


@router.post("/backup-db", response_model=BackupOut)
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


@router.get("/backups", response_model=BackupListOut)
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


@router.post("/restore-db", response_model=RestoreOut)
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

@router.post("/trigger-backup", response_model=BackupOut)
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


@router.post("/recompute-porsi", response_model=RecomputePorsiOut)
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
            # Fallback default
            cfg_x, cfg_pt, cfg_kh = 1.0, 0.5, 0.5
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
            dist = calculate_distribution(
                perpuluhan_x=k.perpuluhan_x_angka,
                pt=k.pt_angka,
                khusus=k.khusus_angka,
                pct_x_jemaat=cfg_x,
                pct_pt_jemaat=cfg_pt,
                pct_khusus_jemaat=cfg_kh,
                pct_x_uni=cfg_xu,
                pct_pt_uni=cfg_ptu,
                pct_khusus_uni=cfg_khu,
            )
            old_misi = k.porsi_kantor_misi
            old_jemaat = k.porsi_kas_jemaat
            k.porsi_kantor_misi = dist["porsi_kantor_misi"]
            k.porsi_kas_jemaat = dist["porsi_kas_jemaat"]
            k.porsi_khusus_misi = dist["porsi_khusus_misi"]
            k.porsi_khusus_jemaat = dist["porsi_khusus_jemaat"]
            if old_misi != dist["porsi_kantor_misi"] or old_jemaat != dist["porsi_kas_jemaat"]:
                updated += 1

    db.add(AuditLog(
        tenant_id=current_user["tenant_id"],
        action=f"RECOMPUTE_PORSI_by_user_{current_user['id']}_tenants_{tenant_ids}",
        payload_hash=f"processed={processed},updated={updated}",
    ))
    db.commit()

    return RecomputePorsiOut(
        status="ok",
        kuitansi_processed=processed,
        kuitansi_updated=updated,
        note=f"Recompute selesai. {updated} dari {processed} kuitansi ter-update.",
    )


# ===== Audit Logs =====

class AuditLogOut(BaseModel):
    id: int
    tenant_id: int
    action: str
    payload_hash: Optional[str] = None
    porsi_dana_misi: int = 0
    id_rekap_mingguan: Optional[str] = None
    created_at: str


class AuditLogsOut(BaseModel):
    logs: List[AuditLogOut]
    count: int
    page: int
    per_page: int


@router.get("/audit-logs", response_model=AuditLogsOut)
def list_audit_logs(
    page: int = 1,
    per_page: int = 50,
    action_like: Optional[str] = None,
    tenant_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List audit logs dengan pagination & filter.

    Args:
        page: page number (default 1)
        per_page: items per page (default 50, max 200)
        action_like: substring filter untuk action (e.g., "BLAST", "REGISTER")
        tenant_id: filter by specific tenant (default: all)

    RBAC: ADMIN_UNI only.
    """
    if current_user["role"] != "ADMIN_UNI":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Admin Uni (Jerry)")

    if per_page > 200:
        per_page = 200
    if per_page < 1:
        per_page = 50
    if page < 1:
        page = 1

    q = db.query(AuditLog)
    if action_like:
        q = q.filter(AuditLog.action.like(f"%{action_like}%"))
    if tenant_id is not None:
        q = q.filter(AuditLog.tenant_id == tenant_id)

    total = q.count()
    logs = (
        q.order_by(AuditLog.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    items = []
    for l in logs:
        items.append(AuditLogOut(
            id=l.id,
            tenant_id=l.tenant_id,
            action=l.action or "UNKNOWN",
            payload_hash=l.payload_hash,
            porsi_dana_misi=l.porsi_dana_misi or 0,
            id_rekap_mingguan=l.id_rekap_mingguan,
            created_at=l.created_at.isoformat() if l.created_at else "",
        ))

    return AuditLogsOut(
        logs=items,
        count=total,
        page=page,
        per_page=per_page,
    )

