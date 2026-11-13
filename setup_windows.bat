@echo off
setlocal EnableDelayedExpansion
title Sudharshan AI (Alpha v0.9) — Smart Windows 11 Setup & Uninstaller

set "INSTALL_DIR=%LOCALAPPDATA%\SudharshanAI"
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
set "LOG_FILE=%INSTALL_DIR%\install_diagnostics.log"

if "%~1"=="--uninstall" (
    echo [UNINSTALL] Removing Sudharshan AI application files and Desktop shortcut...
    if exist "%USERPROFILE%\Desktop\Sudharshan AI.lnk" del /f /q "%USERPROFILE%\Desktop\Sudharshan AI.lnk"
    if exist "%USERPROFILE%\Desktop\Bajrang AI Pro.lnk" del /f /q "%USERPROFILE%\Desktop\Bajrang AI Pro.lnk"
    for %%F in (bajrang_core.py bajrang_windows.py windows.py installer_windows.py requirements_windows.txt setup_windows.bat Launch_Bajrang_AI.bat Modelfile.bajrang) do (
        if exist "%INSTALL_DIR%\%%F" del /f /q "%INSTALL_DIR%\%%F"
    )
    echo [UNINSTALL] Complete. User database (%INSTALL_DIR%\history.db) was preserved.
    exit /b 0
)

echo ======================================================================
echo   Sudharshan AI (Alpha v0.9) — Windows 11 Smart Selective Installer
echo   Diagnostic Log: %LOG_FILE%
echo ======================================================================
echo [%DATE% %TIME%] Starting Sudharshan AI Windows Setup > "%LOG_FILE%"

:: [Step 0] Unblock downloaded files (Remove Zone.Identifier Mark-of-the-Web)
powershell.exe -NoProfile -Command "Get-ChildItem -Path '%~dp0*' -Recurse | Unblock-File -ErrorAction SilentlyContinue" 2>nul

:: [Step 0.5] Register Code Signing Certificate to Trusted Publishers if present
if exist "%~dp0certificates\Sudharshan_AI_CodeSigning.cer" (
    certutil.exe -addstore -f "TrustedPublisher" "%~dp0certificates\Sudharshan_AI_CodeSigning.cer" >nul 2>&1
) else if exist "%~dp0Sudharshan_AI_CodeSigning.cer" (
    certutil.exe -addstore -f "TrustedPublisher" "%~dp0Sudharshan_AI_CodeSigning.cer" >nul 2>&1
)

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

echo [4/5] Copying application files to %INSTALL_DIR%...
for %%F in (bajrang_core.py bajrang_windows.py windows.py installer_windows.py requirements_windows.txt setup_windows.bat) do (
    if exist "%%F" copy /y "%%F" "%INSTALL_DIR%\%%F" >nul
)

echo [5/5] Launching Sudharshan AI (Alpha v0.9)...
start "" python "%INSTALL_DIR%\windows.py"
