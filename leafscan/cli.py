"""
CLI entry point.

Commands:
  leafscan scan <url>   — run the full pipeline
  leafscan setup        — verify/repair Leafhub credential binding
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

_ROOT  = Path(__file__).resolve().parent.parent


def _get_default_alias() -> str:
    """Read the primary alias from leafhub.toml, fall back to 'llm'."""
    try:
        from leafhub_sdk.manifest import get_default_alias
        return get_default_alias(project_dir=_ROOT, fallback="llm")
    except ImportError:
        pass
    return "llm"

_ALIAS = _get_default_alias()


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="leafscan",
        description="Extract design DNA from any public webpage.",
    )
    sub = parser.add_subparsers(dest="cmd", metavar="<command>")

    # scan
    scan_p = sub.add_parser("scan", help="Scan a URL and generate a design report")
    scan_p.add_argument("url", help="Public URL to analyse")
    scan_p.add_argument("--alias", default=_ALIAS,
                        help=f"Leafhub alias to use (default: {_ALIAS})")
    scan_p.add_argument("--no-pdf", action="store_true",
                        help="Skip PDF generation (only produce report.md)")

    # setup
    sub.add_parser("setup", help="Verify and repair Leafhub credential binding")

    # clean
    clean_p = sub.add_parser("clean", help="Remove all generated outputs")
    clean_p.add_argument("--yes", "-y", action="store_true",
                         help="Skip confirmation prompt")

    args = parser.parse_args()

    if args.cmd == "scan":
        _cmd_scan(args.url, alias=args.alias, pdf=not args.no_pdf)
    elif args.cmd == "setup":
        _cmd_setup()
    elif args.cmd == "clean":
        _cmd_clean(yes=args.yes)
    else:
        parser.print_help()
        sys.exit(0)


# ── clean ─────────────────────────────────────────────────────────────────────

def _cmd_clean(yes: bool = False) -> None:
    """Remove all generated output directories."""
    outputs_dir = _ROOT / "outputs"
    if not outputs_dir.is_dir():
        print("Nothing to clean — outputs/ does not exist.")
        return

    entries = sorted(p for p in outputs_dir.iterdir() if p.is_dir())
    if not entries:
        print("Nothing to clean — outputs/ is empty.")
        return

    total_mb = sum(
        f.stat().st_size for d in entries for f in d.rglob("*") if f.is_file()
    ) / (1024 * 1024)
    print(f"Found {len(entries)} output(s) ({total_mb:.1f} MB)")

    if not yes:
        try:
            ans = input("Delete all? [y/N] ").strip().lower()
        except EOFError:
            ans = ""
        if ans not in ("y", "yes"):
            print("Cancelled.")
            return

    for d in entries:
        shutil.rmtree(d)
    print(f"Removed {len(entries)} output(s).")


# ── scan ──────────────────────────────────────────────────────────────────────

def _cmd_scan(url: str, alias: str = "llm", pdf: bool = True) -> None:
    from .pipeline import run
    try:
        report_path = run(url, alias=alias, pdf=pdf)
        print(f"\nReport saved to: {report_path}")
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except Exception as e:
        print(f"\n[leafscan] Pipeline failed: {e}", file=sys.stderr)
        sys.exit(1)


# ── setup ─────────────────────────────────────────────────────────────────────

def _find_leafhub() -> str | None:
    """Locate the leafhub binary, checking PATH then the current venv."""
    path = shutil.which("leafhub")
    if path:
        return path
    venv_bin = Path(sys.executable).parent / (
        "leafhub.exe" if sys.platform == "win32" else "leafhub"
    )
    return str(venv_bin) if venv_bin.exists() else None


def _ensure_leafhub() -> str:
    """Return leafhub binary path, installing it first if necessary."""
    leafhub_bin = _find_leafhub()
    if leafhub_bin:
        return leafhub_bin

    print("[setup] LeafHub not found -- installing (required dependency) ...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "leafhub @ git+https://github.com/Rebas9512/Leafhub.git"],
            check=True,
        )
    except Exception as e:
        print(f"[setup] Auto-install failed: {e}")
        print("        Install manually: pip install 'leafhub @ git+https://github.com/Rebas9512/Leafhub.git'")
        sys.exit(1)

    leafhub_bin = _find_leafhub()
    if not leafhub_bin:
        print("[setup] leafhub binary not found after install.")
        sys.exit(1)
    print(f"[setup] LeafHub installed: {leafhub_bin}")
    return leafhub_bin


def _cmd_setup() -> None:
    """
    Self-repair command:
      1. Fast-path: if credentials already resolve, exit OK
      2. Ensure leafhub is installed
      3. Run `leafhub register` interactively so the user can
         add a provider and bind it to this project
      4. Verify credentials resolve after registration
    """
    # ── Fast path: probe credentials ──────────────────────────────────────
    try:
        from leafhub_sdk import resolve as _sdk_resolve
        _sdk_resolve(_ALIAS, project_dir=_ROOT)
        print(f"[setup] OK -- credentials resolve (alias: {_ALIAS!r})")
        return
    except ImportError:
        pass
    except Exception:
        pass
    # Fallback: try leafhub.probe directly
    try:
        from leafhub.probe import detect
        result = detect(project_dir=_ROOT)
        if result.ready:
            hub = result.open_sdk()
            hub.get_key(_ALIAS)
            print(f"[setup] OK -- credentials resolve via LeafHub (alias: {_ALIAS!r})")
            return
    except Exception:
        pass

    # ── Ensure leafhub is installed ───────────────────────────────────────
    leafhub_bin = _ensure_leafhub()

    # ── Run interactive registration ──────────────────────────────────────
    # leafhub register handles the full flow:
    #   - create/link project
    #   - if no providers: prompt user to add one (Web UI or terminal)
    #   - auto-bind provider to project
    print()
    print("[setup] Setting up LeafScan with LeafHub...")
    print("        This will guide you through provider configuration.")
    print()

    # Use manifest mode if leafhub.toml exists, otherwise legacy
    if (_ROOT / "leafhub.toml").is_file():
        reg_cmd = [leafhub_bin, "register", str(_ROOT)]
    else:
        reg_cmd = [leafhub_bin, "register", "leafscan",
                   "--path", str(_ROOT), "--alias", _ALIAS]
    result = subprocess.run(reg_cmd)

    if result.returncode != 0:
        print()
        print("[setup] Registration did not complete.")
        print(f"        Retry: leafhub register .  (from {_ROOT})")
        sys.exit(1)

    # ── Verify credentials resolve ────────────────────────────────────────
    print()
    try:
        from leafhub_sdk import resolve as _sdk_resolve
        _sdk_resolve(_ALIAS, project_dir=_ROOT)
        print(f"[setup] OK -- credentials resolve (alias: {_ALIAS!r})")
        return
    except Exception:
        pass
    try:
        from leafhub.probe import detect
        import importlib
        importlib.invalidate_caches()
        res = detect(project_dir=_ROOT)
        if res.ready:
            hub = res.open_sdk()
            hub.get_key(_ALIAS)
            print(f"[setup] OK -- credentials resolve via LeafHub (alias: {_ALIAS!r})")
            return
    except Exception:
        pass

    print("[setup] Registration completed but credentials could not be verified.")
    print("        Run: leafhub doctor .")
