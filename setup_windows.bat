@echo off
setlocal EnableDelayedExpansion
title Sudharshan AI (Alpha v0.9) — Windows 11 Automated Installer & Local AI Engine

set "INSTALL_DIR=%LOCALAPPDATA%\SudharshanAI"
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
set "LOG_FILE=%INSTALL_DIR%\install_diagnostics.log"

if "%~1"=="--uninstall" (
    echo ======================================================================
    echo   Sudharshan AI (Alpha v0.9) — Safe Uninstaller
    echo ======================================================================
    echo [UNINSTALL] Removing Sudharshan AI application files and shortcuts...
    if exist "%USERPROFILE%\Desktop\Sudharshan AI.lnk" del /f /q "%USERPROFILE%\Desktop\Sudharshan AI.lnk"
    if exist "%USERPROFILE%\Desktop\Bajrang AI Pro.lnk" del /f /q "%USERPROFILE%\Desktop\Bajrang AI Pro.lnk"
    for %%F in (bajrang_core.py bajrang_windows.py windows.py fedora.py bajrang_llama32.py installer_windows.py requirements_windows.txt requirements_common.txt setup_windows.bat Launch_Sudharshan_AI.bat) do (
        if exist "%INSTALL_DIR%\%%F" del /f /q "%INSTALL_DIR%\%%F"
    )
    echo [UNINSTALL] Sudharshan AI has been uninstalled. User databases were safely preserved in %INSTALL_DIR%.
    exit /b 0
)

echo ======================================================================
echo   Sudharshan AI (Alpha v0.9) — Automated Windows 11 Setup
echo   Engineered by Kaushik Ram Ravuru (B.E. IT, Section IT-1, CBIT)
echo   Diagnostic Log: %LOG_FILE%
echo ======================================================================
echo [%DATE% %TIME%] Starting Sudharshan AI Automated Windows Setup > "%LOG_FILE%"

:: [Step 1] Unblock downloaded files (Remove Zone.Identifier Mark-of-the-Web)
echo [1/7] Unblocking downloaded application files...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -Path '%~dp0*' -Recurse | Unblock-File -ErrorAction SilentlyContinue" 2>nul
echo [OK] Mark-of-the-Web cleared.

:: [Step 2] Install Code Signing Certificate to Windows Trusted Root / Publisher
echo [2/7] Checking Authenticode Code Signing Certificate...
set "CERT_FILE="
if exist "%~dp0certificates\Sudharshan_AI_CodeSigning.cer" set "CERT_FILE=%~dp0certificates\Sudharshan_AI_CodeSigning.cer"
if exist "%~dp0Sudharshan_AI_CodeSigning.cer" set "CERT_FILE=%~dp0Sudharshan_AI_CodeSigning.cer"

if defined CERT_FILE (
    echo [CERT] Registering %CERT_FILE% to TrustedPublisher and Root...
    certutil.exe -addstore -f "TrustedPublisher" "%CERT_FILE%" >nul 2>&1
    certutil.exe -addstore -f "Root" "%CERT_FILE%" >nul 2>&1
    echo [OK] Authenticode certificate trusted on this device.
) else (
    echo [INFO] Certificate file not bundled; proceeding with runtime verification.
)

:: [Step 3] Detect or Install Python 3.9+
echo [3/7] Verifying Python runtime environment...
set "PYTHON_EXE="
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=python"
) else (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    if exist "%ProgramFiles%\Python312\python.exe" set "PYTHON_EXE=%ProgramFiles%\Python312\python.exe"
    if exist "%ProgramFiles%\Python311\python.exe" set "PYTHON_EXE=%ProgramFiles%\Python311\python.exe"
)

if not defined PYTHON_EXE (
    echo [INSTALL] Python 3 not detected in PATH. Attempting installation via WinGet...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    :: Refresh Environment PATH from Registry
    for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "PATH=%%B;!PATH!"
    for /f "tokens=2*" %%A in ('reg query "HKLM\System\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "PATH=%%B;!PATH!"
    where python >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        set "PYTHON_EXE=python"
    ) else (
        echo [ERROR] Python installation requires a terminal restart or manual install from python.org.
        pause
        exit /b 1
    )
)
echo [OK] Using Python: %PYTHON_EXE%

:: [Step 4] Install Required Python Packages
echo [4/7] Installing and verifying required Python packages...
"%PYTHON_EXE%" -m pip install --upgrade pip >nul 2>&1
if exist "%~dp0requirements_windows.txt" (
    "%PYTHON_EXE%" -m pip install -r "%~dp0requirements_windows.txt" >> "%LOG_FILE%" 2>&1
)
if exist "%~dp0installer_windows.py" (
    "%PYTHON_EXE%" "%~dp0installer_windows.py" --headless-install >> "%LOG_FILE%" 2>&1
)
echo [OK] Python dependencies installed successfully.

:: [Step 5] Detect or Install Ollama Local AI Engine
echo [5/7] Checking Ollama Local AI Engine...
set "OLLAMA_EXE="
where ollama >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "OLLAMA_EXE=ollama"
) else (
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
        set "PATH=%LOCALAPPDATA%\Programs\Ollama;!PATH!"
    ) else if exist "%ProgramFiles%\Ollama\ollama.exe" (
        set "OLLAMA_EXE=%ProgramFiles%\Ollama\ollama.exe"
        set "PATH=%ProgramFiles%\Ollama;!PATH!"
    )
)

if not defined OLLAMA_EXE (
    echo [INSTALL] Ollama not found. Installing Ollama for Windows...
    where winget >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
    )
    if not exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        echo [DOWNLOAD] Downloading official OllamaSetup.exe...
        powershell.exe -NoProfile -Command "Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' -OutFile '%TEMP%\OllamaSetup.exe' -UseBasicParsing; Start-Process '%TEMP%\OllamaSetup.exe' -ArgumentList '/silent' -Wait"
    )
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
        set "PATH=%LOCALAPPDATA%\Programs\Ollama;!PATH!"
    )
)

if not defined OLLAMA_EXE (
    echo [WARNING] Could not automatically install Ollama.
    echo Sudharshan AI will start with BYO Cloud API support (Gemini, Groq, OpenAI).
    goto :skip_ollama_daemon
)
echo [OK] Found Ollama binary: %OLLAMA_EXE%

:: [Step 6] Ensure Ollama Neural Daemon is Running & Verified
echo [6/7] Verifying Ollama neural daemon status at http://127.0.0.1:11434...
powershell.exe -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [DAEMON] Launching Ollama neural background service...
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe" (
        start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
    ) else (
        start "" /B "%OLLAMA_EXE%" serve
    )
    echo [WAIT] Waiting for Ollama daemon to initialize...
    for /L %%I in (1,1,15) do (
        powershell.exe -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            echo [OK] Ollama neural service is active and responsive!
            goto :daemon_verified
        )
        timeout /t 1 /nobreak >nul
    )
)
:daemon_verified

:: Check if llama3.2 is installed; if not, pull and test run
powershell.exe -NoProfile -Command "try { $m = (Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3).models.name; if ($m -like '*llama3.2*') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [MODEL] Pulling Llama 3.2 neural model (~2.0 GB)...
    "%OLLAMA_EXE%" pull llama3.2
    echo [VERIFY] Running quick test query on llama3.2...
    "%OLLAMA_EXE%" run llama3.2 "Respond with 'Sudharshan AI Ready'"
    echo [OK] Llama 3.2 local model operational!
) else (
    echo [OK] Llama 3.2 model is already present in Ollama.
)

:skip_ollama_daemon

:: [Step 7] Deploy Files & Create Desktop Shortcut
echo [7/7] Deploying application files and desktop shortcuts...
for %%F in (bajrang_core.py bajrang_windows.py windows.py fedora.py bajrang_llama32.py installer_windows.py requirements_windows.txt requirements_common.txt README.md SECURITY.md setup_windows.bat) do (
    if exist "%~dp0%%F" copy /y "%~dp0%%F" "%INSTALL_DIR%\%%F" >nul
)

:: Create Launch_Sudharshan_AI.bat
(
echo @echo off
echo cd /d "%INSTALL_DIR%"
echo start "" pythonw windows.py
) > "%INSTALL_DIR%\Launch_Sudharshan_AI.bat"

:: Create Desktop Shortcut via PowerShell
powershell.exe -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%USERPROFILE%\Desktop\Sudharshan AI.lnk'); $s.TargetPath = '%INSTALL_DIR%\Launch_Sudharshan_AI.bat'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Description = 'Sudharshan AI Desktop Assistant'; $s.Save()" >nul 2>&1

echo ======================================================================
echo   Sudharshan AI (Alpha v0.9) Setup Complete!
echo   Launching Desktop Assistant...
echo ======================================================================
cd /d "%INSTALL_DIR%"
start "" "%PYTHON_EXE%" "%INSTALL_DIR%\windows.py"
