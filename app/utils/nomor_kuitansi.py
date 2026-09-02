"""
FLIPUS v1.1 — Generator nomor kuitansi.

Format: `{urutan:03d}/{initial_jemaat}/{bulan_romawi}/{tahun_2digit}`
Contoh: `001/NT/I/27` (Sabat ke-1, jemaat Nataan, bulan Januari, tahun 2027)

Reset per bulan (counter urut dari 1 tiap awal bulan Romawi).
"""

from datetime import datetime
from typing import Optional


# Konversi bulan (1-12) → Romawi
_BULAN_ROMAN = {
    1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI",
    7: "VII", 8: "VIII", 9: "IX", 10: "X", 11: "XI", 12: "XII",
}


def bulan_ke_romawi(bulan: int) -> str:
    """1 → 'I', 12 → 'XII'."""
    if bulan < 1 or bulan > 12:
        raise ValueError(f"Bulan harus 1-12, dapat: {bulan}")
    return _BULAN_ROMAN[bulan]


def generate_nomor_kuitansi(
    urutan: int,
    initial_jemaat: str,
    tanggal: Optional[datetime] = None,
) -> str:
    """
    Generate nomor kuitansi sesuai format GMAHK.

    Args:
        urutan: nomor urut (1, 2, 3, ...) - reset per bulan
        initial_jemaat: 2 huruf inisial jemaat (misal "NT" untuk Nataan)
        tanggal: datetime object (default: now)

    Returns:
        String format `001/NT/I/27`
    """
    if urutan < 1:
        raise ValueError(f"urutan harus >= 1, dapat: {urutan}")
    if not initial_jemaat or len(initial_jemaat) < 1:
        raise ValueError("initial_jemaat wajib diisi")

    # Normalisasi initial: uppercase, max 4 char
    initial = initial_jemaat.upper().strip()[:4]

    tgl = tanggal or datetime.now()
    bulan_romawi = bulan_ke_romawi(tgl.month)
    tahun_2d = str(tgl.year)[-2:].zfill(2)

    return f"{urutan:03d}/{initial}/{bulan_romawi}/{tahun_2d}"


def generate_id_rekap_mingguan(tanggal: Optional[datetime] = None) -> str:
    """
    Generate id_rekap_mingguan per minggu (Sabat).

    Format: `RK-{YYYYMMDD}-{iso_week}`
    Contoh: RK-20260822-34
    """
    tgl = tanggal or datetime.now()
    iso_year, iso_week, _ = tgl.isocalendar()
    return f"RK-{tgl.strftime('%Y%m%d')}-{iso_year}W{iso_week:02d}"
