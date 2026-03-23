"""
Layer 4: LLM analysis and Markdown report generation.

Adapts the prompt payload to model capabilities detected by model.probe_caps():
  - Cap.TEXT | Cap.VISION  → structured CSS data + scroll-captured screenshots
  - Cap.TEXT only          → structured CSS data only, screenshots omitted

Supports all Leafhub api_format values via thin adapters:
  - "anthropic-messages"              → Anthropic Messages API
  - "openai-completions" / "ollama"   → OpenAI Chat Completions API
  - "openai-responses"                → OpenAI Responses API (Codex endpoint)
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from .model import Cap, ResolvedModel


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_report(
    css_data:         dict,
    assets_data:      dict,
    screenshot_paths: list[Path],
    system_prompt:    str,
    model:            ResolvedModel,
) -> str:
    """
    Build the prompt payload according to model.caps, call the LLM,
    return the raw Markdown string.
    """
    user_content = _build_user_content(css_data, assets_data, screenshot_paths, model.caps)

    if model.api_format == "anthropic-messages":
        return _call_anthropic(model, system_prompt, user_content)
    elif model.api_format in ("openai-completions", "ollama"):
        return _call_openai(model, system_prompt, user_content)
    elif model.api_format == "openai-responses":
        return _call_openai_responses(model, system_prompt, user_content)

    raise ValueError(f"Unsupported api_format: {model.api_format!r}")


# ── Payload builder ────────────────────────────────────────────────────────────

def _build_user_content(
    css_data:         dict,
    assets_data:      dict,
    screenshot_paths: list[Path],
    caps:             Cap,
) -> list[dict]:
    """
    Produce a list of content blocks.

    Vision mode:   [image_block_1, ..., image_block_N, text_block]
      Each image is one viewport "fold" captured during scroll.
    Text-only mode: [text_block]  (with a note explaining no screenshots)
    """
    # Separate architecture signals for clearer prompt structure
    arch_data = {
        k: assets_data[k]
        for k in ("detected_frameworks", "build_tools", "media")
        if k in assets_data
    }

    data_text = (
        f"## CSS & Typography\n```json\n{json.dumps(css_data, indent=2)}\n```\n\n"
        f"## Assets & Libraries\n```json\n{json.dumps(assets_data, indent=2)}\n```\n\n"
        f"## Architecture Signals\n```json\n{json.dumps(arch_data, indent=2)}\n```"
    )

    if Cap.VISION not in caps:
        return [{
            "type": "text",
            "text": (
                "[Note: This model does not support image input. "
                "Analysis is based on extracted CSS data only — "
                "no visual screenshots were provided.]\n\n" + data_text
            ),
        }]

    # Sample key frames — all frames are saved on disk, but sending too many
    # to the LLM wastes tokens (adjacent frames are near-identical) and can
    # exceed API size limits.  Pick evenly-spaced frames including first & last.
    sampled = _sample_frames(screenshot_paths, max_frames=8)

    blocks: list[dict] = []
    for path in sampled:
        img_b64 = base64.standard_b64encode(path.read_bytes()).decode()
        blocks.append({
            "type": "image",
            "source": {
                "type":       "base64",
                "media_type": "image/png",
                "data":       img_b64,
            },
        })

    # Label the frames so the LLM knows the scroll order
    frame_note = (
        f"[{len(sampled)} viewport screenshots provided (sampled from "
        f"{len(screenshot_paths)} total scroll frames). "
        f"Frame 1 = top of page, Frame {len(sampled)} = bottom.]\n\n"
    )
    blocks.append({"type": "text", "text": frame_note + data_text})

    return blocks


def _sample_frames(paths: list[Path], max_frames: int = 8) -> list[Path]:
    """
    Evenly sample up to *max_frames* from the full frame list.

    Always includes the first and last frame.  Remaining slots are
    distributed evenly across the scroll depth so every major section
    of the page is represented.
    """
    n = len(paths)
    if n <= max_frames:
        return paths

    # First + last are always included; fill the middle evenly
    indices = {0, n - 1}
    for i in range(1, max_frames - 1):
        idx = round(i * (n - 1) / (max_frames - 1))
        indices.add(idx)

    return [paths[i] for i in sorted(indices)]


# ── API format adapters ────────────────────────────────────────────────────────

def _call_anthropic(model: ResolvedModel, system_prompt: str, user_content: list) -> str:
    resp = model.client.messages.create(
        model=model.model,
        max_tokens=8192,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    # Some models (e.g. MiniMax-M2.5) return ThinkingBlock before TextBlock.
    # Skip non-text blocks and return the first text content.
    for block in resp.content:
        if block.type == "text":
            return block.text
    raise RuntimeError(
        f"No text block in LLM response. "
        f"Got {len(resp.content)} block(s): {[b.type for b in resp.content]}"
    )


def _call_openai(model: ResolvedModel, system_prompt: str, user_content: list) -> str:
    resp = model.client.chat.completions.create(
        model=model.model,
        max_tokens=8192,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": _to_openai_blocks(user_content)},
        ],
    )
    return resp.choices[0].message.content


def _to_openai_blocks(content: list[dict]) -> list[dict]:
    """
    Convert Anthropic-style content blocks to OpenAI Chat Completions format.
    Anthropic image source (base64) → OpenAI image_url (data URI).
    """
    out = []
    for block in content:
        if block["type"] == "text":
            out.append({"type": "text", "text": block["text"]})
        elif block["type"] == "image":
            src      = block["source"]
            data_uri = f"data:{src['media_type']};base64,{src['data']}"
            out.append({"type": "image_url", "image_url": {"url": data_uri}})
    return out


# ── OpenAI Responses API (Codex endpoint) ─────────────────────────────────────
# Protocol differences from Chat Completions:
#   messages  → input
#   system    → instructions
#   max_tokens → max_output_tokens
#   content block types: input_text / input_image (not text / image_url)

def _call_openai_responses(
    model: ResolvedModel, system_prompt: str, user_content: list,
) -> str:
    # Codex endpoint: stream=True, store=False required.
    # max_output_tokens / temperature NOT supported — omit them.
    stream = model.client.responses.create(
        model=model.model,
        instructions=system_prompt,
        input=[{"role": "user", "content": _to_responses_blocks(user_content)}],
        store=False,
        stream=True,
    )
    chunks: list[str] = []
    for event in stream:
        if event.type == "response.output_text.delta":
            chunks.append(event.delta)
    return "".join(chunks)


def _to_responses_blocks(content: list[dict]) -> list[dict]:
    """
    Convert Anthropic-style content blocks to OpenAI Responses API format.
    Block types: input_text, input_image (image_url is a plain string, not nested).
    """
    out = []
    for block in content:
        if block["type"] == "text":
            out.append({"type": "input_text", "text": block["text"]})
        elif block["type"] == "image":
            src      = block["source"]
            data_uri = f"data:{src['media_type']};base64,{src['data']}"
            out.append({"type": "input_image", "image_url": data_uri})
    return out
