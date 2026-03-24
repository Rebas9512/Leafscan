"""Tests for leafscan.pdf — Markdown-to-PDF converter."""
from __future__ import annotations

import pytest
from pathlib import Path

from leafscan.pdf import (
    md_to_pdf,
    _wrap_html,
    _inject_screenshots,
    _find_section_breaks,
    _sample_screenshots,
    _frame_labels,
)

_has_weasyprint = True
try:
    import weasyprint  # noqa: F401
except (ImportError, OSError):
    _has_weasyprint = False

needs_weasyprint = pytest.mark.skipif(
    not _has_weasyprint,
    reason="weasyprint not available (requires system GTK/Pango libraries)",
)


# ── HTML wrapping ─────────────────────────────────────────────────────────────

class TestWrapHtml:
    def test_wraps_with_html_skeleton(self):
        html = _wrap_html("<p>hello</p>")
        assert "<!DOCTYPE html>" in html
        assert "<article>" in html
        assert "<p>hello</p>" in html
        assert "</article>" in html

    def test_includes_css(self):
        html = _wrap_html("")
        assert "@page" in html
        assert "font-family" in html

    def test_screenshot_css_included(self):
        html = _wrap_html("")
        assert "figure.screenshot" in html


# ── Screenshot helpers ────────────────────────────────────────────────────────

class TestSampleScreenshots:
    def _make_pngs(self, tmp_path: Path, n: int) -> list[Path]:
        """Create n tiny PNG-like files for testing."""
        paths = []
        for i in range(n):
            p = tmp_path / f"frame_{i+1:02d}.png"
            p.write_bytes(b"\x89PNG" + bytes([i]) * 16)
            paths.append(p)
        return paths

    def test_empty(self):
        assert _sample_screenshots([], 3) == []

    def test_fewer_than_n(self, tmp_path: Path):
        paths = self._make_pngs(tmp_path, 2)
        assert _sample_screenshots(paths, 3) == paths

    def test_exact_n(self, tmp_path: Path):
        paths = self._make_pngs(tmp_path, 3)
        assert _sample_screenshots(paths, 3) == paths

    def test_samples_first_mid_last(self, tmp_path: Path):
        paths = self._make_pngs(tmp_path, 10)
        sampled = _sample_screenshots(paths, 3)
        assert len(sampled) == 3
        assert sampled[0] == paths[0]
        assert sampled[-1] == paths[-1]


class TestFrameLabels:
    def test_single(self):
        assert _frame_labels(1) == ["Page screenshot"]

    def test_three(self):
        labels = _frame_labels(3)
        assert labels[0] == "Top of page"
        assert labels[1] == "Mid-page"
        assert labels[2] == "Bottom of page"


class TestFindSectionBreaks:
    def test_prefers_h2(self):
        html = "<h2>A</h2><h3>B</h3><h2>C</h2><h3>D</h3>"
        breaks = _find_section_breaks(html)
        # Should return h2 positions only
        assert len(breaks) == 2
        assert all(html[pos:pos+3] == "<h2" for pos in breaks)

    def test_falls_back_to_h3(self):
        html = "<h3>A</h3><p>text</p><h3>B</h3><p>more</p><h3>C</h3>"
        breaks = _find_section_breaks(html)
        assert len(breaks) == 3
        assert all(html[pos:pos+3] == "<h3" for pos in breaks)

    def test_single_h2_merges_with_h3(self):
        html = "<h2>Title</h2><h3>A</h3>"
        breaks = _find_section_breaks(html)
        assert len(breaks) == 2


class TestInjectScreenshots:
    def _make_pngs(self, tmp_path: Path, n: int) -> list[Path]:
        paths = []
        for i in range(n):
            p = tmp_path / f"frame_{i+1:02d}.png"
            p.write_bytes(b"\x89PNG" + bytes([i]) * 16)
            paths.append(p)
        return paths

    def test_no_screenshots_returns_unchanged(self):
        html = "<h1>Title</h1><h2>A</h2><p>text</p>"
        assert _inject_screenshots(html, []) == html

    def test_inserts_figures_with_img_tags(self, tmp_path: Path):
        paths = self._make_pngs(tmp_path, 3)
        html = "<h1>Title</h1><h2>A</h2><p>a</p><h2>B</h2><p>b</p><h2>C</h2><p>c</p><h2>D</h2><p>d</p>"
        result = _inject_screenshots(html, paths)
        assert result.count("<figure") == 3
        assert result.count("data:image/png;base64,") == 3
        assert "Top of page" in result
        assert "Mid-page" in result
        assert "Bottom of page" in result

    def test_few_h2_appends_at_end(self, tmp_path: Path):
        paths = self._make_pngs(tmp_path, 2)
        html = "<h1>Title</h1><h2>Only</h2><p>text</p>"
        result = _inject_screenshots(html, paths)
        # Figures appended at the end since only 1 h2
        assert result.startswith(html)
        assert result.count("<figure") == 2

    def test_h3_fallback_distributes_figures(self, tmp_path: Path):
        """When the LLM uses ### for sections, screenshots should still
        be distributed at section breaks, not dumped at the end."""
        paths = self._make_pngs(tmp_path, 3)
        html = "<h3>A</h3><p>a</p><h3>B</h3><p>b</p><h3>C</h3><p>c</p><h3>D</h3><p>d</p>"
        result = _inject_screenshots(html, paths)
        assert result.count("<figure") == 3
        # Figures should be interleaved, not all at the end
        last_figure_pos = result.rfind("<figure")
        last_h3_pos = result.rfind("<h3")
        assert last_figure_pos < last_h3_pos


# ── PDF generation ────────────────────────────────────────────────────────────

@needs_weasyprint
class TestMdToPdf:
    def test_generates_pdf_file(self, tmp_path: Path):
        md = "# Test Report\n\nHello **world**.\n\n- item 1\n- item 2\n"
        out = tmp_path / "report.pdf"
        result = md_to_pdf(md, out)

        assert result is not None
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 0
        # PDF magic bytes
        assert out.read_bytes()[:5] == b"%PDF-"

    def test_supports_tables(self, tmp_path: Path):
        md = "| A | B |\n|---|---|\n| 1 | 2 |\n"
        out = tmp_path / "table.pdf"
        result = md_to_pdf(md, out)
        assert result is not None
        assert out.exists()

    def test_supports_fenced_code(self, tmp_path: Path):
        md = "```python\nprint('hello')\n```\n"
        out = tmp_path / "code.pdf"
        result = md_to_pdf(md, out)
        assert result is not None
        assert out.exists()
