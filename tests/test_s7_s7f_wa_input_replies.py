"""
FASE 5 Sprint 7 — Unit tests untuk app/api/v1/wa_input.py reply builders.

Covers:
- _reply_menu, _reply_await_kategori, _reply_await_nama, _reply_confirm,
  _reply_saved, _reply_pilih_jemaat, _reply_bantuan — pure reply builders.
- _send_fonnte_reply — WA token/env gating + mocked requests.post.
"""

from unittest.mock import patch

import pytest

from app.api.v1.wa_input import (
    _reply_await_kategori,
    _reply_await_nama,
    _reply_bantuan,
    _reply_confirm,
    _reply_menu,
    _reply_pilih_jemaat,
    _reply_saved,
    _send_fonnte_reply,
)


class TestReplyMenu:
    def test_empty_tenant(self) -> None:
        reply = _reply_menu()
        assert "*FLIPUS Input Kuitansi*" in reply["message"]
        assert len(reply["buttons"]) == 3

    def test_with_tenant(self) -> None:
        reply = _reply_menu("Nataan")
        assert "Nataan" in reply["message"]
        assert reply["buttons"][0]["id"] == "btn_input"

    def test_button_ids(self) -> None:
        reply = _reply_menu()
        ids = [b["id"] for b in reply["buttons"]]
        assert ids == ["btn_input", "btn_cocokkan", "btn_bantuan"]


class TestReplyAwaitKategori:
    def test_x_label(self) -> None:
        reply = _reply_await_kategori("X")
        assert "Perpuluhan (X)" in reply["message"]
        assert "Format:" in reply["message"]

    def test_pt_label(self) -> None:
        reply = _reply_await_kategori("PT")
        assert "Persembahan Terpadu (PT)" in reply["message"]

    def test_kh_label(self) -> None:
        reply = _reply_await_kategori("KH")
        assert "Persembahan Khusus (KH)" in reply["message"]

    def test_invalid_kategori_raises(self) -> None:
        with pytest.raises(KeyError):
            _reply_await_kategori("INVALID")

    def test_buttons(self) -> None:
        reply = _reply_await_kategori("X")
        ids = [b["id"] for b in reply["buttons"]]
        assert "btn_lewati" in ids
        assert "btn_batal" in ids


class TestReplyAwaitNama:
    def test_message(self) -> None:
        reply = _reply_await_nama()
        assert "nama pemberi" in reply["message"]

    def test_buttons(self) -> None:
        reply = _reply_await_nama()
        ids = [b["id"] for b in reply["buttons"]]
        assert "btn_lewati" in ids
        assert "btn_batal" in ids


class TestReplyConfirm:
    def test_matches_values(self) -> None:
        reply = _reply_confirm(x=100000, pt=50000, kh=25000, nama="Budi")
        msg = reply["message"]
        assert "Budi" in msg
        assert "100,000" in msg  # X
        assert "50,000" in msg  # PT
        assert "25,000" in msg  # KH
        assert "175,000" in msg  # Total

    def test_zero_values(self) -> None:
        reply = _reply_confirm(x=0, pt=0, kh=0, nama="X")
        assert "0" in reply["message"]

    def test_buttons(self) -> None:
        reply = _reply_confirm(1, 2, 3, "x")
        ids = [b["id"] for b in reply["buttons"]]
        assert "btn_simpan" in ids
        assert "btn_batal" in ids


class TestReplySaved:
    def test_message(self) -> None:
        reply = _reply_saved(nomor_temp="STG-00001", nama="Budi")
        assert "tersimpan" in reply["message"].lower()
        assert "STG-00001" in reply["message"]


class TestReplyPilihJemaat:
    def test_empty(self) -> None:
        reply = _reply_pilih_jemaat([])
        assert reply["buttons"] == []

    def test_multiple_tenants(self) -> None:
        from types import SimpleNamespace

        t1 = SimpleNamespace(id=11, nama_jemaat_lokal="Nataan")
        t2 = SimpleNamespace(id=22, nama_jemaat_lokal="Kawah")
        reply = _reply_pilih_jemaat([t1, t2])
        ids = [b["id"] for b in reply["buttons"]]
        assert ids == ["btn_pilih_11", "btn_pilih_22"]

    def test_max_three(self) -> None:
        from types import SimpleNamespace

        tenants = [SimpleNamespace(id=i, nama_jemaat_lokal=f"J{i}") for i in range(10)]
        reply = _reply_pilih_jemaat(tenants)
        assert len(reply["buttons"]) == 3

    def test_name_truncated_to_20(self) -> None:
        from types import SimpleNamespace

        t = SimpleNamespace(id=1, nama_jemaat_lokal="Jemaat Dengan Nama Sangat Panjang Sekali")
        reply = _reply_pilih_jemaat([t])
        assert len(reply["buttons"][0]["text"]) <= 20


class TestReplyBantuan:
    def test_message(self) -> None:
        reply = _reply_bantuan()
        assert "Bantuan" in reply["message"]
        assert "100rb" in reply["message"]
        assert reply["buttons"] == []


class TestSendFonnteReply:
    def test_skipped_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WHATSAPP_ENABLED", "false")
        result = _send_fonnte_reply("6281234567890", "test")
        assert result["status"] == "skipped"
        assert result["reason"] == "WHATSAPP_ENABLED=false"

    def test_skipped_when_no_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WHATSAPP_ENABLED", "true")
        monkeypatch.delenv("FONNTE_TOKEN", raising=False)
        result = _send_fonnte_reply("6281234567890", "test")
        assert result["status"] == "skipped"
        assert result["reason"] == "no token"

    def test_skipped_when_placeholder_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WHATSAPP_ENABLED", "true")
        monkeypatch.setenv("FONNTE_TOKEN", "paste_your_token_here")
        result = _send_fonnte_reply("6281234567890", "test")
        assert result["status"] == "skipped"

    def test_sent_via_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WHATSAPP_ENABLED", "true")
        monkeypatch.setenv("FONNTE_TOKEN", "real-token")
        with patch("app.api.v1.wa_input.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"status": True}
            result = _send_fonnte_reply("081234567890", "hello")
        assert result["status"] == "sent"
        # Verify normalized phone + button extraction
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["data"]["target"] == "6281234567890"

    def test_with_buttons_extracts_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WHATSAPP_ENABLED", "true")
        monkeypatch.setenv("FONNTE_TOKEN", "real-token")
        buttons = [
            {"id": "btn_input", "text": "💰 Input Kuitansi"},
            {"id": "btn_cocokkan", "text": "📊 Cocokkan Total"},
        ]
        with patch("app.api.v1.wa_input.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"status": True}
            _send_fonnte_reply("6281234567890", "menu", buttons)
        data = mock_post.call_args.kwargs["data"]
        assert data["button1"] == "💰 Input Kuitansi"
        assert data["button2"] == "📊 Cocokkan Total"
        assert "button3" not in data

    def test_failed_when_fonnte_status_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WHATSAPP_ENABLED", "true")
        monkeypatch.setenv("FONNTE_TOKEN", "real-token")
        with patch("app.api.v1.wa_input.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"status": False}
            result = _send_fonnte_reply("6281234567890", "hello")
        assert result["status"] == "failed"

    def test_error_on_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WHATSAPP_ENABLED", "true")
        monkeypatch.setenv("FONNTE_TOKEN", "real-token")
        with patch("app.api.v1.wa_input.requests.post") as mock_post:
            mock_post.side_effect = Exception("network down")
            result = _send_fonnte_reply("6281234567890", "hello")
        assert result["status"] == "error"
        assert "network down" in result["reason"]
