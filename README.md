# LeafScan

**LeafScan** extracts the design DNA from any public webpage. Give it a URL, get back a structured design report covering typography, color system, animation, layout strategy, third-party dependencies, and a full **architecture reproduction blueprint**.

It uses a headless browser to render the page, scrolls through to trigger lazy-loaded content and animations, extracts CSS data from the live DOM, detects frontend frameworks and media elements, and sends both the structured data and viewport screenshots to an LLM for analysis. Reports are generated in both **Markdown** and **PDF** formats.

---

## Report showcase — linear.app

The following report was generated automatically by running `leafscan scan https://linear.app` with GPT-5.4 (vision mode, 12 scroll frames captured).

**Scroll-captured viewport samples:**

| Top of page | Mid-page | Bottom |
|:-----------:|:--------:|:------:|
| ![frame 1](screenshot/showcase_frame_01.png) | ![frame 6](screenshot/showcase_frame_06.png) | ![frame 12](screenshot/showcase_frame_12.png) |

<details>
<summary><b>Full generated report (click to expand)</b></summary>

<!-- auto-generated from outputs/linear.app_20260323_214857/report.md -->

### 1. Font System
- **Data shows:** The primary font is `"Inter Variable"` with fallbacks `"SF Pro Display", -apple-system, ... sans-serif`.
- **Data shows:** `Inter Variable` is loaded with a weight range of `"100 900"`, indicating variable font usage.
- **Data shows:** `Berkeley Mono` is also loaded with weight range `"100 900"`.
- **Data shows:** Body text uses `fontSize: 16px`, `fontWeight: 400`, `lineHeight: 24px`.
- **Data shows:** `h1` uses `fontSize: 64px`, `fontWeight: 510`, `letterSpacing: -1.408px`.
- **Data shows:** `[class*="heading"]` reaches `fontSize: 72px`, `fontWeight: 510`.
- **Data shows:** No Google Fonts, Typekit, or external font service was detected.
- **Interpretation:** Variable-weight midpoints like `510` and `590` give headings a refined, slightly denser feel than standard steps.

### 2. Color System
- **Data shows:** Body/background: `#08090A`. Primary text: `#F7F8F8`. Secondary: `#8A8F98`.
- **Data shows:** Brand accent: `#5E6AD2` (link backgrounds).
- **Interpretation:** Restrained dark theme with layered grays and a violet accent used sparingly.

### 3. Animation & Motion
- **Data shows:** No JS animation libraries detected. Hundreds of `grid-dot-*` keyframes animate opacity. Transitions cluster around `0.2s–0.4s`.
- **Interpretation:** Motion is moderate — polished and CSS-driven, not library-dependent.

### 4. Layout Strategy
- **Data shows:** Flexbox-dominant (`main`, `nav`, `[class*="container"]`). Persistent header, split hero/content rows, product showcase cards, multi-column footer.

### 5. Third-Party Dependencies
- **Data shows:** Next.js bundled chunks from `static.linear.app`. Detected: Next.js framework, Webpack build tool.
- **Data shows:** External origins: `api.linear.app`, `constellation.linear.app`, `static.linear.app`, `webassets.linear.app`.

### 6. Design Style Summary
Premium, high-discipline SaaS aesthetic: dark, quiet, product-first. The brand turns real product UI into the visual system itself.

### 7. Architecture & Reproduction Blueprint
- **Detected:** Next.js + Webpack, no CSS framework explicitly detected
- **Recommended stack:** React + Next.js, CSS Modules + design tokens, minimal global state
- **Component breakdown:** ~25–40 unique components including `<HeroSection>`, `<StorySection>`, `<ProductShowcasePanel>`, `<ChangelogSection>`, `<Footer>`
- **Media:** No video, canvas, WebGL, or iframe embeds — product mockups are DOM/image-based
- **Complexity:** High — challenges include dark-theme contrast discipline, responsive product mockups, and sequenced dot/grid animations
- **Build priority:** foundations → hero + story sections → product showcase panels → changelog → motion polish

</details>

---

## Requirements

| Requirement | Notes |
|-------------|-------|
| Python 3.11+ | 3.12 recommended |
| **LeafHub** | API key management — install first (see below) |
| Internet connection | For page scraping and LLM API calls |

LeafScan uses **[LeafHub](https://github.com/Rebas9512/Leafhub)** for encrypted API key management. LeafHub must be installed and configured before you can run LeafScan. Head to the LeafHub repo to install it and add your provider credentials.

LeafScan supports three API backends:

| Backend | LeafHub `api_format` | Notes |
|---------|---------------------|-------|
| OpenAI Chat Completions | `openai-completions` | OpenAI, Groq, vLLM, any OpenAI-compatible endpoint |
| OpenAI Responses API | `openai-responses` | ChatGPT Codex endpoint — uses subscription quota, not API credits |
| Anthropic Messages | `anthropic-messages` | Anthropic, MiniMax (Anthropic-compatible) |

**Using your ChatGPT subscription** — run `leafhub provider login --name codex` to authenticate via OAuth. No API key needed; tokens auto-refresh on every request.

---

## Install

**macOS / Linux / WSL**

```bash
curl -fsSL https://raw.githubusercontent.com/Rebas9512/Leafscan/main/install.sh | bash
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/Rebas9512/Leafscan/main/install.ps1 | iex
```

**Windows (CMD)**

```cmd
curl -fsSL https://raw.githubusercontent.com/Rebas9512/Leafscan/main/install.cmd -o install.cmd && install.cmd && del install.cmd
```

The installer clones the repo, creates an isolated virtual environment, installs Playwright + Chromium, and registers the `leafscan` command on your PATH.


---

## Configure

LeafScan reads API credentials from LeafHub at startup. After installing LeafHub and adding a provider, link LeafScan to it:

```bash
leafhub register leafscan --path <leafscan-install-dir> --alias llm
```

Or let the setup script handle it automatically:

```bash
./setup.sh
```

`leafscan setup` can also be used at any time to verify or auto-repair the LeafHub binding.

To switch providers or add a second model, update them in LeafHub — no changes to LeafScan needed:

```bash
leafhub manage                                                # Web UI
leafhub project bind leafscan --alias minimax --provider "MiniMax"  # Add second model
```

---

## Run

```bash
# Scan a website
leafscan scan https://linear.app

# Use a specific model alias
leafscan scan https://linear.app --alias minimax

# Skip PDF generation (Markdown only)
leafscan scan https://linear.app --no-pdf
```

Output is saved to `outputs/{domain}_{timestamp}/`:

```
outputs/linear.app_20260323_214857/
├── frame_01.png ~ frame_12.png   # Scroll-captured viewport screenshots
├── css.json                       # Raw CSS extraction data
├── network.json                   # Network request log
├── assets.json                    # Aggregated libraries, fonts, CDN origins
├── report.md                      # LLM-generated design analysis report
└── report.pdf                     # PDF version of the report (optional)
```

---

## CLI reference

| Command | What it does |
|---------|-------------|
| `leafscan scan <url>` | Scan a URL and generate a design report (MD + PDF) |
| `leafscan scan <url> --alias <name>` | Scan using a specific LeafHub model alias |
| `leafscan scan <url> --no-pdf` | Scan without generating the PDF report |
| `leafscan setup` | Verify and repair LeafHub credential binding |
| `leafscan clean` | Remove all generated outputs |
| `leafscan clean -y` | Remove outputs without confirmation |

---

## How the pipeline works

```
URL
 │
 ▼
┌──────────────────────────────────────────────┐
│  Step 0: Model Resolution + Capability Probe │
│  Connect to LeafHub, send a test image to    │
│  determine if the model supports vision.     │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│  Step 1+2: Scrape + Extract                  │
│  Playwright renders the page, auto-dismisses │
│  cookie banners, scrolls top-to-bottom       │
│  (DOM scroll or wheel events for WebGL),     │
│  captures viewport screenshots at each stop, │
│  then runs JS extraction on the fully        │
│  rendered DOM.                               │
└──────────────────┬───────────────────────────┘
                   │  produces
             ┌─────┴──────┐
             │ css.json   │  fonts, colors, keyframes, transitions, layout,
             │            │  detected frameworks, media elements
             │ assets.json│  detected libraries, font services, CDN origins,
             │            │  frameworks, build tools, media summary
             │ frame_*.png│  scroll-captured viewport screenshots
             └─────┬──────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│  Step 3: Aggregate                           │
│  Merge network data + extractor output.      │
│  Identify libraries, frameworks, build tools │
│  from CDN URLs, global variables, and DOM.   │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│  Step 4: LLM Report                          │
│  Sample ≤8 key frames from the scroll,       │
│  send structured CSS data + architecture     │
│  signals + screenshots to the LLM.           │
│  Receive Markdown design report with         │
│  architecture reproduction blueprint.        │
│                                              │
│  Adapts automatically:                       │
│    vision model → screenshots + data         │
│    text-only model → data only               │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│  Step 5: PDF Export (optional)               │
│  Convert Markdown report to styled PDF.      │
│  Skip with --no-pdf or if deps not installed.│
└──────────────────────────────────────────────┘
```

### Scroll capture strategies

| Page type | Detection | Strategy |
|-----------|-----------|----------|
| Normal scrollable page | `scrollHeight > viewport + 100px` | DOM `scrollTo` in viewport steps, capture at each stop |
| WebGL / canvas site | `scrollHeight ≈ viewport` | Synthetic wheel events to drive Three.js / custom scroll handlers |

Cookie consent banners (OneTrust, TrustArc, CookieBot, etc.) are auto-dismissed before capture, including banners rendered inside iframes.

### Model capability probe

At pipeline start, a small test image is sent to the model. If accepted → vision mode (screenshots + data). If rejected → text-only mode (data only). This happens automatically — no configuration needed.

---

## Tested sites

| Site | Type | Frames | Key findings |
|------|------|--------|-------------|
| linear.app | SaaS landing page | 12 | Next.js + Webpack detected, Inter Variable, 607 keyframes, grid-dot animations |
| giellygreen.co.uk | Luxury beauty e-commerce | 12 | Vue + Nuxt detected, Prismic CMS + Shopify, Swiper, self-hosted fonts |
| nippori.lamm.tokyo | Editorial podcast site | 18 | WordPress + Remix detected, 7 self-hosted videos, Typekit + Google Fonts |
| ironhill.au | Premium brand microsite | 19 | Vue + Nuxt detected, WebGL2 canvas, 3 autoplay videos, self-hosted fonts |
| memorial.fcporto.pt | Video / narrative memorial | 30 | GSAP + ScrollTrigger + Lenis (bundled), Astro build |
| good-fella.com | Creative studio portfolio | 9 | Typekit fonts, 12-column grid, Next.js/Turbopack |
| d2c-lifescience.com | 3D life science | 30 | Custom 3D rendering, Prismic CMS, Astro build |
| cornrevolution.resn.global | WebGL experience | 9 | Three.js detected via global, wheel-event scroll capture |
| bruno-simon.com | Interactive 3D game | 9 | Rapier physics engine, Google Fonts, game-first layout |

---

## Project structure

```
Leafscan/
├── leafscan/
│   ├── __init__.py
│   ├── model.py          # LeafHub resolution + capability probe
│   ├── scraper.py        # Playwright: navigate, cookie dismiss, scroll, capture
│   ├── extractor.py      # Browser-side JS extraction + Python parser
│   ├── aggregator.py     # Library detection, font service matching, data merge
│   ├── reporter.py       # LLM call with api_format adapters
│   ├── pdf.py            # Markdown → PDF conversion (optional deps)
│   ├── pipeline.py       # Orchestration: probe → scrape → aggregate → report → PDF
│   └── cli.py            # CLI entry point
│
├── prompts/
│   └── design_report.txt # LLM system prompt
│
├── tests/
│   ├── smoke_e2e.py      # End-to-end smoke test
│   ├── test_model.py     # Capability probe tests
│   ├── test_reporter.py  # Payload builder + API adapter tests
│   ├── test_aggregator.py# Library / font / framework detection tests
│   ├── test_extractor.py # CSS data parser tests
│   └── test_pdf.py       # PDF converter tests
│
├── outputs/              # Generated reports (git-ignored)
├── leafhub_dist/         # LeafHub integration module (auto-generated)
├── pyproject.toml
├── setup.sh
└── install.sh / install.ps1 / install.cmd
```

## Acknowledgements

- [**LeafHub**](https://github.com/Rebas9512/Leafhub) — local encrypted API key vault, required for credential management
- [**Playwright**](https://playwright.dev/) — headless browser automation
