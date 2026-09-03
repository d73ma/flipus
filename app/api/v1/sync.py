"""FLIPUS v1.1 — Sync API."""
import json
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core.security import decode_access_token
from app.models.transaction import Kuitansi
from app.models.tenant import Tenant
from app.models.user import User
from app.core.tenant_scope import TenantScope, require_tenant_scope
from app.models.audit import AuditLog
from app.models.sync import SyncOutbox
from app.services.anonymizer import anonymize_batch, verify_hash

router = APIRouter(tags=["sync"])
security = HTTPBearer(auto_error=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    payload = decode_access_token(creds.credentials)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    user = db.query(User).filter(User.id == int(payload.get("sub"))).first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user

@router.post("/upload", tags=['Sync'])
def upload_sync(db: Session = Depends(get_db), scope: TenantScope = Depends(require_tenant_scope)):
    """Jemaat push anonymized kuitansi ke sync_outbox."""
    if scope.role not in ("BENDAHARA", "KETUA_KEUANGAN"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya bendahara/ketua keuangan")
    # FASE4-S6H: pakai primary_tenant_id dari TenantScope (single source of truth).
    # Untuk BENDAHARA/KETUA_KEUANGAN, visible_tenant_ids selalu [primary_tenant_id]
    # sehingga hasilnya identik dengan filter lama.
    tenant_id = scope.primary_tenant_id
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    kuitansi_list = (
        db.query(Kuitansi)
        .filter(Kuitansi.tenant_id == tenant.id)
        .filter(Kuitansi.is_purged == False)
        .all()
    )
    payloads = anonymize_batch(kuitansi_list, tenant.nama_jemaat_lokal)
    inserted = 0
    for p in payloads:
        row = SyncOutbox(
            tenant_id=tenant.id,
            payload_json=json.dumps(p, ensure_ascii=False),
            payload_hash=p["payload_hash"],
        )
        db.add(row)
        inserted += 1
    total_porsi = sum(p["porsi_kantor_misi"] for p in payloads) if payloads else 0
    audit = AuditLog(
        tenant_id=tenant.id,
        action="SYNC_UPLOAD_user_{}".format(scope.user_id),
        payload_hash=payloads[0]["payload_hash"] if payloads else "",
        porsi_dana_misi=total_porsi,
    )
    db.add(audit)
    db.commit()
    return {"status": "ok", "tenant_id": tenant.id, "uploaded": inserted}

@router.get("/pull", tags=['Sync'])
def pull_sync(since: str = None, db: Session = Depends(get_db), scope: TenantScope = Depends(require_tenant_scope)):
    """Kantor Misi / Uni pull anonymized payload dari sync_outbox."""
    if scope.role not in ("AUDITOR_MISI", "ADMIN_UNI"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya auditor misi / admin uni")
    # FASE4-S6H: REAL FIX — filter via scope.visible_tenant_ids (sebelumnya
    # kode lama pakai user.tenant_id yg utk AUDITOR_MISI hanya 1 tenant).
    # Sekarang AUDITOR_MISI lihat SEMUA jemaat di misi caller, ADMIN_UNI lihat
    # SEMUA jemaat via chain uni → misi → jemaat.
    q = db.query(SyncOutbox).filter(SyncOutbox.pulled_at.is_(None))
    if scope.visible_tenant_ids:
        q = q.filter(SyncOutbox.tenant_id.in_(scope.visible_tenant_ids))
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            q = q.filter(SyncOutbox.created_at >= since_dt)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "since harus ISO datetime")
    rows = q.order_by(SyncOutbox.created_at.asc()).all()
    items = []
    for r in rows:
        payload = json.loads(r.payload_json)
        if not verify_hash(payload):
            continue
        payload["sync_outbox_id"] = r.id
        payload["tenant_id"] = r.tenant_id
        items.append(payload)
        r.pulled_at = datetime.now(timezone.utc)
    audit = AuditLog(
        tenant_id=scope.primary_tenant_id,
        action="SYNC_PULL_user_{}_count_{}".format(scope.user_id, len(items)),
        payload_hash=items[0]["payload_hash"] if items else "",
        porsi_dana_misi=sum(i["porsi_kantor_misi"] for i in items),
    )
    db.add(audit)
    db.commit()
    return {"status": "ok", "count": len(items), "items": items}