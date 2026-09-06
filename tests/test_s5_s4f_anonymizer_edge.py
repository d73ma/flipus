"""
FASE 5 Sprint 4 — Unit tests for app/services/anonymizer.py.

Covers edge cases in batch anonymization (skip purged) and hash verification
(missing payload_hash, tampered payload).
"""

import hashlib
import json

from app.services.anonymizer import anonymize_batch, verify_hash


class _FakeKuitansi:
    """Minimal stand-in for app.models.transaction.Kuitansi."""

    def __init__(self, is_purged: bool = False, **kwargs: object) -> None:
        self.is_purged = is_purged
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestAnonymizeBatch:
    def test_skips_purged(self) -> None:
        active = _FakeKuitansi(
            nomor_kuitansi="001/NT/I/26",
            id_rekap_mingguan="RK-20260101-2026W01",
            tanggal_sabat="2026-01-03",
            perpuluhan_x_angka=100000,
            pt_angka=0,
            total_pemberian_angka=100000,
            porsi_kantor_misi=100000,
            porsi_kas_jemaat=0,
        )
        purged = _FakeKuitansi(is_purged=True, nomor_kuitansi="002/NT/I/26")
        out = anonymize_batch([active, purged], nama_jemaat="Nataan")
        assert len(out) == 1
        assert out[0]["nomor_kuitansi"] == "001/NT/I/26"

    def test_returns_empty_for_empty_input(self) -> None:
        assert anonymize_batch([], nama_jemaat="Nataan") == []

    def test_all_purged_returns_empty(self) -> None:
        purged = _FakeKuitansi(is_purged=True)
        assert anonymize_batch([purged, purged], nama_jemaat="X") == []


class TestVerifyHash:
    def test_missing_payload_hash(self) -> None:
        """verify_hash returns False when no payload_hash key."""
        assert verify_hash({"nomor_kuitansi": "001/NT/I/26"}) is False

    def test_matching_hash(self) -> None:
        """verify_hash returns True for a valid payload_hash."""
        payload = {
            "nomor_kuitansi": "001/NT/I/26",
            "nominal": 100000,
        }
        # Compute hash the same way the implementation does
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        payload["payload_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
        assert verify_hash(payload) is True

    def test_tampered_hash(self) -> None:
        """verify_hash returns False when payload was tampered after signing."""
        payload = {
            "nomor_kuitansi": "001/NT/I/26",
            "nominal": 100000,
            "payload_hash": "0" * 64,  # wrong hash
        }
        assert verify_hash(payload) is False
