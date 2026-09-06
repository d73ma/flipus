"""
v2.0 M3 — Model KategoriPemasukan (kategori fleksibel per jemaat).

Tabel ini menggantikan field hardcoded Kuitansi.perpuluhan_x_angka/pt_angka/khusus_angka.
v2.0 migration: Kuitansi.perpuluhan_x_angka dll tetap di-keep selama 1 release sebagai fallback baca.

Aturan Jerry (2026-08-27):
- Default: X (Perpuluhan) + PT (Persembahan Terpadu)
- KH tidak default — auto-create saat Bendahara pertama kali ketik
- Custom kategori apapun auto-create dengan smart alias
- Scope: per tenant (jemaat lokal)
- Siapa bisa menambah: hanya Bendahara jemaat (lihat RBAC v2.0)
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func

from app.core.database import Base


class KategoriPemasukan(Base):
    """
    Master kategori pemasukan per tenant (jemaat).

    Kolom:
    - id: PK
    - tenant_id: FK ke tenants (jemaat lokal)
    - nama: display name (misal "Perpuluhan", "Pembangunan", "Persembahan Khusus")
    - alias: short code (misal "X", "PT", "PEMB", "SS") — unique per tenant
    - urutan: untuk sorting tampilan di tabel/form
    - is_rutin: True untuk X/PT (default), False untuk custom
    - is_aktif: soft delete flag
    - created_at: timestamp

    Constraint:
    - UNIQUE(tenant_id, alias) — tidak boleh duplikat alias per jemaat
    - UNIQUE(tenant_id, LOWER(nama)) — handled di app layer (SQLite gak support functional index easily)
    """
    __tablename__ = "kategori_pemasukan"

    __table_args__ = (
        Index("ix_kategori_pemasukan_tenant_active", "tenant_id", "is_aktif"),
        UniqueConstraint("tenant_id", "alias", name="uq_kategori_pemasukan_tenant_alias"),
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


class KuitansiKategori(Base):
    """
    Pivot table: Kuitansi <-> KategoriPemasukan (many-to-many dengan nominal).

    Setiap baris Kuitansi bisa punya 1+ kategori dengan nominal masing-masing.
    v2.0 migration: data existing (perpuluhan_x_angka, pt_angka, khusus_angka)
    akan dimigrasikan ke tabel ini dengan kategori_id yang sesuai.
    """
    __tablename__ = "kuitansi_kategori"

    __table_args__ = (
        Index("ix_kuitansi_kategori_kuitansi", "kuitansi_id"),
        Index("ix_kuitansi_kategori_kategori", "kategori_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    kuitansi_id = Column(Integer, ForeignKey("kuitansi.id"), nullable=False, index=True)
    kategori_id = Column(Integer, ForeignKey("kategori_pemasukan.id"), nullable=False, index=True)
    nominal = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, server_default=func.now())
