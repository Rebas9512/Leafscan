"""
Model resolution and capability probing.

Flow:
  resolve(alias) -> ResolvedModel   # client + api_format + model name, caps=TEXT default
  probe_caps(model) -> Cap          # sends a 1x1 PNG probe, confirms actual capabilities
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Flag, auto
from pathlib import Path


# ── Capability flags ───────────────────────────────────────────────────────────

class Cap(Flag):
    TEXT   = auto()
    VISION = auto()


# Minimal 8x8 red PNG — used only for the capability probe request.
# Some endpoints (e.g. Codex) reject 1x1 images as invalid; 8x8 is universally accepted.
_PROBE_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAEklEQVR4nGP4z8CA"
    "FWEXHbQSACj/P8Fu7N9hAAAAAElFTkSuQmCC"
)


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class ResolvedModel:
    client:     object        # anthropic.Anthropic | openai.OpenAI
    api_format: str           # "anthropic-messages" | "openai-completions" | "openai-responses" | "ollama"
    model:      str           # model id string
    caps:       Cap = field(default_factory=lambda: Cap.TEXT)


# ── Public API ─────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _get_default_alias() -> str:
    """Read the primary alias from leafhub.toml, fall back to 'llm'."""
    try:
        from leafhub_sdk.manifest import get_default_alias
        return get_default_alias(project_dir=_PROJECT_ROOT, fallback="llm")
    except ImportError:
        pass
    return "llm"


def resolve(alias: str | None = None) -> ResolvedModel:
    """
    Resolve model client. Tries leafhub-sdk first, then direct leafhub probe,
    then env vars. Caps are NOT determined here — call probe_caps() after.
    """
    if alias is None:
        alias = _get_default_alias()

    # ── Strategy 1: leafhub-sdk unified resolve ──────────────────────────────
    try:
        from leafhub_sdk import resolve as lh_resolve

        cred = lh_resolve(alias, project_dir=_PROJECT_ROOT, as_client=True)
        return ResolvedModel(
            client=cred.client,
            api_format=cred.api_format,
            model=cred.model,
        )
    except ImportError:
        pass  # leafhub-sdk not installed — try legacy path
    except Exception:
        pass  # resolve failed — fall through

    # ── Strategy 2: legacy leafhub probe ─────────────────────────────────────
    try:
        from leafhub.probe import detect

        result = detect(project_dir=_PROJECT_ROOT)
        if result.ready:
            hub = result.open_sdk()
            cfg = hub.get_config(alias)
            client = _build_client_legacy(hub, cfg, alias)
            return ResolvedModel(
                client=client, api_format=cfg.api_format, model=cfg.model,
            )
    except ImportError:
        pass
    except Exception:
        pass

    # ── Strategy 3: env var fallback ─────────────────────────────────────────
    return _fallback_from_env()


def probe_caps(m: ResolvedModel) -> Cap:
    """
    Send a minimal image request to determine actual model capabilities.

    Returns Cap.TEXT | Cap.VISION if the model accepts image input.
    Returns Cap.TEXT on any failure (400, unsupported modality, timeout, etc.).

    The probe uses max_tokens=1 — it only needs the model to *accept* the
    request, not actually analyze anything. Cost and latency are negligible.
    """
    try:
        if m.api_format == "anthropic-messages":
            m.client.messages.create(
                model=m.model,
                max_tokens=1,
                messages=[{"role": "user", "content": [
                    {"type": "image",
                     "source": {"type": "base64",
                                "media_type": "image/png",
                                "data": _PROBE_PNG_B64}},
                    {"type": "text", "text": "."},
                ]}],
            )
            return Cap.TEXT | Cap.VISION

        elif m.api_format in ("openai-completions", "ollama"):
            m.client.chat.completions.create(
                model=m.model,
                max_tokens=1,
                messages=[{"role": "user", "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{_PROBE_PNG_B64}"}},
                    {"type": "text", "text": "."},
                ]}],
            )
            return Cap.TEXT | Cap.VISION

        elif m.api_format == "openai-responses":
            # Codex endpoint: stream=True, store=False, instructions required.
            # max_output_tokens / temperature NOT supported — omit them.
            stream = m.client.responses.create(
                model=m.model,
                instructions="Reply with one word.",
                store=False,
                stream=True,
                input=[{"role": "user", "content": [
                    {"type": "input_image",
                     "image_url": f"data:image/png;base64,{_PROBE_PNG_B64}"},
                    {"type": "input_text", "text": "."},
                ]}],
            )
            # Consume stream minimally — we only care that the request was accepted
            for _event in stream:
                break
            stream.close()
            return Cap.TEXT | Cap.VISION

    except Exception:
        pass  # any error → safe downgrade to text-only

    return Cap.TEXT


# ── Internal helpers ───────────────────────────────────────────────────────────

def _build_client_legacy(hub, cfg, alias: str):
    """Build client from legacy LeafHub SDK (when leafhub-sdk is not available)."""
    fmt = cfg.api_format
    if fmt == "anthropic-messages":
        return hub.anthropic(alias)
    if fmt in ("openai-completions", "ollama"):
        return hub.openai(alias)
    if fmt == "openai-responses":
        from openai import OpenAI
        base = cfg.base_url.rstrip("/")
        if base.endswith("/responses"):
            base = base[: -len("/responses")]
        return OpenAI(api_key=cfg.api_key, base_url=base)
    raise ValueError(f"Unsupported api_format: {fmt!r}")


def _fallback_from_env() -> ResolvedModel:
    if key := os.getenv("ANTHROPIC_API_KEY"):
        import anthropic
        return ResolvedModel(
            client=anthropic.Anthropic(api_key=key),
            api_format="anthropic-messages",
            model=os.getenv("LEAFSCAN_MODEL", "claude-sonnet-4-6"),
        )
    if key := os.getenv("OPENAI_API_KEY"):
        import openai
        return ResolvedModel(
            client=openai.OpenAI(api_key=key),
            api_format="openai-completions",
            model=os.getenv("LEAFSCAN_MODEL", "gpt-4o"),
        )
    raise RuntimeError(
        "No credentials found.\n"
        "Run:  leafhub register .   (if leafhub.toml exists)\n"
        "Or set ANTHROPIC_API_KEY / OPENAI_API_KEY."
    )
