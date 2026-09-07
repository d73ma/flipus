"""
FASE 5 Sprint 7 — Additional _wa_inbound_impl branch coverage.

Covers remaining branches:
- Multi-tenant Bendahara: pilih_jemaat + btn_pilih_<id>
- btn_cocokkan summary (with staging items)
- Max staging per day guard
- form-data / JSON wrapper (wa_inbound + _set_wa_from_state)
"""

import asyncio

import pytest

from app.core.security import encrypt_pii, hash_password


def _run_impl(db, body, monkeypatch: pytest.MonkeyPatch):
    from app.api.v1 import wa_input

    replies = []

    def fake_send(phone, message, buttons=None):
        replies.append((phone, message))
        return {"status": "sent"}

    monkeypatch.setattr(wa_input, "_send_fonnte_reply", fake_send)
    result = asyncio.run(wa_input._wa_inbound_impl(None, db, body))
    return result, replies


class TestMultiTenantBendahara:
    def _make_multi_tenant_bendahara(self, test_db, jemaat_a, jemaat_b):
        """Bendahara yang terdaftar di 2 jemaat (nomor_whatsapp sama)."""
        from app.models.user import User

        db = test_db()
        u = User(
            username="bendahara_multi",
            nama_lengkap="Multi Tenant Bendahara",
            password_hash=hash_password("Bendahara123!"),
            role="BENDAHARA",
            tenant_id=jemaat_a.id,
            is_active=True,
            nomor_whatsapp="6281234567900",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        u2 = User(
            username="bendahara_multi_2",
            nama_lengkap="Multi Tenant Bendahara 2",
            password_hash=hash_password("Bendahara123!"),
            role="BENDAHARA",
            tenant_id=jemaat_b.id,
            is_active=True,
            nomor_whatsapp="6281234567900",
        )
        db.add(u2)
        db.commit()
        db.close()
        return "6281234567900"

    def test_multi_tenant_shows_pilih_jemaat(self, test_db, jemaat_a, jemaat_b, monkeypatch) -> None:
        phone = self._make_multi_tenant_bendahara(test_db, jemaat_a, jemaat_b)
        result, replies = _run_impl(test_db(), {"sender": phone, "button_id": "btn_input"}, monkeypatch)
        assert result["reply"] == "pilih_jemaat"
        assert any("Pilih jemaat" in m for _, m in replies)

    def test_multi_tenant_btn_pilih(self, test_db, jemaat_a, jemaat_b, monkeypatch) -> None:
        phone = self._make_multi_tenant_bendahara(test_db, jemaat_a, jemaat_b)
        result, replies = _run_impl(
            test_db(),
            {"sender": phone, "button_id": f"btn_pilih_{jemaat_a.id}"},
            monkeypatch,
        )
        assert result["status"] == "ok"
        assert any("Perpuluhan (X)" in m for _, m in replies)

    def test_multi_tenant_invalid_tenant(self, test_db, jemaat_a, jemaat_b, monkeypatch) -> None:
        phone = self._make_multi_tenant_bendahara(test_db, jemaat_a, jemaat_b)
        result, replies = _run_impl(test_db(), {"sender": phone, "button_id": "btn_pilih_99999"}, monkeypatch)
        assert result["status"] == "ok"
        assert any("tidak valid" in m for _, m in replies)


class TestBtnCocokkan:
    def test_cocokkan_with_staging(self, test_db, jemaat_a, bendahara_a, monkeypatch) -> None:
        """btn_cocokkan → summary staging items."""
        from app.models.transaction import Kuitansi

        db = test_db()
        k = Kuitansi(
            tenant_id=jemaat_a.id,
            id_rekap_mingguan="STG-2026-09-05",
            nomor_kuitansi="PENDING-1-1",
            tanggal_sabat="2026-09-05",
            nama_umat_encrypted=encrypt_pii("Budi"),
            perpuluhan_x_angka=100000,
            pt_angka=50000,
            khusus_angka=0,
            total_pemberian_angka=150000,
            status="draft",
            is_purged=False,
            is_finalized=False,
            created_via="wa",
            wa_sender=bendahara_a.nomor_whatsapp,
            temp_nomor="STG-00001",
            staging_id=1,
        )
        db.add(k)
        db.commit()
        db.close()

        result, replies = _run_impl(
            test_db(),
            {"sender": bendahara_a.nomor_whatsapp, "button_id": "btn_cocokkan"},
            monkeypatch,
        )
        assert result["status"] == "ok"
        assert any("Ringkasan Kuitansi" in m for _, m in replies)
        assert any("150,000" in m for _, m in replies)


class TestMaxStagingGuard:
    def test_max_staging_reached_blocks_save(self, test_db, jemaat_a, bendahara_a, monkeypatch) -> None:
        """MAX_STAGING_PER_DAY reached → warning reply, no save."""
        from app.models.transaction import Kuitansi
        from app.services.wa_input_state import MAX_STAGING_PER_DAY

        db = test_db()
        phone = bendahara_a.nomor_whatsapp
        # Insert MAX_STAGING_PER_DAY items for today
        from datetime import UTC, datetime

        today = datetime.now(UTC).replace(tzinfo=None)
        for i in range(MAX_STAGING_PER_DAY):
            db.add(
                Kuitansi(
                    tenant_id=jemaat_a.id,
                    id_rekap_mingguan="STG-X",
                    nomor_kuitansi=f"PENDING-{i}",
                    tanggal_sabat="2026-09-05",
                    nama_umat_encrypted=encrypt_pii("X"),
                    perpuluhan_x_angka=1000,
                    pt_angka=0,
                    khusus_angka=0,
                    total_pemberian_angka=1000,
                    status="draft",
                    is_purged=False,
                    is_finalized=False,
                    created_via="wa",
                    wa_sender=phone,
                    temp_nomor=f"STG-{i}",
                    staging_id=i,
                    created_at=today,
                )
            )
        db.commit()
        db.close()

        from app.api.v1 import wa_input

        replies = []

        def fake_send(phone, message, buttons=None):
            replies.append(message)
            return {"status": "sent"}

        monkeypatch.setattr(wa_input, "_send_fonnte_reply", fake_send)
        db = test_db()
        # Setup session to CONFIRM state then save
        asyncio.run(wa_input._wa_inbound_impl(None, db, {"sender": phone, "button_id": "btn_input"}))
        asyncio.run(wa_input._wa_inbound_impl(None, db, {"sender": phone, "message": "100000"}))
        asyncio.run(wa_input._wa_inbound_impl(None, db, {"sender": phone, "message": "0"}))
        asyncio.run(wa_input._wa_inbound_impl(None, db, {"sender": phone, "message": "0"}))
        asyncio.run(wa_input._wa_inbound_impl(None, db, {"sender": phone, "message": "Budi"}))
        result = asyncio.run(
            wa_input._wa_inbound_impl(None, db, {"sender": phone, "button_id": "btn_simpan"})
        )
        db.close()
        assert result["status"] == "ok"
        assert any("sudah menginput" in m for m in replies)


class TestWaInboundWrapper:
    """POST /wa/inbound wrapper — form-data + JSON fallback parsing."""

    @pytest.mark.anyio
    async def test_post_form_data(self, client, test_db, monkeypatch) -> None:
        """Form-data body parsing (Fonnte's actual format)."""
        from app.api.v1 import wa_input

        monkeypatch.setenv("WHATSAPP_ENABLED", "false")  # avoid network
        monkeypatch.setattr(wa_input, "_send_fonnte_reply", lambda *a, **k: {"status": "skipped"})
        # Empty sender → ignored (no crash)
        resp = client.post(
            "/api/v1/wa/inbound",
            data={"sender": "", "message": "hello"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    @pytest.mark.anyio
    async def test_post_json_fallback(self, client, test_db, monkeypatch) -> None:
        """JSON body fallback parsing."""
        from app.api.v1 import wa_input

        monkeypatch.setenv("WHATSAPP_ENABLED", "false")
        monkeypatch.setattr(wa_input, "_send_fonnte_reply", lambda *a, **k: {"status": "skipped"})
        resp = client.post(
            "/api/v1/wa/inbound",
            json={"sender": "", "message": "hello"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"
