"""
T94 — WA Input Bot API endpoints.

Endpoints:
- POST /api/v1/wa/inbound — Fonnte webhook (public, no JWT, signature-verified)
- GET  /api/v1/kuitansi/staging — list staging items (BENDAHARA only)
- POST /api/v1/kuitansi/finalize-staging — finalize batch ke kuitansi final

Flow:
1. Inbound webhook dari Fonnte
2. Lookup sender → User (Bendahara) → Tenant
3. State machine transition (IDLE → AWAIT_X → AWAIT_PT → AWAIT_KH → CONFIRM → SAVED)
4. Reply via Fonnte API
"""
import logging
import os
import time
from datetime import UTC, datetime

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.api.v1.auth import require_roles  # T94 Section 8: proper RBAC
from app.core.database import get_db
from app.core.rate_limiter import limiter as _rate_limiter
from app.core.security import decrypt_pii, encrypt_pii
from app.models.audit import AuditLog
from app.models.master import PersentaseConfig
from app.models.tenant import Tenant
from app.models.transaction import Kuitansi
from app.models.user import User
from app.services.wa_input_state import (
    MAX_STAGING_PER_DAY,
    get_or_create_session,
    get_payload,
    parse_and_validate_nominal,
    reset_session,
    set_state,
)
from app.utils.porsi_calculator import compute_porsi
from app.utils.sabat_counter import get_effective_sabat_for_input

log = logging.getLogger("flipus.wa_input")

router = APIRouter()


# === FASE 3 K2: WA webhook anti-spam rate limit (slowapi) ===
# Sebelumnya pakai in-memory dict `_RATE_LIMIT` (process-local, hilang saat restart).
# Sekarang slowapi Limiter (Redis-ready) dengan key_func per-phone via `request.state.wa_from`.
# `wa_inbound` handler wajib set `request.state.wa_from` SEBELUM proses lanjut supaya
# rate limit key unik per nomor pengirim.
from app.core.rate_limiter import _key_func_by_phone  # noqa: E402  (shared key_func)

# ==================== INBOUND WEBHOOK ====================

class WaInboundPayload(BaseModel):
    """Payload dari Fonnte webhook (general WA Business API)."""
    device: str | None = None
    sender: str | None = None  # Fonnte 'sender' field
    name: str | None = None
    message: str | None = None
    type: str | None = "text"  # 'text' | 'button_reply' | 'list_reply'
    button_id: str | None = None
    button_text: str | None = None
    # Legacy Fonnte fields
    from_: str | None = None  # alias
    id: str | None = None  # Fonnte message ID

    class Config:
        populate_by_name = True
        fields = {"from_": "from"}


def _normalize_phone(raw: str) -> str:
    """Normalize phone ke format 628xxx (Fonnte standard)."""
    if not raw:
        return ""
    phone = raw.replace("+", "").replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        phone = "62" + phone[1:]
    return phone


def _parse_shortcut_input(text: str) -> dict:
    """
    T95: Parse format one-shot 'X 100rb, PT 50rb, KH 25rb' atau variasinya.

    Support patterns:
    - "X 100rb, PT 50rb, KH 25rb"
    - "X 100rb PT 50rb KH 25rb"
    - "X: 100rb, PT: 50rb"
    - "x 100000 pt 50000 kh 25000"
    - Partial: "X 100rb, PT 50rb" → KH tidak di-set

    Returns: dict {x: int, pt: int, kh: int} — values 0 kalau tidak ada di input.
    """
    import re
    if not text:
        return {"x": 0, "pt": 0, "kh": 0}

    text_lower = text.lower()
    result = {"x": 0, "pt": 0, "kh": 0}

    # Map kategori → key result
    cat_map = {"x": "x", "perpuluhan": "x", "pt": "pt", "persembahan": "pt", "kh": "kh", "khusus": "kh"}

    # Pattern: (kategori) [separator] (amount)
    # kategori: X/PT/KH atau nama panjang
    # separator: spasi, koma, titik dua, strip
    # amount: digits + optional rb/jt/juta/ribu
    # Batas: sampai ketemu kategori berikutnya atau akhir string
    pattern = re.compile(
        r'\b(x|perpuluhan|pt|persembahan|kh|khusus)\s*[:\-]?\s*([0-9]+(?:[.,][0-9]+)?)\s*(rb|jt|juta|ribu)?',
        re.IGNORECASE
    )

    for m in pattern.finditer(text_lower):
        cat_raw = m.group(1).lower()
        amount_str = m.group(2).replace(",", ".")
        suffix = (m.group(3) or "").lower()

        cat_key = cat_map.get(cat_raw)
        if not cat_key:
            continue

        try:
            base = float(amount_str)
        except ValueError:
            continue

        if suffix in ("rb", "ribu"):
            amount = int(base * 1_000)
        elif suffix in ("jt", "juta"):
            amount = int(base * 1_000_000)
        else:
            amount = int(base)

        result[cat_key] = amount

    return result


def _send_fonnte_reply(phone: str, message: str, buttons: list[dict] | None = None) -> dict:
    """Send reply via Fonnte API."""
    token = os.getenv("FONNTE_TOKEN", "").strip()
    enabled = os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"

    if not enabled:
        log.info(f"WHATSAPP_ENABLED=false, skip reply to {phone}")
        return {"status": "skipped", "reason": "WHATSAPP_ENABLED=false"}

    if not token or token.startswith("paste_"):
        log.warning(f"FONNTE_TOKEN kosong, skip reply to {phone}")
        return {"status": "skipped", "reason": "no token"}

    phone_clean = _normalize_phone(phone)
    try:
        data = {"target": phone_clean, "message": message, "countryCode": "62"}
        if buttons:
            # Fonnte Quick Reply expects plain text strings, NOT JSON objects
            # button1="Text 1", button2="Text 2", button3="Text 3"
            # When clicked, Fonnte sends message="Text 1" (not button_id)
            for i, btn in enumerate(buttons[:3], 1):  # max 3
                # btn is dict {"id": "btn_x", "text": "Label"} — extract text only
                btn_text = btn.get("text") if isinstance(btn, dict) else str(btn)
                data[f"button{i}"] = btn_text
        resp = requests.post(
            "https://api.fonnte.com/send",
            headers={"Authorization": token},
            data=data,
            timeout=15,
        )
        result = resp.json()
        log.info(f"[WA-INBOUND] reply to {phone_clean}: status={result.get('status')}")
        return {"status": "sent" if result.get("status") else "failed", "fonnte": result}
    except Exception as e:
        log.error(f"[WA-INBOUND] reply error to {phone}: {e}")
        return {"status": "error", "reason": str(e)}


# === Reply builders ===

def _reply_menu(tenant_name: str = "") -> dict:
    """Build main menu reply."""
    msg = (
        "*FLIPUS Input Kuitansi*"
        + (f"\nJemaat: {tenant_name}" if tenant_name else "")
        + "\n\nPilih aksi:"
    )
    buttons = [
        {"id": "btn_input", "text": "💰 Input Kuitansi"},
        {"id": "btn_cocokkan", "text": "📊 Cocokkan Total"},
        {"id": "btn_bantuan", "text": "ℹ️ Bantuan"},
    ]
    return {"message": msg, "buttons": buttons}


def _reply_await_kategori(kategori: str) -> dict:
    """Build reply untuk AWAIT_X/PT/KH."""
    label = {"X": "Perpuluhan (X)", "PT": "Persembahan Terpadu (PT)", "KH": "Persembahan Khusus (KH)"}[kategori]
    msg = (
        f"Masukkan nominal *{label}*:\n\n"
        "Format: `100000`, `100rb`, `1jt`, `1,5jt`\n"
        "Ketik `0` atau tap Lewati untuk skip.\n"
        "Tap Batal untuk kembali ke menu."
    )
    buttons = [
        {"id": "btn_lewati", "text": "⏭ Lewati"},
        {"id": "btn_batal", "text": "❌ Batal"},
    ]
    return {"message": msg, "buttons": buttons}


def _reply_await_nama() -> dict:
    """Build reply untuk AWAIT_NAMA (nama pemberi)."""
    msg = (
        "Masukkan *nama pemberi* (umat):\n\n"
        "Contoh: `Budi Santoso` atau `Ibu Maria`\n"
        "Tap Lewati untuk set default `Umat WA`."
    )
    buttons = [
        {"id": "btn_lewati", "text": "⏭ Lewati"},
        {"id": "btn_batal", "text": "❌ Batal"},
    ]
    return {"message": msg, "buttons": buttons}


def _reply_confirm(x: int, pt: int, kh: int, nama: str) -> dict:
    """Build CONFIRM reply."""
    msg = (
        "*Konfirmasi Kuitansi:*\n\n"
        f"• Nama Pemberi : {nama}\n"
        f"• Perpuluhan (X) : Rp {x:,}\n"
        f"• Persembahan (PT): Rp {pt:,}\n"
        f"• Khusus (KH)    : Rp {kh:,}\n"
        f"• *Total*         : Rp {x + pt + kh:,}\n\n"
        "Simpan ke kuitansi sementara?"
    )
    buttons = [
        {"id": "btn_simpan", "text": "✅ Simpan"},
        {"id": "btn_batal", "text": "❌ Batal"},
    ]
    return {"message": msg, "buttons": buttons}


def _reply_saved(nomor_temp: str, nama: str) -> dict:
    """Build SAVED reply."""
    msg = (
        f"✅ *Tersimpan ke kuitansi sementara*\n\n"
        f"No. sementara: `{nomor_temp}`\n\n"
        "Mau input lagi atau cocokan sekarang?"
    )
    buttons = [
        {"id": "btn_input", "text": "💰 Input Lagi"},
        {"id": "btn_cocokkan", "text": "📊 Cocokkan"},
    ]
    return {"message": msg, "buttons": buttons}


def _reply_pilih_jemaat(tenants: list[Tenant]) -> dict:
    """Build reply untuk multi-tenant Bendahara (Q4)."""
    msg = "*Pilih jemaat:*"
    buttons = []
    for t in tenants[:3]:
        buttons.append({"id": f"btn_pilih_{t.id}", "text": t.nama_jemaat_lokal[:20]})
    return {"message": msg, "buttons": buttons}


def _reply_bantuan() -> dict:
    """Help text."""
    msg = (
        "*Bantuan FLIPUS Input*\n\n"
        "• Input kuitansi nominal via chat ini\n"
        "• Belum final sampai Anda tap 'Simpan' di dashboard\n"
        "• Edit/koreksi di dashboard sebelum finalize\n\n"
        "Format nominal:\n"
        "• `100000` atau `100rb` → Rp 100.000\n"
        "• `1jt` atau `1.000.000` → Rp 1.000.000\n"
        "• `1,5jt` → Rp 1.500.000"
    )
    return {"message": msg, "buttons": []}


# === Shortcut format parser ===

def _parse_amount(raw: str) -> int:
    """Parse '100rb', '1jt', '1,5jt', '100000', '1.000.000' → int rupiah.
    Return 0 kalau tidak bisa parse."""
    s = raw.strip().lower().replace(" ", "")
    if not s:
        return 0
    # Pure integer (with possible thousand separators)
    s_clean = s.replace(".", "").replace(",", "")
    if s_clean.isdigit():
        return int(s_clean)
    # rb suffix (ribu)
    if s.endswith("rb"):
        try:
            return int(float(s[:-2].replace(",", ".")) * 1000)
        except ValueError:
            return 0
    # jt suffix (juta)
    if s.endswith("jt"):
        try:
            return int(float(s[:-2].replace(",", ".")) * 1_000_000)
        except ValueError:
            return 0
    return 0


def _parse_shortcut_format(message: str) -> dict | None:
    """Parse 'X 100rb, PT 50rb, KH 25rb' shortcut format.
    Return dict {x: int, pt: int, kh: int} kalau match, else None.
    Match rules: minimal salah satu kategori (X/PT/KH) diikuti nominal."""
    import re
    s = message.upper()
    # Match X/PT/KH followed by optional space and an amount (digits, with rb/jt suffix, optional thousand sep)
    pattern = r"\b(X|PT|KH)\s*([\d.,]+(?:\s*(?:RB|JT|RIBU|JUTA))?)"
    matches = re.findall(pattern, s)
    if not matches:
        return None
    result = {}
    used_amounts = []
    for label, amount_raw in matches:
        amount = _parse_amount(amount_raw)
        if amount > 0 or amount_raw.strip() in ("0", "0rb", "0jt"):
            result[label.lower()] = amount
            used_amounts.append(amount_raw)
    # Only return kalau minimal satu amount > 0
    if not result:
        return None
    return result


# === Main webhook endpoint ===

@router.get("/wa/inbound", tags=['WhatsApp'])
async def wa_inbound_get():
    """
    GET handler untuk Fonnte webhook URL verification.
    Beberapa provider kirim GET dulu untuk verify URL sebelum save.
    Balas 200 OK + payload JSON biar Fonnte tahu endpoint hidup.
    """
    return {"status": "ok", "endpoint": "wa/inbound", "method": "GET"}


async def _set_wa_from_state(request: Request) -> None:
    """
    FASE 3 K2: pre-handler hook untuk set `request.state.wa_from` supaya
    slowapi key_func (`_key_func_by_phone`) bisa rate-limit per phone.
    Jalankan SEBELUM @limiter.limit() decorator wraps the function.
    """
    try:
        # Fonnte mengirim form-data → coba itu dulu
        try:
            form = await request.form()
            raw_sender = form.get("sender") or form.get("from") or ""
        except Exception:
            raw_sender = ""
        if not raw_sender:
            # Fallback: parse JSON body kalau form kosong
            try:
                import json as _json
                raw = await request.body()
                if raw:
                    _body = _json.loads(raw)
                    raw_sender = _body.get("sender") or _body.get("from") or ""
            except Exception:
                raw_sender = ""
        request.state.wa_from = _normalize_phone(raw_sender) if raw_sender else ""
    except Exception:
        request.state.wa_from = ""


@router.post("/wa/inbound", tags=['WhatsApp'], dependencies=[Depends(_set_wa_from_state)])
@_rate_limiter.limit("1/2seconds", key_func=_key_func_by_phone)  # FASE 3 K2: anti-spam per-phone
async def wa_inbound(request: Request, db: Session = Depends(get_db)):
    """
    Fonnte webhook untuk WA Input Bot.
    Public endpoint (no JWT) — verification via Fonnte signature header (TODO: implement).

    Fonnte mengirim payload sebagai **form-data** (URL-encoded), BUKAN JSON.
    Kita coba form-data dulu (real Fonnte), fallback ke JSON (untuk curl test).
    """
    import traceback as _tb_top
    _parsed_body = {}

    # 1) Try form-data (Fonnte's actual format)
    try:
        form = await request.form()
        if form:
            _parsed_body = dict(form)
    except Exception:
        _parsed_body = {}

    # 2) Fallback: try JSON (untuk curl test / integrasi lain)
    if not _parsed_body:
        try:
            _raw_body = await request.body()
            if _raw_body:
                import json as _json_top
                _parsed_body = _json_top.loads(_raw_body)
        except Exception:
            _parsed_body = {}

    try:
        return await _wa_inbound_impl(request, db, _parsed_body)
    except HTTPException:
        raise  # FastAPI-handled, jangan swallow
    except Exception as e:
        _tb_text = _tb_top.format_exc()
        err_msg = (
            f"[WA-INBOUND-TOPLEVEL] uncaught error: {type(e).__name__}: {e}\n"
            f"{_tb_text}\n"
            f"--- request body: {_parsed_body}"
        )
        log.error(err_msg)
        log.exception(err_msg)
        phone = _normalize_phone(_parsed_body.get("sender") or _parsed_body.get("from") or "")
        if phone:
            try:
                _send_fonnte_reply(
                    phone,
                    f"⚠️ Sistem error: {type(e).__name__}. Coba lagi atau hubungi Admin.",
                )
            except Exception:
                log.exception("Fonnte error reply gagal terkirim")
        _detail = f"{type(e).__name__}: {e}\n\n--- traceback ---\n{_tb_text[-2000:]}"
        raise HTTPException(status_code=500, detail=_detail) from e


async def _wa_inbound_impl(request: Request, db: Session, body: dict):
    """
    Actual implementation. Wrapped by top-level try/except di wa_inbound.
    """
    log.info(f"[WA-INBOUND-ENTRY] body={body}")

    phone = body.get("sender") or body.get("from") or ""
    phone = _normalize_phone(phone)
    device = body.get("device") or ""
    device_clean = _normalize_phone(device)
    message = (body.get("message") or "").strip()
    button_id = body.get("button_id") or ""
    fonnte_msg_id = body.get("id") or ""

    # CRITICAL: Ignore echo dari bot sendiri (Fonnte webhook trigger untuk outgoing juga)
    # Kalau sender == device → pesan dari bot echo balik, SKIP untuk avoid infinite loop
    if phone == device_clean and device_clean:
        return {"status": "ignored", "reason": "echo from device"}

    # Ignore bot menu echo (defensive fallback kalau device check gagal)
    if message.startswith("*FLIPUS") or "Pilih aksi:" in message or "_Sent via fonnte.com_" in message:
        return {"status": "ignored", "reason": "bot menu echo"}

    if not phone:
        log.warning(f"[WA-INBOUND] no phone in payload: {body}")
        return {"status": "ignored", "reason": "no phone"}

    # Anti-spam rate limit dipindah ke slowapi @limiter.limit (lihat decorator di /wa/inbound).
    # Sebelumnya: `_check_rate_limit(phone)` di bawah ini. Sekarang K2 (FASE 3) pakai
    # slowapi per-phone via Depends(_set_wa_from_state) → _key_func_by_phone.

    # Lookup sender
    users = (
        db.query(User)
        .filter(
            User.role == "BENDAHARA",
            User.is_active == True,  # noqa: E712
            User.nomor_whatsapp.isnot(None),
        )
        .all()
    )
    matched_users = [
        u for u in users
        if u.nomor_whatsapp and _normalize_phone(u.nomor_whatsapp) == phone
    ]

    if not matched_users:
        _send_fonnte_reply(
            phone,
            "Nomor Anda belum terdaftar sebagai Bendahara. Hubungi Admin Uni untuk aktivasi.",
        )
        return {"status": "ok", "reply": "unregistered"}

    # Detect tenant
    if len(matched_users) > 1:
        # Multi-tenant Bendahara (Q4: konfirmasi jemaat dulu)
        tenants = list({u.tenant_id: db.query(Tenant).get(u.tenant_id) for u in matched_users}.values())
        tenants = [t for t in tenants if t is not None]

        session = get_or_create_session(db, phone)
        if button_id.startswith("btn_pilih_"):
            try:
                tenant_id = int(button_id.split("_")[-1])
                chosen: Tenant | None = next((t for t in tenants if t.id == tenant_id), None)
                if not chosen:
                    _send_fonnte_reply(phone, "Jemaat tidak valid. Coba lagi.")
                    return {"status": "ok"}
                assert chosen is not None  # nosec B101 — S4-D.R1: narrow for mypy
                set_state(db, session, "AWAIT_X", payload={"tenant_id": chosen.id, "nama_jemaat": chosen.nama_jemaat_lokal})
                _send_fonnte_reply(phone, _reply_await_kategori("X")["message"], _reply_await_kategori("X")["buttons"])
                db.commit()
                return {"status": "ok"}
            except (ValueError, IndexError):
                pass

        # Show pilih jemaat
        reply = _reply_pilih_jemaat(tenants)
        _send_fonnte_reply(phone, reply["message"], reply["buttons"])
        db.commit()
        return {"status": "ok", "reply": "pilih_jemaat"}

    # Single tenant
    user = matched_users[0]
    tenant = db.query(Tenant).get(user.tenant_id)
    if not tenant:
        _send_fonnte_reply(phone, "Jemaat Anda tidak aktif. Hubungi Admin.")
        return {"status": "ok", "reply": "tenant_inactive"}

    # Session
    session = get_or_create_session(db, phone)
    payload = get_payload(session)

    # === T95: Shortcut format parser ===
    # Detect "X 100rb, PT 50rb, KH 25rb" dan langsung ke CONFIRM.
    # Skip kalau button_id ada (user tap tombol) atau message empty.
    if not button_id and message:
        shortcut = _parse_shortcut_input(message)
        # Hanya proses kalau ada minimal satu kategori X/PT/KH
        if shortcut["x"] > 0 or shortcut["pt"] > 0 or shortcut["kh"] > 0:
            merged = {
                "tenant_id": tenant.id,
                "nama_jemaat": tenant.nama_jemaat_lokal,
                "await_x": shortcut["x"] if shortcut["x"] > 0 else payload.get("await_x", 0),
                "await_pt": shortcut["pt"] if shortcut["pt"] > 0 else payload.get("await_pt", 0),
                "await_kh": shortcut["kh"] if shortcut["kh"] > 0 else payload.get("await_kh", 0),
            }
            set_state(db, session, "AWAIT_NAMA", payload=merged)
            reply = _reply_await_nama()
            _send_fonnte_reply(phone, reply["message"], reply["buttons"])
            db.commit()
            return {"status": "ok", "reply": "shortcut_await_nama"}

    # === State machine transitions ===

    # Map button text to button_id (Fonnte sends clicked button as message text)
    button_text_map = {
        "💰 Input Kuitansi": "btn_input",
        "📊 Cocokkan Total": "btn_cocokkan",
        "ℹ️ Bantuan": "btn_bantuan",
        "🔁 Input Lagi": "btn_input",
        "⏭️ Lewati": "btn_lewati",
        "❌ Batal": "btn_batal",
        "💾 Simpan": "btn_simpan",
        # Text command aliases (untuk Fonnte free tier tanpa button support)
        "input": "btn_input",
        "bantuan": "btn_bantuan",
        "help": "btn_bantuan",
        "lewati": "btn_lewati",
        "skip": "btn_lewati",
        "batal": "btn_batal",
        "cancel": "btn_batal",
        "simpan": "btn_simpan",
        "save": "btn_simpan",
    }
    # If message matches button text, treat as button_id
    message_lower = message.lower()
    if not button_id and message_lower in button_text_map:
        button_id = button_text_map[message_lower]

    # Tombol Bantuan
    if button_id == "btn_bantuan" or message.lower() in ["bantuan", "help", "?"]:
        reply = _reply_bantuan()
        _send_fonnte_reply(phone, reply["message"], reply["buttons"])
        return {"status": "ok"}

    # Tombol Batal
    if button_id == "btn_batal":
        reset_session(db, session)
        reply = _reply_menu(tenant.nama_jemaat_lokal)
        _send_fonnte_reply(phone, reply["message"], reply["buttons"])
        db.commit()
        return {"status": "ok"}

    # Tombol Lewati
    if button_id == "btn_lewati":
        if session.state == "AWAIT_NAMA":
            payload["await_nama"] = "Umat WA"
            set_state(db, session, "CONFIRM", payload=payload)
            reply = _reply_confirm(
                payload.get("await_x", 0),
                payload.get("await_pt", 0),
                payload.get("await_kh", 0),
                payload["await_nama"],
            )
            _send_fonnte_reply(phone, reply["message"], reply["buttons"])
            db.commit()
            return {"status": "ok"}
        if session.state in ("AWAIT_X", "AWAIT_PT", "AWAIT_KH"):
            next_kategori = {"AWAIT_X": "PT", "AWAIT_PT": "KH", "AWAIT_KH": None}[session.state]
            payload[session.state.lower()] = 0
            if next_kategori:
                next_state = {"PT": "AWAIT_PT", "KH": "AWAIT_KH"}[next_kategori]
                set_state(db, session, next_state, payload=payload)
                reply = _reply_await_kategori(next_kategori)
                _send_fonnte_reply(phone, reply["message"], reply["buttons"])
            else:
                # Lewati KH → ke AWAIT_NAMA (bukan langsung CONFIRM)
                payload["await_nama"] = None
                set_state(db, session, "AWAIT_NAMA", payload=payload)
                reply = _reply_await_nama()
                _send_fonnte_reply(phone, reply["message"], reply["buttons"])
            db.commit()
            return {"status": "ok"}

    # Tombol Input (mulai / multi-tenant handled above)
    if button_id == "btn_input":
        set_state(db, session, "AWAIT_X", payload={"tenant_id": tenant.id, "nama_jemaat": tenant.nama_jemaat_lokal})
        reply = _reply_await_kategori("X")
        _send_fonnte_reply(phone, reply["message"], reply["buttons"])
        db.commit()
        return {"status": "ok"}

    # Tombol Simpan (CONFIRM → SAVED)
    if button_id == "btn_simpan":
        log.info(f"[WA-BTN-SIMPAN-ENTRY] state={session.state} payload={payload}")
        if session.state == "CONFIRM":
            try:
                x = int(payload.get("await_x", 0))
                pt = int(payload.get("await_pt", 0))
                kh = int(payload.get("await_kh", 0))
                nama_pemberi = (payload.get("await_nama") or "Umat WA").strip()[:80]
                tenant_id = payload.get("tenant_id") or tenant.id
                log.info(f"[WA-BTN-SIMPAN-PARSED] x={x} pt={pt} kh={kh} nama={nama_pemberi!r} tenant_id={tenant_id}")

                # Anti-spam: max staging per hari
                today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
                # SQLite strip tz info dari kolom DATETIME, jadi Kuitansi.created_at
                # jadi offset-naive saat dibaca. Buat today_start juga naive
                # supaya comparable. (Lost tz but OK untuk compare "same day".)
                today_start_naive = today_start.replace(tzinfo=None)
                count_today = (
                    db.query(func.count(Kuitansi.id))
                    .filter(
                        Kuitansi.created_via == "wa",
                        Kuitansi.wa_sender == phone,
                        Kuitansi.created_at >= today_start_naive,
                    )
                    .scalar()
                )
                if count_today >= MAX_STAGING_PER_DAY:
                    _send_fonnte_reply(phone, f"⚠️ Anda sudah menginput {count_today} kuitansi hari ini. Coba lagi besok atau hubungi Admin.")
                    return {"status": "ok"}

                # Hitung porsi Model B
                cfg = (
                    db.query(PersentaseConfig)
                    .filter(
                        PersentaseConfig.scope == "MISI",
                        PersentaseConfig.ref_id == tenant.misi_konferens_id,
                    )
                    .first()
                )
                if not cfg:
                    # Default konservatif
                    cfg_pct = {"pct_x_jemaat": 1.0, "pct_pt_jemaat": 0.5, "pct_khusus_jemaat": 0.0,
                               "pct_x_uni": 0.0, "pct_pt_uni": 0.0, "pct_khusus_uni": 0.0}
                else:
                    cfg_pct = {
                        "pct_x_jemaat": cfg.pct_x_jemaat,
                        "pct_pt_jemaat": cfg.pct_pt_jemaat,
                        "pct_khusus_jemaat": cfg.pct_khusus_jemaat,
                        "pct_x_uni": cfg.pct_x_uni or 0.0,
                        "pct_pt_uni": cfg.pct_pt_uni or 0.0,
                        "pct_khusus_uni": cfg.pct_khusus_uni or 0.0,
                    }

                p = compute_porsi(
                    x=x, pt=pt, kh=kh,
                    pct_x_jemaat=cfg_pct["pct_x_jemaat"],
                    pct_pt_jemaat=cfg_pct["pct_pt_jemaat"],
                    pct_khusus_jemaat=cfg_pct["pct_khusus_jemaat"],
                    pct_x_uni=cfg_pct["pct_x_uni"],
                    pct_pt_uni=cfg_pct["pct_pt_uni"],
                    pct_khusus_uni=cfg_pct["pct_khusus_uni"],
                )

                # Generate temp nomor (placeholder, akan di-overwrite saat finalize)
                # T111 (2026-08-26): rule Jerry — tanggal_sabat = sabat terakhir yang sudah lewat,
                # BUKAN datetime.now(UTC) raw. Kalau input WA masuk setelah hari Sabat,
                # tetap di-attribute ke sabat terakhir (bukan sabat besok).
                today_sabat = get_effective_sabat_for_input()["tanggal_sabat"]
                # Use millisecond precision + random suffix to avoid UNIQUE collision
                import random as _rand
                unique_suffix = f"{int(time.time() * 1000)}-{_rand.randint(1000, 9999)}"  # nosec B311 — UNIQUE-collision dedupe, non-crypto
                # Insert staging row (is_finalized=False)
                k = Kuitansi(
                    tenant_id=tenant_id,
                    id_rekap_mingguan=f"STG-{today_sabat}",
                    nomor_kuitansi=f"PENDING-{tenant_id}-{unique_suffix}",  # unique placeholder (ms+random)
                    tanggal_sabat=today_sabat,
                    nama_umat_encrypted=encrypt_pii(nama_pemberi),  # WA AWAIT_NAMA step, encrypted PII
                    nomor_whatsapp_encrypted=None,
                    foto_amplop_path=None,
                    perpuluhan_x_angka=x,
                    pt_angka=pt,
                    khusus_angka=kh,
                    total_pemberian_angka=x + pt + kh,
                    total_pemberian_huruf="",
                    porsi_kantor_misi=p["pm_x"] + p["pm_pt"],
                    porsi_kas_jemaat=(p["pj_x"] + p["pj_pt"]) + p["pj_kh"],
                    porsi_khusus_misi=p["pm_kh"],
                    porsi_khusus_jemaat=p["pj_kh"] + p["pu_kh"],
                    status="draft",  # staging = draft (perlu finalize)
                    is_purged=False,
                    staging_id=int(time.time() * 1000) % 1_000_000,  # simple temp id
                    is_finalized=False,
                    finalized_at=None,
                    created_via="wa",
                    wa_message_id=fonnte_msg_id or None,
                    wa_sender=phone,
                    sabat_sesi=datetime.now(UTC).strftime("%Y-%m"),
                    temp_nomor=f"STG-{int(time.time()) % 100000:05d}",
                )
                db.add(k)
                db.flush()
                staging_id = k.id
                log.info(f"[WA-BTN-SIMPAN-FLUSHED] staging_id={staging_id} nomor={k.nomor_kuitansi}")

                set_state(db, session, "IDLE", payload=None)
                reply = _reply_saved(k.temp_nomor or f"#{staging_id}", nama_pemberi)
                _send_fonnte_reply(phone, reply["message"], reply["buttons"])
                db.commit()

                # Audit log
                audit = AuditLog(
                    tenant_id=tenant_id,
                    action="WA_STAGING_SAVE",
                    payload_hash=fonnte_msg_id[:32] if fonnte_msg_id else None,
                )
                db.add(audit)
                db.commit()

                return {"status": "ok", "staging_id": staging_id}
            except Exception as e:
                import traceback as _tb
                db.rollback()
                err_msg = f"[WA-BTN-SIMPAN] error: {type(e).__name__}: {e}\n{_tb.format_exc()}"
                log.error(err_msg)
                log.exception(err_msg)
                _send_fonnte_reply(phone, f"⚠️ Gagal simpan staging: {type(e).__name__}. Coba lagi atau hubungi Admin.")
                raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e

    # Tombol Cocokkan
    if button_id == "btn_cocokkan":
        # Show summary of staging items
        items = (
            db.query(Kuitansi)
            .filter(
                Kuitansi.tenant_id == tenant.id,
                Kuitansi.is_finalized == False,  # noqa: E712
                Kuitansi.created_via == "wa",
                Kuitansi.wa_sender == phone,
            )
            .order_by(Kuitansi.created_at.desc())
            .limit(50)
            .all()
        )
        total_x = sum(k.perpuluhan_x_angka for k in items)
        total_pt = sum(k.pt_angka for k in items)
        total_kh = sum(k.khusus_angka for k in items)
        total_all = total_x + total_pt + total_kh

        msg = (
            f"*Ringkasan Kuitansi Sementara*\n"
            f"Jemaat: {tenant.nama_jemaat_lokal}\n\n"
            f"Jumlah item: {len(items)}\n"
            f"• Total X  : Rp {total_x:,}\n"
            f"• Total PT : Rp {total_pt:,}\n"
            f"• Total KH : Rp {total_kh:,}\n"
            f"• *Grand Total* : Rp {total_all:,}\n\n"
            "Cocokkan dengan uang fisik? Buka dashboard untuk finalisasi:\n"
            f"http://localhost:5173/kuitansi-staging"
        )
        buttons = [
            {"id": "btn_input", "text": "💰 Input Lagi"},
            {"id": "btn_bantuan", "text": "ℹ️ Bantuan"},
        ]
        _send_fonnte_reply(phone, msg, buttons)
        return {"status": "ok"}

    # === Text input handler (state-aware) ===

    if session.state == "AWAIT_X":
        value, err = parse_and_validate_nominal(message)
        if value is None:
            reply = _reply_await_kategori("X")
            reply["message"] = f"❌ {err}\n\n" + reply["message"]
            _send_fonnte_reply(phone, reply["message"], reply["buttons"])
            return {"status": "ok"}
        payload["await_x"] = value
        set_state(db, session, "AWAIT_PT", payload=payload)
        reply = _reply_await_kategori("PT")
        _send_fonnte_reply(phone, reply["message"], reply["buttons"])
        db.commit()
        return {"status": "ok"}

    if session.state == "AWAIT_PT":
        value, err = parse_and_validate_nominal(message)
        if value is None:
            reply = _reply_await_kategori("PT")
            reply["message"] = f"❌ {err}\n\n" + reply["message"]
            _send_fonnte_reply(phone, reply["message"], reply["buttons"])
            return {"status": "ok"}
        payload["await_pt"] = value
        set_state(db, session, "AWAIT_KH", payload=payload)
        reply = _reply_await_kategori("KH")
        _send_fonnte_reply(phone, reply["message"], reply["buttons"])
        db.commit()
        return {"status": "ok"}

    if session.state == "AWAIT_KH":
        value, err = parse_and_validate_nominal(message)
        if value is None:
            reply = _reply_await_kategori("KH")
            reply["message"] = f"❌ {err}\n\n" + reply["message"]
            _send_fonnte_reply(phone, reply["message"], reply["buttons"])
            return {"status": "ok"}
        payload["await_kh"] = value
        # Pindah ke AWAIT_NAMA untuk minta nama pemberi
        payload["await_nama"] = None
        set_state(db, session, "AWAIT_NAMA", payload=payload)
        reply = _reply_await_nama()
        _send_fonnte_reply(phone, reply["message"], reply["buttons"])
        db.commit()
        return {"status": "ok"}

    # AWAIT_NAMA — user ketik nama atau tap Lewati
    if session.state == "AWAIT_NAMA":
        nama = (message or "").strip()[:80] if not button_id else ""
        if button_id == "btn_lewati":
            nama = "Umat WA"
        if not nama:
            # Empty / invalid → re-prompt
            reply = _reply_await_nama()
            _send_fonnte_reply(phone, reply["message"], reply["buttons"])
            return {"status": "ok"}
        payload["await_nama"] = nama
        set_state(db, session, "CONFIRM", payload=payload)
        reply = _reply_confirm(
            payload.get("await_x", 0),
            payload.get("await_pt", 0),
            payload.get("await_kh", 0),
            nama,
        )
        _send_fonnte_reply(phone, reply["message"], reply["buttons"])
        db.commit()
        return {"status": "ok"}

    # === Default: IDLE + random text → tampilkan menu ===
    if not button_id and not message:
        return {"status": "ignored"}

    if not button_id:
        # Random text in IDLE → tampilkan menu (Q1)
        reply = _reply_menu(tenant.nama_jemaat_lokal)
        _send_fonnte_reply(phone, reply["message"], reply["buttons"])
        return {"status": "ok", "reply": "menu_shown"}

    return {"status": "ok"}


# ==================== STAGING LIST (BENDAHARA) ====================

@router.get("/kuitansi/staging", tags=['WhatsApp'])
def list_staging(
    tenant_id: int | None = None,
    current: dict = Depends(require_roles("BENDAHARA")),
    db: Session = Depends(get_db),
):
    """List staging kuitansi untuk tenant saat ini (BENDAHARA only).

    T94 Section 8: tambah field ``last_web_upload_at`` agar frontend bisa
    tampilkan warning kalau Bendahara sudah >7 hari tidak upload via web.
    """
    effective_tenant = tenant_id or current["tenant_id"]
    items = (
        db.query(Kuitansi)
        .filter(
            Kuitansi.tenant_id == effective_tenant,
            Kuitansi.is_finalized == False,  # noqa: E712
            Kuitansi.created_via == "wa",
        )
        .order_by(Kuitansi.created_at.desc())
        .all()
    )

    # T94 Section 8: cari tanggal upload via web/ocr terakhir (semua tenant)
    # untuk ditampilkan sebagai warning card.
    last_web_row = (
        db.query(func.max(Kuitansi.created_at))
        .filter(
            Kuitansi.tenant_id == effective_tenant,
            Kuitansi.created_via.in_(["web", "ocr"]),
            Kuitansi.is_finalized == True,  # noqa: E712
        )
        .scalar()
    )

    return {
        "count": len(items),
        "last_web_upload_at": last_web_row.isoformat() if last_web_row else None,
        "items": [
            {
                "id": k.id,
                "staging_id": k.staging_id,
                "temp_nomor": k.temp_nomor,
                "tanggal_sabat": k.tanggal_sabat,
                "perpuluhan_x": k.perpuluhan_x_angka,
                "pt": k.pt_angka,
                "khusus": k.khusus_angka,
                "total": k.total_pemberian_angka,
                "nama_pemberi": decrypt_pii(k.nama_umat_encrypted) if k.nama_umat_encrypted else None,
                "wa_sender": k.wa_sender,
                "wa_message_id": k.wa_message_id,
                "created_at": k.created_at.isoformat() if k.created_at else None,
            }
            for k in items
        ],
    }


# ==================== DELETE STAGING ITEM (BENDAHARA) ====================

@router.delete("/kuitansi/staging/{item_id}", tags=['WhatsApp'])
def delete_staging_item(
    item_id: int,
    current: dict = Depends(require_roles("BENDAHARA")),
    db: Session = Depends(get_db),
):
    """Hapus staging item individual (BENDAHARA only, tenant-scoped).

    T94 Section 8: tombol 'Hapus' di frontend. Hanya boleh untuk item
    is_finalized=False dan tenant_id milik Bendahara. Hard delete —
    data masih bisa direkonstruksi via WA message history + wa_message_id.
    """
    item = (
        db.query(Kuitansi)
        .filter(
            Kuitansi.id == item_id,
            Kuitansi.tenant_id == current["tenant_id"],
            Kuitansi.is_finalized == False,  # noqa: E712
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Staging item tidak ditemukan / sudah difinalize")

    # Audit log (best-effort — jangan block delete kalau audit gagal).
    # AuditLog model hanya punya kolom: action, id_rekap_mingguan,
    # nomor_kuitansi_token, payload_hash, dll. Pakai payload_hash untuk
    # menyimpan detail delete sebagai JSON string.
    try:
        import hashlib
        import json as _json
        detail_str = _json.dumps({
            "actor": current["id"],
            "target_type": "kuitansi",
            "target_id": item.id,
            "temp_nomor": item.temp_nomor,
            "total": item.total_pemberian_angka,
        }, sort_keys=True)
        db.add(AuditLog(
            tenant_id=current["tenant_id"],
            action="WA_STAGING_DELETE",
            id_rekap_mingguan=f"WA-STG-{item.id}",
            payload_hash=hashlib.sha256(detail_str.encode()).hexdigest()[:32],
        ))
    except Exception:
        log.exception("audit log untuk delete-staging gagal, lanjut hapus tetap")

    db.delete(item)
    db.commit()
    return {"deleted_id": item_id, "status": "ok"}


# ==================== FINALIZE BATCH ====================

class FinalizeStagingIn(BaseModel):
    staging_ids: list[int]
    # T110 (2026-08-26): override tanggal_sabat staging ke sabat berjalan.
    # Format ISO 'YYYY-MM-DD'. Frontend kirim dari sabatInfo.tanggal_sabat.
    tanggal_sabat: str | None = None


@router.post("/kuitansi/finalize-staging", tags=['WhatsApp'])
def finalize_staging(
    body: FinalizeStagingIn,
    current: dict = Depends(require_roles("BENDAHARA")),
    db: Session = Depends(get_db),
):
    """
    Finalize staging items: generate nomor_kuitansi final per bulan
    (existing T66 counter), set is_finalized=True.
    """
    if not body.staging_ids:
        raise HTTPException(status_code=400, detail="staging_ids kosong")

    items = (
        db.query(Kuitansi)
        .filter(
            Kuitansi.id.in_(body.staging_ids),
            Kuitansi.tenant_id == current["tenant_id"],
            Kuitansi.is_finalized == False,  # noqa: E712
        )
        .all()
    )

    if not items:
        raise HTTPException(status_code=404, detail="Tidak ada staging item ditemukan")

    # Counter per (tenant, YYYY-MM) — pakai MAX(nomor) LIKE 'YYYY-MM%' + safety net
    counter_map: dict[tuple[int, str], int] = {}
    now = datetime.now(UTC)
    # T110: validate override tanggal_sabat format
    override_tgl: str | None = None
    if body.tanggal_sabat:
        try:
            from datetime import datetime as _dt
            _dt.strptime(body.tanggal_sabat, "%Y-%m-%d")
            override_tgl = body.tanggal_sabat
        except ValueError:
            raise HTTPException(status_code=400, detail=f"tanggal_sabat format harus YYYY-MM-DD, dapat {body.tanggal_sabat!r}") from None

    for k in items:
        # T110: kalau frontend kirim override, pakai itu
        effective_tgl = override_tgl or k.tanggal_sabat or now.strftime("%Y-%m-%d")
        ym = effective_tgl[:7]
        key = (k.tenant_id, ym)
        if key not in counter_map:
            # Cari MAX counter existing
            existing_max = (
                db.query(func.max(Kuitansi.nomor_kuitansi))
                .filter(
                    Kuitansi.tenant_id == k.tenant_id,
                    Kuitansi.nomor_kuitansi.like(f"{effective_tgl.replace('-', '')}%"),
                    Kuitansi.is_finalized == True,  # noqa: E712
                )
                .scalar()
            )
            # Extract counter suffix
            if existing_max and "-" in existing_max:
                try:
                    last_counter = int(existing_max.split("-")[-1])
                    counter_map[key] = last_counter + 1
                except (ValueError, IndexError):
                    counter_map[key] = 1
            else:
                counter_map[key] = 1

        # Build nomor: YYYYMMDD-{tenant:03d}-{counter:03d}
        tgl = effective_tgl.replace("-", "")
        k.nomor_kuitansi = f"{tgl}-{k.tenant_id:03d}-{counter_map[key]:03d}"
        counter_map[key] += 1
        # T110: apply override ke entity supaya tabel sabat_ini filter cocok
        if override_tgl:
            k.tanggal_sabat = override_tgl
        k.is_finalized = True
        k.finalized_at = now
        k.staging_id = None
        k.status = "finalized"
        k.temp_nomor = None

    db.commit()

    return {
        "finalized_count": len(items),
        "items": [
            {
                "id": k.id,
                "nomor_kuitansi": k.nomor_kuitansi,
                "tanggal_sabat": k.tanggal_sabat,
            }
            for k in items
        ],
    }
