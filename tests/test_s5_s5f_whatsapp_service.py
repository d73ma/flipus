"""
FASE 5 Sprint 5 — Unit tests for app/services/whatsapp.py.

Covers:
- send_kuitansi_whatsapp: skip when WHATSAPP_ENABLED=false, error when no token,
  success via mocked requests.post.
- send_simple_message: error when no token, phone normalization, mocked success.
- send_document_message: similar.
- get_device_status: mocked Fonnte device-status endpoint.
"""

from unittest.mock import patch

import pytest

from app.services.whatsapp import (
    get_device_status,
    send_document_message,
    send_kuitansi_whatsapp,
    send_simple_message,
)


class TestSendKuitansiWhatsapp:
    def test_skipped_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """WHATSAPP_ENABLED not true → return skipped."""
        monkeypatch.setenv("WHATSAPP_ENABLED", "false")
        monkeypatch.setenv("FONNTE_TOKEN", "real-token-xyz")
        result = send_kuitansi_whatsapp(
            phone="6281234567890",
            nama="Test",
            perpuluhan_x=100000,
            pt=50000,
            porsi_misi=50000,
            porsi_jemaat=50000,
        )
        assert result["status"] == "skipped"

    def test_error_when_no_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """FONNTE_TOKEN empty → return error."""
        monkeypatch.setenv("WHATSAPP_ENABLED", "true")
        monkeypatch.delenv("FONNTE_TOKEN", raising=False)
        result = send_kuitansi_whatsapp(
            phone="6281234567890",
            nama="Test",
            perpuluhan_x=100000,
            pt=50000,
            porsi_misi=50000,
            porsi_jemaat=50000,
        )
        assert result["status"] == "error"
        assert "token" in result["reason"].lower()

    def test_error_when_placeholder_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Token starts with 'paste_' → return error."""
        monkeypatch.setenv("WHATSAPP_ENABLED", "true")
        monkeypatch.setenv("FONNTE_TOKEN", "paste_your_token_here")
        result = send_kuitansi_whatsapp(
            phone="6281234567890",
            nama="Test",
            perpuluhan_x=100000,
            pt=50000,
            porsi_misi=50000,
            porsi_jemaat=50000,
        )
        assert result["status"] == "error"

    def test_success_via_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Happy path: token set + enabled + mocked Fonnte success."""
        monkeypatch.setenv("WHATSAPP_ENABLED", "true")
        monkeypatch.setenv("FONNTE_TOKEN", "real-token-abc")
        with patch("app.services.whatsapp.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"status": True, "detail": "OK"}
            result = send_kuitansi_whatsapp(
                phone="6281234567890",
                nama="Pak Budi",
                perpuluhan_x=200000,
                pt=100000,
                porsi_misi=100000,
                porsi_jemaat=100000,
            )
        assert result["status"] == "sent"

    def test_phone_normalization_local_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Phone starting with 0 gets 62 prefix."""
        monkeypatch.setenv("WHATSAPP_ENABLED", "true")
        monkeypatch.setenv("FONNTE_TOKEN", "real-token")
        with patch("app.services.whatsapp.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"status": True}
            send_kuitansi_whatsapp(
                phone="081234567890",
                nama="X",
                perpuluhan_x=0,
                pt=0,
                porsi_misi=0,
                porsi_jemaat=0,
            )
        # Verify phone was normalized
        call_args = mock_post.call_args
        assert "6281234567890" in call_args.kwargs["data"]["target"]

    def test_request_exception_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Network error during request → return error status."""
        monkeypatch.setenv("WHATSAPP_ENABLED", "true")
        monkeypatch.setenv("FONNTE_TOKEN", "real-token")
        with patch("app.services.whatsapp.requests.post") as mock_post:
            mock_post.side_effect = Exception("network down")
            result = send_kuitansi_whatsapp(
                phone="6281234567890",
                nama="X",
                perpuluhan_x=0,
                pt=0,
                porsi_misi=0,
                porsi_jemaat=0,
            )
        assert result["status"] == "error"
        assert "network down" in result["reason"]


class TestSendSimpleMessage:
    def test_error_when_no_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing token → error."""
        monkeypatch.delenv("FONNTE_TOKEN", raising=False)
        result = send_simple_message(phone="6281234567890", message="hi")
        assert result["status"] == "error"

    def test_success_via_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Happy path: token + mocked POST."""
        monkeypatch.setenv("FONNTE_TOKEN", "real-token")
        with patch("app.services.whatsapp.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"status": True}
            result = send_simple_message(phone="6281234567890", message="hello")
        assert result["status"] == "sent"

    def test_phone_normalization(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Local phone format (0xxx) gets normalized to 62xxx."""
        monkeypatch.setenv("FONNTE_TOKEN", "real-token")
        with patch("app.services.whatsapp.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"status": True}
            send_simple_message(phone="0812345678", message="hi")
        call_args = mock_post.call_args
        assert "62812345678" in call_args.kwargs["data"]["target"]


class TestSendDocumentMessage:
    def test_error_when_no_token(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        """Missing token → error."""
        monkeypatch.delenv("FONNTE_TOKEN", raising=False)
        # Create dummy file
        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF-1.4 dummy")
        result = send_document_message(
            phone="6281234567890",
            message="doc",
            file_path=str(f),
        )
        assert result["status"] == "failed"


class TestGetDeviceStatus:
    def test_disabled_when_not_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """WHATSAPP_ENABLED=false → return disabled status."""
        monkeypatch.setenv("WHATSAPP_ENABLED", "false")
        result = get_device_status()
        assert result["status"] == "disabled"

    def test_no_token_returns_no_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """FONNTE_TOKEN empty → return no_token status."""
        monkeypatch.setenv("WHATSAPP_ENABLED", "true")
        monkeypatch.delenv("FONNTE_TOKEN", raising=False)
        result = get_device_status()
        assert result["status"] == "no_token"

    def test_placeholder_token_returns_no_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Token starts with 'paste_' → return no_token status."""
        monkeypatch.setenv("WHATSAPP_ENABLED", "true")
        monkeypatch.setenv("FONNTE_TOKEN", "paste_here")
        result = get_device_status()
        assert result["status"] == "no_token"

    def test_success_via_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Happy path: token + mocked Fonnte get-device endpoint."""
        monkeypatch.setenv("WHATSAPP_ENABLED", "true")
        monkeypatch.setenv("FONNTE_TOKEN", "real-token")
        with patch("app.services.whatsapp.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "status": True,
                "device": "connected",
                "quota": 1000,
            }
            result = get_device_status()
        assert result["device"] == "connected"
        assert result["quota"] == 1000

    def test_request_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Network error → return error status with reason."""
        monkeypatch.setenv("WHATSAPP_ENABLED", "true")
        monkeypatch.setenv("FONNTE_TOKEN", "real-token")
        with patch("app.services.whatsapp.requests.post") as mock_post:
            mock_post.side_effect = Exception("connection refused")
            result = get_device_status()
        assert result["status"] == "error"
        assert "connection refused" in result["reason"]
