# ------------------------------------------------------------------------------
#  LeafScan -- Windows One-liner Installer
#
#  irm https://raw.githubusercontent.com/Rebas9512/Leafscan/main/install.ps1 | iex
#
#  Parameters:
#    -InstallDir <path>   Install directory  (default: $HOME\leafscan)
#    -Headless            Non-interactive / CI mode
#  Environment variables:
#    LEAFSCAN_DIR         Override the install directory
#    LEAFSCAN_REPO_URL    Override the git clone URL
# ------------------------------------------------------------------------------
param(
    [string]$InstallDir = "",
    [switch]$Headless
)

$ErrorActionPreference = "Stop"
$DefaultInstallDir = Join-Path $env:USERPROFILE "leafscan"
$RepoUrl = if ($env:LEAFSCAN_REPO_URL) { $env:LEAFSCAN_REPO_URL } `
           else { "https://github.com/Rebas9512/Leafscan.git" }

$ESC = [char]0x1b
$GREEN = "${ESC}[38;2;0;229;180m"; $RED = "${ESC}[38;2;230;57;70m"
$MUTED = "${ESC}[38;2;110;120;148m"; $BOLD = "${ESC}[1m"; $NC = "${ESC}[0m"
function Write-Ok($msg)   { Write-Host "${GREEN}+${NC}  $msg" }
function Write-Info($msg) { Write-Host "${MUTED}.${NC}  $msg" }
function Write-Fail($msg) { Write-Host "${RED}x${NC}  $msg"; exit 1 }

function Assert-ExitCode($msg) {
    if ($LASTEXITCODE -ne 0) { Write-Fail "$msg (exit code $LASTEXITCODE)" }
}

function Test-DirHasEntries([string]$Dir) {
    if (-not (Test-Path $Dir -PathType Container)) { return $false }
    return $null -ne (Get-ChildItem -Force -LiteralPath $Dir | Select-Object -First 1)
}

# -- Select install directory -------------------------------------------------
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
        Write-Info "Target is non-empty -- using subdirectory: $InstallDir\leafscan"
        $InstallDir = [IO.Path]::GetFullPath((Join-Path $InstallDir "leafscan"))
    }
}

# -- Banner -------------------------------------------------------------------
Write-Host ""
Write-Host "${BOLD}  LeafScan -- Installer${NC}"
Write-Host "${MUTED}  Install path: $InstallDir${NC}"
Write-Host ""

# -- Prerequisites ------------------------------------------------------------
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Fail "git is required.`n  Install: winget install Git.Git  or  https://git-scm.com"
}

# -- Clone / update -----------------------------------------------------------
if (Test-Path (Join-Path $InstallDir ".git")) {
    Write-Info "Existing installation found -- syncing to latest..."
    git -C $InstallDir fetch origin --quiet
    Assert-ExitCode "git fetch failed"
    # Determine default branch (main or master)
    $branch = (git -C $InstallDir symbolic-ref refs/remotes/origin/HEAD 2>$null) -replace '.*/','';
    if (-not $branch) { $branch = "main" }
    git -C $InstallDir reset --hard "origin/$branch" --quiet
    Assert-ExitCode "git reset failed"
    Write-Ok "Updated to latest ($branch)."
} else {
    if ((Test-Path $InstallDir -PathType Container) -and (Test-DirHasEntries $InstallDir)) {
        Write-Info "Directory exists without .git -- removing stale files..."
        Remove-Item -Recurse -Force $InstallDir
    }
    Write-Info "Cloning into $InstallDir ..."
    git clone --depth=1 $RepoUrl $InstallDir --quiet
    Assert-ExitCode "git clone failed"
    Write-Ok "Cloned."
}

# -- Python 3.11+ --------------------------------------------------------------
Write-Host "${BOLD}-- Python --${NC}"

function Find-Python {
    foreach ($cmd in @("python3.13","python3.12","python3.11","python3","python")) {
        try {
            $result = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($result) {
                $parts = $result.Trim().Split(".")
                if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 11) { return $cmd }
            }
        } catch {}
    }
    return $null
}

$Python = Find-Python
if (-not $Python) {
    Write-Fail "Python 3.11+ not found.`n  Download from https://www.python.org/downloads/ (tick 'Add Python to PATH')"
}
$PyVer = & $Python -c "import sys; print(sys.version.split()[0])" 2>$null
Write-Ok "Python: $Python ($PyVer)"

# -- Virtual environment + install ---------------------------------------------
Write-Host ""
Write-Host "${BOLD}-- Virtual environment --${NC}"

$VenvDir    = Join-Path $InstallDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip    = Join-Path $VenvDir "Scripts\pip.exe"
$ScriptsDir = Join-Path $VenvDir "Scripts"

if (-not (Test-Path $VenvPython)) {
    Write-Info "Creating .venv ..."
    & $Python -m venv $VenvDir
    Assert-ExitCode "Failed to create virtual environment"
    Write-Ok "Venv created."
} else {
    Write-Ok "Venv exists -- reusing."
}

Write-Info "Upgrading pip ..."
& $VenvPython -m pip install --upgrade pip --quiet
Assert-ExitCode "pip upgrade failed"

Write-Info "Installing leafscan[leafhub] ..."
& $VenvPip install -e "$InstallDir[leafhub]" --quiet
Assert-ExitCode "Package install failed"
Write-Ok "Package installed."

Write-Info "Installing Playwright + Chromium ..."
& $VenvPython -m playwright install chromium
Assert-ExitCode "Playwright install failed"
Write-Ok "Playwright ready."

# -- PATH ----------------------------------------------------------------------
Write-Host ""
Write-Host "${BOLD}-- PATH --${NC}"

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) { $userPath = "" }

if ($userPath -notlike "*$ScriptsDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$ScriptsDir", "User")
    Write-Info "Added $ScriptsDir to user PATH (takes effect in new terminals)."
}
$env:Path = "$ScriptsDir;$env:Path"
Write-Ok "PATH updated."

# -- Done ----------------------------------------------------------------------
Write-Host ""
Write-Host "${BOLD}  LeafScan installed!${NC}"
Write-Host ""
Write-Host "  ${MUTED}If the command is not recognised, open a new terminal first.${NC}"
Write-Host ""
Write-Host "  ${GREEN}leafscan --help${NC}       # verify install"
Write-Host "  ${GREEN}leafscan run${NC}          # start scanning"
Write-Host ""
Write-Host "  ${MUTED}Install dir:  $InstallDir${NC}"
Write-Host "  ${MUTED}To update:    git -C `"$InstallDir`" pull${NC}"
Write-Host "  ${MUTED}To uninstall: Remove-Item -Recurse `"$InstallDir`"${NC}"
Write-Host ""
