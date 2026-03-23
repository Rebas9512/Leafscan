"""Tests for leafscan.model — capability probing across all api_formats."""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from leafscan.model import Cap, ResolvedModel, probe_caps


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_model(api_format: str, model: str = "test-model") -> ResolvedModel:
    return ResolvedModel(client=MagicMock(), api_format=api_format, model=model)


# ── probe_caps: success → VISION ───────────────────────────────────────────────

class TestProbeSuccess:
    """When the probe request succeeds, all formats should return TEXT | VISION."""

    def test_anthropic_messages(self):
        m = _make_model("anthropic-messages")
        assert probe_caps(m) == Cap.TEXT | Cap.VISION
        m.client.messages.create.assert_called_once()

    def test_openai_completions(self):
        m = _make_model("openai-completions")
        assert probe_caps(m) == Cap.TEXT | Cap.VISION
        m.client.chat.completions.create.assert_called_once()

    def test_ollama(self):
        m = _make_model("ollama")
        assert probe_caps(m) == Cap.TEXT | Cap.VISION
        m.client.chat.completions.create.assert_called_once()

    def test_openai_responses(self):
        m = _make_model("openai-responses", model="gpt-5.4")
        assert probe_caps(m) == Cap.TEXT | Cap.VISION
        m.client.responses.create.assert_called_once()

        # Verify Responses API uses correct content block types
        call_kwargs = m.client.responses.create.call_args.kwargs
        input_content = call_kwargs["input"][0]["content"]
        types = {b["type"] for b in input_content}
        assert types == {"input_image", "input_text"}


# ── probe_caps: failure → TEXT only ────────────────────────────────────────────

class TestProbeFailure:
    """When the probe request fails, all formats should fall back to TEXT."""

    def test_anthropic_messages_400(self):
        m = _make_model("anthropic-messages")
        m.client.messages.create.side_effect = Exception("400 Bad Request")
        assert probe_caps(m) == Cap.TEXT

    def test_openai_completions_400(self):
        m = _make_model("openai-completions")
        m.client.chat.completions.create.side_effect = Exception("model does not support images")
        assert probe_caps(m) == Cap.TEXT

    def test_openai_responses_400(self):
        m = _make_model("openai-responses")
        m.client.responses.create.side_effect = Exception("unsupported modality")
        assert probe_caps(m) == Cap.TEXT

    def test_ollama_connection_error(self):
        m = _make_model("ollama")
        m.client.chat.completions.create.side_effect = ConnectionError("refused")
        assert probe_caps(m) == Cap.TEXT


# ── probe_caps: unknown format → TEXT ──────────────────────────────────────────

class TestProbeUnknownFormat:
    def test_unknown_api_format(self):
        m = _make_model("some-future-format")
        assert probe_caps(m) == Cap.TEXT


# ── probe_caps: max_tokens=1 / max_output_tokens=1 ────────────────────────────

class TestProbeMinimalTokens:
    """Probes should request exactly 1 token to minimise cost."""

    def test_anthropic_max_tokens(self):
        m = _make_model("anthropic-messages")
        probe_caps(m)
        kwargs = m.client.messages.create.call_args.kwargs
        assert kwargs["max_tokens"] == 1

    def test_openai_max_tokens(self):
        m = _make_model("openai-completions")
        probe_caps(m)
        kwargs = m.client.chat.completions.create.call_args.kwargs
        assert kwargs["max_tokens"] == 1

    def test_responses_codex_protocol(self):
        """Codex requires stream=True, store=False, no max_output_tokens."""
        m = _make_model("openai-responses")
        probe_caps(m)
        kwargs = m.client.responses.create.call_args.kwargs
        assert kwargs["stream"] is True
        assert kwargs["store"] is False
        assert "max_output_tokens" not in kwargs
