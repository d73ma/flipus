"""
v2.0 M6 — WA Input Bot untuk Pengeluaran.

Chat WA center: Bendahara kirim chat dengan keyword "keluar" / "pengeluaran"
→ bot masuk mode AWAIT_NOMINAL → AWAIT_PENERIMA → AWAIT_KATEGORI → CONFIRM → SAVE.

Pattern lebih sederhana dari Kuitansi (single-step, satu pengeluaran = satu chat).
Reuse WaSession.state machine, tambah state P_*: P_IDLE, P_AWAIT_NOMINAL, P_AWAIT_PENERIMA, P_AWAIT_KATEGORI, P_CONFIRM, P_SAVED.
"""
import json
import re
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.wa_session import WaSession
from app.models.pengeluaran import Pengeluaran
from app.models.kategori_pengeluaran import KategoriPengeluaran
from app.models.user import User
from app.models.tenant import Tenant
from app.models.audit import AuditLog
from app.services.whatsapp import send_simple_message

router = APIRouter()
log = logging.getLogger("flipus.pengeluaran_wa")

# === State machine untuk Pengeluaran ===
P_VALID_STATES = {
    "P_IDLE": ["P_AWAIT_NOMINAL"],
    "P_AWAIT_NOMINAL": ["P_AWAIT_PENERIMA", "P_IDLE"],
    "P_AWAIT_PENERIMA": ["P_AWAIT_KATEGORI", "P_IDLE"],
    "P_AWAIT_KATEGORI": ["P_CONFIRM", "P_IDLE"],
    "P_CONFIRM": ["P_SAVED", "P_IDLE"],
    "P_SAVED": ["P_IDLE"],
}

P_TIMEOUT_MINUTES = 15

# Keyword triggers
TRIGGER_KEYWORDS = ["keluar", "pengeluaran", "bayar"]


def _ensure_p_state(session: WaSession, expected: str):
    if session.state != expected:
        return False
    return True


def _set_p_state(db: Session, session: WaSession, new_state: str, payload: Optional[dict] = None):
    if new_state not in P_VALID_STATES:
        raise ValueError(f"Invalid P-state: {new_state}")
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    session.state = new_state
    if payload is not None:
        session.payload = json.dumps(payload)
    elif new_state == "P_IDLE":
        session.payload = None
        session.expires_at = None
    session.updated_at = now_naive
    if new_state != "P_IDLE":
        session.expires_at = now_naive


def _parse_nominal(text: str) -> Optional[int]:
    """Extract nominal dari teks. Support 250k, 1.5jt, 250000, 250,000."""
    t = text.strip().lower().replace(".", "").replace(",", "")
    t = t.replace("rp", "").replace(" ", "")
    # 1jt = 1000000, 1m = 1000000
    mult = 1
    if t.endswith("jt") or t.endswith("juta"):
        t = t.replace("jt", "").replace("juta", "")
        mult = 1_000_000
    elif t.endswith("k") or t.endswith("rb") or t.endswith("ribu"):
        t = t[:-1] if t.endswith("k") else t.replace("rb", "").replace("ribu", "")
        mult = 1_000
    elif t.endswith("m"):
        t = t[:-1]
        mult = 1_000_000
    t = re.sub(r"[^0-9]", "", t)
    if not t:
        return None
    try:
        return int(t) * mult
    except ValueError:
        return None


def _detect_sender_tenant(db: Session, phone: str) -> Optional[Tenant]:
    """Find tenant based on sender phone. Match ke nomor_whatsapp Bendahara tenant.

    Coba beberapa format: 62xxx, 08xxx, +62xxx.
    Seed demo pakai format 62xxx langsung (tanpa leading 0).
    """
    candidates = [phone]
    if phone.startswith("62"):
        candidates.append("0" + phone[2:])
    elif phone.startswith("08"):
        candidates.append("62" + phone[1:])
    elif phone.startswith("8"):
        candidates.append("62" + phone)
        candidates.append("0" + phone)

    user = db.query(User).filter(
        User.nomor_whatsapp.in_(candidates),
        User.role == "BENDAHARA",
        User.is_active == True,
    ).first()
    if user:
        return db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    return None


def _gen_nomor_pengeluaran_inline(db: Session, tenant_id: int, tanggal: str) -> str:
    today_compact = tanggal.replace("-", "")[:8]
    prefix = f"OUT-{today_compact}-"
    existing = db.query(Pengeluaran).filter(
        Pengeluaran.tenant_id == tenant_id,
        Pengeluaran.nomor_pengeluaran.like(f"{prefix}%"),
    ).all()
    seq = max([int(p.nomor_pengeluaran.split("-")[-1] or 0) for p in existing], default=0) + 1
    return f"{prefix}{seq:03d}"


@router.post("/wa/pengeluaran/inbound")
async def wa_pengeluaran_inbound(request: Request, db: Session = Depends(get_db)):
    """Webhook Fonnte untuk chat Bendahara terkait Pengeluaran."""
    body = await request.json()
    sender = body.get("sender") or body.get("from") or ""
    message = (body.get("message") or "").strip()
    # Normalisasi phone
    phone = sender.replace("@c.us", "").replace("+", "").replace(" ", "")
    if not phone.startswith("62"):
        phone = "62" + phone.lstrip("0")

    log.info(f"[WA-PENG-INBOUND] phone={phone} msg={message[:80]}")

    # Detect tenant
    tenant = _detect_sender_tenant(db, phone)
    if not tenant:
        return {"status": "ignored", "reason": "sender bukan Bendahara aktif"}

    # Get/create session
    session = db.query(WaSession).filter(WaSession.phone == phone).first()
    if session is None:
        session = WaSession(phone=phone, state="P_IDLE", payload=None,
                            updated_at=datetime.now(timezone.utc).replace(tzinfo=None))
        db.add(session)
        db.flush()
    elif session.state.startswith("P_") is False:
        # Bukan session Pengeluaran, tetap IDLE.
        session.state = "P_IDLE"
        session.payload = None

    current_state = session.state
    payload = json.loads(session.payload) if session.payload else {}
    msg_low = message.lower().strip()

    # === Trigger dari IDLE ===
    if current_state == "P_IDLE":
        if any(kw in msg_low for kw in TRIGGER_KEYWORDS) and len(msg_low) < 40:
            # Enter mode Pengeluaran
            _set_p_state(db, session, "P_AWAIT_NOMINAL")
            db.commit()
            reply = f"💸 *Input Pengeluaran*\n_{tenant.nama_jemaat_lokal}_\n\nBerapa nominalnya? (contoh: 250000 atau 250k)"
            _send_reply(phone, reply)
            return {"status": "ok", "state": "P_AWAIT_NOMINAL"}
        else:
            # Bukan trigger, abaikan (handle oleh wa_input.py kalau ada)
            return {"status": "ignored", "reason": "no trigger keyword"}

    # === AWAIT_NOMINAL ===
    if current_state == "P_AWAIT_NOMINAL":
        # Kalau "batal" → cancel
        if msg_low in ("batal", "cancel", "stop"):
            _set_p_state(db, session, "P_IDLE")
            db.commit()
            _send_reply(phone, "❌ Dibatalkan.")
            return {"status": "cancelled"}

        nominal = _parse_nominal(message)
        if nominal is None or nominal <= 0:
            _send_reply(phone, "⚠️ Nominal tidak valid. Coba lagi (contoh: 250000 atau 250k).\nKetik *batal* untuk cancel.")
            return {"status": "invalid_nominal"}

        payload["nominal"] = nominal
        _set_p_state(db, session, "P_AWAIT_PENERIMA", payload)
        db.commit()
        reply = f"✅ Nominal: Rp {nominal:,}\n\nSiapa penerimanya? (contoh: PLN, Toko ATK, Bpk. Budi)"
        _send_reply(phone, reply)
        return {"status": "ok", "state": "P_AWAIT_PENERIMA"}

    # === AWAIT_PENERIMA ===
    if current_state == "P_AWAIT_PENERIMA":
        if msg_low in ("batal", "cancel", "stop"):
            _set_p_state(db, session, "P_IDLE")
            db.commit()
            _send_reply(phone, "❌ Dibatalkan.")
            return {"status": "cancelled"}

        penerima = message.strip()[:100]
        if not penerima:
            _send_reply(phone, "⚠️ Penerima kosong. Coba lagi.")
            return {"status": "invalid_penerima"}

        payload["penerima"] = penerima
        _set_p_state(db, session, "P_AWAIT_KATEGORI", payload)
        db.commit()

        # List kategori aktif tenant
        kats = db.query(KategoriPengeluaran).filter(
            KategoriPengeluaran.tenant_id == tenant.id,
            KategoriPengeluaran.is_aktif == True,
        ).order_by(KategoriPengeluaran.urutan).all()
        # Format pilihan
        kat_list = "\n".join([f"  {i+1}. {k.nama} ({k.alias}){'(rutin)' if k.is_rutin else ''}" for i, k in enumerate(kats)])
        reply = f"✅ Penerima: {penerima}\n\nPilih kategori:\n{kat_list}\n\nKetik *nomor* atau *alias* (LIS/AIR/TLP/KOSTOR/dll)."
        _send_reply(phone, reply)
        return {"status": "ok", "state": "P_AWAIT_KATEGORI", "kategori_count": len(kats)}

    # === AWAIT_KATEGORI ===
    if current_state == "P_AWAIT_KATEGORI":
        if msg_low in ("batal", "cancel", "stop"):
            _set_p_state(db, session, "P_IDLE")
            db.commit()
            _send_reply(phone, "❌ Dibatalkan.")
            return {"status": "cancelled"}

        # Match by alias, nama, atau nomor urut
        kats = db.query(KategoriPengeluaran).filter(
            KategoriPengeluaran.tenant_id == tenant.id,
            KategoriPengeluaran.is_aktif == True,
        ).order_by(KategoriPengeluaran.urutan).all()

        chosen: Optional[KategoriPengeluaran] = None
        # Try numeric index
        if msg_low.isdigit():
            idx = int(msg_low) - 1
            if 0 <= idx < len(kats):
                chosen = kats[idx]
        # Try alias
        if chosen is None:
            chosen = next((k for k in kats if k.alias.lower() == msg_low), None)
        # Try nama (case-insensitive contains)
        if chosen is None:
            chosen = next((k for k in kats if msg_low in k.nama.lower()), None)

        if not chosen:
            _send_reply(phone, "⚠️ Kategori tidak dikenal. Coba lagi dengan nomor/alias/nama.")
            return {"status": "invalid_kategori"}

        payload["kategori_pengeluaran_id"] = chosen.id
        payload["kategori_nama"] = chosen.nama
        payload["is_rutin"] = chosen.is_rutin
        _set_p_state(db, session, "P_CONFIRM", payload)
        db.commit()

        rutin_label = "✅ auto-approved (rutin)" if chosen.is_rutin else "⏳ perlu approval Ketua + Pendeta"
        reply = (
            f"📋 *Konfirmasi Pengeluaran*\n\n"
            f"Kategori: {chosen.nama} ({chosen.alias})\n"
            f"Nominal: Rp {payload['nominal']:,}\n"
            f"Penerima: {payload['penerima']}\n"
            f"Workflow: {rutin_label}\n\n"
            f"Ketik *ya* untuk simpan, atau *batal* untuk cancel."
        )
        _send_reply(phone, reply)
        return {"status": "ok", "state": "P_CONFIRM"}

    # === CONFIRM ===
    if current_state == "P_CONFIRM":
        if msg_low in ("batal", "cancel", "stop", "tidak", "no"):
            _set_p_state(db, session, "P_IDLE")
            db.commit()
            _send_reply(phone, "❌ Dibatalkan.")
            return {"status": "cancelled"}
        if msg_low not in ("ya", "y", "yes", "ok", "simpan", "s"):
            _send_reply(phone, "⚠️ Ketik *ya* untuk simpan, atau *batal*.")
            return {"status": "invalid_confirm"}

        # Save Pengeluaran
        tanggal = datetime.now().strftime("%Y-%m-%d")
        id_rekap = f"WA-{tanggal}"
        nomor = _gen_nomor_pengeluaran_inline(db, tenant.id, tanggal)

        p = Pengeluaran(
            tenant_id=tenant.id,
            id_rekap_mingguan=id_rekap,
            nomor_pengeluaran=nomor,
            tanggal=tanggal,
            tanggal_sabat=tanggal,
            kategori_pengeluaran_id=payload["kategori_pengeluaran_id"],
            jumlah=payload["nominal"],
            deskripsi=f"Input via WA oleh {phone}",
            penerima=payload["penerima"],
            metode_bayar="tunai",
            bukti_path=None,
            status='draft',
            created_via='wa',
        )
        db.add(p)
        db.flush()

        # Auto-submit (apply approval workflow)
        is_rutin = payload.get("is_rutin", False)
        if is_rutin:
            p.status = 'approved'
            # Lookup Bendahara user
            user = db.query(User).filter(User.tenant_id == tenant.id, User.role == "BENDAHARA", User.is_active == True).first()
            if user:
                p.created_by_user_id = user.id
                p.approved_ketua_by_user_id = user.id  # auto-stub (rutin skip approval)
                p.approved_pendeta_by_user_id = user.id
                p.approved_ketua_at = datetime.now(timezone.utc).replace(tzinfo=None)
                p.approved_pendeta_at = p.approved_ketua_at
        else:
            p.status = 'pending_approval'
            user = db.query(User).filter(User.tenant_id == tenant.id, User.role == "BENDAHARA", User.is_active == True).first()
            if user:
                p.created_by_user_id = user.id

        db.add(AuditLog(
            tenant_id=tenant.id,
            action=f"WA_PENGELUARAN_SAVE_id_{p.id}_by_user_{p.created_by_user_id}_via_wa_bot_nomor_{nomor}_jumlah_{payload['nominal']}_rutin_{is_rutin}",
        ))
        _set_p_state(db, session, "P_SAVED")
        db.commit()

        status_label = "✅ AUTO-APPROVED" if is_rutin else "⏳ PENDING APPROVAL (Ketua → Pendeta)"
        reply = (
            f"✅ Tersimpan!\n\n"
            f"Nomor: {nomor}\n"
            f"Kategori: {payload['kategori_nama']}\n"
            f"Nominal: Rp {payload['nominal']:,}\n"
            f"Penerima: {payload['penerima']}\n"
            f"Status: {status_label}\n\n"
            f"Ketik *keluar* untuk input lagi, atau *batal* untuk selesai."
        )
        _send_reply(phone, reply)
        return {"status": "saved", "nomor": nomor, "is_rutin": is_rutin}

    # === Default: clear state ===
    _set_p_state(db, session, "P_IDLE")
    db.commit()
    return {"status": "unknown_state_cleared"}


def _send_reply(phone: str, message: str):
    """Send WA reply via Fonnte. Best-effort, swallow error."""
    try:
        send_simple_message(phone, message)
    except Exception as exc:
        err = f"[WA-PENG-REPLY] failed: {type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        print(err, file=sys.stderr)


@router.post("/wa/pengeluaran/reset")
def reset_session(request: Request, db: Session = Depends(get_db)):
    """Admin endpoint untuk reset WaSession P_*. Body: {phone: ...}."""
    body = __import__("asyncio").run(request.json())
    phone = body.get("phone", "").replace("+", "").replace(" ", "")
    if not phone.startswith("62"):
        phone = "62" + phone.lstrip("0")
    session = db.query(WaSession).filter(WaSession.phone == phone).first()
    if session and session.state.startswith("P_"):
        session.state = "P_IDLE"
        session.payload = None
        db.commit()
        return {"status": "reset", "phone": phone}
    return {"status": "no_p_session", "phone": phone}