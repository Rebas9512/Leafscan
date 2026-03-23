#!/usr/bin/env python3
"""
LeafScan end-to-end smoke test.

Validates the full pipeline from setup.sh → model resolution → scrape → report,
with checkpoints and clear diagnostics at each stage.

Usage:
    python tests/smoke_e2e.py [url]

Default URL: https://linear.app  (public, JS-heavy, good test surface)
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────────────────

DEFAULT_URL = "https://linear.app"
PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"


# ── Helpers ────────────────────────────────────────────────────────────────────

def step(label: str):
    print(f"\n── {label} ──")


def ok(msg: str):
    print(f"  {PASS} {msg}")


def fail(msg: str):
    print(f"  {FAIL} {msg}")


def warn(msg: str):
    print(f"  {WARN} {msg}")


def abort(msg: str):
    fail(msg)
    sys.exit(1)


# ── Stage 1: Imports ───────────────────────────────────────────────────────────

def test_imports() -> bool:
    step("Stage 1 — Imports")
    errors = []
    for mod in [
        "leafscan.model",
        "leafscan.scraper",
        "leafscan.extractor",
        "leafscan.aggregator",
        "leafscan.reporter",
        "leafscan.pipeline",
        "leafscan.cli",
    ]:
        try:
            __import__(mod)
            ok(mod)
        except Exception as e:
            fail(f"{mod}: {e}")
            errors.append(mod)

    if errors:
        abort(f"Import failures: {errors}")
    return True


# ── Stage 2: Model resolution ─────────────────────────────────────────────────

def test_model_resolve(alias: str = "llm"):
    step(f"Stage 2 — Model resolution (alias={alias!r})")
    from leafscan.model import resolve

    try:
        model = resolve(alias=alias)
    except Exception as e:
        abort(f"resolve() failed: {e}")

    ok(f"api_format = {model.api_format}")
    ok(f"model      = {model.model}")
    ok(f"client     = {type(model.client).__name__}")
    return model


# ── Stage 3: Capability probe ─────────────────────────────────────────────────

def test_probe(model):
    step("Stage 3 — Capability probe")
    from leafscan.model import Cap, probe_caps

    t0   = time.monotonic()
    caps = probe_caps(model)
    dt   = time.monotonic() - t0

    model.caps = caps

    if Cap.VISION in caps:
        ok(f"Vision supported ({dt:.2f}s)")
    else:
        warn(f"Text-only mode ({dt:.2f}s) — screenshot will NOT be sent to LLM")

    return caps


# ── Stage 4: Scraper ──────────────────────────────────────────────────────────

def test_scraper(url: str, output_dir: Path):
    step("Stage 4 — Scraper (Playwright)")
    from leafscan.scraper import scrape

    t0     = time.monotonic()
    result = scrape(url, output_dir)
    dt     = time.monotonic() - t0

    ok(f"Scrape completed in {dt:.1f}s")

    # Screenshots (scroll frames)
    n_frames = len(result.screenshot_paths)
    ok(f"Scroll frames captured: {n_frames}")
    for p in result.screenshot_paths:
        if not p.exists():
            fail(f"Frame missing: {p.name}")
            break
    else:
        total_kb = sum(p.stat().st_size for p in result.screenshot_paths) / 1024
        ok(f"Total screenshot size: {total_kb:.0f} KB")

    # Network entries
    n = len(result.network_entries)
    ok(f"Network entries captured: {n}")
    if n == 0:
        warn("Zero network entries — possible issue with network interception")

    # CSS data
    sections = list(result.css_data.keys())
    ok(f"CSS data sections: {sections}")

    fonts = result.css_data.get("fonts", [])
    ok(f"Fonts detected: {len(fonts)}")

    typo = result.css_data.get("typography", {})
    ok(f"Typography samples: {len(typo)} elements")

    kf = result.css_data.get("keyframes", [])
    ok(f"Keyframes found: {len(kf)}")

    globs = result.css_data.get("globals", [])
    if globs:
        ok(f"JS globals detected: {globs}")
    else:
        warn("No JS animation globals detected (may be expected)")

    # Persist raw data
    (output_dir / "css.json").write_text(
        json.dumps(result.css_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "network.json").write_text(
        json.dumps(result.network_entries, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    ok("Raw data written to output dir")

    return result


# ── Stage 5: Aggregator ──────────────────────────────────────────────────────

def test_aggregator(css_data, network_entries, output_dir: Path):
    step("Stage 5 — Aggregator")
    from leafscan.aggregator import aggregate

    assets = aggregate(css_data, network_entries)

    libs = assets.get("detected_libraries", [])
    ok(f"Animation libraries: {libs or '(none detected)'}")

    font_svc = assets.get("font_services", [])
    ok(f"Font services: {[f['service'] for f in font_svc] or '(none detected)'}")

    scripts = assets.get("external_scripts", [])
    ok(f"External scripts: {len(scripts)}")

    cdns = assets.get("cdn_origins", [])
    ok(f"CDN origins: {len(cdns)}")

    (output_dir / "assets.json").write_text(
        json.dumps(assets, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    ok("assets.json written")

    return assets


# ── Stage 6: Reporter (LLM call) ──────────────────────────────────────────────

def test_reporter(css_data, assets_data, screenshot_paths, model, output_dir: Path):
    step("Stage 6 — Reporter (LLM call)")
    from leafscan.model import Cap
    from leafscan.reporter import generate_report

    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "design_report.txt"
    if not prompt_path.exists():
        abort(f"System prompt not found: {prompt_path}")

    system_prompt = prompt_path.read_text()
    ok(f"System prompt loaded ({len(system_prompt)} chars)")

    mode = "vision + text" if Cap.VISION in model.caps else "text-only"
    ok(f"Sending payload in {mode} mode ({len(screenshot_paths)} frames) ...")

    t0     = time.monotonic()
    report = generate_report(css_data, assets_data, screenshot_paths, system_prompt, model)
    dt     = time.monotonic() - t0

    ok(f"LLM response received ({dt:.1f}s, {len(report)} chars)")

    report_path = output_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")
    ok(f"Report written: {report_path}")

    # Quick quality check
    expected_sections = ["Font", "Color", "Animation", "Layout"]
    found = [s for s in expected_sections if s.lower() in report.lower()]
    missing = [s for s in expected_sections if s not in found]

    if missing:
        warn(f"Report may be missing sections: {missing}")
    else:
        ok(f"All expected sections present: {found}")

    return report


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    url   = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    alias = sys.argv[2] if len(sys.argv) > 2 else "llm"

    print("=" * 60)
    print(f"  LeafScan E2E Smoke Test")
    print(f"  URL:   {url}")
    print(f"  Alias: {alias}")
    print("=" * 60)

    t_total = time.monotonic()

    # 1. Imports
    test_imports()

    # 2. Model resolve
    model = test_model_resolve(alias=alias)

    # 3. Capability probe
    caps = test_probe(model)

    # 4. Scraper
    from urllib.parse import urlparse
    from datetime import datetime, timezone
    domain    = urlparse(url).hostname or "unknown"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = Path(__file__).resolve().parent.parent / "outputs" / f"{domain}_{timestamp}_smoke"
    output_dir.mkdir(parents=True, exist_ok=True)

    result = test_scraper(url, output_dir)

    # 5. Aggregator
    assets_data = test_aggregator(result.css_data, result.network_entries, output_dir)

    # 6. Reporter
    try:
        report = test_reporter(
            result.css_data, assets_data, result.screenshot_paths, model, output_dir,
        )
    except Exception as e:
        fail(f"Reporter failed: {e}")
        traceback.print_exc()
        report = None

    # Summary
    dt_total = time.monotonic() - t_total
    step("Summary")
    ok(f"Total time: {dt_total:.1f}s")
    ok(f"Output dir: {output_dir}")
    if report:
        ok("Pipeline completed successfully")
    else:
        warn("Pipeline completed with reporter failure — check output dir for partial results")

    print()


if __name__ == "__main__":
    main()
