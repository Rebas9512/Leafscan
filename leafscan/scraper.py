"""
Layer 1: Playwright-based page scraping.

Responsibilities:
  - Launch headless Chromium
  - Intercept network requests (for library/font/CDN detection)
  - Navigate, wait for initial render
  - Auto-dismiss cookie consent banners (uncovers the real page content)
  - Scroll through the entire page, capturing viewport screenshots.
    Uses DOM scrollTo for normal pages, and synthetic wheel events as
    fallback for WebGL/canvas sites where scrollHeight ≈ viewport.
  - Run extractor JS *after* the full scroll — the DOM is now fully rendered
  - Return structured data + list of screenshot paths

The browser lifecycle is fully contained here. Extractor and aggregator
receive plain Python dicts — no Playwright objects leave this module.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Request,
    async_playwright,
)

log = logging.getLogger(__name__)

from .extractor import EXTRACT_SCRIPT, parse_raw


# ── Configuration ─────────────────────────────────────────────────────────────

SCROLL_PAUSE_MS       = 800   # pause between scroll steps (ms)
MAX_SCROLL_STEPS      = 30    # safety cap — avoid infinite scroll pages
WHEEL_STEPS           = 8     # number of wheel-event frames for canvas/WebGL sites
WHEEL_DELTA           = 600   # pixels per wheel event
WHEEL_PAUSE_MS        = 1200  # longer pause for WebGL scenes to animate
VIEWPORT_WIDTH        = 1440
VIEWPORT_HEIGHT       = 900


# ── Data returned to the pipeline ─────────────────────────────────────────────

@dataclass
class ScrapeResult:
    css_data:         dict         # output of extractor.parse_raw()
    network_entries:  list[dict]   # [{url, resource_type}, ...]
    screenshot_paths: list[Path]   # ordered viewport captures [frame_01.png, ...]


# ── Public API ─────────────────────────────────────────────────────────────────

def scrape(url: str, output_dir: Path) -> ScrapeResult:
    """Synchronous wrapper — pipeline calls this without needing async."""
    return asyncio.run(_scrape_async(url, output_dir))


# ── Async implementation ───────────────────────────────────────────────────────

async def _scrape_async(url: str, output_dir: Path) -> ScrapeResult:
    output_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await _make_context(browser)
        page    = await context.new_page()

        network_entries = _attach_network_listener(page)

        await _navigate(page, url)
        await _dismiss_cookie_banner(page)

        # ── Scroll-and-capture ────────────────────────────────────────────
        screenshot_paths = await _scroll_and_capture(page, output_dir)

        # ── Extract CSS data AFTER full scroll (DOM is now fully rendered) ─
        raw      = await page.evaluate(EXTRACT_SCRIPT)
        css_data = parse_raw(raw)

        await browser.close()

    return ScrapeResult(
        css_data=css_data,
        network_entries=network_entries,
        screenshot_paths=screenshot_paths,
    )


# ── Cookie banner dismissal ───────────────────────────────────────────────────

# Common selectors for cookie consent "accept" buttons, ordered by specificity.
# Each entry is (selector, description) for debugging.
_CONSENT_SELECTORS = [
    # Generic buttons by text content
    'button:has-text("Accept All")',
    'button:has-text("Accept all")',
    'button:has-text("Accept")',
    'button:has-text("I agree")',
    'button:has-text("Got it")',
    'button:has-text("OK")',
    'button:has-text("Agree")',
    'button:has-text("Allow all")',
    'button:has-text("Allow All")',
    'button:has-text("Consent")',
    'button:has-text("Continue")',
    'button:has-text("Decline Non-Required")',
    # Common IDs and classes
    '#onetrust-accept-btn-handler',
    '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
    '[data-testid="cookie-accept"]',
    '.cookie-accept',
    '.cc-accept',
    '.cc-allow',
    '.js-cookie-accept',
    # TrustArc (used by cornrevolution)
    '.call[tabindex="0"]',
    '#truste-consent-button',
    'a:has-text("Agree and Proceed")',
]


async def _dismiss_cookie_banner(page: Page) -> None:
    """
    Try to click a cookie consent "accept" button.

    Searches the main page first, then any iframes (TrustArc, OneTrust,
    and similar consent managers often render inside an iframe).
    Fails silently if no banner is found — many sites don't have one.
    """
    # 1. Try main page
    if await _try_click_consent(page):
        return

    # 2. Try inside iframes (TrustArc, CookieBot, etc.)
    for frame in page.frames[1:]:
        try:
            if await _try_click_consent(frame):
                await asyncio.sleep(0.5)
                return
        except Exception:
            continue


async def _try_click_consent(target) -> bool:
    """Try consent selectors on a Page or Frame. Returns True if clicked."""
    for selector in _CONSENT_SELECTORS:
        try:
            btn = target.locator(selector).first
            if await btn.is_visible(timeout=300):
                await btn.click(timeout=1000)
                log.debug("Dismissed cookie banner via: %s", selector)
                await asyncio.sleep(0.5)
                return True
        except Exception:
            # Selector not found, not visible, or click failed — try next
            continue
    return False


# ── Scroll and capture ────────────────────────────────────────────────────────

async def _scroll_and_capture(page: Page, output_dir: Path) -> list[Path]:
    """
    Scroll the page and capture viewport screenshots.

    Two strategies:
      1. DOM scroll (normal pages): scrollTo in viewport-height steps.
         Triggers IntersectionObserver, ScrollTrigger, lazy loaders.
      2. Wheel events (WebGL/canvas sites): when scrollHeight ≈ viewport
         (no DOM scroll possible), dispatch synthetic wheel events to drive
         Three.js / custom scroll handlers.
    """
    total_height = await page.evaluate("document.body.scrollHeight")
    viewport_h   = VIEWPORT_HEIGHT

    # Detect if the page is a "fixed canvas" site — scrollHeight ≤ viewport + small margin
    is_canvas_site = total_height <= viewport_h + 100

    if is_canvas_site:
        return await _wheel_scroll_capture(page, output_dir)
    else:
        return await _dom_scroll_capture(page, output_dir, total_height)


async def _dom_scroll_capture(
    page: Page, output_dir: Path, total_height: int,
) -> list[Path]:
    """Standard DOM-based scroll capture for normal scrollable pages."""
    viewport_h = VIEWPORT_HEIGHT
    paths: list[Path] = []
    step = 0

    while step < MAX_SCROLL_STEPS:
        step += 1
        frame_path = output_dir / f"frame_{step:02d}.png"

        await page.screenshot(path=str(frame_path))
        paths.append(frame_path)

        current_y = await page.evaluate("window.scrollY")
        next_y    = current_y + viewport_h

        if current_y + viewport_h >= total_height:
            break

        await page.evaluate(f"window.scrollTo({{top: {next_y}, behavior: 'smooth'}})")
        await asyncio.sleep(SCROLL_PAUSE_MS / 1000)

        # Page might have grown (infinite scroll / dynamic content)
        total_height = await page.evaluate("document.body.scrollHeight")

    return paths


async def _wheel_scroll_capture(page: Page, output_dir: Path) -> list[Path]:
    """
    Wheel-event based capture for full-viewport WebGL/canvas sites.

    These sites handle scrolling via JS (Three.js camera, custom scroll
    managers) — DOM scrollTo has no effect because scrollHeight = viewportHeight.
    Synthetic wheel events simulate real user scrolling to drive the scene.

    After capture, duplicate frames are removed: if a wheel event didn't
    change the viewport (e.g. static pages like YouTube that happen to have
    scrollHeight ≈ viewport on initial load), only unique frames are kept.
    """
    paths: list[Path] = []
    step = 0
    prev_bytes: bytes = b""

    # Capture initial frame before any wheel events
    step += 1
    frame_path = output_dir / f"frame_{step:02d}.png"
    await page.screenshot(path=str(frame_path))
    prev_bytes = frame_path.read_bytes()
    paths.append(frame_path)

    for _ in range(WHEEL_STEPS):
        await page.mouse.wheel(0, WHEEL_DELTA)
        await asyncio.sleep(WHEEL_PAUSE_MS / 1000)

        step += 1
        frame_path = output_dir / f"frame_{step:02d}.png"
        await page.screenshot(path=str(frame_path))

        current_bytes = frame_path.read_bytes()
        if current_bytes == prev_bytes:
            frame_path.unlink()
            log.debug("Dropped duplicate frame: %s", frame_path.name)
        else:
            paths.append(frame_path)
            prev_bytes = current_bytes

    return paths


# ── Browser setup ─────────────────────────────────────────────────────────────

async def _make_context(browser: Browser) -> BrowserContext:
    return await browser.new_context(
        viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="en-US",
    )


def _attach_network_listener(page: Page) -> list[dict]:
    """
    Register a request handler that appends to a shared list.
    Returns the list — it will be populated during navigation.
    """
    entries: list[dict] = []

    def on_request(req: Request) -> None:
        entries.append({
            "url":           req.url,
            "resource_type": req.resource_type,
        })

    page.on("request", on_request)
    return entries


async def _navigate(page: Page, url: str) -> None:
    """
    Navigate with a two-stage wait:
      1. networkidle — all in-flight requests have settled
      2. Extra 1.5 s — lets JS-driven animations and lazy loaders initialise

    Falls back gracefully if networkidle times out (heavy SPAs sometimes
    never fully settle — domcontentloaded is the safe floor).
    """
    try:
        await page.goto(url, wait_until="networkidle", timeout=30_000)
    except Exception:
        log.warning("networkidle timeout for %s — falling back to domcontentloaded", url)
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    # Let deferred JS (IntersectionObserver callbacks, lazy fonts) run
    await asyncio.sleep(1.5)
