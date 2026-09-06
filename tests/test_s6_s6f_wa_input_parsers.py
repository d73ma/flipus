"""
FASE 5 Sprint 6 — Unit tests for app/api/v1/wa_input.py pure functions.

Covers:
- _normalize_phone: 08xx → 628xx, +62, spaces, dashes.
- _parse_amount: 100rb, 1jt, 1,5jt, 100000, 1.000.000, invalid → 0.
- _parse_shortcut_format: 'X 100rb PT 50rb' → {x: 100000, pt: 50000}.
- _parse_shortcut_input: 'X 100rb, PT 50rb, KH 25rb' → {x: 100000, pt: 50000, kh: 25000}.
"""
import pytest

from app.api.v1.wa_input import (
    _normalize_phone,
    _parse_amount,
    _parse_shortcut_format,
    _parse_shortcut_input,
)


class TestNormalizePhone:
    """_normalize_phone — convert phone ke format 628xxx."""

    def test_empty(self) -> None:
        assert _normalize_phone("") == ""

    def test_already_international(self) -> None:
        """Phone starting with 62 unchanged."""
        assert _normalize_phone("6281234567890") == "6281234567890"

    def test_local_format_0(self) -> None:
        """Phone starting with 0 gets 62 prefix."""
        assert _normalize_phone("081234567890") == "6281234567890"

    def test_with_plus(self) -> None:
        """Plus prefix removed."""
        assert _normalize_phone("+6281234567890") == "6281234567890"

    def test_with_spaces(self) -> None:
        """Spaces removed."""
        assert _normalize_phone("0812 3456 7890") == "6281234567890"

    def test_with_dashes(self) -> None:
        """Dashes removed."""
        assert _normalize_phone("0812-3456-7890") == "6281234567890"

    def test_all_cleaners(self) -> None:
        """All cleaning rules combined."""
        assert _normalize_phone("+62 812-3456-7890") == "6281234567890"


class TestParseAmount:
    """_parse_amount — parse '100rb', '1jt', '1,5jt', '100000', '1.000.000'."""

    def test_pure_integer(self) -> None:
        assert _parse_amount("100000") == 100000

    def test_with_thousand_separator(self) -> None:
        """Indonesian format: 1.000.000 (period = thousand)."""
        assert _parse_amount("1.000.000") == 1000000

    def test_with_comma_separator(self) -> None:
        """European format: 1,000,000 (comma = thousand)."""
        assert _parse_amount("1,000,000") == 1000000

    def test_rb_suffix(self) -> None:
        """rb = ribu × 1000."""
        assert _parse_amount("100rb") == 100000
        assert _parse_amount("5rb") == 5000

    def test_jt_suffix(self) -> None:
        """jt = juta × 1.000.000."""
        assert _parse_amount("1jt") == 1000000
        assert _parse_amount("2jt") == 2000000

    def test_decimal_jt(self) -> None:
        """1,5jt = 1.5 juta."""
        assert _parse_amount("1,5jt") == 1500000
        assert _parse_amount("2.5jt") == 2500000

    def test_decimal_rb(self) -> None:
        """1,5rb = 1500."""
        assert _parse_amount("1,5rb") == 1500

    def test_empty(self) -> None:
        assert _parse_amount("") == 0

    def test_invalid_returns_zero(self) -> None:
        assert _parse_amount("abc") == 0
        assert _parse_amount("xyz123") == 0

    def test_zero(self) -> None:
        assert _parse_amount("0") == 0
        assert _parse_amount("0rb") == 0
        assert _parse_amount("0jt") == 0

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace removed."""
        assert _parse_amount("  100rb  ") == 100000


class TestParseShortcutFormat:
    """_parse_shortcut_format — parse 'X 100rb PT 50rb' format."""

    def test_x_pt_kh_all(self) -> None:
        result = _parse_shortcut_format("X 100rb PT 50rb KH 25rb")
        assert result == {"x": 100000, "pt": 50000, "kh": 25000}

    def test_x_pt_only(self) -> None:
        """Partial: only X and PT present."""
        result = _parse_shortcut_format("X 100rb PT 50rb")
        assert result is not None
        assert result["x"] == 100000
        assert result["pt"] == 50000
        assert "kh" not in result

    def test_x_only(self) -> None:
        result = _parse_shortcut_format("X 100000")
        assert result is not None
        assert result["x"] == 100000

    def test_no_match_returns_none(self) -> None:
        """No X/PT/KH keyword → None."""
        assert _parse_shortcut_format("hello world") is None
        assert _parse_shortcut_format("") is None
        assert _parse_shortcut_format("100rb") is None  # No category

    def test_lowercase_works(self) -> None:
        """Lowercase x/pt/kh should also match (case-insensitive)."""
        result = _parse_shortcut_format("x 100rb pt 50rb")
        assert result is not None
        assert result["x"] == 100000
        assert result["pt"] == 50000

    def test_zero_amount_kept_as_zero(self) -> None:
        """Explicit '0' is kept as zero (not filtered)."""
        result = _parse_shortcut_format("X 0 PT 50rb")
        assert result is not None
        # X=0 explicitly stated → kept
        assert result["x"] == 0
        assert result["pt"] == 50000

    def test_with_commas(self) -> None:
        """Comma as decimal separator."""
        result = _parse_shortcut_format("X 1,5jt")
        assert result is not None
        assert result["x"] == 1500000


class TestParseShortcutInput:
    """_parse_shortcut_input — parse 'X 100rb, PT 50rb, KH 25rb' longer format."""

    def test_all_three(self) -> None:
        result = _parse_shortcut_input("X 100rb, PT 50rb, KH 25rb")
        assert result == {"x": 100000, "pt": 50000, "kh": 25000}

    def test_full_names(self) -> None:
        """Panjang: Perpuluhan, Persembahan, Khusus."""
        result = _parse_shortcut_input("Perpuluhan 100rb, Persembahan 50rb, Khusus 25rb")
        assert result is not None
        assert result["x"] == 100000
        assert result["pt"] == 50000
        assert result["kh"] == 25000

    def test_no_commas(self) -> None:
        """Tanpa koma."""
        result = _parse_shortcut_input("X 100rb PT 50rb KH 25rb")
        assert result == {"x": 100000, "pt": 50000, "kh": 25000}

    def test_colon_separator(self) -> None:
        """Format 'X: 100rb'."""
        result = _parse_shortcut_input("X: 100rb, PT: 50rb")
        assert result is not None
        assert result["x"] == 100000
        assert result["pt"] == 50000

    def test_empty(self) -> None:
        result = _parse_shortcut_input("")
        assert result == {"x": 0, "pt": 0, "kh": 0}

    def test_partial(self) -> None:
        """Only X present."""
        result = _parse_shortcut_input("X 100rb")
        assert result is not None
        assert result["x"] == 100000
        assert result["pt"] == 0
        assert result["kh"] == 0

    def test_lowercase(self) -> None:
        result = _parse_shortcut_input("x 100rb, pt 50rb")
        assert result == {"x": 100000, "pt": 50000, "kh": 0}