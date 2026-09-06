"""
v2.0 M3 — Smart alias generator untuk kategori_pemasukan.

Aturan Jerry (2026-08-27):
- Kalau 2+ kata → ambil huruf pertama tiap kata (maks 3 kata)
- Kalau 1 kata → 4 huruf pertama
- Kata "persembahan" diabaikan
- Prefix "persembahan" di-strip sebelum proses

Contoh:
- "Sekolah Sabat" → "SS"
- "Persembahan Sekolah Sabat" → "SS"
- "Pembangunan" → "Pemb"
- "Persembahan Pembangunan" → "Pemb"
- "Ulang Tahun" → "UT"
- "Khusus" → "Khus"
- "Syukur" → "Suku"
- "Pendidikan" → "Pend"
"""
import re


def _strip_persembahan(nama: str) -> str:
    """Buang prefix 'persembahan' kalau ada."""
    cleaned = nama.strip()
    # Case-insensitive strip prefix
    cleaned = re.sub(r"^\s*persembahan\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def generate_alias(nama: str) -> str:
    """
    Generate alias pendek dari nama kategori.

    Args:
        nama: nama kategori full (misal "Persembahan Sekolah Sabat")

    Returns:
        Alias 2-4 char (misal "SS", "Pemb", "UT")
    """
    if not nama or not nama.strip():
        return "?"

    cleaned = _strip_persembahan(nama)
    if not cleaned:
        return "?"

    # Pisahkan jadi kata-kata, abaikan "persembahan" kalau masih ada
    words = [w for w in re.split(r"\s+", cleaned) if w and w.lower() != "persembahan"]

    if not words:
        return "?"

    if len(words) >= 2:
        # Multi-word: ambil huruf pertama tiap kata (max 3 kata biar tidak panjang)
        return "".join(w[0].upper() for w in words[:3])
    else:
        # Single word: 4 huruf pertama, uppercase semua
        word = words[0]
        return word[:4].upper()


def normalize_nama(nama: str) -> str:
    """Normalisasi nama untuk dedup: title-case, collapse whitespace."""
    cleaned = re.sub(r"\s+", " ", nama.strip())
    return cleaned.title()


def is_valid_nama(nama: str) -> bool:
    """Validasi nama kategori: max 30 char, alpha-numeric + spasi."""
    if not nama or not nama.strip():
        return False
    if len(nama) > 30:
        return False
    # Allow letters, numbers, spasi, dash
    return bool(re.match(r"^[A-Za-z0-9\s\-]+$", nama.strip()))


# ===== Self-test =====
if __name__ == "__main__":
    test_cases = [
        ("Sekolah Sabat", "SS"),
        ("Persembahan Sekolah Sabat", "SS"),
        ("Pembangunan", "Pemb"),
        ("Persembahan Pembangunan", "Pemb"),
        ("Ulang Tahun", "UT"),
        ("Khusus", "Khus"),
        ("Syukur", "Suku"),
        ("Pendidikan", "Pend"),
        ("Persembahan Khusus", "Khus"),
        ("Persembahan Pendidikan Umum", "PPU"),  # 3 kata → 3 huruf
        ("X", "X"),
        ("PT", "PT"),
        ("", "?"),
    ]

    passed = 0
    failed = 0
    for input_nama, expected in test_cases:
        actual = generate_alias(input_nama)
        status = "✓" if actual == expected else "✗"
        if actual == expected:
            passed += 1
        else:
            failed += 1

    sys_exit_if_fail = failed > 0

    import sys
    if sys_exit_if_fail:
        sys.exit(1)
