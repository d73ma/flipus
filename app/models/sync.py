"""FLIPUS v1.1 — SyncOutbox model."""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func, Index
from app.core.database import Base

class SyncOutbox(Base):
    """Anonymized payload jemaat siap di-pull Kantor Misi / Uni."""
    __tablename__ = "sync_outbox"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    payload_json = Column(String, nullable=False)
    payload_hash = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    pulled_at = Column(DateTime, nullable=True)
Index("ix_sync_outbox_tenant_created", SyncOutbox.tenant_id, SyncOutbox.created_at)