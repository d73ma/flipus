"""
T94 — WA Input Bot state machine.

States:
- IDLE: default, tampilkan menu utama
- AWAIT_X: menunggu nominal Perpuluhan
- AWAIT_PT: menunggu nominal Persembahan Terpadu
- AWAIT_KH: menunggu nominal Persembahan Khusus
- CONFIRM: konfirmasi ringkasan sebelum save ke staging
- SAVED: item baru tersimpan, tampilkan pesan sukses
- AWAIT_RECONCILE: menunggu konfirmasi cocokkan total

Buttons ID (Fonnte quick_reply):
- btn_input        → mulai input kuitansi baru
- btn_lewati       → skip kategori (isi 0)
- btn_batal        → cancel, kembali ke IDLE
- btn_simpan       → confirm save ke staging
- btn_cocokkan     → tampilkan summary & cocokkan
- btn_cocok_simpan → finalize batch (di-handle di endpoint, bukan state machine)
- btn_undo         → hapus staging item terakhir (window 5 menit)
- btn_pilih_<tenant_id> → multi-tenant confirmation

TTL: 30 menit idle → auto-reset ke IDLE
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.wa_session import WaSession
from app.services.wa_input_parser import parse_nominal, is_valid_nominal


log = logging.getLogger("flipus.wa_input_state")


# === Constants ===
IDLE_TIMEOUT_MINUTES = 30
UNDO_WINDOW_MINUTES = 5
MAX_STAGING_PER_DAY = 100


def _ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite tidak preserve tz info, jadi expires_at dari DB bisa naive.
    Normalisasi ke UTC-aware agar comparable dengan datetime.now(timezone.utc).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

# === State machine — valid transitions ===
VALID_NEXT_STATES = {
    "IDLE": ["AWAIT_X"],  # ditambah via button "input" atau multi-tenant "pilih_<id>"
    "AWAIT_X": ["AWAIT_PT", "IDLE"],  # nominal valid → AWAIT_PT, "Batal" → IDLE
    "AWAIT_PT": ["AWAIT_KH", "IDLE"],
    "AWAIT_KH": ["CONFIRM", "IDLE"],
    "CONFIRM": ["SAVED", "IDLE"],
    "SAVED": ["IDLE"],
    "AWAIT_RECONCILE": ["IDLE"],
}


def get_or_create_session(db: Session, phone: str) -> WaSession:
    """Ambil session per phone, auto-reset kalau expired."""
    import sys as _sys
    import traceback as _tb
    try:
        session = db.query(WaSession).filter(WaSession.phone == phone).first()
        now = datetime.now(timezone.utc)
        # SQLite tidak preserve tz info — pakai naive untuk assignment ke kolom DateTime.
        now_naive = now.replace(tzinfo=None)

        if session is None:
            session = WaSession(
                phone=phone,
                state="IDLE",
                payload=None,
                updated_at=now_naive,
                expires_at=None,
            )
            db.add(session)
            db.flush()
            return session

        # Auto-reset kalau expired
        if session.expires_at and _ensure_aware(session.expires_at) < now:
            session.state = "IDLE"
            session.payload = None
            session.expires_at = None
            session.updated_at = now_naive

        return session
    except Exception as _e:
        err = f"[DBG get_or_create_session] FAILED: {type(_e).__name__}: {_e}\n{_tb.format_exc()}"
        print(err, file=_sys.stderr)
        raise


def set_state(
    db: Session,
    session: WaSession,
    new_state: str,
    payload: Optional[dict] = None,
):
    """Update state + payload + expires_at."""
    if new_state not in VALID_NEXT_STATES:
        raise ValueError(f"Invalid state: {new_state}")

    now = datetime.now(timezone.utc)
    # SQLite tidak preserve tz info — pakai naive untuk assignment ke kolom DateTime.
    now_naive = now.replace(tzinfo=None)
    session.state = new_state
    if payload is not None:
        session.payload = json.dumps(payload)
    session.updated_at = now_naive
    # IDLE tidak perlu TTL (akan di-reset saat incoming message)
    # AWAIT_* dapat TTL 5 menit (reset kalau user diem)
    if new_state == "IDLE":
        session.expires_at = None
    else:
        session.expires_at = now_naive + timedelta(minutes=5)
    db.flush()


def get_payload(session: WaSession) -> dict:
    """Parse JSON payload safely."""
    if not session.payload:
        return {}
    try:
        return json.loads(session.payload)
    except (json.JSONDecodeError, TypeError):
        return {}


def parse_and_validate_nominal(text: str) -> tuple[Optional[int], str]:
    """Parse + validate nominal. Returns (value, error_msg)."""
    value = parse_nominal(text)
    valid, reason = is_valid_nominal(value)
    if not valid:
        return None, reason
    return value, ""


def reset_session(db: Session, session: WaSession):
    """Reset ke IDLE, clear payload."""
    set_state(db, session, "IDLE", payload=None)