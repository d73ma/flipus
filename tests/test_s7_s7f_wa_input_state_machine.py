"""
FASE 5 Sprint 7 — Integration tests untuk _wa_inbound_impl state machine.

Memanggil `_wa_inbound_impl(request, db, body)` secara langsung (tanpa rate
limiter / form-parsing wrapper `wa_inbound`), dengan `_send_fonnte_reply`
di-mock supaya tidak ada network call. Fokus pada logika state machine:

- Guard: echo, empty phone, unregistered
- Menu: btn_input → AWAIT_X
- Full happy path: AWAIT_X → AWAIT_PT → AWAIT_KH → AWAIT_NAMA → CONFIRM → SAVED
- Shortcut: "X 100rb PT 50rb" → AWAIT_NAMA langsung
- Batal / Lewati
"""

import asyncio

import pytest


def _run(body: dict, test_db, monkeypatch: pytest.MonkeyPatch):
    """Panggil _wa_inbound_impl dengan _send_fonnte_reply di-mock.

    Returns (result, replies) — replies adalah list dari (phone, message)
    yang dikirim ke _send_fonnte_reply.
    """
    from app.api.v1 import wa_input

    replies: list[tuple[str, str]] = []

    def fake_send(phone: str, message: str, buttons=None):
        replies.append((phone, message))
        return {"status": "sent"}

    monkeypatch.setattr(wa_input, "_send_fonnte_reply", fake_send)

    db = test_db()

    result = asyncio.run(wa_input._wa_inbound_impl(None, db, body))
    db.close()
    return result, replies


class TestEchoAndGuards:
    def test_echo_from_device(self, test_db, monkeypatch) -> None:
        """sender == device → ignored (avoid infinite loop)."""
        result, replies = _run(
            {"sender": "6281234567001", "device": "6281234567001"},
            test_db,
            monkeypatch,
        )
        assert result["status"] == "ignored"
        assert result["reason"] == "echo from device"
        assert replies == []

    def test_bot_menu_echo(self, test_db, monkeypatch) -> None:
        """Message starting with *FLIPUS → ignored."""
        result, replies = _run(
            {"sender": "628999", "message": "*FLIPUS Input Kuitansi*"},
            test_db,
            monkeypatch,
        )
        assert result["status"] == "ignored"

    def test_no_phone(self, test_db, monkeypatch) -> None:
        """No sender/from → ignored."""
        result, replies = _run({"message": "hello"}, test_db, monkeypatch)
        assert result["status"] == "ignored"
        assert result["reason"] == "no phone"


class TestUnregisteredAndMenu:
    def test_unregistered_phone(self, test_db, monkeypatch) -> None:
        """Phone not matching any Bendahara → unregistered reply."""
        result, replies = _run(
            {"sender": "6289999999999", "message": "input"},
            test_db,
            monkeypatch,
        )
        assert result["status"] == "ok"
        assert result["reply"] == "unregistered"
        assert len(replies) == 1
        assert "belum terdaftar" in replies[0][1]

    def test_btn_input_starts_await_x(self, test_db, monkeypatch, bendahara_a, jemaat_a) -> None:
        """Tap 'btn_input' → AWAIT_X + reply await kategori X."""
        result, replies = _run(
            {"sender": bendahara_a.nomor_whatsapp, "button_id": "btn_input"},
            test_db,
            monkeypatch,
        )
        assert result["status"] == "ok"
        assert len(replies) == 1
        assert "Perpuluhan (X)" in replies[0][1]

    def test_idle_random_text_shows_menu(self, test_db, monkeypatch, bendahara_a) -> None:
        """Random text in IDLE → menu shown."""
        result, replies = _run(
            {"sender": bendahara_a.nomor_whatsapp, "message": "halo"},
            test_db,
            monkeypatch,
        )
        assert result["status"] == "ok"
        assert result["reply"] == "menu_shown"
        assert "*FLIPUS Input Kuitansi*" in replies[0][1]

    def test_btn_bantuan(self, test_db, monkeypatch, bendahara_a) -> None:
        result, replies = _run(
            {"sender": bendahara_a.nomor_whatsapp, "button_id": "btn_bantuan"},
            test_db,
            monkeypatch,
        )
        assert result["status"] == "ok"
        assert "Bantuan" in replies[0][1]


class TestFullHappyPath:
    def test_full_flow_creates_staging(self, test_db, monkeypatch, bendahara_a, jemaat_a) -> None:
        """Full flow: input X, PT, KH, nama, simpan → staging row created."""
        phone = bendahara_a.nomor_whatsapp
        replies = []

        def fake_send(phone, message, buttons=None):
            replies.append(message)
            return {"status": "sent"}

        from app.api.v1 import wa_input

        monkeypatch.setattr(wa_input, "_send_fonnte_reply", fake_send)
        db = test_db()

        # 1. Tap input
        asyncio.run(wa_input._wa_inbound_impl(None, db, {"sender": phone, "button_id": "btn_input"}))
        # 2. Enter X
        asyncio.run(wa_input._wa_inbound_impl(None, db, {"sender": phone, "message": "100000"}))
        # 3. Enter PT
        asyncio.run(wa_input._wa_inbound_impl(None, db, {"sender": phone, "message": "50000"}))
        # 4. Enter KH
        asyncio.run(wa_input._wa_inbound_impl(None, db, {"sender": phone, "message": "25000"}))
        # 5. Enter nama
        asyncio.run(wa_input._wa_inbound_impl(None, db, {"sender": phone, "message": "Budi Santoso"}))
        # 6. Tap simpan
        result = asyncio.run(
            wa_input._wa_inbound_impl(None, db, {"sender": phone, "button_id": "btn_simpan"})
        )

        db.close()
        assert result["status"] == "ok"
        assert "staging_id" in result
        # Reply contains the saved confirmation
        assert any("tersimpan" in r.lower() for r in replies)
        # Confirm reply has the values
        assert any("175,000" in r for r in replies)  # total in CONFIRM

    def test_shortcut_flows_to_await_nama(self, test_db, monkeypatch, bendahara_a) -> None:
        """Shortcut 'X 100rb PT 50rb' → langsung AWAIT_NAMA."""
        result, replies = _run(
            {"sender": bendahara_a.nomor_whatsapp, "message": "X 100rb PT 50rb"},
            test_db,
            monkeypatch,
        )
        assert result["status"] == "ok"
        assert result["reply"] == "shortcut_await_nama"
        assert "nama pemberi" in replies[0][1]

    def test_batal_resets_session(self, test_db, monkeypatch, bendahara_a) -> None:
        """'batal' → reset ke menu."""
        phone = bendahara_a.nomor_whatsapp
        result, replies = _run(
            {"sender": phone, "button_id": "btn_batal"},
            test_db,
            monkeypatch,
        )
        assert result["status"] == "ok"
        assert "*FLIPUS Input Kuitansi*" in replies[0][1]

    def test_lewati_nama_uses_default(self, test_db, monkeypatch, bendahara_a) -> None:
        """Lewati pada AWAIT_NAMA → default 'Umat WA'."""
        phone = bendahara_a.nomor_whatsapp

        from app.api.v1 import wa_input

        replies = []

        def fake_send(phone, message, buttons=None):
            replies.append(message)
            return {"status": "sent"}

        monkeypatch.setattr(wa_input, "_send_fonnte_reply", fake_send)
        db = test_db()

        # Start input, fill X only
        asyncio.run(wa_input._wa_inbound_impl(None, db, {"sender": phone, "button_id": "btn_input"}))
        asyncio.run(wa_input._wa_inbound_impl(None, db, {"sender": phone, "message": "100000"}))
        # Lewati PT, KH
        asyncio.run(wa_input._wa_inbound_impl(None, db, {"sender": phone, "button_id": "btn_lewati"}))
        asyncio.run(wa_input._wa_inbound_impl(None, db, {"sender": phone, "button_id": "btn_lewati"}))
        # Now at AWAIT_NAMA, tap lewati → default "Umat WA"
        result = asyncio.run(
            wa_input._wa_inbound_impl(None, db, {"sender": phone, "button_id": "btn_lewati"})
        )
        db.close()
        assert result["status"] == "ok"
        # CONFIRM reply should show "Umat WA"
        assert any("Umat WA" in r for r in replies)


class TestInvalidNominal:
    def test_invalid_nominal_reprompts(self, test_db, monkeypatch, bendahara_a) -> None:
        """Invalid nominal in AWAIT_X → re-prompt with error."""
        phone = bendahara_a.nomor_whatsapp

        from app.api.v1 import wa_input

        replies = []

        def fake_send(phone, message, buttons=None):
            replies.append(message)
            return {"status": "sent"}

        monkeypatch.setattr(wa_input, "_send_fonnte_reply", fake_send)
        db = test_db()

        asyncio.run(wa_input._wa_inbound_impl(None, db, {"sender": phone, "button_id": "btn_input"}))
        result = asyncio.run(wa_input._wa_inbound_impl(None, db, {"sender": phone, "message": "abc"}))
        db.close()
        assert result["status"] == "ok"
        # Last reply contains error + re-prompt
        assert any("❌" in r for r in replies)
        assert any("Perpuluhan (X)" in r for r in replies)
