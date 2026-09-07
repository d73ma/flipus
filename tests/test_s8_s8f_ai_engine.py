"""
FASE 5 Sprint 8 — Unit tests untuk app/ai_engine/cloud_parser.py + batch_processor.py.

Covers:
- _is_suspicious_response (pure heuristic)
- validate_with_gemini (skip saat API key kosong)
- _validate_with_gemini_impl (mock genai — parse fail, valid, suspect)
- process_batch + _try_ollama_fallback (mock upstream)
"""

import json
import sys
import types

import pytest

from app.ai_engine.cloud_parser import _is_suspicious_response


def _install_fake_genai(monkeypatch: pytest.MonkeyPatch, model) -> None:
    """Install a fake `google.generativeai` module into sys.modules."""
    fake = types.SimpleNamespace(
        configure=lambda **kw: None,
        GenerativeModel=lambda name: model,
    )
    monkeypatch.setitem(sys.modules, "google.generativeai", fake)


class TestIsSuspiciousResponse:
    def test_clean_response(self) -> None:
        ok, _ = _is_suspicious_response(
            {
                "nama_umat": "Budi",
                "perpuluhan_X_angka": 100000,
                "PT_angka": 50000,
            }
        )
        assert ok is False

    def test_nama_kosong(self) -> None:
        ok, reason = _is_suspicious_response(
            {
                "nama_umat": "",
                "perpuluhan_X_angka": 100000,
                "PT_angka": 0,
            }
        )
        assert ok is True
        assert reason == "NAMA_KOSONG"

    def test_total_nol(self) -> None:
        ok, reason = _is_suspicious_response(
            {
                "nama_umat": "Budi",
                "perpuluhan_X_angka": 0,
                "PT_angka": 0,
            }
        )
        assert ok is True
        assert reason == "TOTAL_NOL"

    def test_placeholder_pair(self) -> None:
        """X == PT == 100000 (placeholder generic) → suspect."""
        ok, reason = _is_suspicious_response(
            {
                "nama_umat": "Budi",
                "perpuluhan_X_angka": 100000,
                "PT_angka": 100000,
            }
        )
        assert ok is True
        assert "NILAI_PLACEHOLDER" in reason

    def test_legitimate_equal_x_pt_not_placeholder(self) -> None:
        """X == PT == 125000 (bukan placeholder) → NOT suspect."""
        ok, _ = _is_suspicious_response(
            {
                "nama_umat": "Budi",
                "perpuluhan_X_angka": 125000,
                "PT_angka": 125000,
            }
        )
        assert ok is False


class TestValidateWithGemini:
    def test_skips_when_no_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.ai_engine.cloud_parser import validate_with_gemini

        monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "")
        result = validate_with_gemini({}, None)
        assert result["status"] == "NEED_REVIEW"
        assert result["reason"] == "GEMINI_DISABLED"

    def test_skips_placeholder_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.ai_engine.cloud_parser import validate_with_gemini

        monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "GANTI_XXX")
        result = validate_with_gemini({}, None)
        assert result["reason"] == "GEMINI_DISABLED"


class TestValidateWithGeminiImpl:
    def test_parse_fail_no_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.ai_engine.cloud_parser import _validate_with_gemini_impl

        class FakeObs:
            def set_outcome(self, o):
                pass

        class FakeResp:
            text = "no json here"

        class FakeModel:
            def generate_content(self, parts):
                return FakeResp()

        monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "real")
        _install_fake_genai(monkeypatch, FakeModel())
        result = _validate_with_gemini_impl({}, None, "gemini-test", FakeObs())
        assert result["status"] == "NEED_REVIEW"
        assert result["reason"] == "GEMINI_PARSE_FAIL"

    def test_valid_ocr_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.ai_engine.cloud_parser import _validate_with_gemini_impl

        class FakeObs:
            def set_outcome(self, o):
                self.outcome = o

        class FakeResp:
            text = json.dumps(
                {
                    "nama_umat": "Budi",
                    "perpuluhan_X_angka": 100000,
                    "PT_angka": 50000,
                    "total_huruf": "seratus lima puluh ribu",
                }
            )

        class FakeModel:
            def generate_content(self, parts):
                return FakeResp()

        monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "real")
        _install_fake_genai(monkeypatch, FakeModel())
        obs = FakeObs()
        result = _validate_with_gemini_impl({}, None, "gemini-test", obs)
        assert result["status"] == "VALID_MATCH"
        assert result["ocr"]["nama_umat"] == "Budi"
        assert obs.outcome == "ok"

    def test_numeric_validation_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-OCR path (pure numeric validation) returns parsed as-is with img_hash."""
        from app.ai_engine.cloud_parser import _validate_with_gemini_impl

        class FakeObs:
            def set_outcome(self, o):
                self.outcome = o

        class FakeResp:
            text = json.dumps({"status": "VALID_MATCH", "alasan": "konsisten"})

        class FakeModel:
            def generate_content(self, parts):
                return FakeResp()

        monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "real")
        _install_fake_genai(monkeypatch, FakeModel())
        obs = FakeObs()
        result = _validate_with_gemini_impl({"foo": "bar"}, None, "gemini-test", obs)
        assert result["status"] == "VALID_MATCH"

    def test_exception_returns_unreachable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.ai_engine.cloud_parser import _validate_with_gemini_impl

        class FakeObs:
            def set_outcome(self, o):
                pass

        class FakeModel:
            def generate_content(self, parts):
                raise Exception("connection timeout")

        monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "real")
        _install_fake_genai(monkeypatch, FakeModel())
        result = _validate_with_gemini_impl({}, None, "gemini-test", FakeObs())
        assert result["status"] == "NEED_REVIEW"
        assert result["reason"] == "GEMINI_UNREACHABLE"


class TestBatchProcessor:
    def test_process_batch_mock_gemini(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.ai_engine import batch_processor

        def fake_gemini(payload, image_path):
            return {
                "status": "VALID_MATCH",
                "ocr": {
                    "nama_umat": "Budi",
                    "perpuluhan_X_angka": 100000,
                    "PT_angka": 50000,
                    "total_huruf": "150 ribu",
                },
                "img_hash": "abc",
            }

        monkeypatch.setattr(batch_processor, "validate_with_gemini", fake_gemini)
        result = batch_processor.process_batch(["img1.jpg", "img2.jpg"])
        assert result["total_amplop"] == 2
        assert result["total_x_terbaca"] == 200000
        assert result["total_pt_terbaca"] == 100000
        assert result["need_review_count"] == 0
        assert len(result["items"]) == 2

    def test_process_batch_need_review_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.ai_engine import batch_processor

        def fake_gemini(payload, image_path):
            return {
                "status": "NEED_REVIEW",
                "ocr": {"nama_umat": "", "perpuluhan_X_angka": 0, "PT_angka": 0},
                "img_hash": "abc",
            }

        # Ollama fallback unavailable
        monkeypatch.setattr(batch_processor, "validate_with_gemini", fake_gemini)
        monkeypatch.setattr(
            batch_processor,
            "extract_with_ollama",
            lambda img: {"error": "FILE_NOT_FOUND"},
        )
        result = batch_processor.process_batch(["img1.jpg"])
        assert result["need_review_count"] == 1
        assert result["items"][0]["needs_manual_review"] is True

    def test_try_ollama_fallback_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.ai_engine.batch_processor import _try_ollama_fallback

        monkeypatch.setattr(
            "app.ai_engine.batch_processor.extract_with_ollama",
            lambda img: {"error": "FILE_NOT_FOUND"},
        )
        primary = {"perpuluhan_X_angka": 100000, "PT_angka": 50000}
        result = _try_ollama_fallback("img.jpg", primary)
        assert result == primary  # unchanged

    def test_try_ollama_fallback_no_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.ai_engine.batch_processor import _try_ollama_fallback

        monkeypatch.setattr(
            "app.ai_engine.batch_processor.extract_with_ollama",
            lambda img: {"raw": "no json"},
        )
        monkeypatch.setattr(
            "app.ai_engine.batch_processor.parse_ocr_payload",
            lambda raw: {},
        )
        primary = {"perpuluhan_X_angka": 100000}
        result = _try_ollama_fallback("img.jpg", primary)
        assert result == primary

    def test_try_ollama_fallback_different_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.ai_engine.batch_processor import _try_ollama_fallback

        monkeypatch.setattr(
            "app.ai_engine.batch_processor.extract_with_ollama",
            lambda img: {"raw": "json"},
        )
        monkeypatch.setattr(
            "app.ai_engine.batch_processor.parse_ocr_payload",
            lambda raw: {
                "nama_umat": "Andi",
                "perpuluhan_X_angka": 200000,
                "PT_angka": 0,
                "total_huruf": "200 ribu",
            },
        )
        primary = {"perpuluhan_X_angka": 100000, "PT_angka": 50000}
        result = _try_ollama_fallback("img.jpg", primary)
        assert result["ocr_source"] == "ollama_fallback"
        assert result["perpuluhan_X_angka"] == 200000
