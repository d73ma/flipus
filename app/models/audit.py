from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, func

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    id_rekap_mingguan = Column(String(64), index=True)

    nomor_kuitansi_token = Column(String(32), index=True)
    porsi_dana_misi = Column(BigInteger)

    verifikasi_sintaks_ai = Column(String(32))  # VALID_MATCH / NEED_REVIEW
    action = Column(String(64))                  # CREATE / ANONYMIZE / PURGED / SYNC
    payload_hash = Column(String(64))           # hash unik untuk audit anti-tamper

    created_at = Column(DateTime, server_default=func.now())
