"""
Layer 3: Data aggregation and prompt payload assembly.

Takes the raw outputs from Layers 1+2 and produces two clean dicts
ready to be serialised into the LLM prompt:

  css_data    — typography, color, animation, layout (from extractor)
  assets_data — fonts, CDN libraries, third-party resources (from network)

Library detection works at two levels:
  - CDN-loaded: URL pattern matching on network_entries
  - npm-bundled: global variable names already collected by extractor JS
"""
from __future__ import annotations

import re
from urllib.parse import urlparse


# ── CDN library fingerprints ───────────────────────────────────────────────────
# Each entry: (display_name, [url_substring, ...])
# Matched against request URLs (case-insensitive substring search).

_CDN_PATTERNS: list[tuple[str, list[str]]] = [
    ("GSAP",                  ["gsap.min.js", "gsap.js", "gsap@", "gsap/"]),
    ("GSAP ScrollTrigger",    ["ScrollTrigger.min.js", "ScrollTrigger.js"]),
    ("Framer Motion",         ["framer-motion"]),
    ("Lottie",                ["lottie.min.js", "lottie.js", "lottie@", "lottie-web"]),
    ("Three.js",              ["three.min.js", "three.js", "three@", "three/"]),
    ("Anime.js",              ["anime.min.js", "anime.js", "animejs"]),
    ("Swiper",                ["swiper.min.js", "swiper.js", "swiper@"]),
    ("AOS",                   ["aos.js", "aos@", "aos/"]),
    ("Locomotive Scroll",     ["locomotive-scroll"]),
    ("Splitting.js",          ["splitting.js", "splitting.min.js"]),
    ("Barba.js",              ["barba.js", "barba@"]),
    ("Alpine.js",             ["alpine.js", "alpinejs"]),
    ("Intersection Observer Polyfill", ["intersection-observer.js"]),
    ("HTMX",                  ["htmx.min.js", "htmx.js"]),
]

# Font service hostnames → display label
_FONT_SERVICES: dict[str, str] = {
    "fonts.googleapis.com":  "Google Fonts",
    "fonts.gstatic.com":     "Google Fonts (static)",
    "use.typekit.net":       "Adobe Fonts (Typekit)",
    "p.typekit.net":         "Adobe Fonts (Typekit)",
    "fast.fonts.net":        "Fonts.com",
    "cloud.typography.com":  "H&FJ Cloud.Typography",
    "rsms.me":               "Inter (rsms.me)",
}


# ── Public API ─────────────────────────────────────────────────────────────────

def aggregate(css_data: dict, network_entries: list[dict]) -> dict:
    """
    Merge extractor output + network entries into a single assets_data dict.
    Also enriches css_data with library info discovered from globals.

    Returns assets_data — a self-contained dict for the LLM prompt.
    """
    libs    = _detect_libraries(network_entries, css_data.get("globals", []))
    fonts   = _detect_font_services(network_entries)
    scripts = _collect_external_scripts(network_entries)
    cdns    = _collect_cdn_origins(network_entries)

    assets_data = {
        "detected_libraries": libs,
        "font_services":      fonts,
        "external_scripts":   scripts[:30],   # cap to keep prompt compact
        "cdn_origins":        cdns,
    }

    return assets_data


# ── Detection helpers ──────────────────────────────────────────────────────────

def _detect_libraries(network_entries: list[dict], globals_found: list[str]) -> list[str]:
    """
    Union of CDN-pattern matches (from network) and global-variable matches
    (from extractor JS). Deduped, sorted.
    """
    found: set[str] = set(globals_found)

    for entry in network_entries:
        url_lower = entry["url"].lower()
        for name, patterns in _CDN_PATTERNS:
            if any(p.lower() in url_lower for p in patterns):
                found.add(name)

    return sorted(found)


def _detect_font_services(network_entries: list[dict]) -> list[dict]:
    """Return [{service, url}] for each recognised font CDN hit."""
    seen: set[str] = set()
    out:  list[dict] = []

    for entry in network_entries:
        if entry["resource_type"] not in ("font", "stylesheet", "fetch", "xhr", "other"):
            continue
        host = urlparse(entry["url"]).hostname
        if not host:
            continue
        for domain, label in _FONT_SERVICES.items():
            if host == domain or host.endswith("." + domain):
                if label not in seen:
                    seen.add(label)
                    out.append({"service": label, "url": entry["url"]})
                break

    return out


def _collect_external_scripts(network_entries: list[dict]) -> list[str]:
    """Return unique external script URLs (not same-origin bundles)."""
    seen: set[str] = set()
    out:  list[str] = []

    for entry in network_entries:
        if entry["resource_type"] != "script":
            continue
        url = entry["url"]
        if url not in seen:
            seen.add(url)
            out.append(url)

    return out


def _collect_cdn_origins(network_entries: list[dict]) -> list[str]:
    """Return unique external hostnames (excludes data: and blob: URIs)."""
    seen: set[str] = set()
    out:  list[str] = []

    for entry in network_entries:
        url = entry["url"]
        if url.startswith(("data:", "blob:")):
            continue
        host = urlparse(url).hostname
        if host and host not in seen:
            seen.add(host)
            out.append(host)

    return sorted(out)
