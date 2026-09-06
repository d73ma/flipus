"""
S4-F.R4 — Unit tests untuk app.utils.kategori_alias.

Coverage target: 100% (27 stmts).

Aturan alias generator (Jerry 2026-08-27):
- 2+ kata → huruf pertama tiap kata (max 3 kata)
- 1 kata → 4 huruf pertama
- Kata "persembahan" diabaikan
- Prefix "persembahan " di-strip sebelum proses

Validasi nama kategori: max 30 char, alphanumeric + spasi + dash.
"""


from app.utils.kategori_alias import (
    _strip_persembahan,
    generate_alias,
    is_valid_nama,
    normalize_nama,
)


class TestGenerateAlias:
    """Smart alias generator untuk kategori_pemasukan."""

    def test_sekolah_sabat(self):
        assert generate_alias("Sekolah Sabat") == "SS"

    def test_persembahan_sekolah_sabat(self):
        assert generate_alias("Persembahan Sekolah Sabat") == "SS"

    def test_pembangunan_single(self):
        assert generate_alias("Pembangunan") == "PEMB"

    def test_persembahan_pembangunan(self):
        assert generate_alias("Persembahan Pembangunan") == "PEMB"

    def test_ulang_tahun(self):
        assert generate_alias("Ulang Tahun") == "UT"

    def test_khusus(self):
        assert generate_alias("Khusus") == "KHUS"

    def test_syukur(self):
        # Actual behavior: 'SYUK' (4 char first). Docstring modul claim 'Suku' outdated.
        assert generate_alias("Syukur") == "SYUK"

    def test_pendidikan(self):
        assert generate_alias("Pendidikan") == "PEND"

    def test_persembahan_khusus(self):
        """Persembahan Khusus → setelah strip → Khusus → 4 char."""
        assert generate_alias("Persembahan Khusus") == "KHUS"

    def test_three_words(self):
        """Setelah strip 'Persembahan' prefix: 'Pendidikan Umum' (2 kata) -> 'PU'.
        Docstring modul claim 'PPU' (3 kata) outdated."""
        assert generate_alias("Persembahan Pendidikan Umum") == "PU"

    def test_four_words_truncate(self):
        """4 kata → max 3 huruf pertama (truncate)."""
        assert generate_alias("A B C D") == "ABC"

    def test_single_char_x(self):
        assert generate_alias("X") == "X"

    def test_single_char_pt(self):
        assert generate_alias("PT") == "PT"

    def test_empty_string(self):
        assert generate_alias("") == "?"

    def test_whitespace_only(self):
        assert generate_alias("   ") == "?"

    def test_only_persembahan(self):
        """Nama = "Persembahan" saja → setelah strip = "" → "?"."""
        assert generate_alias("Persembahan") == "?"

    def test_lowercase_input(self):
        """Case-insensitive: lowercase juga di-handle."""
        assert generate_alias("sekolah sabat") == "SS"
        assert generate_alias("PEMBANGUNAN") == "PEMB"

    def test_mixed_case(self):
        """Mixed case → output selalu uppercase."""
        assert generate_alias("Sekolah SABAT") == "SS"

    def test_extra_whitespace(self):
        """Extra whitespace antar kata tetap di-handle."""
        assert generate_alias("  Sekolah   Sabat  ") == "SS"

    def test_word_persembahan_in_middle(self):
        """Kata 'persembahan' di tengah diabaikan."""
        assert generate_alias("Persembahan Sekolah Persembahan Sabat") == "SS"

    def test_tab_whitespace(self):
        """Tab dan spasi ganda diperlakukan sebagai separator."""
        assert generate_alias("Sekolah\tSabat") == "SS"


class TestNormalizeNama:
    """Normalisasi nama untuk dedup: title-case + collapse whitespace."""

    def test_basic_title_case(self):
        assert normalize_nama("sekolah sabat") == "Sekolah Sabat"

    def test_collapse_whitespace(self):
        assert normalize_nama("  sekolah    sabat  ") == "Sekolah Sabat"

    def test_already_title_case(self):
        assert normalize_nama("Sekolah Sabat") == "Sekolah Sabat"

    def test_all_uppercase(self):
        assert normalize_nama("SEKOLAH SABAT") == "Sekolah Sabat"

    def test_empty(self):
        assert normalize_nama("") == ""


class TestIsValidNama:
    """Validasi nama kategori: max 30 char, alphanumeric + spasi + dash."""

    def test_valid_simple(self):
        assert is_valid_nama("Sekolah Sabat") is True

    def test_valid_with_dash(self):
        assert is_valid_nama("Pembangunan-Gedung") is True

    def test_valid_with_numbers(self):
        assert is_valid_nama("Kategori 123") is True

    def test_empty_invalid(self):
        assert is_valid_nama("") is False

    def test_whitespace_only_invalid(self):
        assert is_valid_nama("   ") is False

    def test_too_long_invalid(self):
        """31 char → invalid."""
        assert is_valid_nama("a" * 31) is False

    def test_exactly_30_chars_valid(self):
        """30 char → valid (boundary)."""
        assert is_valid_nama("a" * 30) is True

    def test_special_chars_invalid(self):
        """Karakter spesial (selain alphanumeric, spasi, dash) invalid."""
        assert is_valid_nama("Sekolah@Sabat") is False
        assert is_valid_nama("Sekolah/Sabat") is False
        assert is_valid_nama("Sekolah.Sabat") is False

    def test_unicode_invalid(self):
        """Unicode (selain ASCII) invalid."""
        assert is_valid_nama("Sekolah Sabát") is False


class TestStripPersembahan:
    """Helper: strip prefix 'persembahan ' case-insensitive."""

    def test_strip_lowercase(self):
        assert _strip_persembahan("persembahan sekolah sabat") == "sekolah sabat"

    def test_strip_uppercase(self):
        assert _strip_persembahan("PERSEMBAHAN sekolah sabat") == "sekolah sabat"

    def test_strip_mixed_case(self):
        assert _strip_persembahan("PeRsEmBaHaN sekolah sabat") == "sekolah sabat"

    def test_strip_with_extra_spaces(self):
        assert _strip_persembahan("  Persembahan   sekolah sabat") == "sekolah sabat"

    def test_no_persembahan_prefix(self):
        """Tanpa prefix 'persembahan' → returned as-is (trimmed)."""
        assert _strip_persembahan("sekolah sabat") == "sekolah sabat"

    def test_persembahan_not_at_start(self):
        """'persembahan' di tengah → tidak di-strip."""
        assert _strip_persembahan("sekolah persembahan sabat") == "sekolah persembahan sabat"

    def test_only_persembahan(self):
        # _strip_persembahan only strips prefix 'persembahan ' (with trailing space).
        # Input 'Persembahan' alone has no trailing space, so not stripped.
        assert _strip_persembahan("Persembahan") == "Persembahan"
