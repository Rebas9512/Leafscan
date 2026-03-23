"""
Markdown-to-PDF converter for LeafScan reports.

Uses the `markdown` library to render Markdown → HTML, then `weasyprint`
to produce a professionally styled PDF.

Usage:
    from .pdf import md_to_pdf
    pdf_path = md_to_pdf(report_md, output_dir / "report.pdf")
"""
from __future__ import annotations

from pathlib import Path

import markdown
from weasyprint import HTML


def md_to_pdf(md_text: str, output_path: Path) -> Path:
    """
    Convert a Markdown string to a styled PDF file.
    Returns the output Path.
    """
    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "codehilite", "toc"],
        extension_configs={
            "codehilite": {"css_class": "code"},
        },
    )

    full_html = _wrap_html(html_body)
    HTML(string=full_html).write_pdf(str(output_path))
    return output_path


# ── HTML template with print-optimised CSS ────────────────────────────────────

def _wrap_html(body: str) -> str:
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
{_CSS}
</style>
</head>
<body>
<article>
{body}
</article>
</body>
</html>"""


_CSS = """\
/* ── Page setup ─────────────────────────────────────────────────────── */
@page {
    size: A4;
    margin: 2cm 2.2cm;
    @bottom-center {
        content: counter(page);
        font-size: 9pt;
        color: #888;
    }
}

/* ── Base typography ────────────────────────────────────────────────── */
body {
    font-family: "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.65;
    color: #1a1a1a;
    background: #fff;
}

article {
    max-width: 100%;
}

/* ── Headings ───────────────────────────────────────────────────────── */
h1 {
    font-size: 22pt;
    font-weight: 700;
    color: #111;
    margin-top: 0;
    margin-bottom: 0.4em;
    padding-bottom: 0.3em;
    border-bottom: 2px solid #e0e0e0;
}

h2 {
    font-size: 16pt;
    font-weight: 700;
    color: #222;
    margin-top: 1.8em;
    margin-bottom: 0.4em;
    padding-bottom: 0.2em;
    border-bottom: 1px solid #eee;
    page-break-after: avoid;
}

h3 {
    font-size: 13pt;
    font-weight: 600;
    color: #333;
    margin-top: 1.4em;
    margin-bottom: 0.3em;
    page-break-after: avoid;
}

h4 {
    font-size: 11pt;
    font-weight: 600;
    color: #444;
    margin-top: 1.2em;
    margin-bottom: 0.2em;
    page-break-after: avoid;
}

/* ── Paragraphs & lists ─────────────────────────────────────────────── */
p {
    margin: 0.5em 0;
}

ul, ol {
    margin: 0.4em 0;
    padding-left: 1.5em;
}

li {
    margin-bottom: 0.2em;
}

/* ── Code blocks ────────────────────────────────────────────────────── */
code {
    font-family: "JetBrains Mono", "Fira Code", "Consolas", monospace;
    font-size: 9.5pt;
    background: #f5f5f5;
    padding: 0.15em 0.35em;
    border-radius: 3px;
}

pre {
    background: #f5f5f5;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 0.8em 1em;
    font-size: 9pt;
    line-height: 1.5;
    overflow-x: auto;
    page-break-inside: avoid;
}

pre code {
    background: none;
    padding: 0;
    border-radius: 0;
}

/* ── Tables ─────────────────────────────────────────────────────────── */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 0.8em 0;
    font-size: 10pt;
    page-break-inside: avoid;
}

th, td {
    border: 1px solid #ddd;
    padding: 0.4em 0.6em;
    text-align: left;
}

th {
    background: #f5f5f5;
    font-weight: 600;
}

tr:nth-child(even) {
    background: #fafafa;
}

/* ── Blockquotes ────────────────────────────────────────────────────── */
blockquote {
    border-left: 3px solid #ccc;
    margin: 0.8em 0;
    padding: 0.3em 1em;
    color: #555;
    background: #fafafa;
}

/* ── Horizontal rules ───────────────────────────────────────────────── */
hr {
    border: none;
    border-top: 1px solid #e0e0e0;
    margin: 1.5em 0;
}

/* ── Strong / emphasis ──────────────────────────────────────────────── */
strong {
    font-weight: 600;
    color: #111;
}

/* ── Links ──────────────────────────────────────────────────────────── */
a {
    color: #2563eb;
    text-decoration: none;
}
"""
