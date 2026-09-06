"""
FLIPUS v1.1 — Counter urutan kuitansi per jemaat per bulan.

Reset otomatis tiap awal bulan (counter kembali ke 1).
"""
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.transaction import Kuitansi


def get_next_urutan(
    db: Session,
    tenant_id: int,
    bulan: int | None = None,
    tahun: int | None = None,
) -> int:
    """
    Hitung nomor urut berikutnya untuk jemaat tertentu di bulan/tahun tertentu.

    Returns: urutan berikutnya (1 jika belum ada kuitansi bulan ini)
    """
    now = datetime.now()
    bulan = bulan or now.month
    tahun = tahun or now.year

    # Filter by YYYY-MM di kolom tanggal_sabat (format ISO date string)
    prefix = f"{tahun:04d}-{bulan:02d}"

    count = (
        db.query(func.count(Kuitansi.id))
        .filter(Kuitansi.tenant_id == tenant_id)
        .filter(Kuitansi.tanggal_sabat.like(f"{prefix}%"))
        .scalar()
    ) or 0

    return count + 1
