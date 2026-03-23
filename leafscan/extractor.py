"""
Layer 2: CSS/font/animation extraction via browser-side JS.

This module owns the JS extraction script and the Python-side parser that
converts raw JS output into clean structured dicts.

The script runs inside the Playwright page context — no external deps needed
inside the browser. It uses only standard Web APIs:
  - window.getComputedStyle()   → typography, colors, layout
  - document.styleSheets        → @keyframes, transitions, CSS variables
  - document.fonts              → loaded font faces
  - window.*                    → global variable detection for bundled libs
"""
from __future__ import annotations


# ── JS extraction script ───────────────────────────────────────────────────────
# Injected via page.evaluate(). Returns a plain JSON-serializable object.

EXTRACT_SCRIPT = """
(() => {
  const result = {
    fonts_api:   [],
    typography:  {},
    css_vars:    {},
    keyframes:   [],
    transitions: [],
    layout:      {},
    globals:     [],
  };

  // ── 1. Loaded fonts via document.fonts API ─────────────────────────────────
  document.fonts.forEach(f => {
    result.fonts_api.push({
      family:  f.family,
      style:   f.style,
      weight:  f.weight,
      stretch: f.stretch,
      status:  f.status,
    });
  });

  // ── 2. Computed styles on representative elements ──────────────────────────
  // Priority: semantic elements first, then common class-name fragments.
  // getComputedStyle() reads the *final rendered* values — works with
  // CSS-in-JS and inline styles, not just static class names.
  const SELECTORS = [
    'body', 'h1', 'h2', 'h3', 'p', 'a', 'button',
    'nav', 'header', 'footer', 'main', 'section', 'article',
    '[class*="hero"]', '[class*="title"]', '[class*="heading"]',
    '[class*="btn"]',  '[class*="cta"]',
  ];

  for (const sel of SELECTORS) {
    let el;
    try { el = document.querySelector(sel); } catch(_) { continue; }
    if (!el) continue;

    const cs = window.getComputedStyle(el);
    result.typography[sel] = {
      fontFamily:    cs.fontFamily,
      fontSize:      cs.fontSize,
      fontWeight:    cs.fontWeight,
      lineHeight:    cs.lineHeight,
      letterSpacing: cs.letterSpacing,
      textTransform: cs.textTransform,
      color:         cs.color,
      backgroundColor: cs.backgroundColor,
    };
  }

  // ── 3. CSS custom properties from :root ───────────────────────────────────
  try {
    for (const sheet of document.styleSheets) {
      try {
        for (const rule of sheet.cssRules) {
          if (rule.selectorText === ':root') {
            const s = rule.style;
            for (let i = 0; i < s.length; i++) {
              const name = s[i];
              if (name.startsWith('--')) {
                result.css_vars[name] = s.getPropertyValue(name).trim();
              }
            }
          }
        }
      } catch(_) { /* cross-origin stylesheet — skip */ }
    }
  } catch(_) {}

  // ── 4. @keyframes + transition rules from stylesheets ─────────────────────
  const seenTransitions = new Set();
  try {
    for (const sheet of document.styleSheets) {
      try {
        for (const rule of sheet.cssRules) {
          // @keyframes
          if (rule.type === CSSRule.KEYFRAMES_RULE) {
            result.keyframes.push({
              name:    rule.name,
              // truncate very long keyframe bodies to keep payload manageable
              cssText: rule.cssText.length > 600
                ? rule.cssText.substring(0, 600) + '…'
                : rule.cssText,
            });
          }

          // transition declarations from regular rules
          if (rule.style) {
            const t = rule.style.transition;
            if (t && t !== 'none' && t !== 'all 0s ease 0s' && !seenTransitions.has(t)) {
              seenTransitions.add(t);
              result.transitions.push(t);
              if (result.transitions.length >= 30) break;
            }
          }
        }
      } catch(_) {}
    }
  } catch(_) {}

  // ── 5. Layout detection on major containers ───────────────────────────────
  const LAYOUT_SELS = [
    'body', 'main', 'header', 'footer', 'nav', 'section',
    '[class*="container"]', '[class*="wrapper"]',
    '[class*="grid"]',      '[class*="layout"]',
  ];

  for (const sel of LAYOUT_SELS) {
    let el;
    try { el = document.querySelector(sel); } catch(_) { continue; }
    if (!el) continue;

    const cs = window.getComputedStyle(el);
    if (cs.display === 'grid' || cs.display === 'flex') {
      result.layout[sel] = {
        display:             cs.display,
        flexDirection:       cs.flexDirection,
        flexWrap:            cs.flexWrap,
        gridTemplateColumns: cs.gridTemplateColumns,
        gridTemplateRows:    cs.gridTemplateRows,
        gap:                 cs.gap,
        maxWidth:            cs.maxWidth,
        alignItems:          cs.alignItems,
        justifyContent:      cs.justifyContent,
      };
    }
  }

  // ── 6. Global variable detection (bundled libraries) ──────────────────────
  // Libraries loaded via CDN are visible in network requests (handled in
  // aggregator). Libraries bundled via npm expose globals we can check here.
  const GLOBAL_CHECKS = [
    ['gsap',         'GSAP'],
    ['ScrollTrigger','GSAP ScrollTrigger'],
    ['THREE',        'Three.js'],
    ['anime',        'Anime.js'],
    ['Lottie',       'Lottie'],
    ['lottie',       'Lottie'],
    ['LocomotiveScroll', 'Locomotive Scroll'],
    ['Swiper',       'Swiper'],
    ['AOS',          'AOS (Animate on Scroll)'],
    ['Splitting',    'Splitting.js'],
    ['barba',        'Barba.js'],
  ];

  for (const [globalName, label] of GLOBAL_CHECKS) {
    if (window[globalName] !== undefined) {
      result.globals.push(label);
    }
  }

  return result;
})()
"""


# ── Python-side parser ─────────────────────────────────────────────────────────

def parse_raw(raw: dict) -> dict:
    """
    Clean and normalise the raw JS output into a structured css_data dict.
    Removes empty/noise values so the LLM prompt stays compact.
    """
    return {
        "fonts":       _clean_fonts(raw.get("fonts_api", [])),
        "typography":  _clean_typography(raw.get("typography", {})),
        "css_vars":    raw.get("css_vars", {}),
        "keyframes":   raw.get("keyframes", []),
        "transitions": _dedup(raw.get("transitions", [])),
        "layout":      _clean_layout(raw.get("layout", {})),
        "globals":     raw.get("globals", []),
    }


def _clean_fonts(fonts: list) -> list:
    seen = set()
    out  = []
    for f in fonts:
        key = (f.get("family", ""), f.get("weight", ""), f.get("style", ""))
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def _clean_typography(typo: dict) -> dict:
    """Drop entries where every computed value is empty or 'normal'."""
    NOISE = {"", "normal", "none", "auto", "0px", "rgba(0, 0, 0, 0)"}
    out = {}
    for sel, vals in typo.items():
        cleaned = {k: v for k, v in vals.items() if v not in NOISE}
        if cleaned:
            out[sel] = cleaned
    return out


def _clean_layout(layout: dict) -> dict:
    NOISE = {"", "none", "auto", "normal", "0px", "nowrap", "row"}
    out = {}
    for sel, vals in layout.items():
        cleaned = {k: v for k, v in vals.items() if v not in NOISE}
        if cleaned:
            out[sel] = cleaned
    return out


def _dedup(lst: list) -> list:
    seen = set()
    return [x for x in lst if not (x in seen or seen.add(x))]
