"""
FLIPUS v1.1 — Master data 3-tier hierarchy.

Tabel:
- Uni: 3 master (UIKT, UIKB, UIKC)
- Misi_Konferens: 12 master (3 Konferens + 9 Misi), FK ke Uni
- PersentaseConfig: konfigurasi % pembagian X/PT/Khusus per Misi (Jemaat→Misi)
  dan per Uni (Misi→Uni). Diset oleh Auditor / Admin Uni.
"""

from sqlalchemy import Column, Integer, String, ForeignKey, Float, DateTime, func
from app.core.database import Base


class Uni(Base):
    """Master Uni (3 entitas)."""
    __tablename__ = "uni"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kode = Column(String(8), unique=True, nullable=False)  # UIKT / UIKB / UIKC
    nama_resmi = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class MisiKonferens(Base):
    """Master Misi/Konferens (12 entitas di bawah Uni)."""
    __tablename__ = "misi_konferens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uni_id = Column(Integer, ForeignKey("uni.id"), nullable=False, index=True)
    kode = Column(String(16), unique=True, nullable=False)  # DKM, DKL, DMM, ...
    nama_resmi = Column(String(255), nullable=False)
    jenis = Column(String(16), nullable=False)  # KONFERENS / MISI
    created_at = Column(DateTime, server_default=func.now())


class PersentaseConfig(Base):
    """
    Konfigurasi persentase pembagian.

    Scope:
    - "MISI": baris konfigurasi per Misi (Jemaat→Misi). Diatur oleh Auditor.
      Field: pct_x_jemaat, pct_pt_jemaat, pct_khusus_jemaat
    - "UNI": baris konfigurasi per Uni (Misi→Uni). Diatur oleh Admin Uni.
      Field: pct_x_uni, pct_pt_uni, pct_khusus_uni

    Ref_id merujuk ke id MisiKonferens (jika scope=MISI) atau id Uni (jika scope=UNI).
    """
    __tablename__ = "persentase_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scope = Column(String(16), nullable=False, index=True)  # MISI / UNI
    ref_id = Column(Integer, nullable=False, index=True)    # FK ke misi_konferens.id atau uni.id

    # Field Jemaat→Misi (diisi saat scope=MISI)
    pct_x_jemaat = Column(Float, default=1.0)       # default 100% X ke Misi
    pct_pt_jemaat = Column(Float, default=0.5)      # default 50% PT ke Misi
    pct_khusus_jemaat = Column(Float, default=0.5)  # default 50% Khusus ke Misi

    # Field Misi→Uni (diisi saat scope=UNI)
    pct_x_uni = Column(Float, default=0.0)
    pct_pt_uni = Column(Float, default=0.0)
    pct_khusus_uni = Column(Float, default=0.0)

    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
