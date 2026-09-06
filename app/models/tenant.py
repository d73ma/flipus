from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Tenant(Base):
    """
    FLIPUS v1.3 — Tenant model (Tahap 20 SaaS extension).

    Setiap jemaat (level 3) adalah 1 tenant. Auditor Misi & Admin Uni juga
    punya tenant placeholder (nama_jemaat_lokal = "[AUDITOR-...]" / "[ADMIN-...]")
    untuk scope transaksi.

    Identity (backward-compat):
      - tenant_signature: SHA-256(uni|misi|jemaat|salt) untuk license guard (anti-clone)
      - (uni, nama_kantor_misi, nama_jemaat_lokal): composite identity (legacy)

    New SaaS identity (Tahap 20):
      - slug:        URL-safe identifier (auto-generated, unique)
      - subdomain:   optional custom subdomain (e.g. "nataan" → nataan.flipus.app)
      - plan:        subscription plan (free / standard / premium)
      - status:      lifecycle (active / suspended / archived)
      - owner_user_id: FK → users.id (primary contact / owner of this tenant)
      - contact_email: tenant admin email
      - contact_phone: tenant admin phone (non-WA, optional)

    Status flow:
      - active:    bisa login & transaksi
      - suspended: sementara ditahan (admin hold)
      - archived:   jangka panjang nonaktif (misal jemaat merger)

    Migration notes (FASE 3 Sprint 4 — S4-E):
      - Migrated dari `Column[T]` legacy ke SQLAlchemy 2.0 `Mapped[T]` style.
      - Field types sekarang eksplisit via `Mapped[...]` annotation, sehingga
        mypy bisa infer tipe kolom tanpa `disable_error_code = ["arg-type", "assignment"]`.
      - Runtime behavior identik: kolom, index, FK, default, onupdate semua
        diwariskan dari `mapped_column(...)` kwargs yang sama dengan `Column(...)`.
    """

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ===== License guard (legacy, preserved) =====
    tenant_signature: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # ===== Organizational identity (Level 1-3) =====
    nama_uni: Mapped[str] = mapped_column(String(120), nullable=False)
    nama_kantor_misi: Mapped[str] = mapped_column(String(120), nullable=False)
    nama_jemaat_lokal: Mapped[str] = mapped_column(String(120), nullable=False)

    # Pejabat (Level 2)
    nama_pendeta: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, default=None)
    nama_ketua_keuangan: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, default=None)
    nama_bendahara: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, default=None)

    # Inisial jemaat (untuk format nomor kuitansi: 001/NT/I/27).
    initial_jemaat: Mapped[Optional[str]] = mapped_column(String(4), nullable=True, default=None)

    # FK ke Misi/Konferens (opsional, untuk aggregation tier 2)
    misi_konferens_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("misi_konferens.id"),
        nullable=True,
        default=None,
    )

    # ===== SaaS identity (Tahap 20) =====
    slug: Mapped[Optional[str]] = mapped_column(String(80), unique=True, nullable=True, index=True, default=None)
    subdomain: Mapped[Optional[str]] = mapped_column(String(80), unique=True, nullable=True, index=True, default=None)
    plan: Mapped[str] = mapped_column(String(20), nullable=False, default="free")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    # Owner metadata
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", use_alter=True, name="fk_tenants_owner_user_alter"),
        nullable=True,
        default=None,
    )
    contact_email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, default=None)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, default=None)

    # ===== Branding (Tahap 21) =====
    # Logo URL/path (relative ke /storage, served via static endpoint)
    logo_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default=None)
    # Primary color (hex, misal "#1B4332" = Sabbath green). Default ke green theme.
    primary_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#1B4332")
    # Secondary color (hex). Default ke cream theme.
    secondary_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#F5EFE0")
    # Footer text (tampil di PDF + akhir pesan WA)
    footer_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default=None)
    # Updated branding timestamp + actor
    branding_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)
    branding_updated_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", use_alter=True, name="fk_tenants_branding_updated_by_alter"),
        nullable=True,
        default=None,
    )

    # ===== Lifecycle =====
    # is_active tetap dipakai (legacy alias untuk status="active")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Composite index untuk query by uni + misi
    __table_args__ = (
        Index("ix_tenant_uni_misi", "nama_uni", "nama_kantor_misi"),
    )

    # ===== Domain helpers =====
    @property
    def is_active_status(self) -> bool:
        """Status aktif = status active AND is_active True."""
        return self.status == "active" and bool(self.is_active)
