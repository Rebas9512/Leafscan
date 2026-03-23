"""Tests for leafscan.pdf — Markdown-to-PDF converter."""
from __future__ import annotations

import pytest
from pathlib import Path

from leafscan.pdf import md_to_pdf, _wrap_html


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


# ── PDF generation ────────────────────────────────────────────────────────────

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
