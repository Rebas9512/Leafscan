# ──────────────────────────────────────────────────────────────────────────────
#  LeafScan — Windows One-liner Installer
#
#  irm https://raw.githubusercontent.com/Rebas9512/Leafscan/main/install.ps1 | iex
#
#  Parameters:
#    -InstallDir <path>   Install directory  (default: $HOME\leafscan)
#    -Headless            Non-interactive / CI mode
#  Environment variables:
#    LEAFSCAN_DIR         Override the install directory
#    LEAFSCAN_REPO_URL    Override the git clone URL
# ──────────────────────────────────────────────────────────────────────────────
param(
    [string]$InstallDir = "",
    [switch]$Headless
)

$ErrorActionPreference = "Stop"
$DefaultInstallDir = Join-Path $env:USERPROFILE "leafscan"
$RepoUrl = if ($env:LEAFSCAN_REPO_URL) { $env:LEAFSCAN_REPO_URL } `
           else { "https://github.com/Rebas9512/Leafscan.git" }

$GREEN = "`e[38;2;0;229;180m"; $RED = "`e[38;2;230;57;70m"
$MUTED = "`e[38;2;110;120;148m"; $BOLD = "`e[1m"; $NC = "`e[0m"
function Write-Ok($msg)   { Write-Host "${GREEN}√${NC}  $msg" }
function Write-Info($msg) { Write-Host "${MUTED}·${NC}  $msg" }
function Write-Fail($msg) { Write-Host "${RED}x${NC}  $msg"; exit 1 }

function Test-DirHasEntries([string]$Dir) {
    if (-not (Test-Path $Dir -PathType Container)) { return $false }
    return $null -ne (Get-ChildItem -Force -LiteralPath $Dir | Select-Object -First 1)
}

# ── Select install directory ─────────────────────────────────────────────────
if (-not $InstallDir) {
    if ($env:LEAFSCAN_DIR) {
        $InstallDir = $env:LEAFSCAN_DIR
    } else {
        $canPrompt = $false
        try { $canPrompt = -not [Console]::IsInputRedirected } catch {}
        if ($canPrompt -and -not $Headless) {
            $raw = Read-Host "Install directory [$DefaultInstallDir]"
            $InstallDir = if ($raw) { $raw } else { $DefaultInstallDir }
        } else {
            $InstallDir = $DefaultInstallDir
        }
    }
}

$InstallDir = $InstallDir.Trim()
if ($InstallDir -eq "~") { $InstallDir = $env:USERPROFILE }
elseif ($InstallDir.StartsWith("~\")) { $InstallDir = Join-Path $env:USERPROFILE $InstallDir.Substring(2) }
$InstallDir = [IO.Path]::GetFullPath($InstallDir)

if (-not (Test-Path (Join-Path $InstallDir ".git"))) {
    if ((Test-Path $InstallDir -PathType Container) -and (Test-DirHasEntries $InstallDir)) {
        Write-Info "Target is non-empty — using subdirectory: $InstallDir\leafscan"
        $InstallDir = [IO.Path]::GetFullPath((Join-Path $InstallDir "leafscan"))
    }
}

# ── Banner ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "${BOLD}  LeafScan — Installer${NC}"
Write-Host "${MUTED}  Install path: $InstallDir${NC}"
Write-Host ""

# ── Prerequisites ────────────────────────────────────────────────────────────
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Fail "git is required.`n  Install: winget install Git.Git  or  https://git-scm.com"
}

# ── Clone / update ───────────────────────────────────────────────────────────
if (Test-Path (Join-Path $InstallDir ".git")) {
    Write-Info "Existing installation found — updating..."
    git -C $InstallDir pull --ff-only --quiet
    Write-Ok "Updated."
} else {
    Write-Info "Cloning into $InstallDir ..."
    git clone --depth=1 $RepoUrl $InstallDir --quiet
    Write-Ok "Cloned."
}

# ── Delegate to setup.ps1 or setup.sh via WSL ────────────────────────────────
$SetupSh = Join-Path $InstallDir "setup.sh"
if (Test-Path $SetupSh) {
    Write-Info "Running setup.sh ..."
    & bash $SetupSh --from-installer
    exit $LASTEXITCODE
} else {
    Write-Fail "setup.sh not found in $InstallDir."
}
