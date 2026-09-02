"""
FLIPUS v1.1 — WhatsApp notifier via Fonnte API
"""

import os
from typing import Optional
from dotenv import load_dotenv
load_dotenv()
import requests
from app.utils.number_to_words import terbilang as rupiah_to_words



def _append_branding_footer(msg: str, footer_text: Optional[str] = None) -> str:
    """Append optional footer text + signature kalau ada."""
    if footer_text:
        msg += f"\n\n_{footer_text}_"
    return msg


def _get_greeting_with_branding(nama: str, nama_jemaat: Optional[str] = None) -> str:
    """Standard greeting dengan nama jemaat opsional."""
    if nama_jemaat:
        return f"*SELAMAT DATANG DI FLIPUS*\n\nGMAHK {nama_jemaat}\n\nShalom {nama},\n\n"
    return f"*SELAMAT DATANG DI FLIPUS*\n\nShalom {nama},\n\n"


def send_kuitansi_whatsapp(
    phone: str,
    nama: str,
    perpuluhan_x: int,
    pt: int,
    porsi_misi: int,
    porsi_jemaat: int,
) -> dict:
    token = os.getenv("FONNTE_TOKEN", "")
    enabled = os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"

    if not enabled:
        return {"status": "skipped", "reason": "WHATSAPP_ENABLED=false di .env"}

    if not token or token.startswith("paste_"):
        return {"status": "error", "reason": "FONNTE_TOKEN belum diisi di .env"}

    phone_clean = phone.replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("0"):
        phone_clean = "62" + phone_clean[1:]

    total = perpuluhan_x + pt
    msg = (
        "*TANDA TERIMA PERPULUHAN*\n"
        "GMAHK UKIKT\n\n"
        f"Salam sejahtera, *{nama}*.\n\n"
        "Kami menerima titipan perpuluhan Anda:\n"
        f"• Perpuluhan (X) : Rp {perpuluhan_x:,}\n"
        f"• Persembahan (PT): Rp {pt:,}\n"
        f"• *Total* : Rp {total:,}\n\n"
        "*Penyaluran:*\n"
        f"• Kantor Misi : Rp {porsi_misi:,}\n"
        f"• Kas Jemaat  : Rp {porsi_jemaat:,}\n\n"
        "*Terbilang:*\n"
        f"{rupiah_to_words(total)}\n\n"
        "Semoga Tuhan memberkati keluarga Anda. 🙏\n"
        "— Bendahara GMAHK UKIKT"
    )

    try:
        resp = requests.post(
            "https://api.fonnte.com/send",
            headers={"Authorization": token},
            data={"target": phone_clean, "message": msg, "countryCode": "62"},
            timeout=30,
        )
        result = resp.json()
        return {
            "status": "sent" if result.get("status") else "failed",
            "phone": phone_clean,
            "fonnte_response": result,
        }
    except Exception as e:
        return {"status": "error", "reason": str(e), "phone": phone_clean}

def send_simple_message(phone: str, message: str) -> dict:
    token = os.getenv("FONNTE_TOKEN", "")
    if not token:
        return {"status": "error", "reason": "no token"}

    phone_clean = phone.replace("+", "").replace(" ", "")
    if phone_clean.startswith("0"):
        phone_clean = "62" + phone_clean[1:]

    try:
        resp = requests.post(
            "https://api.fonnte.com/send",
            headers={"Authorization": token},
            data={"target": phone_clean, "message": message, "countryCode": "62"},
            timeout=30,
        )
        return resp.json()
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def send_document_message(
    phone: str,
    message: str,
    file_path: str,
    filename: Optional[str] = None,
) -> dict:
    """
    Kirim dokumen (PDF) via Fonnte dengan multipart upload.

    Fonnte support file upload via field 'file' di form-data.

    Reliability (T74):
    - Retry on Timeout/ConnectionError: up to settings.WA_BLAST_MAX_RETRIES
      dengan exponential backoff (WA_BLAST_RETRY_BACKOFF).
    - Rate limit: sleep WA_BLAST_RATE_PER_SEC detik di akhir fungsi supaya
      tidak exceed Fonnte ~60 req/menit.

    Args:
        phone: nomor WA target
        message: caption text
        file_path: absolute path ke file PDF
        filename: override nama file (default: basename dari file_path)

    Returns:
        dict {status: 'sent'/'failed'/'error'/'skipped', phone, filename, fonnte_response, reason}
    """
    import logging
    import sys as _sys
    import time as _time

    log = logging.getLogger("flipus.whatsapp")

    from pathlib import Path
    token = os.getenv("FONNTE_TOKEN", "").strip()
    enabled = os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"

    phone_clean = (phone or "").replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("0"):
        phone_clean = "62" + phone_clean[1:]

    if not enabled:
        msg = "WHATSAPP_ENABLED=false di .env (blast di-skip)"
        print(f"[WA] {msg} phone={phone_clean}", file=_sys.stderr)
        log.warning(msg)
        return {"status": "skipped", "reason": msg, "phone": phone_clean}

    if not token or token.startswith("paste_"):
        msg = "FONNTE_TOKEN belum diisi di .env"
        print(f"[WA] {msg} phone={phone_clean}", file=_sys.stderr)
        log.warning(msg)
        return {"status": "error", "reason": msg, "phone": phone_clean}

    if not phone_clean or phone_clean in ("0", "62"):
        msg = f"Nomor WhatsApp target kosong/invalid: {phone!r}"
        print(f"[WA] {msg}", file=_sys.stderr)
        log.warning(msg)
        return {"status": "error", "reason": msg, "phone": phone_clean}

    p = Path(file_path)
    if not p.exists():
        msg = f"File PDF tidak ditemukan: {file_path}"
        print(f"[WA] {msg}", file=_sys.stderr)
        log.warning(msg)
        return {"status": "error", "reason": msg, "phone": phone_clean}

    fname = filename or p.name

    # T74: Retry loop dengan exponential backoff.
    max_retries = max(1, int(os.getenv("WA_BLAST_MAX_RETRIES", "3")))
    base_backoff = float(os.getenv("WA_BLAST_RETRY_BACKOFF", "2.0"))
    rate_sleep = float(os.getenv("WA_BLAST_RATE_PER_SEC", "1.1"))

    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            with open(file_path, "rb") as f:
                resp = requests.post(
                    "https://api.fonnte.com/send",
                    headers={"Authorization": token},
                    data={"target": phone_clean, "message": message, "countryCode": "62"},
                    files={"file": (fname, f, "application/pdf")},
                    timeout=60,
                )
            result = resp.json()
            ok = bool(result.get("status"))
            reason = ""
            if not ok:
                reason = (
                    result.get("reason")
                    or result.get("detail")
                    or result.get("message")
                    or "Fonnte reply tanpa field 'status=true'"
                )
            print(
                f"[WA] blast phone={phone_clean} attempt={attempt}/{max_retries} "
                f"status={'sent' if ok else 'failed'} reason={reason!r}",
                file=_sys.stderr,
            )
            log.info(f"blast phone={phone_clean} attempt={attempt} ok={ok} reason={reason!r}")
            ret = {
                "status": "sent" if ok else "failed",
                "phone": phone_clean,
                "filename": fname,
                "attempts": attempt,
                "reason": reason,
                "fonnte_response": result,
            }
            # T74: Rate limit antar call — sleep di akhir supaya caller berikutnya tidak exceed limit.
            # Skip sleep kalau ini adalah call terakhir di batch (caller bisa set _suppress_rate_sleep)
            if not getattr(send_document_message, "_suppress_rate_sleep", False):
                _time.sleep(rate_sleep)
            return ret
        except requests.exceptions.Timeout as e:
            last_exc = e
            wait = base_backoff * (2 ** (attempt - 1))
            print(
                f"[WA] blast phone={phone_clean} attempt={attempt}/{max_retries} TIMEOUT, "
                f"retry dalam {wait:.1f}s",
                file=_sys.stderr,
            )
            log.warning(f"blast timeout attempt {attempt}: {e}")
            if attempt < max_retries:
                _time.sleep(wait)
        except requests.exceptions.ConnectionError as e:
            last_exc = e
            wait = base_backoff * (2 ** (attempt - 1))
            print(
                f"[WA] blast phone={phone_clean} attempt={attempt}/{max_retries} CONNECTION_ERROR, "
                f"retry dalam {wait:.1f}s: {e}",
                file=_sys.stderr,
            )
            log.warning(f"blast conn error attempt {attempt}: {e}")
            if attempt < max_retries:
                _time.sleep(wait)
        except Exception as e:
            # Unexpected — tidak retry
            msg = f"{type(e).__name__}: {e}"
            print(f"[WA] blast error phone={phone_clean} {msg}", file=_sys.stderr)
            log.error(f"blast error {msg}")
            return {
                "status": "error", "reason": msg, "phone": phone_clean, "filename": fname,
                "attempts": attempt,
            }

    # All retries exhausted
    msg = (
        f"Gagal setelah {max_retries} attempt (last error: "
        f"{type(last_exc).__name__ if last_exc else 'unknown'}: {last_exc})"
    )
    print(f"[WA] blast phone={phone_clean} EXHAUSTED: {msg}", file=_sys.stderr)
    log.error(msg)
    return {
        "status": "failed", "reason": msg, "phone": phone_clean, "filename": fname,
        "attempts": max_retries,
    }


def send_auto_thanks(
    phone: str,
    nama: str,
    nama_jemaat: str,
    tanggal_sabat: str,
    perpuluhan_x: int,
    pt: int,
    khusus: int = 0,
    nama_pendeta: str = "Pendeta",
    nama_bendahara: str = "Bendahara",
) -> dict:
    """
    Auto-thanks message — dikirim otomatis ke unit pemberi jika nomor WA terbaca di amplop.

    Format: personal, singkat, menggugah. Signed by Pendeta + Bendahara.
    """
    token = os.getenv("FONNTE_TOKEN", "")
    enabled = os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"

    if not enabled:
        return {"status": "skipped", "reason": "WHATSAPP_ENABLED=false"}

    if not token or token.startswith("paste_"):
        return {"status": "error", "reason": "FONNTE_TOKEN belum diisi"}

    phone_clean = phone.replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("0"):
        phone_clean = "62" + phone_clean[1:]

    total = perpuluhan_x + pt + khusus

    # Build bagian khusus (hanya jika > 0)
    khusus_line = f"• Persembahan Khusus : Rp {khusus:,}\n" if khusus > 0 else ""

    msg = (
        f"Shalom {nama},\n\n"
        f"Atas nama jemaat GMAHK {nama_jemaat}, kami mengucapkan "
        f"terima kasih yang sebesar-besarnya atas persembahan Anda "
        f"pada Sabat {tanggal_sabat}. Tuhan Yesus yang murah hati "
        f"memberkati kehidupan Saudara sekeluarga.\n\n"
        f"*Rincian Pemberian:*\n"
        f"• Perpuluhan (X) : Rp {perpuluhan_x:,}\n"
        f"• Persembahan Terpadu (PT) : Rp {pt:,}\n"
        f"{khusus_line}"
        f"• *Total* : Rp {total:,}\n\n"
        f"Melayani jemaat adalah sukacita kami.\n\n"
        f"Tertanda,\n"
        f"Pdt. {nama_pendeta}\n"
        f"Bendahara {nama_bendahara}\n"
        f"Jemaat GMAHK {nama_jemaat}"
    )

    try:
        resp = requests.post(
            "https://api.fonnte.com/send",
            headers={"Authorization": token},
            data={"target": phone_clean, "message": msg, "countryCode": "62"},
            timeout=30,
        )
        result = resp.json()
        return {
            "status": "sent" if result.get("status") else "failed",
            "phone": phone_clean,
            "nama": nama,
            "fonnte_response": result,
        }
    except Exception as e:
        return {"status": "error", "reason": str(e), "phone": phone_clean}

def get_device_status() -> dict:
    """
    v1.5-F: Cek status device Fonnte (connected/disconnected/quota).

    Returns:
        dict {
            'status': 'connected' | 'disconnected' | 'unknown',
            'device': str | None,
            'phone': str | None,
            'quota': int | None,
            'quota_remaining': int | None,
            'expired': str | None,
            'reason': str | None,
        }
    """
    import logging
    token = os.getenv("FONNTE_TOKEN", "").strip()
    enabled = os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"

    if not enabled:
        return {
            "status": "disabled",
            "device": None,
            "phone": None,
            "quota": None,
            "quota_remaining": None,
            "expired": None,
            "reason": "WHATSAPP_ENABLED=false di .env",
        }

    if not token or token.startswith("paste_"):
        return {
            "status": "no_token",
            "device": None,
            "phone": None,
            "quota": None,
            "quota_remaining": None,
            "expired": None,
            "reason": "FONNTE_TOKEN belum diisi di .env",
        }

    try:
        resp = requests.post(
            "https://api.fonnte.com/get-device",
            headers={"Authorization": token},
            timeout=15,
        )
        # Fonnte v2025: /get-device endpoint di-deprecated → return 404
        # Fallback ke status='unknown' supaya WA Bot tetap bisa kirim via /send
        if resp.status_code == 404:
            logging.getLogger("flipus.whatsapp").warning(
                "Fonnte /get-device deprecated (404). Cek device manual di console."
            )
            return {
                "status": "unknown",
                "device": None,
                "phone": None,
                "quota": None,
                "quota_remaining": None,
                "expired": None,
                "reason": "Fonnte /get-device deprecated (404). Cek device manual di https://fonnte.com/app/console",
            }
        resp.raise_for_status()
        result = resp.json()
        # Fonnte get-device returns: {status: bool, device: ..., phone: ..., quota: int, quota_remaining: int, expired: str}
        is_connected = bool(result.get("status"))
        return {
            "status": "connected" if is_connected else "disconnected",
            "device": result.get("device"),
            "phone": result.get("phone"),
            "quota": result.get("quota"),
            "quota_remaining": result.get("quota_remaining"),
            "expired": result.get("expired"),
            "reason": (
                result.get("reason")
                or result.get("detail")
                or ("Device connected" if is_connected else "Device tidak terhubung / expired")
            ),
        }
    except Exception as e:
        log_msg = f"get_device_status error: {type(e).__name__}: {e}"
        try:
            logging.getLogger("flipus.whatsapp").error(log_msg)
        except Exception:
            pass
        return {
            "status": "error",
            "device": None,
            "phone": None,
            "quota": None,
            "quota_remaining": None,
            "expired": None,
            "reason": log_msg,
        }


def build_credentials_message_tenant(
    role_label: str,
    unit_name: str,
    username: str,
    password: str,
    tenant,
) -> str:
    """
    Build credentials message with tenant branding (Tahap 21).
    """
    greeting = "Shalom,"
    if tenant:
        greeting = f"Shalom,\n\nAtas nama jemaat GMAHK {tenant.nama_jemaat_lokal}, kami mengucapkan selamat datang."

    msg = (
        f"*SELAMAT DATANG DI FLIPUS*\n\n"
        f"{greeting}\n\n"
        f"Akun {role_label} untuk {unit_name} telah aktif di FLIPUS.\n\n"
        f"*Kredensial Anda:*\n"
        f"Username: {username}\n"
        f"Password: {password}\n\n"
        f"Login di: [link app akan dikirim setelah deploy]\n\n"
        f"Segera ganti password setelah login pertama."
    )

    if tenant and tenant.footer_text:
        msg += f"\n\n_{tenant.footer_text}_"

    msg += "\n\n— Sistem FLIPUS"
    return msg


def build_thanks_message_tenant(
    nama: str,
    nama_jemaat: str,
    tanggal_sabat: str,
    perpuluhan_x: int,
    pt: int,
    khusus: int,
    nama_pendeta: str,
    nama_bendahara: str,
    tenant=None,
) -> str:
    """
    Build auto-thanks message with tenant branding (Tahap 21).
    """
    total = perpuluhan_x + pt + khusus
    khusus_line = f"• Persembahan Khusus : Rp {khusus:,}\n" if khusus > 0 else ""

    msg = (
        f"Shalom {nama},\n\n"
        f"Atas nama jemaat GMAHK {nama_jemaat}, kami mengucapkan "
        f"terima kasih yang sebesar-besarnya atas persembahan Anda "
        f"pada Sabat {tanggal_sabat}. Tuhan Yesus yang murah hati "
        f"memberkati kehidupan Saudara sekeluarga.\n\n"
        f"*Rincian Pemberian:*\n"
        f"• Perpuluhan (X) : Rp {perpuluhan_x:,}\n"
        f"• Persembahan Terpadu (PT) : Rp {pt:,}\n"
        f"{khusus_line}"
        f"• *Total* : Rp {total:,}\n\n"
        f"Melayani jemaat adalah sukacita kami.\n\n"
        f"Tertanda,\n"
        f"Pdt. {nama_pendeta}\n"
        f"Bendahara {nama_bendahara}\n"
        f"Jemaat GMAHK {nama_jemaat}"
    )

    if tenant and tenant.footer_text:
        msg += f"\n\n_{tenant.footer_text}_"

    return msg


def build_blast_message_tenant(
    nama_jemaat: str,
    id_rekap: str,
    tanggal_sabat: str,
    total_x: int,
    total_pt: int,
    grand_total: int,
    tenant=None,
) -> str:
    """
    Build weekly blast message with tenant branding (Tahap 21).
    """
    msg = (
        f"*LAPORAN MINGGUAN*\n\n"
        f"Jemaat: *{nama_jemaat}*\n"
        f"ID Rekap: {id_rekap}\n"
        f"Tanggal Sabat: {tanggal_sabat}\n\n"
        f"*Ringkasan:*\n"
        f"• Perpuluhan (X): Rp {total_x:,}\n"
        f"• Persembahan (PT): Rp {total_pt:,}\n"
        f"• *Total*: Rp {grand_total:,}\n\n"
        f"Laporan lengkap terlampir."
    )

    if tenant and tenant.footer_text:
        msg += f"\n\n_{tenant.footer_text}_"

    msg += "\n\n— Sistem FLIPUS"
    return msg

