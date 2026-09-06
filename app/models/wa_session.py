"""T94 — WA Session (1 nomor pusat Fonnte, multi-jemaat, state machine per sender).

Tujuan: track state percakapan WA per nomor pengirim, dengan payload
JSON untuk simpan nominal X/PT/KH yang sedang di-input. TTL 30 menit
auto-reset ke IDLE.

Kolom:
- phone: VARCHAR(32) PK (nomor WA sender, format 628xxx)
- state: VARCHAR(32) NOT NULL DEFAULT 'IDLE' (state machine)
- payload: TEXT NULL (JSON staging draft {x, pt, kh, tenant_id, last_staging_id, ...})
- updated_at: DATETIME
- expires_at: DATETIME NULL (TTL 30 menit)
"""
from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy.sql import func

from app.core.database import Base


class WaSession(Base):
    __tablename__ = "wa_sessions"

    __table_args__ = (
        Index("ix_wa_sessions_state", "state"),
        Index("ix_wa_sessions_expires", "expires_at"),
    )

    phone = Column(String(32), primary_key=True)
    state = Column(String(32), nullable=False, default="IDLE")
    payload = Column(String, nullable=True)  # JSON string
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime, nullable=True)
