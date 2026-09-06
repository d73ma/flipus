"""
FASE 5 Sprint 4 — Unit tests for app/utils/password_gen.py.

Pure-logic functions — no DB, no FastAPI. Covers:
- generate_random_password: length validation, charset exclusion (0/O/1/l/I),
  entropy (1 upper + 1 lower + 1 digit).
- validate_password_strength: policy enforcement (length, upper, lower, digit).
- mask_password: visible-char masking for audit logs.
"""

import pytest

from app.utils.password_gen import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    generate_random_password,
    mask_password,
    validate_password_strength,
)


class TestGenerateRandomPassword:
    def test_default_length(self) -> None:
        pwd = generate_random_password()
        assert len(pwd) == MIN_PASSWORD_LENGTH
        assert any(c.isupper() for c in pwd)
        assert any(c.islower() for c in pwd)
        assert any(c.isdigit() for c in pwd)

    def test_custom_length(self) -> None:
        pwd = generate_random_password(12)
        assert len(pwd) == 12

    def test_minimum_length(self) -> None:
        pwd = generate_random_password(MIN_PASSWORD_LENGTH)
        assert len(pwd) == MIN_PASSWORD_LENGTH

    def test_maximum_length(self) -> None:
        # Charset size after exclusions (0/O/1/l/I) is 56 chars.
        # 54 keeps within charset without infinite-loop risk.
        pwd = generate_random_password(54)
        assert len(pwd) == 54

    def test_rejects_below_minimum(self) -> None:
        with pytest.raises(ValueError, match="length minimal"):
            generate_random_password(MIN_PASSWORD_LENGTH - 1)

    def test_rejects_above_maximum(self) -> None:
        with pytest.raises(ValueError, match="length maksimal"):
            generate_random_password(MAX_PASSWORD_LENGTH + 1)

    def test_excludes_ambiguous_chars(self) -> None:
        """T49 — exclude 0/O/1/l/I to avoid WA misread."""
        # Generate many passwords, ensure none contain ambiguous chars
        for _ in range(50):
            pwd = generate_random_password(16)
            for ch in pwd:
                assert ch not in "0O1lI", f"Found ambiguous char '{ch}' in '{pwd}'"

    def test_uniqueness_across_calls(self) -> None:
        """Two consecutive calls should not return the same password."""
        seen = set()
        for _ in range(100):
            seen.add(generate_random_password())
        assert len(seen) > 95, f"Got only {len(seen)} unique passwords out of 100"


class TestValidatePasswordStrength:
    def test_valid_password(self) -> None:
        ok, msg = validate_password_strength("Strong1Pass")
        assert ok is True
        assert msg == ""

    def test_empty_password(self) -> None:
        ok, msg = validate_password_strength("")
        assert ok is False
        assert "kosong" in msg.lower()

    def test_too_short(self) -> None:
        ok, msg = validate_password_strength("Aa1")
        assert ok is False
        assert "minimal" in msg.lower()

    def test_no_uppercase(self) -> None:
        ok, msg = validate_password_strength("weakpass1")
        assert ok is False
        assert "besar" in msg.lower()

    def test_no_lowercase(self) -> None:
        ok, msg = validate_password_strength("WEAKPASS1")
        assert ok is False
        assert "kecil" in msg.lower()

    def test_no_digit(self) -> None:
        ok, msg = validate_password_strength("WeakPassw")
        assert ok is False
        assert "angka" in msg.lower()

    def test_too_long(self) -> None:
        ok, msg = validate_password_strength("A1" + "a" * (MAX_PASSWORD_LENGTH + 10))
        assert ok is False
        assert "maksimal" in msg.lower()


class TestMaskPassword:
    def test_default_visible_2(self) -> None:
        assert mask_password("Secret23") == "Se****23"

    def test_visible_1(self) -> None:
        assert mask_password("Secret23", visible=1) == "S******3"

    def test_short_password_all_masked(self) -> None:
        # 4 chars, visible=2*2=4 → fully masked
        assert mask_password("Ab1c", visible=2) == "****"

    def test_empty_password(self) -> None:
        assert mask_password("") == ""

    def test_exact_visible_x2_length(self) -> None:
        # length=4, visible=2 → exact boundary, fully masked
        assert mask_password("abcd", visible=2) == "****"
