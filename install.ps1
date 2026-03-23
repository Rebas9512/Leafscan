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

# If path is a file (not a directory), remove it
if ((Test-Path $InstallDir) -and -not (Test-Path $InstallDir -PathType Container)) {
    Remove-Item -Force $InstallDir
}

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
$hasGit = Test-Path (Join-Path $InstallDir ".git")
if (-not $hasGit -and -not (Test-Path $InstallDir)) {
    # Fresh install -- simple clone
    Write-Info "Cloning into $InstallDir ..."
    git clone --depth=1 $RepoUrl $InstallDir --quiet
    Assert-ExitCode "git clone failed"
    Write-Ok "Cloned."
} else {
    # Directory exists (with or without .git) -- sync to latest in-place
    if (-not $hasGit) {
        Write-Info "Directory exists -- initialising git..."
        git -C $InstallDir init --quiet
        Assert-ExitCode "git init failed"
        git -C $InstallDir remote add origin $RepoUrl 2>$null
    } else {
        Write-Info "Existing installation found -- syncing to latest..."
    }
    git -C $InstallDir fetch origin --depth=1 --quiet
    Assert-ExitCode "git fetch failed"
    $branch = (git -C $InstallDir symbolic-ref refs/remotes/origin/HEAD 2>$null) -replace '.*/','';
    if (-not $branch) { $branch = "main" }
    git -C $InstallDir reset --hard "origin/$branch" --quiet
    Assert-ExitCode "git reset failed"
    git -C $InstallDir clean -fdx --quiet 2>$null
    Write-Ok "Synced to latest ($branch)."
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

# -- LeafHub setup -------------------------------------------------------------
# The venv leafhub (pip package) can register/bind but cannot run the Web UI
# (it needs the ui/ directory from a full git clone). Find or install a
# standalone leafhub for manage, and use the venv one for register/bind.
$VenvLeafhub = Join-Path $ScriptsDir "leafhub.exe"
if (-not (Test-Path $VenvLeafhub)) { $VenvLeafhub = Join-Path $ScriptsDir "leafhub" }

# Look for a standalone leafhub installation (full clone with ui/)
$SystemLeafhub = $null
$candidates = @(
    (Join-Path $env:USERPROFILE "leafhub\.venv\Scripts\leafhub.exe"),
    (Join-Path $env:USERPROFILE "leafhub\.venv\Scripts\leafhub")
)
foreach ($c in $candidates) {
    if (Test-Path $c) { $SystemLeafhub = $c; break }
}

# Check if providers are already configured
$needsSetup = $true
if (Test-Path $VenvLeafhub) {
    $provCheck = & $VenvLeafhub provider list 2>$null
    if ($LASTEXITCODE -eq 0 -and $provCheck -and ($provCheck | Where-Object { $_ -match '\S' }).Count -gt 1) {
        $needsSetup = $false
    }
}

if ($needsSetup) {
    Write-Host ""
    Write-Host "${BOLD}-- LeafHub --${NC}"

    # Install standalone leafhub if not present (needed for Web UI)
    if (-not $SystemLeafhub) {
        Write-Info "Installing LeafHub (required for API key management)..."
        Write-Host "  ${MUTED}This provides the Web UI for configuring API providers.${NC}"
        Write-Host ""
        try {
            $leafhubInstallUrl = "https://raw.githubusercontent.com/Rebas9512/Leafhub/main/install.ps1"
            & ([scriptblock]::Create((Invoke-RestMethod $leafhubInstallUrl)))
        } catch {
            Write-Host "  ${MUTED}LeafHub auto-install failed. Install manually:${NC}"
            Write-Host "  ${MUTED}  irm https://raw.githubusercontent.com/Rebas9512/Leafhub/main/install.ps1 | iex${NC}"
        }
        # Re-check after install
        foreach ($c in $candidates) {
            if (Test-Path $c) { $SystemLeafhub = $c; break }
        }
    }

    # Use standalone leafhub for all operations (has fastapi + ui/)
    $LeafhubCmd = if ($SystemLeafhub) { $SystemLeafhub } else { $VenvLeafhub }

    # Register project
    Write-Info "Registering LeafScan project..."
    & $LeafhubCmd register leafscan --path $InstallDir --alias llm --headless 2>$null

    # Guide provider setup
    $canPrompt = $false
    try { $canPrompt = [Console]::KeyAvailable -ne $null -and -not [Console]::IsInputRedirected } catch {}

    if ($canPrompt -and $SystemLeafhub) {
        Write-Host ""
        Write-Host "  ${BOLD}LeafScan needs an AI provider to work.${NC}"
        Write-Host "  ${MUTED}LeafHub stores API keys encrypted locally -- nothing leaves your system.${NC}"
        Write-Host ""
        Write-Host "  How would you like to configure your provider?"
        Write-Host "    ${GREEN}[1]${NC} Launch Web UI   -- visual setup at http://localhost:8765  (recommended)"
        Write-Host "    ${GREEN}[2]${NC} Terminal        -- step-by-step CLI prompts"
        Write-Host "    ${GREEN}[s]${NC} Skip            -- configure later with: leafscan setup"
        Write-Host ""
        $choice = Read-Host "  Choice [1]"
        if (-not $choice) { $choice = "1" }

        if ($choice -eq "1") {
            Write-Info "Starting LeafHub Web UI..."
            $manageProc = Start-Process -FilePath $SystemLeafhub -ArgumentList "manage","--no-browser" -PassThru -WindowStyle Hidden
            Start-Sleep -Seconds 3
            Start-Process "http://localhost:8765"
            Write-Host ""
            Write-Host "  ${GREEN}Web UI opened at http://localhost:8765${NC}"
            Write-Host "  Add a provider, then come back here."
            Read-Host "`n  Press Enter when done"
            Stop-Process -Id $manageProc.Id -Force -ErrorAction SilentlyContinue
            & $LeafhubCmd register leafscan --path $InstallDir --alias llm --headless 2>$null
        } elseif ($choice -eq "2") {
            & $LeafhubCmd provider add
            if ($LASTEXITCODE -eq 0) {
                & $LeafhubCmd register leafscan --path $InstallDir --alias llm --headless 2>$null
            }
        } else {
            Write-Host "  ${MUTED}Skipped. Run 'leafscan setup' later to configure.${NC}"
        }
    } elseif ($canPrompt) {
        # No system leafhub with Web UI -- offer terminal only
        Write-Host ""
        Write-Host "  ${BOLD}LeafScan needs an AI provider to work.${NC}"
        Write-Host "  ${MUTED}Configure now via terminal, or skip and run 'leafscan setup' later.${NC}"
        Write-Host ""
        Write-Host "    ${GREEN}[1]${NC} Terminal        -- step-by-step CLI prompts"
        Write-Host "    ${GREEN}[s]${NC} Skip"
        Write-Host ""
        $choice = Read-Host "  Choice [1]"
        if (-not $choice) { $choice = "1" }
        if ($choice -eq "1") {
            & $LeafhubCmd provider add
            if ($LASTEXITCODE -eq 0) {
                & $LeafhubCmd register leafscan --path $InstallDir --alias llm --headless 2>$null
            }
        }
    }

    # Verify
    $provCheck2 = & $LeafhubCmd provider list 2>$null
    if ($LASTEXITCODE -eq 0 -and $provCheck2 -and ($provCheck2 | Where-Object { $_ -match '\S' }).Count -gt 1) {
        Write-Ok "LeafHub configured."
    } else {
        Write-Host "  ${MUTED}No providers configured yet. Run 'leafscan setup' to add one.${NC}"
    }
}

# -- Playwright ----------------------------------------------------------------
Write-Host ""
Write-Host "${BOLD}-- Playwright --${NC}"
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
Write-Host "  ${GREEN}leafscan --help${NC}              # verify install"
Write-Host "  ${GREEN}leafscan scan <url>${NC}          # scan a webpage"
Write-Host "  ${GREEN}leafscan setup${NC}               # configure LeafHub"
Write-Host ""
Write-Host "  ${MUTED}Install dir:  $InstallDir${NC}"
Write-Host "  ${MUTED}To update:    git -C `"$InstallDir`" pull${NC}"
Write-Host "  ${MUTED}To uninstall: Remove-Item -Recurse `"$InstallDir`"${NC}"
Write-Host ""
