from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, BigInteger, Boolean, Index, func
from sqlalchemy.orm import relationship
from app.core.database import Base

class Kuitansi(Base):
    __tablename__ = "kuitansi"

    # T22-5: Composite indexes untuk query pattern umum
    __table_args__ = (
        Index("ix_kuitansi_tenant_tanggal", "tenant_id", "tanggal_sabat"),
        Index("ix_kuitansi_tenant_purged_tanggal", "tenant_id", "is_purged", "tanggal_sabat"),
        Index("ix_kuitansi_tenant_nominal", "tenant_id", "total_pemberian_angka"),
        Index("ix_kuitansi_tenant_rekap", "tenant_id", "id_rekap_mingguan"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    id_rekap_mingguan = Column(String(64), nullable=False, index=True)

    nomor_kuitansi = Column(String(32), unique=True, nullable=False, index=True)
    tanggal_sabat = Column(String(16), nullable=False)  # ISO date

    # FIELD TER-ENKRIPSI (Fernet) — PII
    nama_umat_encrypted = Column(String, nullable=True)
    nomor_whatsapp_encrypted = Column(String, nullable=True)

    foto_amplop_path = Column(String, nullable=True)
    is_purged = Column(Boolean, default=False)

    # Nominal
    perpuluhan_x_angka = Column(BigInteger, default=0)
    pt_angka = Column(BigInteger, default=0)
    khusus_angka = Column(BigInteger, default=0)  # Persembahan Khusus (opsional)

    total_pemberian_angka = Column(BigInteger, default=0)
    total_pemberian_huruf = Column(String(255))

    # Distribusi otomatis (configurable via persentase_config)
    # - X: 100% ke Misi (atau sesuai pct_x_jemaat)
    # - PT: sebagian ke Misi, sisanya Kas Jemaat (atau sesuai pct_pt_jemaat)
    # - Khusus: sebagian ke Misi, sisanya Kas Jemaat (atau sesuai pct_khusus_jemaat)
    porsi_kantor_misi = Column(BigInteger, default=0)
    porsi_kas_jemaat = Column(BigInteger, default=0)
    porsi_khusus_misi = Column(BigInteger, default=0)  # Porsi Khusus yg ke Misi
    porsi_khusus_jemaat = Column(BigInteger, default=0)  # Porsi Khusus yg ke Jemaat

    created_at = Column(DateTime, server_default=func.now())

    # T23-1: Approval Workflow
    # Status: 'draft' (Bendahara created, awaiting Ketua approval)
    #         'finalized' (approved, locked, PDF/WA eligible)
    #         'rejected' (denied with reason)
    status = Column(String(20), default='finalized', nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejected_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    rejected_reason = Column(String(500), nullable=True)

    # T94 — WA Input Bot staging columns (2026-08-23)
    staging_id = Column(Integer, nullable=True, index=True)  # auto-increment sementara, NULL setelah finalize
    is_finalized = Column(Boolean, default=True, nullable=False, index=True)  # default True untuk row existing (backward-compat)
    finalized_at = Column(DateTime, nullable=True)
    created_via = Column(String(16), default='web', nullable=False, index=True)  # 'web' | 'ocr' | 'wa'
    wa_message_id = Column(String(64), nullable=True)  # Fonnte msg ID untuk anti-duplicate
    wa_sender = Column(String(32), nullable=True)  # nomor WA pengirim (audit trail)
    sabat_sesi = Column(String(16), nullable=True, index=True)  # 'YYYY-MM' untuk lock per sesi sabat
    temp_nomor = Column(String(32), nullable=True)  # placeholder 'STG-{staging_id}' saat staging
