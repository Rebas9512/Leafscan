"""
Markdown-to-PDF converter for LeafScan reports.

Uses the `markdown` library to render Markdown → HTML, then `weasyprint`
to produce a professionally styled PDF.  Optionally embeds page screenshots
at section breaks for visual context.

Usage:
    from .pdf import md_to_pdf
    pdf_path = md_to_pdf(report_md, output_dir / "report.pdf")
    pdf_path = md_to_pdf(report_md, out, screenshot_paths=frames)
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

import markdown


def md_to_pdf(
    md_text: str,
    output_path: Path,
    screenshot_paths: list[Path] | None = None,
) -> Path:
    """
    Convert a Markdown string to a styled PDF file.
    If *screenshot_paths* is provided, up to 3 page screenshots are embedded
    at evenly-spaced section breaks.  Returns the output Path.
    """
    from weasyprint import HTML

    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "codehilite", "toc"],
        extension_configs={
            "codehilite": {"css_class": "code"},
        },
    )

    if screenshot_paths:
        html_body = _inject_screenshots(html_body, screenshot_paths)

    full_html = _wrap_html(html_body)
    HTML(string=full_html).write_pdf(str(output_path))
    return output_path


# ── Screenshot injection ──────────────────────────────────────────────────────

def _inject_screenshots(
    html_body: str,
    screenshot_paths: list[Path],
    max_images: int = 3,
) -> str:
    """
    Insert evenly-spaced screenshot <figure> blocks into the HTML at
    section breaks.  Model-agnostic — runs after the LLM has already
    produced its Markdown.

    Looks for the best heading level to split on: tries <h2> first, then
    falls back to <h3> (some models use ### for top-level report sections).
    """
    sampled = _sample_screenshots(screenshot_paths, max_images)
    if not sampled:
        return html_body

    labels  = _frame_labels(len(sampled))
    figures = []
    for path, label in zip(sampled, labels):
        b64 = base64.standard_b64encode(path.read_bytes()).decode()
        figures.append(
            f'<figure class="screenshot">'
            f'<img src="data:image/png;base64,{b64}" alt="{label}">'
            f'<figcaption>{label}</figcaption>'
            f'</figure>'
        )

    # Find heading positions — try h2 first, fall back to h3
    heading_positions = _find_section_breaks(html_body)

    if len(heading_positions) < 2:
        # Too few sections — append all screenshots at the end
        return html_body + "\n" + "\n".join(figures)

    # Skip the first heading (don't break up the intro) and distribute
    # figures evenly among the remaining section boundaries.
    candidates = heading_positions[1:]
    n_figs  = len(figures)
    n_slots = len(candidates)

    if n_slots <= n_figs:
        chosen = list(range(n_slots))
    else:
        chosen = [
            round(i * (n_slots - 1) / max(n_figs - 1, 1))
            for i in range(n_figs)
        ]

    # Insert in reverse order so earlier positions stay valid
    for fig_idx, slot_idx in reversed(list(enumerate(chosen))):
        pos = candidates[slot_idx]
        html_body = html_body[:pos] + figures[fig_idx] + "\n" + html_body[pos:]

    return html_body


def _find_section_breaks(html: str) -> list[int]:
    """
    Return character positions of top-level section headings.
    Prefers <h2> tags; falls back to <h3> if fewer than 2 h2s exist.
    This handles the common case where different LLMs use different
    heading levels for their report structure.
    """
    h2 = [m.start() for m in re.finditer(r"<h2[\s>]", html)]
    if len(h2) >= 2:
        return h2
    h3 = [m.start() for m in re.finditer(r"<h3[\s>]", html)]
    if len(h3) >= 2:
        return h3
    # Last resort: merge whatever we found
    return sorted(h2 + h3)


def _sample_screenshots(paths: list[Path], n: int = 3) -> list[Path]:
    """Pick *n* evenly-spaced frames — always includes first and last."""
    if not paths:
        return []
    if len(paths) <= n:
        return list(paths)
    indices: set[int] = set()
    for i in range(n):
        indices.add(round(i * (len(paths) - 1) / (n - 1)))
    return [paths[i] for i in sorted(indices)]


def _frame_labels(count: int) -> list[str]:
    if count == 1:
        return ["Page screenshot"]
    if count == 2:
        return ["Top of page", "Bottom of page"]
    if count == 3:
        return ["Top of page", "Mid-page", "Bottom of page"]
    return [f"Screenshot {i + 1} of {count}" for i in range(count)]


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

/* ── Screenshots ───────────────────────────────────────────────────── */
figure.screenshot {
    text-align: center;
    margin: 1.8em 0;
    page-break-inside: avoid;
}

figure.screenshot img {
    max-width: 100%;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

figure.screenshot figcaption {
    font-size: 9pt;
    color: #888;
    margin-top: 0.4em;
    font-style: italic;
}
"""
