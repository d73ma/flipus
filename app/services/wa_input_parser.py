"""
T94 — Parser nominal Indonesia untuk WA Input Bot.

Format yang didukung:
- "100000"     → 100000
- "100.000"    → 100000      (titik = ribuan Indonesia)
- "100,000"    → 100000      (koma = ribuan, US-style)
- "100rb"      → 100000
- "100k"       → 100000
- "1jt"        → 1000000
- "1,5jt"      → 1500000
- "1.5jt"      → 1500000
- "2m"         → 2000000
- "50rb"       → 50000
- "0"          → 0           (valid, lewati kategori)

Returns: int (rupiah) | None (invalid)
"""
import re

# Pattern: digits (optional . or , + digits) + optional suffix
_PATTERN = re.compile(r"^(\d+(?:[.,]\d+)?)(rb|k|jt|m)?$", re.IGNORECASE)

# Maximum nominal untuk tolak typo (Q2 dari Jerry)
MAX_NOMINAL = 100_000_000  # Rp 100 juta

# Suffix multiplier
_MULTIPLIER = {
    None: 1,
    "rb": 1_000,
    "k": 1_000,
    "jt": 1_000_000,
    "m": 1_000_000,
}


def parse_nominal(text: str) -> int | None:
    """
    Parse Indonesian currency format ke integer.
    Returns None kalau invalid.
    """
    if text is None:
        return None

    text = text.strip().lower().replace(" ", "").replace("rp", "").rstrip(",.")
    if not text:
        return None

    m = _PATTERN.match(text)
    if not m:
        return None

    num_str, suffix = m.group(1), m.group(2)
    suffix = suffix.lower() if suffix else None

    # Normalize decimal separator: pakai . untuk float conversion
    # Indonesia pakai "," desimal, US pakai "." desimal
    # Kalau ada "," dan length > 3 → itu ribuan (100,000)
    # Kalau ada "," dan length <= 3 → itu desimal (1,5)
    if "," in num_str and "." in num_str:
        # Asumsi terakhir = desimal, sebelumnya = ribuan
        last_comma = num_str.rfind(",")
        last_dot = num_str.rfind(".")
        if last_dot > last_comma:
            # "1,000.50" → 1000.50
            num_str = num_str.replace(",", "")
        else:
            # "1.000,50" → 1000.50
            num_str = num_str.replace(".", "").replace(",", ".")
    elif "," in num_str:
        # "," only
        parts = num_str.split(",")
        if len(parts[-1]) == 3 and len(parts) > 1:
            # "100,000" → ribuan → "100000"
            num_str = num_str.replace(",", "")
        else:
            # "1,5" → desimal
            num_str = num_str.replace(",", ".")
    elif "." in num_str:
        parts = num_str.split(".")
        if len(parts[-1]) == 3 and len(parts) > 1:
            # "100.000" → ribuan → "100000"
            num_str = num_str.replace(".", "")
        # else: "1.5" → desimal, biarkan

    try:
        num = float(num_str)
    except ValueError:
        return None

    multiplier = _MULTIPLIER.get(suffix, 1)
    result = int(num * multiplier)
    return result


def is_valid_nominal(value: int | None) -> tuple[bool, str]:
    """
    Validasi hasil parser.
    Returns (is_valid, reason).
    """
    if value is None:
        return False, "Format tidak dikenali"
    if value < 0:
        return False, "Nominal tidak boleh negatif"
    if value > MAX_NOMINAL:
        return False, f"Nominal terlalu besar (max Rp {MAX_NOMINAL:,})"
    return True, ""


# ===== Self-test (jalankan langsung untuk verify) =====
if __name__ == "__main__":
    test_cases = [
        ("100000", 100000),
        ("100.000", 100000),
        ("100,000", 100000),
        ("100rb", 100000),
        ("100k", 100000),
        ("1jt", 1_000_000),
        ("1,5jt", 1_500_000),
        ("1.5jt", 1_500_000),
        ("2m", 2_000_000),
        ("50rb", 50_000),
        ("0", 0),
        ("Rp 100.000", 100_000),
        ("100 000", 100_000),
        ("", None),
        ("abc", None),
        ("100jt", 100_000_000),
    ]

    print("Parser self-test:")
    all_pass = True
    for text, expected in test_cases:
        actual = parse_nominal(text)
        status = "OK" if actual == expected else "FAIL"
        if actual != expected:
            all_pass = False
        print(f"  [{status}] parse_nominal({text!r:15}) = {actual}  (expected {expected})")

    print()
    print(f"Validation test:")
    for v in [0, 100_000, 100_000_000, 200_000_000, -1000]:
        valid, reason = is_valid_nominal(v)
        print(f"  is_valid_nominal({v}) = ({valid}, {reason!r})")

    if all_pass:
        print("\n✓ All parse tests passed")
    else:
        print("\n✗ Some tests FAILED")