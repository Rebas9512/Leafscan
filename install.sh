#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
#  LeafScan — One-liner Installer  (macOS / Linux / WSL)
#
#  curl -fsSL https://raw.githubusercontent.com/Rebas9512/Leafscan/main/install.sh | bash
#
#  This script selects an install directory, clones the repo, then delegates
#  all further setup to setup.sh inside the clone.
#
#  Environment variables:
#    LEAFSCAN_DIR=<path>     Install directory  (default: ~/leafscan)
#    LEAFSCAN_REPO_URL=<url> Clone URL          (default: GitHub repo)
#    NO_COLOR=1              Disable colour output
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

DEFAULT_INSTALL_DIR="$HOME/leafscan"
LEAFSCAN_DIR="${LEAFSCAN_DIR:-}"
REPO_URL="${LEAFSCAN_REPO_URL:-https://github.com/Rebas9512/Leafscan.git}"

# ── Minimal colours ──────────────────────────────────────────────────────────
if [[ -n "${NO_COLOR:-}" || "${TERM:-dumb}" == "dumb" ]]; then
    BOLD='' GREEN='' RED='' MUTED='' NC=''
else
    BOLD='\033[1m'
    GREEN='\033[38;2;0;229;180m'
    RED='\033[38;2;230;57;70m'
    MUTED='\033[38;2;110;120;148m'
    NC='\033[0m'
fi

fail() { echo -e "${RED}✗${NC}  $*" >&2; exit 1; }
info() { echo -e "${MUTED}·${NC}  $*"; }
ok()   { echo -e "${GREEN}✓${NC}  $*"; }

# ── Helpers ──────────────────────────────────────────────────────────────────

normalise_path() {
    local raw="${1:-}" expanded="${1:-}"
    while [[ "$expanded" == \'*\' || "$expanded" == \"*\" ]]; do
        if [[ "$expanded" == \'*\' && "$expanded" == *\' ]]; then
            expanded="${expanded:1:${#expanded}-2}"; continue
        fi
        if [[ "$expanded" == \"*\" && "$expanded" == *\" ]]; then
            expanded="${expanded:1:${#expanded}-2}"; continue
        fi
        break
    done
    expanded="${expanded/#\~/$HOME}"
    if [[ -n "$expanded" && "$expanded" != /* ]]; then
        expanded="$(pwd -P)/$expanded"
    fi
    while [[ "${expanded}" != "/" && "${expanded}" == */ ]]; do
        expanded="${expanded%/}"
    done
    printf '%s' "$expanded"
}

dir_has_entries() {
    local dir="$1" entry
    for entry in "$dir"/.[!.]* "$dir"/..?* "$dir"/*; do
        [[ -e "$entry" ]] && return 0
    done
    return 1
}

# ── Select install directory ─────────────────────────────────────────────────

default_dir="$(normalise_path "$DEFAULT_INSTALL_DIR")"

if [[ -n "$LEAFSCAN_DIR" ]]; then
    LEAFSCAN_DIR="$(normalise_path "$LEAFSCAN_DIR")"
elif [[ -r /dev/tty && -w /dev/tty && -z "${CI:-}" ]]; then
    printf 'Install directory [%s]: ' "$default_dir" > /dev/tty
    if IFS= read -r _cand < /dev/tty; then
        _cand="${_cand:-$default_dir}"
    else
        _cand="$default_dir"
    fi
    LEAFSCAN_DIR="$(normalise_path "$_cand")"
else
    LEAFSCAN_DIR="$default_dir"
fi

# If target exists and is non-empty but not a git repo, redirect to subdirectory
if [[ ! -d "$LEAFSCAN_DIR/.git" ]] && \
   [[ -d "$LEAFSCAN_DIR" ]] && dir_has_entries "$LEAFSCAN_DIR"; then
    info "Target is non-empty — using subdirectory: $LEAFSCAN_DIR/leafscan"
    LEAFSCAN_DIR="$(normalise_path "$LEAFSCAN_DIR/leafscan")"
fi

# ── Banner ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}  LeafScan — Installer${NC}"
echo -e "${MUTED}  Install path: $LEAFSCAN_DIR${NC}"
echo ""

# ── Prerequisites ────────────────────────────────────────────────────────────
command -v python3 >/dev/null 2>&1 || \
    fail "Python 3 not found.\n  macOS: brew install python@3.12\n  Ubuntu: sudo apt install python3.12"
command -v git >/dev/null 2>&1 || fail "git is required but not found."

# ── Clone / update ───────────────────────────────────────────────────────────
if [[ ! -d "$LEAFSCAN_DIR/.git" ]] && [[ ! -e "$LEAFSCAN_DIR" ]]; then
    info "Cloning into $LEAFSCAN_DIR ..."
    git clone --depth=1 "$REPO_URL" "$LEAFSCAN_DIR" --quiet
    ok "Cloned."
else
    if [[ ! -d "$LEAFSCAN_DIR/.git" ]]; then
        info "Directory exists — initialising git..."
        git -C "$LEAFSCAN_DIR" init --quiet
        git -C "$LEAFSCAN_DIR" remote add origin "$REPO_URL" 2>/dev/null || true
    else
        info "Existing installation found — syncing to latest..."
    fi
    git -C "$LEAFSCAN_DIR" fetch origin --depth=1 --quiet
    branch="$(git -C "$LEAFSCAN_DIR" symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|.*/||')"
    [[ -z "$branch" ]] && branch="main"
    git -C "$LEAFSCAN_DIR" reset --hard "origin/$branch" --quiet
    git -C "$LEAFSCAN_DIR" clean -fd --quiet 2>/dev/null || true
    ok "Synced to latest ($branch)."
fi

# ── Hand off to setup.sh ────────────────────────────────────────────────────
SETUP_SH="$LEAFSCAN_DIR/setup.sh"
[[ -f "$SETUP_SH" ]] || fail "setup.sh not found in $LEAFSCAN_DIR."
chmod +x "$SETUP_SH"
exec bash "$SETUP_SH" --from-installer "$@"
