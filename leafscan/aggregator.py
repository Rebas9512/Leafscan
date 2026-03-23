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
    # Animation libraries
    ("GSAP",                  ["gsap.min.js", "gsap.js", "gsap@", "gsap/"]),
    ("GSAP ScrollTrigger",    ["ScrollTrigger.min.js", "ScrollTrigger.js"]),
    ("Framer Motion",         ["framer-motion"]),
    ("Lottie",                ["lottie.min.js", "lottie.js", "lottie@", "lottie-web"]),
    ("Anime.js",              ["anime.min.js", "anime.js", "animejs"]),
    ("AOS",                   ["aos.js", "aos@", "aos/"]),
    ("Locomotive Scroll",     ["locomotive-scroll"]),
    ("Splitting.js",          ["splitting.js", "splitting.min.js"]),
    ("Barba.js",              ["barba.js", "barba@"]),
    # 3D / rendering
    ("Three.js",              ["three.min.js", "three.js", "three@", "three/"]),
    ("Babylon.js",            ["babylon.js", "babylonjs"]),
    ("PixiJS",                ["pixi.min.js", "pixi.js", "pixijs"]),
    ("A-Frame",               ["aframe.min.js", "aframe.js"]),
    ("Spline Runtime",        ["splinetool/runtime", "@splinetool"]),
    # UI / component
    ("Swiper",                ["swiper.min.js", "swiper.js", "swiper@"]),
    ("Alpine.js",             ["alpine.js", "alpinejs"]),
    ("HTMX",                  ["htmx.min.js", "htmx.js"]),
    ("Intersection Observer Polyfill", ["intersection-observer.js"]),
    # Video players
    ("Video.js",              ["video.min.js", "video.js", "videojs"]),
    ("Plyr",                  ["plyr.min.js", "plyr.js", "plyr@"]),
    ("HLS.js",                ["hls.min.js", "hls.js"]),
    # Frameworks (CDN-loaded)
    ("React",                 ["react.production.min.js", "react.development.js", "react@", "react-dom"]),
    ("Vue",                   ["vue.global.prod.js", "vue.global.js", "vue@", "vue.min.js"]),
    ("Angular",               ["angular.min.js", "angular.js", "@angular/"]),
    ("Svelte",                ["svelte@", "svelte/"]),
    ("jQuery",                ["jquery.min.js", "jquery.js", "jquery@", "jquery/"]),
    ("Tailwind CSS",          ["tailwindcss", "tailwind.min.css"]),
    ("Bootstrap",             ["bootstrap.min.js", "bootstrap.min.css", "bootstrap@"]),
]

# Framework patterns detected via CDN URL paths (separate from JS globals).
# These supplement the browser-side framework detection in extractor.py.
_CDN_FRAMEWORK_PATTERNS: list[tuple[str, list[str]]] = [
    ("Next.js",   ["_next/static", "_next/data", "_next/image"]),
    ("Nuxt",      ["_nuxt/", "__nuxt"]),
    ("Gatsby",    ["/page-data/", "/static/d/"]),
    ("Remix",     ["/build/", "__remix"]),
    ("Vite",      ["/@vite/", "/@fs/", ".vite/"]),
    ("Webpack",   ["webpack", "__webpack_"]),
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

    # Framework detection: merge browser-side detection + CDN URL patterns
    frameworks_from_js  = css_data.get("frameworks", [])
    frameworks_from_cdn = _detect_frameworks_from_cdn(network_entries)
    build_tools         = _detect_build_tools(network_entries)
    all_frameworks      = sorted(set(frameworks_from_js) | set(frameworks_from_cdn))

    # Media summary from extractor
    media = css_data.get("media", {})

    assets_data = {
        "detected_libraries": libs,
        "font_services":      fonts,
        "external_scripts":   scripts[:30],   # cap to keep prompt compact
        "cdn_origins":        cdns,
        "detected_frameworks": all_frameworks,
        "build_tools":        build_tools,
        "media":              media,
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


def _detect_frameworks_from_cdn(network_entries: list[dict]) -> list[str]:
    """Detect frameworks from URL path patterns in network requests."""
    found: set[str] = set()
    for entry in network_entries:
        url_lower = entry["url"].lower()
        for name, patterns in _CDN_FRAMEWORK_PATTERNS:
            if any(p.lower() in url_lower for p in patterns):
                found.add(name)
    return sorted(found)


def _detect_build_tools(network_entries: list[dict]) -> list[str]:
    """Detect build/bundler tools from URL patterns."""
    found: set[str] = set()
    for entry in network_entries:
        url = entry["url"]
        for name, patterns in _CDN_FRAMEWORK_PATTERNS:
            if name in ("Vite", "Webpack"):
                if any(p in url for p in patterns):
                    found.add(name)
    return sorted(found)


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
