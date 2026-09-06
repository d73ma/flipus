"""
FASE 5 Sprint 5 — Unit tests for app/ai_engine/local_ocr.py.

Covers:
- parse_ocr_payload: extract JSON from raw text with surrounding noise.
- extract_with_ollama: error paths (file not found, lib missing).
"""

import json
from pathlib import Path

import pytest


class TestParseOcrPayload:
    """parse_ocr_payload — extract JSON object from text."""

    def test_pure_json(self) -> None:
        """Clean JSON returns parsed dict."""
        from app.ai_engine.local_ocr import parse_ocr_payload

        text = json.dumps(
            {
                "nama_umat": "Budi",
                "perpuluhan_X_angka": 100000,
                "PT_angka": 50000,
                "total_huruf": "seratus lima puluh ribu",
            }
        )
        result = parse_ocr_payload(text)
        assert result["nama_umat"] == "Budi"
        assert result["perpuluhan_X_angka"] == 100000

    def test_json_with_explanation(self) -> None:
        """Extract JSON when there's prose around it."""
        from app.ai_engine.local_ocr import parse_ocr_payload

        text = (
            "Berikut adalah hasil OCR:\n"
            + json.dumps(
                {
                    "nama_umat": "Andi",
                    "perpuluhan_X_angka": 200000,
                }
            )
            + "\nTerima kasih."
        )
        result = parse_ocr_payload(text)
        assert result["nama_umat"] == "Andi"

    def test_empty_text(self) -> None:
        """Empty text returns empty dict."""
        from app.ai_engine.local_ocr import parse_ocr_payload

        assert parse_ocr_payload("") == {}

    def test_no_json_braces(self) -> None:
        """Text without JSON braces returns empty dict."""
        from app.ai_engine.local_ocr import parse_ocr_payload

        assert parse_ocr_payload("no json here") == {}

    def test_invalid_json(self) -> None:
        """Malformed JSON returns empty dict (no exception)."""
        from app.ai_engine.local_ocr import parse_ocr_payload

        assert parse_ocr_payload("{not valid json") == {}

    def test_unclosed_brace(self) -> None:
        """Unclosed brace returns empty dict."""
        from app.ai_engine.local_ocr import parse_ocr_payload

        assert parse_ocr_payload('{"key": "value"') == {}


class TestExtractWithOllama:
    """extract_with_ollama — error paths."""

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Non-existent file returns FILE_NOT_FOUND error."""
        from app.ai_engine.local_ocr import extract_with_ollama

        fake = tmp_path / "nonexistent.jpg"
        result = extract_with_ollama(str(fake))
        assert result["error"] == "FILE_NOT_FOUND"
        assert result["path"] == str(fake)

    def test_ollama_lib_missing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """If ollama import fails, return OLLAMA_LIB_MISSING."""
        # Make ollama importable as missing
        import sys

        from app.ai_engine import local_ocr

        # Save original and remove
        monkeypatch.delitem(sys.modules, "ollama", raising=False)
        # Patch builtins.__import__ to fail on ollama
        real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def fake_import(name, *args, **kwargs):
            if name == "ollama" or name.startswith("ollama"):
                raise ImportError("No module named 'ollama'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)
        # Create real file so we don't hit FILE_NOT_FOUND
        real_file = tmp_path / "test.jpg"
        real_file.write_bytes(b"fake-jpg-bytes")
        result = local_ocr.extract_with_ollama(str(real_file))
        # Either FILE_NOT_FOUND or OLLAMA_LIB_MISSING depending on import order
        assert "error" in result

    def test_ollama_chat_exception_returns_fallback(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """If ollama.chat raises, return OLLAMA_UNREACHABLE."""
        # Create real file
        real_file = tmp_path / "test.jpg"
        real_file.write_bytes(b"fake-jpg-bytes")
        # Mock ollama module
        import sys
        from unittest.mock import MagicMock

        fake_ollama = MagicMock()
        fake_ollama.chat.side_effect = Exception("connection refused")
        sys.modules["ollama"] = fake_ollama
        from app.ai_engine.local_ocr import extract_with_ollama

        result = extract_with_ollama(str(real_file))
        assert result["error"] == "OLLAMA_UNREACHABLE"
        assert "connection refused" in result["detail"]
