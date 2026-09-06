"""
FASE 3-S3.S8 — Refresh token server-side store.

Refresh token adalah long-lived credential (default 7 hari) yang digunakan
oleh endpoint `/api/v1/auth/refresh` untuk issue access token baru tanpa
user harus login ulang.

Kenapa disimpan server-side (bukan cuma decode JWT):
  1. **Revocation**: kalau refresh token bocor (device hilang, dll), admin
     bisa blacklist JTI tertentu tanpa menunggu expire otomatis.
  2. **Rotation detection**: setiap kali /refresh dipanggil, row lama
     di-mark `used_at` dan row baru dibuat. Kalau ada 2 attempt berbeda
     dengan refresh yang sama (atau satu sudah used), itu signal compromise
     → revoke seluruh chain untuk user_id tersebut (FASE 3-S3.S9).
  3. **Audit trail**: track siapa kapan refresh dari IP mana.

Skema:
  - jti (unique indexed) — identifier utama, sama dengan JTI di JWT
  - user_id, tenant_id — siapa yang punya
  - expires_at — untuk cleanup otomatis (opsional, scheduler bisa pakai)
  - used_at — set saat /refresh pakai token ini (NULL = masih valid)
  - revoked_reason — kalau revoked manual (logout-all, stolen, dll)
  - created_at, ip_address, user_agent — audit

Rotation pattern:
  Old:  (jti=A, used_at=None)
  New:  (jti=A, used_at=now), (jti=B, used_at=None)

Saat request berikutnya pakai jti=A lagi → sudah used → reject.
Saat jti=A pertama kali dipakai → mark used_at dan issue jti=B.
"""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # JWT ID claim (UUID4 hex). Satu refresh token = satu row.
    jti = Column(String(64), nullable=False, unique=True, index=True)

    # Audit trail + relasi
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)

    # Rotation: kalau di-set, token ini sudah pernah di-redeem.
    # NULL = masih valid untuk redeem. Non-NULL → second use = suspicious.
    used_at = Column(DateTime, nullable=True)

    # Revocation: kalau di-set, token di-blacklist permanen (logout-all,
    # stolen, forced, etc). None = aktif.
    revoked_at = Column(DateTime, nullable=True)
    revoked_reason = Column(String(64), nullable=True)

    # Audit info (untuk forensic investigation)
    created_ip = Column(String(64), nullable=True)
    created_user_agent = Column(String(255), nullable=True)
    redeemed_ip = Column(String(64), nullable=True)
    redeemed_user_agent = Column(String(255), nullable=True)


# Composite index untuk "cari semua refresh token milik user yang masih valid"
Index("ix_refresh_user_active", RefreshToken.user_id, RefreshToken.expires_at)
Index("ix_refresh_tenant_active", RefreshToken.tenant_id, RefreshToken.expires_at)
