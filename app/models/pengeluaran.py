"""
v2.0 M5 — Model Pengeluaran (uang keluar jemaat).

Mirror Kuitansi dengan perbedaan:
- 1 kategori per Pengeluaran (1 transaksi = 1 kategori, bukan multi-item)
- Tidak ada PII (pengeluaran uang ke vendor/supplier, bukan umat)
- Approval dual-stage:
  * is_rutin=True (kategori): auto-approved oleh Bendahara saat create
  * is_rutin=False (kategori): perlu approval Ketua + Pendeta

Status workflow:
- 'draft' (Bendahara create, masih editable)
- 'pending_approval' (Bendahara submit, awaiting Ketua)
- 'approved_ketua' (Ketua sudah approve, awaiting Pendeta) — kalau perlu dual
- 'approved' (locked, sudah final approved oleh minimal 1 approver atau keduanya)
- 'rejected' (locked, ada reason)

Nomor pengeluaran: OUT-{YYYYMMDD}-{seq3} auto-generated per tenant per hari
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, BigInteger, Boolean, Index, func, Text
from app.core.database import Base


class Pengeluaran(Base):
    __tablename__ = "pengeluaran"

    __table_args__ = (
        Index("ix_pengeluaran_tenant_tanggal", "tenant_id", "tanggal"),
        Index("ix_pengeluaran_tenant_status_tanggal", "tenant_id", "status", "tanggal"),
        Index("ix_pengeluaran_tenant_kategori", "tenant_id", "kategori_pengeluaran_id"),
        Index("ix_pengeluaran_tenant_rekap", "tenant_id", "id_rekap_mingguan"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    id_rekap_mingguan = Column(String(64), nullable=False, index=True)

    # Identitas
    nomor_pengeluaran = Column(String(32), unique=True, nullable=False, index=True)  # OUT-YYYYMMDD-NNN
    tanggal = Column(String(16), nullable=False)  # ISO date (YYYY-MM-DD)
    tanggal_sabat = Column(String(16), nullable=False, index=True)  # link ke sabat periode

    # Detail transaksi
    kategori_pengeluaran_id = Column(Integer, ForeignKey("kategori_pengeluaran.id"), nullable=False)
    jumlah = Column(BigInteger, nullable=False, default=0)
    deskripsi = Column(String(500), nullable=True)
    penerima = Column(String(200), nullable=True)  # vendor/supplier/personil
    metode_bayar = Column(String(20), nullable=True)  # 'tunai'|'transfer'|'cek'|'lain'
    bukti_path = Column(String(255), nullable=True)  # path foto nota/kuitansi (opsional)
    is_purged = Column(Boolean, default=False)

    # Workflow approval
    status = Column(String(20), default='draft', nullable=False, index=True)
    # 'draft' | 'pending_approval' | 'approved_ketua' | 'approved' | 'rejected'

    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Ketua approval (wajib untuk non-rutin)
    approved_ketua_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_ketua_at = Column(DateTime, nullable=True)
    approved_ketua_note = Column(String(255), nullable=True)

    # Pendeta approval (wajib untuk non-rutin, setelah Ketua)
    approved_pendeta_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_pendeta_at = Column(DateTime, nullable=True)
    approved_pendeta_note = Column(String(255), nullable=True)

    # Rejection (siapa saja yang reject, status jadi terminal 'rejected')
    rejected_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    rejected_reason = Column(String(500), nullable=True)

    # Source tracking
    created_via = Column(String(16), default='web', nullable=False, index=True)  # 'web' | 'ocr' | 'wa'

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())