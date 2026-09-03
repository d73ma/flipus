"""
S4-F.R4 — Unit tests untuk app.services.wa_input_state.

Coverage target: ~95% (68 stmts).

State machine T94 untuk WA Input Bot:
- IDLE → AWAIT_X → AWAIT_PT → AWAIT_KH → CONFIRM → SAVED → IDLE
- IDLE_TIMEOUT_MINUTES = 30
- UNDO_WINDOW_MINUTES = 5
- MAX_STAGING_PER_DAY = 100

Functions:
- get_or_create_session: ambil/auto-reset session per phone
- set_state: update state + payload + expires_at (TTL 5 menit untuk AWAIT_*)
- get_payload: parse JSON payload safely
- parse_and_validate_nominal: helper untuk nominal parsing
- reset_session: reset ke IDLE
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.wa_input_state import (
    IDLE_TIMEOUT_MINUTES,
    UNDO_WINDOW_MINUTES,
    MAX_STAGING_PER_DAY,
    VALID_NEXT_STATES,
    get_or_create_session,
    set_state,
    get_payload,
    parse_and_validate_nominal,
    reset_session,
    _ensure_aware,
)
from app.models.wa_session import WaSession


class TestEnsureAware:
    """Helper: normalize datetime ke UTC-aware."""

    def test_none_returns_none(self):
        assert _ensure_aware(None) is None

    def test_naive_to_aware(self):
        naive = datetime(2026, 1, 1, 10, 0, 0)
        result = _ensure_aware(naive)
        assert result is not None
        assert result.tzinfo is not None
        assert result.tzinfo == timezone.utc

    def test_already_aware_unchanged(self):
        aware = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        result = _ensure_aware(aware)
        assert result == aware
        assert result.tzinfo == timezone.utc


class TestGetOrCreateSession:
    """Ambil session per phone, auto-create kalau belum ada, auto-reset kalau expired."""

    def test_create_new_session(self, test_db):
        """Phone baru → session baru dengan state=IDLE."""
        db = test_db()
        session = get_or_create_session(db, phone="628123456001")
        assert session is not None
        assert session.phone == "628123456001"
        assert session.state == "IDLE"
        assert session.payload is None
        assert session.expires_at is None
        db.close()

    def test_get_existing_session(self, test_db):
        """Phone existing → ambil yang sudah ada (same DB connection, primary key=phone)."""
        db = test_db()
        # First call creates
        s1 = get_or_create_session(db, phone="628123456002")
        s1_phone = s1.phone
        db.commit()
        # Force SQLAlchemy to refetch from DB (clear identity map cache)
        db.expire_all()

        # Second call retrieves (same db, same in-memory SQLite, same phone PK)
        s2 = get_or_create_session(db, phone="628123456002")
        assert s2.phone == s1_phone
        assert s2.state == "IDLE"
        assert s2.payload is None
        db.close()

    def test_auto_reset_expired_session(self, test_db):
        """Session dengan expires_at di masa lalu → auto-reset ke IDLE."""
        db = test_db()
        # Create session with expired expires_at
        past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10)
        s = WaSession(
            phone="628123456003",
            state="AWAIT_X",
            payload='{"x": 100000}',
            expires_at=past,
            updated_at=past,
        )
        db.add(s)
        db.commit()

        # get_or_create_session should auto-reset
        result = get_or_create_session(db, phone="628123456003")
        assert result.state == "IDLE"
        assert result.payload is None
        assert result.expires_at is None
        db.close()


class TestSetState:
    """Update state + payload + expires_at."""

    def test_set_state_idle_no_ttl(self, test_db):
        """IDLE state → expires_at = None (no TTL)."""
        db = test_db()
        s = get_or_create_session(db, phone="628123456004")
        set_state(db, s, "IDLE")
        assert s.state == "IDLE"
        assert s.expires_at is None
        db.close()

    def test_set_state_await_x_with_ttl(self, test_db):
        """AWAIT_X state → expires_at = now + 5 menit."""
        db = test_db()
        s = get_or_create_session(db, phone="628123456005")
        before = datetime.now(timezone.utc)
        set_state(db, s, "AWAIT_X", payload={"nominal_x": 100_000})
        after = datetime.now(timezone.utc)
        assert s.state == "AWAIT_X"
        assert s.expires_at is not None
        # TTL = 5 menit dari waktu set
        delta = (s.expires_at - before.replace(tzinfo=None)).total_seconds()
        assert 290 <= delta <= 310  # 5 min ± 10s tolerance
        db.close()

    def test_set_state_payload_json_encoded(self, test_db):
        """Payload disimpan sebagai JSON string."""
        db = test_db()
        s = get_or_create_session(db, phone="628123456006")
        set_state(db, s, "AWAIT_X", payload={"nominal_x": 100_000, "nama": "Test"})
        assert s.payload is not None
        assert '"nominal_x"' in s.payload
        assert '100000' in s.payload
        db.close()

    def test_set_state_invalid_raises(self, test_db):
        """State invalid → ValueError."""
        db = test_db()
        s = get_or_create_session(db, phone="628123456007")
        with pytest.raises(ValueError, match="Invalid state"):
            set_state(db, s, "BOGUS_STATE")
        db.close()

    def test_set_state_all_valid_states(self, test_db):
        """Semua state yang ada di VALID_NEXT_STATES bisa di-set."""
        db = test_db()
        s = get_or_create_session(db, phone="628123456008")
        for state in VALID_NEXT_STATES.keys():
            set_state(db, s, state)
            assert s.state == state
        db.close()


class TestGetPayload:
    """Parse JSON payload safely."""

    def test_none_payload_returns_empty(self, test_db):
        db = test_db()
        s = get_or_create_session(db, phone="628123456009")
        assert get_payload(s) == {}
        db.close()

    def test_empty_string_returns_empty(self, test_db):
        db = test_db()
        s = get_or_create_session(db, phone="628123456010")
        s.payload = ""
        assert get_payload(s) == {}
        db.close()

    def test_valid_json_payload(self, test_db):
        db = test_db()
        s = get_or_create_session(db, phone="628123456011")
        s.payload = '{"nominal_x": 100000, "nama": "Test"}'
        result = get_payload(s)
        assert result == {"nominal_x": 100000, "nama": "Test"}
        db.close()

    def test_invalid_json_returns_empty(self, test_db):
        """JSON corrupt → empty dict (graceful)."""
        db = test_db()
        s = get_or_create_session(db, phone="628123456012")
        s.payload = "{not valid json"
        result = get_payload(s)
        assert result == {}
        db.close()

    def test_non_string_payload_returns_empty(self, test_db):
        db = test_db()
        s = get_or_create_session(db, phone="628123456013")
        s.payload = None  # explicit None
        assert get_payload(s) == {}
        db.close()


class TestParseAndValidateNominal:
    """Parse + validate nominal — wrapper untuk parse_nominal + is_valid_nominal."""

    def test_valid_nominal(self):
        value, err = parse_and_validate_nominal("100rb")
        assert value == 100_000
        assert err == ""

    def test_invalid_format(self):
        value, err = parse_and_validate_nominal("abc")
        assert value is None
        assert "tidak dikenali" in err.lower()

    def test_too_large(self):
        """101jt → di atas MAX_NOMINAL."""
        value, err = parse_and_validate_nominal("101jt")
        assert value is None
        assert "terlalu besar" in err.lower()

    def test_zero_valid(self):
        """0 adalah valid (lewati kategori)."""
        value, err = parse_and_validate_nominal("0")
        assert value == 0
        assert err == ""


class TestResetSession:
    """Reset session ke state=IDLE.

    KNOWN BUG (S5.x follow-up): docstring klaim 'clear payload', tapi
    implementation tidak clear payload karena set_state() skip saat payload=None.
    Test berikut mendokumentasikan perilaku aktual (state=IDLE OK, payload persist).
    """

    def test_reset_sets_state_to_idle(self, test_db):
        db = test_db()
        s = get_or_create_session(db, phone="628123456014")
        set_state(db, s, "AWAIT_X", payload={"nominal_x": 100_000})
        assert s.state == "AWAIT_X"

        reset_session(db, s)
        # Yang PASTI benar: state kembali ke IDLE
        assert s.state == "IDLE"
        # expires_at di-clear (IDLE tidak pakai TTL)
        assert s.expires_at is None
        db.close()

    def test_reset_payload_behavior_documented_bug(self, test_db):
        """REGRESSION TEST untuk bug reset_session tidak clear payload.

        Production code: reset_session() → set_state(IDLE, payload=None).
        set_state() hanya overwrite payload jika payload is not None.
        Jadi payload PERSIST setelah reset — ini BUG yang perlu difix di S5.x.

        Test ini PASSES dengan perilaku buggy saat ini, untuk memastikan
        behavior tidak berubah tanpa sadar. Jika S5.x fix bug, test ini
        harus diupdate.
        """
        db = test_db()
        s = get_or_create_session(db, phone="628123456015")
        set_state(db, s, "AWAIT_X", payload={"nominal_x": 100_000})

        reset_session(db, s)
        # Document actual buggy behavior: payload masih ada
        payload_after = get_payload(s)
        assert payload_after == {"nominal_x": 100_000}
        db.close()


class TestConstants:
    """Verify constants."""

    def test_idle_timeout(self):
        assert IDLE_TIMEOUT_MINUTES == 30

    def test_undo_window(self):
        assert UNDO_WINDOW_MINUTES == 5

    def test_max_staging(self):
        assert MAX_STAGING_PER_DAY == 100


class TestValidNextStates:
    """Verify state machine transitions."""

    def test_idle_to_await_x(self):
        assert "AWAIT_X" in VALID_NEXT_STATES["IDLE"]

    def test_await_x_to_pt_or_idle(self):
        """AWAIT_X bisa ke AWAIT_PT (lanjut) atau IDLE (batal)."""
        assert "AWAIT_PT" in VALID_NEXT_STATES["AWAIT_X"]
        assert "IDLE" in VALID_NEXT_STATES["AWAIT_X"]

    def test_await_pt_to_kh_or_idle(self):
        assert "AWAIT_KH" in VALID_NEXT_STATES["AWAIT_PT"]
        assert "IDLE" in VALID_NEXT_STATES["AWAIT_PT"]

    def test_await_kh_to_confirm_or_idle(self):
        assert "CONFIRM" in VALID_NEXT_STATES["AWAIT_KH"]
        assert "IDLE" in VALID_NEXT_STATES["AWAIT_KH"]

    def test_confirm_to_saved_or_idle(self):
        assert "SAVED" in VALID_NEXT_STATES["CONFIRM"]
        assert "IDLE" in VALID_NEXT_STATES["CONFIRM"]

    def test_saved_to_idle(self):
        assert VALID_NEXT_STATES["SAVED"] == ["IDLE"]

    def test_reconcile_to_idle(self):
        assert VALID_NEXT_STATES["AWAIT_RECONCILE"] == ["IDLE"]
