"""
v1.5-C — BlastJob model.

Idempotency table untuk WA blast. Cegah double-blast kalau user
menekan tombol "Kirim" dua kali sebelum request pertama selesai.

Flow:
1. Frontend generates UUID idempotency_key per click
2. POST /v1/reports/blast-weekly?idem_key=<uuid>
3. Backend cek BlastJob WHERE idempotency_key = <uuid>
   - Ada → return response yg tersimpan (no re-send)
   - Tidak ada → create job + send + simpan response
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, UniqueConstraint, Index
from sqlalchemy.sql import func
from app.core.database import Base


class BlastJob(Base):
    __tablename__ = "blast_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    idempotency_key = Column(String(64), nullable=False)
    id_rekap_mingguan = Column(String(64), nullable=False, index=True)

    status = Column(String(16), nullable=False, default="pending")  # pending / sent / failed / duplicate
    target_phone = Column(String(32), nullable=True)
    fonnte_response = Column(JSON, nullable=True)
    error_reason = Column(String(255), nullable=True)
    pdf_filename = Column(String(255), nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_blast_jobs_idem"),
        Index("ix_blast_jobs_rekap", "id_rekap_mingguan", "tenant_id"),
    )