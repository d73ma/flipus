"""
v2.0 M5 — Model KategoriPengeluaran (kategori fleksibel per jemaat untuk Pengeluaran).

Mirror KategoriPemasukan tapi dengan flag is_rutin yang signifikan untuk approval workflow:
- is_rutin=True (Listrik, Air, Telpon, Gaji Kostor) → auto-approved oleh Bendahara
- is_rutin=False (lainnya) → butuh approval Ketua + Pendeta (dual-stage)

Aturan Jerry (2026-09-01):
- Default: Listrik (LIS), Air (AIR), Telpon (TLP), Gaji Kostor (KOSTOR) — semua is_rutin=True
- Custom kategori: Bendahara/Admin bisa tambah via UI
- Scope: per tenant (jemaat lokal)
"""
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, Index, func, UniqueConstraint
from app.core.database import Base


class KategoriPengeluaran(Base):
    """
    Master kategori pengeluaran per tenant (jemaat).

    Kolom:
    - id: PK
    - tenant_id: FK ke tenants (jemaat lokal)
    - nama: display name (misal "Listrik", "Pembangunan", "Sosial")
    - alias: short code (misal "LIS", "AIR", "TLP", "KOSTOR", "SOS") — unique per tenant
    - urutan: untuk sorting tampilan di tabel/form
    - is_rutin: True untuk operasional rutin (auto-skip approval), False untuk custom (perlu approval)
    - is_aktif: soft delete flag
    - created_at, updated_at: timestamp

    Constraint:
    - UNIQUE(tenant_id, alias) — tidak boleh duplikat alias per jemaat
    """
    __tablename__ = "kategori_pengeluaran"

    __table_args__ = (
        Index("ix_kategori_pengeluaran_tenant_active", "tenant_id", "is_aktif"),
        UniqueConstraint("tenant_id", "alias", name="uq_kategori_pengeluaran_tenant_alias"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    nama = Column(String(50), nullable=False)
    alias = Column(String(8), nullable=False)  # 2-4 char

    urutan = Column(Integer, default=999)
    is_rutin = Column(Boolean, default=False)
    is_aktif = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())