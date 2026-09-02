from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, func, Index
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
    """

    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ===== License guard (legacy, preserved) =====
    tenant_signature = Column(String(64), unique=True, nullable=False, index=True)

    # ===== Organizational identity (Level 1-3) =====
    nama_uni = Column(String(120), nullable=False)
    nama_kantor_misi = Column(String(120), nullable=False)
    nama_jemaat_lokal = Column(String(120), nullable=False)

    # Pejabat (Level 2)
    nama_pendeta = Column(String(120))
    nama_ketua_keuangan = Column(String(120))
    nama_bendahara = Column(String(120))

    # Inisial jemaat (untuk format nomor kuitansi: 001/NT/I/27).
    initial_jemaat = Column(String(4), nullable=True)

    # FK ke Misi/Konferens (opsional, untuk aggregation tier 2)
    misi_konferens_id = Column(Integer, ForeignKey("misi_konferens.id"), nullable=True)

    # ===== SaaS identity (Tahap 20) =====
    slug = Column(String(80), unique=True, nullable=True, index=True)
    subdomain = Column(String(80), unique=True, nullable=True, index=True)
    plan = Column(String(20), nullable=False, default="free")
    status = Column(String(20), nullable=False, default="active")

    # Owner metadata
    owner_user_id = Column(Integer, ForeignKey("users.id", use_alter=True, name="fk_tenants_owner_user_alter"), nullable=True)
    contact_email = Column(String(120), nullable=True)
    contact_phone = Column(String(32), nullable=True)

    # ===== Branding (Tahap 21) =====
    # Logo URL/path (relative ke /storage, served via static endpoint)
    logo_url = Column(String(255), nullable=True)
    # Primary color (hex, misal "#1B4332" = Sabbath green). Default ke green theme.
    primary_color = Column(String(7), nullable=False, default="#1B4332")
    # Secondary color (hex). Default ke cream theme.
    secondary_color = Column(String(7), nullable=False, default="#F5EFE0")
    # Footer text (tampil di PDF + akhir pesan WA)
    footer_text = Column(String(255), nullable=True)
    # Updated branding timestamp + actor
    branding_updated_at = Column(DateTime, nullable=True)
    branding_updated_by = Column(Integer, ForeignKey("users.id", use_alter=True, name="fk_tenants_branding_updated_by_alter"), nullable=True)

    # ===== Lifecycle =====
    # is_active tetap dipakai (legacy alias untuk status="active")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Composite index untuk query by uni + misi
    __table_args__ = (
        Index("ix_tenant_uni_misi", "nama_uni", "nama_kantor_misi"),
    )

    # ===== Domain helpers =====
    @property
    def is_active_status(self) -> bool:
        """Status aktif = status active AND is_active True."""
        return self.status == "active" and bool(self.is_active)
