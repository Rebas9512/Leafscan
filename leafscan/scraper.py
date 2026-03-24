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
        await _dismiss_modals(page)

        # ── Reset scroll to top ─────────────────────────────────────────
        # Overlay dismissal (clicking buttons, removing DOM nodes) can leave
        # the page scrolled to an arbitrary position.  Reset to top so the
        # scroll-and-capture starts from the beginning of the page.
        await page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
        await asyncio.sleep(0.3)

        # ── Scroll-and-capture ────────────────────────────────────────────
        screenshot_paths = await _scroll_and_capture(page, output_dir)

        # ── Retry cookie dismiss after scroll (late-appearing banners) ───
        # Some banners only appear after scroll or a JS timer.  If one is
        # still visible, click it now and re-take the last captured frame
        # so the final screenshots are clean.
        if await _try_dismiss_late_banner(page, screenshot_paths):
            log.debug("Late cookie banner dismissed after scroll")

        # ── Retry modal dismiss after scroll (late-appearing modals) ───
        await _dismiss_modals(page)

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
    # Generic buttons by text content (button element).
    # IMPORTANT: use :text-is() (exact match) for short/common words like
    # "OK", "Agree" to avoid false positives.  Playwright's :has-text() does
    # case-insensitive substring matching — e.g. "Book" contains "ok".
    'button:has-text("Accept All")',
    'button:has-text("Accept all")',
    'button:has-text("Accept Cookies")',
    'button:has-text("Accept cookies")',
    'button:text-is("Accept")',
    'button:has-text("I agree")',
    'button:has-text("Got it")',
    'button:has-text("Got It")',
    'button:text-is("OK")',
    'button:text-is("Ok")',
    'button:text-is("Agree")',
    'button:has-text("Allow all")',
    'button:has-text("Allow All")',
    'button:has-text("Allow Cookies")',
    'button:has-text("Consent")',
    'button:has-text("Decline Non-Required")',
    # Same patterns but for <a> / <div> / <span> (many banners use non-button elements)
    'a:has-text("Accept All")',
    'a:has-text("Accept all")',
    'a:text-is("Accept")',
    'a:has-text("Got it")',
    'a:has-text("Got It")',
    'a:text-is("OK")',
    'a:has-text("I agree")',
    'a:has-text("Agree and Proceed")',
    'a:has-text("Allow all")',
    '[role="button"]:text-is("Accept")',
    '[role="button"]:has-text("Got it")',
    '[role="button"]:text-is("OK")',
    # Common IDs and classes
    '#onetrust-accept-btn-handler',
    '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
    '[data-testid="cookie-accept"]',
    '.cookie-accept',
    '.cc-accept',
    '.cc-allow',
    '.cc-dismiss',
    '.cc-btn',
    '.js-cookie-accept',
    '.cookie-notice__button',
    '.cookie-consent-accept',
    '[data-cookie-accept]',
    '[data-action="accept-cookies"]',
    # CookieConsent (GDPR Cookie Consent plugin)
    '#cookie_action_close_header',
    '.cli-plugin-button',
    # Complianz
    '#cmplz-cookiebanner-container .cmplz-accept',
    # TrustArc
    '.call[tabindex="0"]',
    '#truste-consent-button',
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


async def _try_dismiss_late_banner(page: Page, screenshot_paths: list[Path]) -> bool:
    """
    Retry cookie dismissal after scrolling — catches banners that appear
    on a delay or after scroll. If dismissed, re-capture the last frame
    so screenshots are clean.
    """
    dismissed = await _try_click_consent(page)
    if not dismissed:
        for frame in page.frames[1:]:
            try:
                dismissed = await _try_click_consent(frame)
                if dismissed:
                    break
            except Exception:
                continue

    if dismissed and screenshot_paths:
        await asyncio.sleep(0.5)
        # Re-take the last frame without the banner
        last = screenshot_paths[-1]
        await page.screenshot(path=str(last))

    return dismissed


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


# ── Modal / overlay dismissal ─────────────────────────────────────────────

# Common selectors for modal close buttons.
# These fire *after* cookie banners, catching CTA modals, newsletter popups,
# intro overlays, etc. that obscure the actual page content.
_MODAL_CLOSE_SELECTORS = [
    # Explicit close / dismiss buttons (aria-label)
    '[aria-label="Close"]',
    '[aria-label="close"]',
    '[aria-label="Dismiss"]',
    '[aria-label="Close dialog"]',
    '[aria-label="Close modal"]',
    # Data attributes
    '[data-dismiss="modal"]',
    '[data-testid="close-button"]',
    '[data-testid="modal-close"]',
    '[data-action="close"]',
    # Class-based close buttons
    'button.close',
    'button.modal-close',
    'button.dialog-close',
    '.modal-close',
    '.close-button',
    '.close-btn',
    '.dialog-close',
    # Text-based close buttons
    'button:has-text("×")',
    'button:has-text("✕")',
    'button:has-text("✖")',
    'button:has-text("Close")',
    # Close buttons scoped inside modal/dialog containers
    '[role="dialog"] button',
    '[class*="modal"] button[class*="close"]',
    '[class*="dialog"] button[class*="close"]',
    '[class*="overlay"] button[class*="close"]',
    '[class*="popup"] button[class*="close"]',
    '[class*="modal"] [class*="close"]',
    '[class*="popup"] [class*="close"]',
]


async def _dismiss_modals(page: Page) -> None:
    """
    Attempt to close non-cookie modal overlays that block page content.

    Runs up to MAX_DISMISS_ROUNDS rounds to handle stacked overlays and
    overlays that appear as a side-effect of dismissing another (e.g. closing
    a CTA modal causes a navigation menu to open underneath).

    Each round tries strategies in order of increasing aggressiveness:
      1. Press Escape key
      2. Click known close-button selectors
      3. JS heuristic: find & click the topmost close affordance in the overlay
      4. Nuclear: force-remove blocking elements via DOM manipulation
    """
    MAX_DISMISS_ROUNDS = 5

    for round_num in range(MAX_DISMISS_ROUNDS):
        if not await _has_blocking_overlay(page):
            return

        log.debug("Blocking overlay detected (round %d)", round_num + 1)

        # Strategy 1: Escape key — fastest and most universal
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.6)
        if not await _has_blocking_overlay(page):
            log.debug("Overlay dismissed via Escape key (round %d)", round_num + 1)
            continue  # re-check for newly revealed overlays

        # Strategy 2: Click known close-button selectors
        if await _try_click_modal_close(page):
            await asyncio.sleep(0.6)
            if not await _has_blocking_overlay(page):
                log.debug("Overlay dismissed via close selector (round %d)", round_num + 1)
                continue

        # Strategy 3: JS heuristic — find the topmost overlay's close button
        if await _try_js_close_button(page):
            await asyncio.sleep(0.6)
            if not await _has_blocking_overlay(page):
                log.debug("Overlay dismissed via JS heuristic (round %d)", round_num + 1)
                continue

        # Strategy 4 (nuclear): force-remove the blocking elements from DOM
        removed = await _force_remove_overlays(page)
        if removed:
            log.debug("Force-removed %d overlay(s) via DOM (round %d)", removed, round_num + 1)
            await asyncio.sleep(0.3)
            # Don't break — loop back to check for newly exposed overlays
        else:
            # Nothing was removed — no point continuing
            log.debug("No removable overlays found, giving up (round %d)", round_num + 1)
            break


async def _has_blocking_overlay(page: Page) -> bool:
    """
    Detect if a modal/overlay is blocking the page content.

    Uses two complementary heuristics:
      1. Semantic: elements with role="dialog" or modal-like class names
         that are large and visible.
      2. Geometric: elements with fixed/absolute position, high z-index,
         and covering ≥60% of the viewport — catches custom overlays that
         don't use standard class names or ARIA roles.
    """
    return await page.evaluate("""
        (() => {
            const vw = window.innerWidth;
            const vh = window.innerHeight;
            const minArea = vw * vh * 0.6;

            // Heuristic 1: semantic selectors
            const semanticSels = [
                '[role="dialog"]',
                '[aria-modal="true"]',
                '[class*="modal"]',
                '[class*="popup"]',
                '[class*="lightbox"]',
            ];
            for (const s of semanticSels) {
                try {
                    for (const el of document.querySelectorAll(s)) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 200 && r.height > 200
                            && el.offsetParent !== null) return true;
                    }
                } catch(_) {}
            }

            // Heuristic 2: geometric — fixed/absolute + high z-index + large area
            const fullscreenArea = vw * vh * 0.8;
            const candidates = document.querySelectorAll(
                'body > *, body > * > *, body > * > * > *'
            );
            for (const el of candidates) {
                const cs = window.getComputedStyle(el);
                const pos = cs.position;
                if (pos !== 'fixed' && pos !== 'absolute') continue;
                const z = parseInt(cs.zIndex, 10);
                if (isNaN(z) || z < 10) continue;
                const r = el.getBoundingClientRect();
                const area = r.width * r.height;
                if (area < minArea) continue;
                if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                if (parseFloat(cs.opacity) < 0.01) continue;
                const tag = el.tagName.toLowerCase();
                if (tag === 'main') continue;
                // Short bars (nav/header) are not blocking unless fullscreen
                if (r.height < vh * 0.4) continue;
                if ((tag === 'header' || tag === 'nav') && area < fullscreenArea) continue;
                return true;
            }
            return false;
        })()
    """)


async def _try_click_modal_close(page: Page) -> bool:
    """Try clicking close buttons inside modal/dialog elements."""
    for selector in _MODAL_CLOSE_SELECTORS:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=200):
                await btn.click(timeout=1000)
                return True
        except Exception:
            continue
    return False


async def _try_js_close_button(page: Page) -> bool:
    """
    JS heuristic: find the topmost overlay, then locate the most likely
    close button within it — typically a small clickable element in the
    top-right corner (icon button, SVG ×, etc.).

    This catches custom close buttons that don't match any text or class
    selector (e.g. inline SVGs, icon fonts, unnamed <button> elements).
    """
    clicked = await page.evaluate("""
        (() => {
            const vw = window.innerWidth;
            const vh = window.innerHeight;

            // Find the topmost overlay element
            let overlay = null;
            let maxZ = -1;

            // Check semantic containers first
            for (const s of ['[role="dialog"]', '[aria-modal="true"]',
                             '[class*="modal"]', '[class*="popup"]']) {
                try {
                    for (const el of document.querySelectorAll(s)) {
                        const r = el.getBoundingClientRect();
                        if (r.width < 200 || r.height < 200) continue;
                        const z = parseInt(window.getComputedStyle(el).zIndex, 10) || 0;
                        if (z >= maxZ) { overlay = el; maxZ = z; }
                    }
                } catch(_) {}
            }

            // Fallback: geometric scan
            if (!overlay) {
                for (const el of document.querySelectorAll('body > *, body > * > *')) {
                    const cs = window.getComputedStyle(el);
                    if (cs.position !== 'fixed' && cs.position !== 'absolute') continue;
                    const z = parseInt(cs.zIndex, 10);
                    if (isNaN(z) || z < 10) continue;
                    const r = el.getBoundingClientRect();
                    if (r.width * r.height >= vw * vh * 0.3 && z >= maxZ) {
                        overlay = el;
                        maxZ = z;
                    }
                }
            }
            if (!overlay) return false;

            // Within the overlay, find small clickable elements near the top-right
            // (the canonical position for a close button).
            const btns = overlay.querySelectorAll(
                'button, [role="button"], a[href="#"], [tabindex="0"]'
            );
            let best = null;
            let bestScore = -Infinity;
            const overlayRect = overlay.getBoundingClientRect();

            for (const btn of btns) {
                const r = btn.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) continue;
                // Skip large buttons (likely form actions, not close)
                if (r.width > 200 && r.height > 60) continue;
                // Score: prefer top-right position, small size
                const xPct = (r.x - overlayRect.x) / overlayRect.width;  // 0=left, 1=right
                const yPct = (r.y - overlayRect.y) / overlayRect.height; // 0=top, 1=bottom
                const score = xPct * 3 - yPct * 5 - (r.width * r.height) / 5000;
                if (score > bestScore) {
                    bestScore = score;
                    best = btn;
                }
            }
            if (best) {
                best.click();
                return true;
            }
            return false;
        })()
    """)
    return bool(clicked)


async def _force_remove_overlays(page: Page) -> int:
    """
    Nuclear option: force-hide blocking overlay elements via DOM manipulation.

    This removes fixed/absolute overlays that cover ≥50% of the viewport
    and also clears body scroll locks (overflow: hidden) that modals set.

    Unlike the polite strategies, this mutates the DOM directly. It handles:
      - Semantic modals ([role="dialog"], [aria-modal])
      - Geometric overlays (fixed/absolute + high z-index + large area)
      - Fullscreen navigation menus (covers ≥ 80% of viewport)

    Returns the number of overlays removed.
    """
    return await page.evaluate("""
        (() => {
            const vw = window.innerWidth;
            const vh = window.innerHeight;
            const minArea = vw * vh * 0.5;
            const fullscreenArea = vw * vh * 0.8;
            let removed = 0;

            // 1. Remove semantic modal containers
            for (const s of ['[role="dialog"]', '[aria-modal="true"]']) {
                for (const el of document.querySelectorAll(s)) {
                    el.remove();
                    removed++;
                }
            }

            // 2. Remove geometric overlay elements (fixed/absolute + high z + large)
            // Scan up to 3 levels deep from body to catch nested wrappers
            const candidates = document.querySelectorAll(
                'body > *, body > * > *, body > * > * > *'
            );
            for (const el of candidates) {
                const cs = window.getComputedStyle(el);
                const pos = cs.position;
                if (pos !== 'fixed' && pos !== 'absolute') continue;
                const z = parseInt(cs.zIndex, 10);
                if (isNaN(z) || z < 10) continue;
                const r = el.getBoundingClientRect();
                const area = r.width * r.height;
                if (area < minArea) continue;
                if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                if (parseFloat(cs.opacity) < 0.01) continue;

                const tag = el.tagName.toLowerCase();
                // Protect <main> — it's never an overlay
                if (tag === 'main') continue;
                // Protect short bars (headers/nav bars) — but NOT if they
                // cover nearly the whole viewport (fullscreen nav menus)
                if ((tag === 'header' || tag === 'nav') && area < fullscreenArea) continue;

                el.remove();
                removed++;
            }

            // 3. Restore body scrollability (modals often set overflow:hidden)
            if (removed > 0) {
                document.body.style.overflow = '';
                document.body.style.overflowY = '';
                document.documentElement.style.overflow = '';
                document.documentElement.style.overflowY = '';
                // Also remove common scroll-lock classes
                document.body.classList.remove(
                    'modal-open', 'overflow-hidden', 'no-scroll',
                    'is-locked', 'scroll-locked'
                );
            }

            return removed;
        })()
    """)


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
      3. Wait for / remove page-transition overlays (loading screens)

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

    # Wait for page-transition / loading overlays to disappear.
    # Many sites show a branded loading screen (fixed overlay with very high
    # z-index) that animates away after fonts/assets load.  We poll for up to
    # 5 s, then forcibly remove any that remain.
    await _wait_for_loading_overlay(page)


async def _wait_for_loading_overlay(page: Page) -> None:
    """
    Poll for fullscreen loading overlays (z-index ≥ 9000, fixed, covers
    100% of viewport) and wait up to 5 s for them to disappear naturally.
    If still present after the timeout, remove them via DOM.
    """
    for _ in range(10):  # 10 × 0.5 s = 5 s max
        has_loader = await page.evaluate("""
            (() => {
                const vw = window.innerWidth;
                const vh = window.innerHeight;
                const fullArea = vw * vh * 0.9;
                const all = document.querySelectorAll('body > *, body > * > *');
                for (const el of all) {
                    const cs = window.getComputedStyle(el);
                    if (cs.position !== 'fixed') continue;
                    const z = parseInt(cs.zIndex, 10);
                    if (isNaN(z) || z < 9000) continue;
                    const r = el.getBoundingClientRect();
                    if (r.width * r.height < fullArea) continue;
                    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                    if (parseFloat(cs.opacity) < 0.01) continue;
                    return true;
                }
                return false;
            })()
        """)
        if not has_loader:
            return
        await asyncio.sleep(0.5)

    # Still present — force-remove
    removed = await page.evaluate("""
        (() => {
            const vw = window.innerWidth;
            const vh = window.innerHeight;
            const fullArea = vw * vh * 0.9;
            let removed = 0;
            const all = document.querySelectorAll('body > *, body > * > *');
            for (const el of all) {
                const cs = window.getComputedStyle(el);
                if (cs.position !== 'fixed') continue;
                const z = parseInt(cs.zIndex, 10);
                if (isNaN(z) || z < 9000) continue;
                const r = el.getBoundingClientRect();
                if (r.width * r.height < fullArea) continue;
                if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                el.remove();
                removed++;
            }
            return removed;
        })()
    """)
    if removed:
        log.debug("Force-removed %d loading overlay(s)", removed)
        await asyncio.sleep(0.3)
