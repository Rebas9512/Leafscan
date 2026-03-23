# LeafScan

**LeafScan** extracts the design DNA from any public webpage. Give it a URL, get back a structured design report covering typography, color system, animation, layout strategy, and third-party dependencies.

It uses a headless browser to render the page, scrolls through to trigger lazy-loaded content and animations, extracts CSS data from the live DOM, and sends both the structured data and viewport screenshots to an LLM for analysis.

---

## Report showcase — linear.app

The following report was generated automatically by running `leafscan scan https://linear.app` with GPT-5.4 (vision mode, 12 scroll frames captured).

**Scroll-captured viewport samples:**

| Top of page | Mid-page | Bottom |
|:-----------:|:--------:|:------:|
| ![frame 1](screenshot/showcase_frame_01.png) | ![frame 6](screenshot/showcase_frame_06.png) | ![frame 12](screenshot/showcase_frame_12.png) |

<details>
<summary><b>Full generated report (click to expand)</b></summary>

### 1. Font System
- **Primary font family and source**
  - Data shows: primary UI font is `"Inter Variable", "SF Pro Display", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", sans-serif`.
  - Data shows: loaded font faces include `Inter Variable` with weight range `100 900`.
  - Data shows: no Google Fonts, Typekit, or other font services were detected.
  - Interpretation: `Inter Variable` appears to be self-hosted or bundled via the app rather than loaded from a third-party font CDN.

- **Heading weight(s), body weight(s)**
  - Data shows:
    - `h1`: `fontWeight: 510`
    - `h2`: `fontWeight: 510`
    - `[class*="heading"]`: `fontWeight: 510`
    - `h3`: `fontWeight: 590`
    - `body`: `fontWeight: 400`
    - `p`: `fontWeight: 400`
    - `a`: `fontWeight: 510`
    - `button`: `fontWeight: 400`
  - Interpretation: the system uses nuanced variable-font weights rather than standard 500/600/700 steps.

- **Base font size and line height**
  - Data shows:
    - `body`: `fontSize: 16px`, `lineHeight: 24px`
    - `p`: `fontSize: 15px`, `lineHeight: 24px`
  - Interpretation: body rhythm is relatively spacious, with a 1.5 line-height baseline.

- **Any variable font usage**
  - Data shows:
    - `Inter Variable` loaded with `weight: "100 900"`
    - `Berkeley Mono` loaded with `weight: "100 900"`
    - non-standard computed weights such as `510` and `590`
  - Interpretation: yes, variable font capabilities are actively used.

- **Notable typographic decisions**
  - Data shows:
    - `h1`: `64px / 64px`, `letterSpacing: -1.408px`
    - `h2`: `48px / 48px`, `letterSpacing: -1.056px`
    - `[class*="heading"]`: `72px / 72px`, `letterSpacing: -1.584px`
    - `p`: `letterSpacing: -0.165px`
    - `h3`: `letterSpacing: -0.24px`
    - `Berkeley Mono` is loaded.
  - Interpretation:
    - Tight line heights and negative tracking create a crisp, dense display style.
    - The mono face is likely used selectively for product UI/code-like content shown in the screenshots.
    - The typography feels precision-tuned for a premium SaaS/product audience.

### 2. Color System
- **Primary brand color**
  - Data shows:
    - `a`: `backgroundColor: rgb(94, 106, 210)` = `#5E6AD2`
  - Interpretation: `#5E6AD2` is the clearest brand/accent color surfaced in computed styles.

- **Background color(s)**
  - Data shows:
    - `body`: `backgroundColor: rgb(8, 9, 10)` = `#08090A`
    - `footer`: `backgroundColor: rgb(8, 9, 10)` = `#08090A`
  - Interpretation: the site is built on a near-black canvas with subtle tonal variation visible in screenshots.

- **Text color(s)**
  - Data shows:
    - `body`: `rgb(247, 248, 248)` = `#F7F8F8`
    - `h1`: `rgb(247, 248, 248)` = `#F7F8F8`
    - `h2`: `rgb(138, 143, 152)` = `#8A8F98`
    - `p`: `rgb(138, 143, 152)` = `#8A8F98`
    - `h3`: `rgb(208, 214, 224)` = `#D0D6E0`
    - `a`: `rgb(255, 255, 255)` = `#FFFFFF`
  - Interpretation: the palette uses strong contrast hierarchy: bright white for primary headlines, muted gray for body copy, and cooler light gray for tertiary headings.

- **Accent / highlight colors**
  - Data shows:
    - primary accent visible in computed styles: `#5E6AD2`
  - Interpretation:
    - Screenshots also show occasional warm/yellow and red/orange status accents inside product imagery, but those are visual observations rather than extracted system colors.
    - The main site chrome remains restrained, with accent color used sparingly.

- **Whether dark mode is present**
  - Data shows:
    - dark backgrounds dominate computed styles
    - no `prefers-color-scheme` data provided
    - no color CSS custom properties or dark-mode tokens were extracted
  - Interpretation: the current page is clearly dark-themed, but the provided data does not confirm a separate dark/light mode switch.

- **CSS custom property tokens related to color**
  - Data shows:
    - `css_vars: {}`
  - Interpretation: no color tokens were captured in the extraction, so token naming conventions cannot be documented from the provided data.

### 3. Animation & Motion
- **JS animation libraries detected and how they are loaded**
  - Data shows:
    - `animation_libraries: []`
    - `detected_libraries: []`
    - scripts are loaded from bundled Next.js chunks on `static.linear.app`
  - Interpretation: there is no evidence of GSAP, Framer Motion, AOS, or similar third-party animation libraries in the provided data; motion may be custom/CSS-driven and bundled.

- **@keyframes rules found**
  - Data shows:
    - a very large set of keyframes named like:
      - `grid-dot-*-*-agent`
      - `grid-dot-*-*-upDown`
      - `grid-dot-*-*-pong`
      - `grid-dot-*-*-empty-once`
    - these primarily animate `opacity`
    - additional keyframes:
      - `swipe-out-left/right/up/down`
      - `sonner-fade-in`, `sonner-fade-out`, `sonner-spin`
  - Interpretation:
    - the `grid-dot-*` animations likely drive decorative or illustrative dot-matrix/product-demo motion patterns.
    - `swipe-out-*` animate transform + opacity for dismiss/motion exits.
    - `sonner-*` are consistent with toast/notification UI animations.

- **Transition patterns**
  - Data shows transitions:
    - `transform 0.4s`
    - `transform 0.4s, opacity 0.4s, height 0.4s, box-shadow 0.2s`
    - `opacity 0.4s, box-shadow 0.2s`
    - `opacity 0.1s, background 0.2s, border-color 0.2s`
  - Interpretation:
    - dominant durations cluster around `0.2s–0.4s`.
    - this suggests a polished but controlled motion system emphasizing fades and gentle movement.

- **Scroll-triggered animation indicators**
  - Data shows: no ScrollTrigger, AOS, or other animation library detection.
  - Interpretation: scroll-linked behavior is visually suggested by the page's progressive product sections, but the provided technical data does not confirm the implementation.

- **Overall motion character**: **moderate** — rich and intentional, but not flashy.

### 4. Layout Strategy
- **Top-level layout approach**
  - Data shows:
    - `main`: `display: flex`, `flexDirection: column`
    - `nav`: `display: flex`, `alignItems: center`
    - `[class*="container"]`: `display: flex`, `flexDirection: column`
  - Interpretation: primarily Flexbox-driven top-level structure.

- **Notable layout patterns** (from screenshots):
  - persistent top navigation/header across scroll frames
  - repeated split-layout sections with large headline left / supporting copy right
  - full-bleed dark sections with embedded product panels
  - footer uses a multi-column link layout

### 5. Third-Party Dependencies
- **Font services**: none detected
- **CDN-loaded scripts**: Next.js bundled chunks from `static.linear.app`
- **Notable external origins**: `api.linear.app`, `constellation.linear.app`, `e.linear.app`, `static.linear.app`, `webassets.linear.app`

### 6. Design Style Summary
The design language is highly refined, minimal, and technical — closer to a premium product brand than a marketing-heavy SaaS site. The near-black palette, precise variable-font weights, tight display typography, and restrained violet accent create a calm, confident mood aimed at design-conscious product and engineering teams. The most distinctive decision is the fusion of austere editorial layout with dense, animated product visuals, which makes the interface itself feel like the brand.

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
```

Output is saved to `outputs/{domain}_{timestamp}/`:

```
outputs/linear.app_20260323_014056/
├── frame_01.png ~ frame_12.png   # Scroll-captured viewport screenshots
├── css.json                       # Raw CSS extraction data
├── network.json                   # Network request log
├── assets.json                    # Aggregated libraries, fonts, CDN origins
└── report.md                      # LLM-generated design analysis report
```

---

## CLI reference

| Command | What it does |
|---------|-------------|
| `leafscan scan <url>` | Scan a URL and generate a design report |
| `leafscan scan <url> --alias <name>` | Scan using a specific LeafHub model alias |
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
             │ css.json   │  fonts, colors, keyframes, transitions, layout
             │ assets.json│  detected libraries, font services, CDN origins
             │ frame_*.png│  scroll-captured viewport screenshots
             └─────┬──────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│  Step 3: Aggregate                           │
│  Merge network data + extractor output.      │
│  Identify bundled libraries from CDN URLs    │
│  and global variables.                       │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│  Step 4: LLM Report                          │
│  Sample ≤8 key frames from the scroll,       │
│  send structured CSS data + screenshots to   │
│  the LLM, receive Markdown design report.    │
│                                              │
│  Adapts automatically:                       │
│    vision model → screenshots + data         │
│    text-only model → data only               │
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
| linear.app | SaaS landing page | 12 | Inter Variable, 607 keyframes, custom grid-dot animations |
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
│   ├── pipeline.py       # Orchestration: probe → scrape → aggregate → report
│   └── cli.py            # CLI entry point
│
├── prompts/
│   └── design_report.txt # LLM system prompt
│
├── tests/
│   ├── smoke_e2e.py      # End-to-end smoke test
│   ├── test_model.py     # Capability probe tests
│   ├── test_reporter.py  # Payload builder + API adapter tests
│   ├── test_aggregator.py# Library / font detection tests
│   └── test_extractor.py # CSS data parser tests
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
