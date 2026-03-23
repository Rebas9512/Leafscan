@echo off
setlocal

rem LeafScan Windows bootstrap for cmd.exe
rem Usage:
rem   curl -fsSL https://raw.githubusercontent.com/Rebas9512/Leafscan/main/install.cmd -o install.cmd && install.cmd && del install.cmd

set "SCRIPT_URL=%LEAFSCAN_INSTALL_PS1_URL%"
if not defined SCRIPT_URL set "SCRIPT_URL=https://raw.githubusercontent.com/Rebas9512/Leafscan/main/install.ps1"
set "SCRIPT_PATH=%TEMP%\leafscan-install-%RANDOM%%RANDOM%.ps1"

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing '%SCRIPT_URL%' -OutFile '%SCRIPT_PATH%' } catch { Write-Host $_; exit 1 }"
if errorlevel 1 (
    echo Failed to download %SCRIPT_URL%
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_PATH%" %*
set "EXITCODE=%ERRORLEVEL%"

del "%SCRIPT_PATH%" >nul 2>&1
exit /b %EXITCODE%
