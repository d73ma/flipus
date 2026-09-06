from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Recipient
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    # Event classification
    event_type = Column(String(40), nullable=False, index=True)
    # Values: KUITANSI_APPROVED, KUITANSI_REJECTED, KUITANSI_DRAFT_CREATED,
    #         WEEKLY_BLAST_DONE, BACKUP_COMPLETED, BACKUP_FAILED,
    #         PENDETA_REGISTERED, AUDITOR_REGISTERED, ADMIN_REGISTERED,
    #         TENANT_SUSPENDED, TENANT_ACTIVATED

    # Content
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    icon = Column(String(10), default="🔔")  # emoji prefix
    link = Column(String(500), nullable=True)  # e.g. /bendahara (deep link)

    # Related entity context (optional)
    related_entity_type = Column(String(40), nullable=True)  # "kuitansi" | "tenant" | "backup" | "user"
    related_entity_id = Column(String(64), nullable=True)   # string-typed to support various id formats
    extra_data = Column(JSON, nullable=True)                # flexible payload (kuitansi info, etc)

    # Read tracking
    is_read = Column(Boolean, default=False, nullable=False)
    read_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_notif_user_unread_created", "user_id", "is_read", "created_at"),
        Index("ix_notif_tenant_created", "tenant_id", "created_at"),
        Index("ix_notif_event_type", "event_type", "created_at"),
    )

    # Optional convenience relationship (back-populated lazily)
    # user = relationship("User", backref="notifications", lazy="select")
