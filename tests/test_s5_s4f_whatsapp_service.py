"""
FASE 5 Sprint 4 — Unit tests for app/services/whatsapp_service.py.

Covers:
- send_kuitansi_whatsapp: WA_API_TOKEN simulation mode.
- Token fallback when WA_API_TOKEN starts with "GANTI".
"""

from unittest.mock import patch

import pytest

from app.services.whatsapp_service import send_kuitansi_whatsapp


class TestSendKuitansiWhatsapp:
    def test_simulated_when_token_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.services.whatsapp_service.settings.WA_API_TOKEN", "")
        monkeypatch.setattr("app.services.whatsapp_service.settings.WA_API_URL", "http://example/api")
        result = send_kuitansi_whatsapp("6281234567890", "test message")
        assert result["status"] == "SIMULATED"
        assert result["to"] == "6281234567890"
        assert result["message"] == "test message"

    def test_simulated_when_token_placeholder(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.services.whatsapp_service.settings.WA_API_TOKEN", "GANTI_INI_DI_ENV")
        result = send_kuitansi_whatsapp("6281234567890", "msg")
        assert result["status"] == "SIMULATED"

    @patch("app.services.whatsapp_service.httpx.post")
    def test_sent_on_2xx(self, mock_post: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.services.whatsapp_service.settings.WA_API_TOKEN", "real-token-123")
        monkeypatch.setattr("app.services.whatsapp_service.settings.WA_API_URL", "http://fonnte/api")
        # Configure mock
        mock_response = mock_post.return_value  # type: ignore[attr-defined]
        mock_response.status_code = 200
        mock_response.text = "OK"
        result = send_kuitansi_whatsapp("6281234567890", "msg")
        assert result["status"] == "SENT"
        assert result["code"] == 200

    @patch("app.services.whatsapp_service.httpx.post")
    def test_failed_on_exception(self, mock_post: object, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.services.whatsapp_service.settings.WA_API_TOKEN", "real-token")
        monkeypatch.setattr("app.services.whatsapp_service.settings.WA_API_URL", "http://fonnte/api")
        mock_post.side_effect = Exception("network error")  # type: ignore[attr-defined]
        result = send_kuitansi_whatsapp("6281234567890", "msg")
        assert result["status"] == "FAILED"
        assert "network error" in result["error"]
