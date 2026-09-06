"""
S4-F.R4 — Unit tests untuk app.services.wa_input_parser.

Coverage target: 100% (45 stmts).

Parser nominal Indonesia untuk WA Input Bot (T94):
- "100000" → 100000
- "100.000" → 100000 (titik = ribuan Indonesia)
- "100,000" → 100000 (koma = ribuan, US-style)
- "100rb"   → 100000
- "1jt"     → 1000000
- "0"       → 0 (valid)
- Invalid   → None

MAX_NOMINAL = 100 juta.
"""


from app.services.wa_input_parser import (
    MAX_NOMINAL,
    is_valid_nominal,
    parse_nominal,
)


class TestParseNominalPlainInteger:
    """Plain integer tanpa suffix/separator."""

    def test_zero(self):
        assert parse_nominal("0") == 0

    def test_simple_100k(self):
        assert parse_nominal("100000") == 100_000

    def test_simple_1jt(self):
        assert parse_nominal("1000000") == 1_000_000

    def test_small_number(self):
        assert parse_nominal("50") == 50


class TestParseNominalSuffix:
    """Suffix: rb, k, jt, m (case-insensitive)."""

    def test_rb(self):
        assert parse_nominal("100rb") == 100_000

    def test_RB_uppercase(self):
        assert parse_nominal("100RB") == 100_000

    def test_k_suffix(self):
        """'k' = ribu (English style)."""
        assert parse_nominal("100k") == 100_000

    def test_jt(self):
        assert parse_nominal("1jt") == 1_000_000

    def test_JT_uppercase(self):
        assert parse_nominal("2JT") == 2_000_000

    def test_m_suffix(self):
        """'m' = juta (English million)."""
        assert parse_nominal("2m") == 2_000_000

    def test_50rb(self):
        assert parse_nominal("50rb") == 50_000

    def test_100jt(self):
        assert parse_nominal("100jt") == 100_000_000


class TestParseNominalSeparator:
    """Separator ribuan (titik atau koma) dan desimal."""

    def test_dot_thousands_id(self):
        """'100.000' (titik ribuan, Indonesia) → 100000."""
        assert parse_nominal("100.000") == 100_000

    def test_comma_thousands_us(self):
        """'100,000' (koma ribuan, US) → 100000."""
        assert parse_nominal("100,000") == 100_000

    def test_dot_decimal_id(self):
        """'1.5' (titik desimal) → 1 (int conversion)."""
        # Parse_nominal returns int — 1.5 → 1
        assert parse_nominal("1.5") == 1

    def test_comma_decimal_id(self):
        """'1,5' (koma desimal) → 1 (int conversion)."""
        assert parse_nominal("1,5") == 1

    def test_comma_decimal_with_jt(self):
        """'1,5jt' → 1.5 * 1jt = 1.500.000."""
        assert parse_nominal("1,5jt") == 1_500_000

    def test_dot_decimal_with_jt(self):
        """'1.5jt' → 1.5 * 1jt = 1.500.000."""
        assert parse_nominal("1.5jt") == 1_500_000


class TestParseNominalRpPrefix:
    """Prefix 'Rp ' dan spasi diabaikan."""

    def test_rp_prefix(self):
        assert parse_nominal("Rp 100.000") == 100_000

    def test_lowercase_rp(self):
        assert parse_nominal("rp 100000") == 100_000

    def test_internal_spaces(self):
        """'100 000' dengan spasi di tengah."""
        assert parse_nominal("100 000") == 100_000

    def test_trailing_comma(self):
        """Trailing koma dihilangkan."""
        assert parse_nominal("100000,") == 100_000

    def test_trailing_dot(self):
        """Trailing titik dihilangkan."""
        assert parse_nominal("100000.") == 100_000


class TestParseNominalInvalid:
    """Invalid input → None."""

    def test_none_input(self):
        assert parse_nominal(None) is None

    def test_empty_string(self):
        assert parse_nominal("") is None

    def test_alphabetic_only(self):
        assert parse_nominal("abc") is None

    def test_mixed_text(self):
        assert parse_nominal("100rb extra") is None

    def test_special_chars(self):
        assert parse_nominal("100@rb") is None

    def test_only_suffix(self):
        """Suffix tanpa angka."""
        assert parse_nominal("rb") is None


class TestIsValidNominal:
    """Validasi hasil parser."""

    def test_valid_zero(self):
        """0 adalah valid (lewati kategori)."""
        valid, reason = is_valid_nominal(0)
        assert valid is True
        assert reason == ""

    def test_valid_100k(self):
        valid, reason = is_valid_nominal(100_000)
        assert valid is True
        assert reason == ""

    def test_valid_max_nominal(self):
        """MAX_NOMINAL persis = valid (boundary)."""
        valid, reason = is_valid_nominal(MAX_NOMINAL)
        assert valid is True

    def test_invalid_none(self):
        """None hasil dari parser invalid."""
        valid, reason = is_valid_nominal(None)
        assert valid is False
        assert "tidak dikenali" in reason.lower()

    def test_invalid_negative(self):
        valid, reason = is_valid_nominal(-100)
        assert valid is False
        assert "negatif" in reason.lower()

    def test_invalid_too_large(self):
        """Di atas MAX_NOMINAL → invalid."""
        valid, reason = is_valid_nominal(MAX_NOMINAL + 1)
        assert valid is False
        assert "terlalu besar" in reason.lower()
