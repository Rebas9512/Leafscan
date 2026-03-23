"""Tests for leafscan.reporter — payload building + API format adapters."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from leafscan.model import Cap, ResolvedModel
from leafscan.reporter import (
    _build_user_content,
    _to_openai_blocks,
    _to_responses_blocks,
    generate_report,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def css_data():
    return {"typography": {"body": {"fontSize": "16px"}}}


@pytest.fixture
def assets_data():
    return {"animation_libraries": ["GSAP"]}


@pytest.fixture
def screenshot_paths(tmp_path):
    """Create two minimal PNGs simulating scroll frames."""
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIA"
        "BQAAbjjaYQAAAABJRU5ErkJggg=="
    )
    paths = []
    for i in range(2):
        p = tmp_path / f"frame_{i+1:02d}.png"
        p.write_bytes(png)
        paths.append(p)
    return paths


def _make_model(api_format: str, caps: Cap) -> ResolvedModel:
    return ResolvedModel(
        client=MagicMock(), api_format=api_format, model="test-model", caps=caps,
    )


# ── _build_user_content ───────────────────────────────────────────────────────

class TestBuildUserContent:
    def test_text_only_has_no_image_block(self, css_data, assets_data, screenshot_paths):
        blocks = _build_user_content(css_data, assets_data, screenshot_paths, Cap.TEXT)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "text"
        assert "[Note:" in blocks[0]["text"]

    def test_vision_has_images_and_text(self, css_data, assets_data, screenshot_paths):
        blocks = _build_user_content(
            css_data, assets_data, screenshot_paths, Cap.TEXT | Cap.VISION,
        )
        # 2 scroll frames + 1 text block
        assert len(blocks) == 3
        assert blocks[0]["type"] == "image"
        assert blocks[1]["type"] == "image"
        assert blocks[2]["type"] == "text"
        assert "2 viewport screenshots" in blocks[2]["text"]

    def test_vision_image_is_valid_base64(self, css_data, assets_data, screenshot_paths):
        blocks = _build_user_content(
            css_data, assets_data, screenshot_paths, Cap.TEXT | Cap.VISION,
        )
        img_data = blocks[0]["source"]["data"]
        decoded = base64.b64decode(img_data)
        assert decoded[:4] == b"\x89PNG"

    def test_text_block_contains_json_data(self, css_data, assets_data, screenshot_paths):
        blocks = _build_user_content(css_data, assets_data, screenshot_paths, Cap.TEXT)
        text = blocks[0]["text"]
        assert "16px" in text
        assert "GSAP" in text


# ── _to_openai_blocks ─────────────────────────────────────────────────────────

class TestToOpenaiBlocks:
    def test_text_block_passthrough(self):
        result = _to_openai_blocks([{"type": "text", "text": "hello"}])
        assert result == [{"type": "text", "text": "hello"}]

    def test_image_block_to_data_uri(self):
        blocks = [{
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"},
        }]
        result = _to_openai_blocks(blocks)
        assert result[0]["type"] == "image_url"
        assert result[0]["image_url"]["url"] == "data:image/png;base64,AAAA"


# ── _to_responses_blocks ──────────────────────────────────────────────────────

class TestToResponsesBlocks:
    def test_text_block_becomes_input_text(self):
        result = _to_responses_blocks([{"type": "text", "text": "hello"}])
        assert result == [{"type": "input_text", "text": "hello"}]

    def test_image_block_becomes_input_image(self):
        blocks = [{
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"},
        }]
        result = _to_responses_blocks(blocks)
        assert result[0]["type"] == "input_image"
        # Responses API: image_url is a plain string, not nested object
        assert result[0]["image_url"] == "data:image/png;base64,AAAA"

    def test_mixed_blocks(self):
        blocks = [
            {"type": "image",
             "source": {"type": "base64", "media_type": "image/png", "data": "X"}},
            {"type": "text", "text": "analyse this"},
        ]
        result = _to_responses_blocks(blocks)
        assert len(result) == 2
        assert result[0]["type"] == "input_image"
        assert result[1]["type"] == "input_text"


# ── generate_report routing ───────────────────────────────────────────────────

class TestGenerateReportRouting:
    """Verify generate_report calls the correct API adapter for each format."""

    def test_anthropic_calls_messages(self, css_data, assets_data, screenshot_paths):
        m = _make_model("anthropic-messages", Cap.TEXT)
        m.client.messages.create.return_value = MagicMock(
            content=[MagicMock(type="text", text="# Report")]
        )
        result = generate_report(css_data, assets_data, screenshot_paths, "sys", m)
        assert result == "# Report"
        m.client.messages.create.assert_called_once()

    def test_openai_calls_chat_completions(self, css_data, assets_data, screenshot_paths):
        m = _make_model("openai-completions", Cap.TEXT)
        m.client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="# Report"))]
        )
        result = generate_report(css_data, assets_data, screenshot_paths, "sys", m)
        assert result == "# Report"
        m.client.chat.completions.create.assert_called_once()

    def test_responses_calls_responses_create(self, css_data, assets_data, screenshot_paths):
        m = _make_model("openai-responses", Cap.TEXT)
        # Codex uses streaming — mock an iterable of SSE events
        event = MagicMock(type="response.output_text.delta", delta="# Report")
        m.client.responses.create.return_value = [event]
        result = generate_report(css_data, assets_data, screenshot_paths, "sys", m)
        assert result == "# Report"
        m.client.responses.create.assert_called_once()

        # Verify Codex protocol: instructions, input, stream=True, store=False, no max_output_tokens
        kwargs = m.client.responses.create.call_args.kwargs
        assert kwargs["instructions"] == "sys"
        assert kwargs["input"][0]["role"] == "user"
        assert kwargs["stream"] is True
        assert kwargs["store"] is False
        assert "max_output_tokens" not in kwargs

    def test_ollama_uses_chat_completions(self, css_data, assets_data, screenshot_paths):
        m = _make_model("ollama", Cap.TEXT)
        m.client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="# Report"))]
        )
        result = generate_report(css_data, assets_data, screenshot_paths, "sys", m)
        assert result == "# Report"

    def test_unknown_format_raises(self, css_data, assets_data, screenshot_paths):
        m = _make_model("grpc-streaming", Cap.TEXT)
        with pytest.raises(ValueError, match="Unsupported api_format"):
            generate_report(css_data, assets_data, screenshot_paths, "sys", m)


# ── Vision vs Text-only payloads ───────────────────────────────────────────────

class TestVisionPayload:
    """Ensure the correct payload is sent to each API format in vision mode."""

    def test_anthropic_vision_sends_image_block(self, css_data, assets_data, screenshot_paths):
        m = _make_model("anthropic-messages", Cap.TEXT | Cap.VISION)
        m.client.messages.create.return_value = MagicMock(
            content=[MagicMock(type="text", text="ok")]
        )
        generate_report(css_data, assets_data, screenshot_paths, "sys", m)

        call_kwargs = m.client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert any(b["type"] == "image" for b in user_content)

    def test_responses_vision_sends_input_image(self, css_data, assets_data, screenshot_paths):
        m = _make_model("openai-responses", Cap.TEXT | Cap.VISION)
        event = MagicMock(type="response.output_text.delta", delta="ok")
        m.client.responses.create.return_value = [event]
        generate_report(css_data, assets_data, screenshot_paths, "sys", m)

        call_kwargs = m.client.responses.create.call_args.kwargs
        input_content = call_kwargs["input"][0]["content"]
        types = {b["type"] for b in input_content}
        assert "input_image" in types
        assert "input_text" in types
