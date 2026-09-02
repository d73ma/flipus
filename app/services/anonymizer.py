"""
FLIPUS v1.1 — Anonymizer Service
=================================
Strip PII dari Kuitansi sebelum di-sync ke Kantor Misi / Uni.
Sesuai policy privasi GMAHK UKIKT: hanya agregat yang dikirim.
"""
import hashlib
import json
from app.models.transaction import Kuitansi

# Field PII yang JANGAN pernah dikirim ke Kantor Misi / Uni
PII_FIELDS = frozenset({
    "nama_umat_encrypted",
    "nomor_whatsapp_encrypted",
    "foto_amplop_path",
})

# Field yang AMAN dikirim ke Kantor Misi (agregat only)
SAFE_FIELDS = (
    "nomor_kuitansi",
    "id_rekap_mingguan",
    "tanggal_sabat",
    "perpuluhan_x_angka",
    "pt_angka",
    "total_pemberian_angka",
    "porsi_kantor_misi",
    "porsi_kas_jemaat",
)

def anonymize_kuitansi(k: "Kuitansi", nama_jemaat: str) -> dict:
    """
    Return dict berisi field AMAN saja (no PII) + payload_hash SHA-256.

    Args:
        k: instance Kuitansi
        nama_jemaat: nama jemaat (diizinkan masuk sync — bukan nama pemberi)

    Returns:
        dict dengan 9 key: 8 SAFE_FIELDS + payload_hash + nama_jemaat_lokal
    """
    payload = {"nama_jemaat_lokal": nama_jemaat}
    for field in SAFE_FIELDS:
        payload[field] = getattr(k, field, None)
    payload["payload_hash"] = compute_hash(payload)
    return payload

def compute_hash(payload: dict) -> str:
    """SHA-256 hex dari JSON kanonik (sorted keys, no whitespace)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def anonymize_batch(kuitansi_list: list, nama_jemaat: str) -> list:
    """Anonymize list of Kuitansi. Skip yang sudah purged atau null."""
    out = []
    for k in kuitansi_list:
        if getattr(k, "is_purged", False):
            continue
        out.append(anonymize_kuitansi(k, nama_jemaat))
    return out

def verify_hash(payload: dict) -> bool:
    """Cek apakah payload_hash di dict cocok dengan hash isi field lain."""
    if "payload_hash" not in payload:
        return False
    expected = payload["payload_hash"]
    test = {k: v for k, v in payload.items() if k != "payload_hash"}
    return compute_hash(test) == expected