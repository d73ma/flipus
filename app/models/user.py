from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, JSON, func
from sqlalchemy.orm import relationship
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    username = Column(String(80), nullable=False)
    password_hash = Column(String(255), nullable=False)
    nama_lengkap = Column(String(120), nullable=False)
    nomor_whatsapp = Column(String(32))  # kept for lookup (login by phone, blast search)
    # v1.5-E: PII at-rest encryption. nomor_whatsapp_encrypted = Fernet(nomor_whatsapp).
    # API responses & outbound WA kirim decrypt dari kolom ini.
    nomor_whatsapp_encrypted = Column(String(255), nullable=True)

    # RBAC: ADMIN_UNI / AUDITOR_MISI / PENDETA / KETUA_KEUANGAN / BENDAHARA
    role = Column(String(32), nullable=False)

    tenant = relationship("Tenant", foreign_keys=[tenant_id])
    created_at = Column(DateTime, server_default=func.now())
    is_active = Column(Boolean, default=True)

    # T23-5: TOTP 2FA fields
    is_2fa_enabled = Column(Boolean, default=False, nullable=False)
    totp_secret_encrypted = Column(String(255), nullable=True)  # Fernet-encrypted base32 TOTP secret
    backup_codes_hashed = Column(JSON, nullable=True)  # List of bcrypt-hashed backup codes
    twofa_enabled_at = Column(DateTime, nullable=True)
    last_2fa_used_at = Column(DateTime, nullable=True)

    # v1.5-D: Track password change timestamp untuk auto-revoke semua token lama
    password_changed_at = Column(DateTime, nullable=True)
