"""
v1.5-A — JWT blacklist untuk logout.

Saat user logout, token JWT saat ini di-blacklist dengan menyimpan JTI
(JWT ID) ke tabel revoked_tokens. get_current_user cek blacklist
sebelum izinkan akses.

Tokens akan expire dengan sendirinya (default ACCESS_TOKEN_EXPIRE_MINUTES).
Kita tetap simpan revoked entry sampai exp — query sederhana: WHERE jti = ?
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Index
from sqlalchemy.sql import func

from app.core.database import Base


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # JWT ID claim (UUID4). Satu token = satu row.
    jti = Column(String(64), nullable=False, unique=True, index=True)

    # Audit trail (GDPR Art. 15 right-to-be-informed)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    # Waktu + alasan
    revoked_at = Column(DateTime, server_default=func.now(), nullable=False)
    reason = Column(String(64), nullable=False, default="logout")  # logout | stolen | rotated | forced

    # Token exp — untuk cleanup otomatis (opsional, scheduler bisa pakai)
    expires_at = Column(DateTime, nullable=False)


Index("ix_revoked_tokens_user", RevokedToken.user_id)
Index("ix_revoked_tokens_tenant", RevokedToken.tenant_id)