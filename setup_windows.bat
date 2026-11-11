@echo off
setlocal EnableDelayedExpansion
title Bajrang AI Pro (v6.0) — Smart Windows 11 Setup & Uninstaller

set "INSTALL_DIR=%LOCALAPPDATA%\BajrangAI"
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
set "LOG_FILE=%INSTALL_DIR%\install_diagnostics.log"

if "%~1"=="--uninstall" (
    echo [UNINSTALL] Removing Bajrang AI Pro v6.0 application files and Desktop shortcut...
    if exist "%USERPROFILE%\Desktop\Bajrang AI Pro.lnk" del /f /q "%USERPROFILE%\Desktop\Bajrang AI Pro.lnk"
    for %%F in (bajrang_core.py bajrang_windows.py installer_windows.py requirements_windows.txt setup_windows.bat Launch_Bajrang_AI.bat Modelfile.bajrang) do (
        if exist "%INSTALL_DIR%\%%F" del /f /q "%INSTALL_DIR%\%%F"
    )
    echo [UNINSTALL] Complete. User database (%INSTALL_DIR%\history.db) was preserved.
    exit /b 0
)

echo ======================================================================
echo   Bajrang AI Pro (v6.0) — Windows 11 Smart Selective Installer
echo   Diagnostic Log: %LOG_FILE%
echo ======================================================================
echo [%DATE% %TIME%] Starting Bajrang AI Pro v6.0 Windows Setup > "%LOG_FILE%"

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [1/5] Python 3 not found. Installing Python 3.12 via WinGet...
    echo [INSTALL] Python.Python.3.12 >> "%LOG_FILE%"
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
) else (
    echo [1/5] [FOUND OK] Python 3 runtime detected.
)

echo [2/5] Running Smart Pre-Flight Scanner & Selective Library Installer...
python installer_windows.py --cli >> "%LOG_FILE%" 2>&1
python installer_windows.py --cli

echo [3/5] Checking Ollama for Windows...
where ollama >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [NOTICE] Ollama not found. Installing via WinGet...
    winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
) else (
    echo [FOUND OK] Ollama for Windows detected.
)

echo [4/5] Copying v6.0 application files to %INSTALL_DIR%...
for %%F in (bajrang_core.py bajrang_windows.py installer_windows.py requirements_windows.txt setup_windows.bat) do (
    if exist "%%F" copy /y "%%F" "%INSTALL_DIR%\%%F" >nul
)

echo [5/5] Launching Bajrang AI Pro v6.0...
start "" python "%INSTALL_DIR%\bajrang_windows.py"
