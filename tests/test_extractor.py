"""Tests for leafscan.extractor — parse_raw data cleaning."""
from __future__ import annotations

from leafscan.extractor import parse_raw


# ── parse_raw ──────────────────────────────────────────────────────────────────

class TestParseRaw:
    def test_empty_input(self):
        result = parse_raw({})
        assert result["fonts"] == []
        assert result["typography"] == {}
        assert result["css_vars"] == {}
        assert result["keyframes"] == []
        assert result["transitions"] == []
        assert result["layout"] == {}
        assert result["globals"] == []

    def test_font_dedup(self):
        raw = {"fonts_api": [
            {"family": "Inter", "weight": "400", "style": "normal", "stretch": "", "status": "loaded"},
            {"family": "Inter", "weight": "400", "style": "normal", "stretch": "", "status": "loaded"},
            {"family": "Inter", "weight": "700", "style": "normal", "stretch": "", "status": "loaded"},
        ]}
        result = parse_raw(raw)
        assert len(result["fonts"]) == 2

    def test_typography_noise_removal(self):
        """Entries with only noise values should be dropped."""
        raw = {"typography": {
            "body":   {"fontFamily": "Inter", "fontSize": "16px", "color": "rgb(0,0,0)"},
            "footer": {"fontFamily": "", "fontSize": "normal", "color": "none"},
        }}
        result = parse_raw(raw)
        assert "body" in result["typography"]
        assert "footer" not in result["typography"]

    def test_layout_noise_removal(self):
        raw = {"layout": {
            "main": {"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "20px"},
            "nav":  {"display": "flex", "flexDirection": "row", "flexWrap": "nowrap", "gap": "0px"},
        }}
        result = parse_raw(raw)
        assert "main" in result["layout"]
        # nav has only noise values after removing defaults
        assert "display" in result["layout"].get("nav", {}) or "nav" not in result["layout"]

    def test_transition_dedup(self):
        raw = {"transitions": [
            "opacity 0.3s ease",
            "opacity 0.3s ease",
            "transform 0.5s ease-in-out",
        ]}
        result = parse_raw(raw)
        assert len(result["transitions"]) == 2

    def test_globals_passthrough(self):
        raw = {"globals": ["GSAP", "Three.js"]}
        result = parse_raw(raw)
        assert result["globals"] == ["GSAP", "Three.js"]

    def test_css_vars_passthrough(self):
        raw = {"css_vars": {"--primary": "#5E6AD2", "--bg": "#0F0F0F"}}
        result = parse_raw(raw)
        assert result["css_vars"]["--primary"] == "#5E6AD2"

    def test_keyframes_passthrough(self):
        raw = {"keyframes": [{"name": "fadeIn", "cssText": "@keyframes fadeIn { ... }"}]}
        result = parse_raw(raw)
        assert result["keyframes"][0]["name"] == "fadeIn"

    def test_frameworks_passthrough(self):
        raw = {"frameworks": ["React", "Next.js"]}
        result = parse_raw(raw)
        assert result["frameworks"] == ["React", "Next.js"]

    def test_frameworks_empty_default(self):
        result = parse_raw({})
        assert result["frameworks"] == []

    def test_media_passthrough(self):
        raw = {"media": {
            "video": [{"src": "bg.mp4", "autoplay": True}],
            "canvas": [{"width": 1440, "height": 900, "context": "webgl2"}],
            "webgl": True,
            "iframe_embeds": [{"service": "YouTube", "src": "https://youtube.com/embed/x"}],
        }}
        result = parse_raw(raw)
        assert result["media"]["webgl"] is True
        assert len(result["media"]["video"]) == 1
        assert result["media"]["canvas"][0]["context"] == "webgl2"
        assert result["media"]["iframe_embeds"][0]["service"] == "YouTube"

    def test_media_empty_default(self):
        result = parse_raw({})
        assert result["media"] == {}
