"""
FLIPUS v1.1 — Sabat counter utility.

Sabat = hari Sabtu (hari ke-6 dalam ISO week).
Counter "Sabat ke-N" dihitung dari awal tahun (reset tiap 1 Januari).

Logika:
- Cari Sabtu di minggu yang sama atau sebelumnya (pakai weekday % 7)
- Hitung berapa Sabtu sejak Sabtu pertama di tahun tersebut
"""

from datetime import datetime, timedelta


def get_sabat_info(tanggal: datetime = None) -> dict:
    """
    Hitung info Sabat untuk tanggal tertentu.

    Returns:
        {
            "sabat_ke": int,         # 1, 2, 3, ... (reset tiap 1 Jan)
            "tanggal_sabat": str,    # ISO date "2026-08-22"
            "hari": str,             # "Sabtu"
            "tahun": int
        }
    """
    tgl = tanggal or datetime.now()

    # Hari dalam minggu: Monday=0, ..., Saturday=5, Sunday=6
    # Cari Sabtu di minggu yang sama (mundur dari tgl)
    if tgl.weekday() == 5:
        # Sudah hari Sabtu
        sabat_ini = tgl
    elif tgl.weekday() == 6:
        # Hari Minggu → sabat kemarin
        sabat_ini = tgl - timedelta(days=1)
    else:
        # Senin-Jumat → mundur ke Sabtu minggu ini
        sabat_ini = tgl - timedelta(days=tgl.weekday() + 2)

    # Cari Sabtu pertama di tahun sabat_ini
    start_of_year = datetime(sabat_ini.year, 1, 1)
    # Saturday = weekday 5
    days_to_first_saturday = (5 - start_of_year.weekday()) % 7
    first_saturday = start_of_year + timedelta(days=days_to_first_saturday)

    # Hitung sabat ke-N
    sabat_ke = ((sabat_ini - first_saturday).days // 7) + 1

    return {
        "sabat_ke": sabat_ke,
        "tanggal_sabat": sabat_ini.strftime("%Y-%m-%d"),
        "hari": "Sabtu",
        "tahun": sabat_ini.year,
    }


def get_current_sabat() -> dict:
    """Convenience: info sabat untuk hari ini."""
    return get_sabat_info()


def get_effective_sabat_for_input(now: datetime = None) -> dict:
    """
    T111 (2026-08-26): Aturan bisnis Jerry — semua input data (OCR, WA, manual)
    yang masuk SETELAH hari Sabat harus ditambahkan ke SABAT TERAKHIR YANG SUDAH
    LEWAT (bukan sabat masa depan).

    Logika sama dengan get_sabat_info() (last Saturday ≤ today), tapi disediain
    sebagai helper terpisah supaya semantik jelas di call site:
    - OCR scan
    - WA staging item
    - Input manual Bendahara

    Contoh (asumsi hari ini Wed 2026-08-26):
        - Wed 2026-08-26 → sabat 2026-08-22 (Sabat ke-34) ✓
        - Sat 2026-08-22 → sabat 2026-08-22 (Sabat ke-34) ✓
        - Sun 2026-08-23 → sabat 2026-08-22 (bukan 2026-08-24) ✓

    Returns: dict {sabat_ke, tanggal_sabat, hari, tahun}.
    """
    return get_sabat_info(now)
