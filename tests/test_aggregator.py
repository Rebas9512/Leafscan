"""Tests for leafscan.aggregator — library detection and data merging."""
from __future__ import annotations

from leafscan.aggregator import (
    aggregate,
    _detect_libraries,
    _detect_font_services,
    _detect_frameworks_from_cdn,
    _detect_build_tools,
)


# ── Library detection ──────────────────────────────────────────────────────────

class TestDetectLibraries:
    def test_gsap_from_cdn(self):
        entries = [{"url": "https://cdn.jsdelivr.net/npm/gsap@3.12/gsap.min.js", "resource_type": "script"}]
        libs = _detect_libraries(entries, [])
        assert "GSAP" in libs

    def test_gsap_scrolltrigger(self):
        entries = [{"url": "https://cdn.example.com/ScrollTrigger.min.js", "resource_type": "script"}]
        libs = _detect_libraries(entries, [])
        assert "GSAP ScrollTrigger" in libs

    def test_globals_override(self):
        """Libraries detected via window globals (bundled, not CDN)."""
        libs = _detect_libraries([], ["Three.js", "GSAP"])
        assert "Three.js" in libs
        assert "GSAP" in libs

    def test_dedup_cdn_and_globals(self):
        """Same library from CDN and globals should appear only once."""
        entries = [{"url": "https://cdn.example.com/gsap.min.js", "resource_type": "script"}]
        libs = _detect_libraries(entries, ["GSAP"])
        assert libs.count("GSAP") == 1

    def test_no_false_positives(self):
        entries = [{"url": "https://example.com/main.js", "resource_type": "script"}]
        libs = _detect_libraries(entries, [])
        assert libs == []

    def test_lottie_detection(self):
        entries = [{"url": "https://unpkg.com/lottie-web@5.12/lottie.min.js", "resource_type": "script"}]
        libs = _detect_libraries(entries, [])
        assert "Lottie" in libs

    def test_case_insensitive(self):
        entries = [{"url": "https://cdn.example.com/GSAP.MIN.JS", "resource_type": "script"}]
        libs = _detect_libraries(entries, [])
        assert "GSAP" in libs


# ── Font service detection ─────────────────────────────────────────────────────

class TestDetectFontServices:
    def test_google_fonts(self):
        entries = [
            {"url": "https://fonts.googleapis.com/css2?family=Inter", "resource_type": "stylesheet"},
            {"url": "https://fonts.gstatic.com/s/inter/v13/font.woff2", "resource_type": "font"},
        ]
        fonts = _detect_font_services(entries)
        labels = {f["service"] for f in fonts}
        assert "Google Fonts" in labels
        assert "Google Fonts (static)" in labels

    def test_typekit(self):
        entries = [{"url": "https://use.typekit.net/abc123.css", "resource_type": "stylesheet"}]
        fonts = _detect_font_services(entries)
        assert fonts[0]["service"] == "Adobe Fonts (Typekit)"

    def test_no_font_service(self):
        entries = [{"url": "https://example.com/style.css", "resource_type": "stylesheet"}]
        fonts = _detect_font_services(entries)
        assert fonts == []


# ── Full aggregate ─────────────────────────────────────────────────────────────

class TestAggregate:
    def test_returns_assets_data(self):
        css_data = {"globals": ["GSAP"]}
        network = [
            {"url": "https://fonts.googleapis.com/css2?family=Inter", "resource_type": "stylesheet"},
            {"url": "https://example.com/main.js", "resource_type": "script"},
        ]
        assets = aggregate(css_data, network)

        assert "detected_libraries" in assets
        assert "font_services" in assets
        assert "external_scripts" in assets
        assert "cdn_origins" in assets

    def test_detected_libraries_in_assets(self):
        css_data = {"globals": ["Three.js"]}
        network = [{"url": "https://cdn.example.com/gsap.min.js", "resource_type": "script"}]
        assets = aggregate(css_data, network)

        assert "detected_libraries" in assets
        assert "GSAP" in assets["detected_libraries"]
        assert "Three.js" in assets["detected_libraries"]

    def test_does_not_mutate_css_data(self):
        css_data = {"globals": ["GSAP"]}
        network = []
        aggregate(css_data, network)
        assert "detected_libraries" not in css_data

    def test_aggregate_includes_frameworks_and_media(self):
        css_data = {
            "globals": [],
            "frameworks": ["Vue", "Nuxt"],
            "media": {"video": [], "canvas": [], "webgl": False, "iframe_embeds": []},
        }
        network = [{"url": "https://example.com/_nuxt/chunk.js", "resource_type": "script"}]
        assets = aggregate(css_data, network)

        assert "detected_frameworks" in assets
        assert "Nuxt" in assets["detected_frameworks"]
        assert "Vue" in assets["detected_frameworks"]
        assert "build_tools" in assets
        assert "media" in assets

    def test_framework_dedup_browser_and_cdn(self):
        """Same framework detected via browser JS and CDN URL should appear only once."""
        css_data = {"globals": [], "frameworks": ["Next.js"]}
        network = [{"url": "https://example.com/_next/static/chunks/main.js", "resource_type": "script"}]
        assets = aggregate(css_data, network)
        assert assets["detected_frameworks"].count("Next.js") == 1


# ── CDN framework detection ──────────────────────────────────────────────────

class TestDetectFrameworksFromCDN:
    def test_nextjs(self):
        entries = [{"url": "https://example.com/_next/static/chunks/main.js", "resource_type": "script"}]
        assert "Next.js" in _detect_frameworks_from_cdn(entries)

    def test_nuxt(self):
        entries = [{"url": "https://example.com/_nuxt/entry.js", "resource_type": "script"}]
        assert "Nuxt" in _detect_frameworks_from_cdn(entries)

    def test_gatsby(self):
        entries = [{"url": "https://example.com/page-data/index/page-data.json", "resource_type": "fetch"}]
        assert "Gatsby" in _detect_frameworks_from_cdn(entries)

    def test_vite(self):
        entries = [{"url": "https://example.com/@vite/client", "resource_type": "script"}]
        assert "Vite" in _detect_frameworks_from_cdn(entries)

    def test_no_false_positives(self):
        entries = [{"url": "https://example.com/app.js", "resource_type": "script"}]
        assert _detect_frameworks_from_cdn(entries) == []


# ── Build tool detection ──────────────────────────────────────────────────────

class TestDetectBuildTools:
    def test_vite(self):
        entries = [{"url": "https://example.com/@vite/client", "resource_type": "script"}]
        assert "Vite" in _detect_build_tools(entries)

    def test_webpack(self):
        entries = [{"url": "https://example.com/static/js/__webpack_require__.js", "resource_type": "script"}]
        assert "Webpack" in _detect_build_tools(entries)

    def test_no_false_positives(self):
        entries = [{"url": "https://example.com/main.js", "resource_type": "script"}]
        assert _detect_build_tools(entries) == []
