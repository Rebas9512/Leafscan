"""
CLI entry point.

Commands:
  leafscan scan <url>   — run the full pipeline
  leafscan setup        — verify/repair Leafhub credential binding
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_ROOT  = Path(__file__).resolve().parent.parent
_ALIAS = "llm"


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
    scan_p.add_argument("--alias", default="llm",
                        help="Leafhub alias to use (default: llm)")

    # setup
    sub.add_parser("setup", help="Verify and repair Leafhub credential binding")

    # clean
    clean_p = sub.add_parser("clean", help="Remove all generated outputs")
    clean_p.add_argument("--yes", "-y", action="store_true",
                         help="Skip confirmation prompt")

    args = parser.parse_args()

    if args.cmd == "scan":
        _cmd_scan(args.url, alias=args.alias)
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

    import shutil
    for d in entries:
        shutil.rmtree(d)
    print(f"Removed {len(entries)} output(s).")


# ── scan ──────────────────────────────────────────────────────────────────────

def _cmd_scan(url: str, alias: str = "llm") -> None:
    from .pipeline import run
    try:
        report_path = run(url, alias=alias)
        print(f"\nReport saved to: {report_path}")
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except Exception as e:
        print(f"\n[leafscan] Pipeline failed: {e}", file=sys.stderr)
        sys.exit(1)


# ── setup ─────────────────────────────────────────────────────────────────────

def _cmd_setup() -> None:
    """
    Self-repair command. Checks in order:
      1. Full credential resolution via Leafhub — exits OK if successful
      2. Tries auto-binding to the first available provider
      3. Prints actionable guidance if everything fails
    """
    # Fast path: probe credentials
    try:
        from leafhub_dist.probe import detect
        result = detect()
        if result.ready:
            hub = result.open_sdk()
            hub.get_key(_ALIAS)
            print(f"[setup] OK — credentials resolve via LeafHub (alias: {_ALIAS!r})")
            return
    except Exception as e:
        print(f"[setup] LeafHub probe failed: {e}")

    # Check prerequisites
    dotfile = _ROOT / ".leafhub"
    if not dotfile.exists():
        print("[setup] .leafhub not found — run ./setup.sh first.")
        sys.exit(1)

    leafhub_bin = shutil.which("leafhub")
    if not leafhub_bin:
        print("[setup] leafhub binary not found — install LeafHub first.")
        sys.exit(1)

    # Read project name from dotfile (never hardcode)
    try:
        project = json.loads(dotfile.read_text())["project"]
    except Exception:
        print("[setup] .leafhub is malformed — re-run ./setup.sh.")
        sys.exit(1)

    # Check vault state
    show = subprocess.run(
        [leafhub_bin, "project", "show", project],
        capture_output=True, text=True,
    )
    if show.returncode != 0 or "not found" in show.stdout.lower():
        print(f"[setup] Project '{project}' not found in vault — re-run ./setup.sh.")
        sys.exit(1)

    if _ALIAS in show.stdout:
        print(f"[setup] Binding '{_ALIAS}' exists but credential resolution failed.")
        print(f"        Run: leafhub status")
        sys.exit(1)

    # Attempt auto-bind to first available provider
    prov_out = subprocess.run(
        [leafhub_bin, "provider", "list"],
        capture_output=True, text=True,
    )
    provider = next(
        (line.strip().split()[0]
         for line in prov_out.stdout.splitlines()
         if line.strip() and not line.strip().startswith(("─", "Label", "Provider"))),
        None,
    )
    if not provider:
        print("[setup] No providers in vault. Run: leafhub manage")
        sys.exit(1)

    bind = subprocess.run(
        [leafhub_bin, "project", "bind", project,
         "--alias", _ALIAS, "--provider", provider],
        capture_output=True, text=True,
    )
    if bind.returncode == 0:
        print(f"[setup] Bound '{_ALIAS}' → '{provider}'. Run `leafscan setup` to verify.")
    else:
        print(f"[setup] Auto-bind failed:\n{bind.stderr}")
        sys.exit(1)
