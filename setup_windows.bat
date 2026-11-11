@echo off
setlocal EnableDelayedExpansion
title Bajrang AI Pro (v5.0) — Complete Windows 11 Installer & Package Setup

echo ======================================================================
echo   Bajrang AI Pro (v5.0) — Windows 11 Full Installer (All Packages)
echo ======================================================================

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [1/6] Python 3 not found. Installing Python 3.12 via WinGet...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
) else (
    echo [1/6] Python 3 detected.
)

echo [2/6] Installing all required Windows Python packages (Pillow, PyAutoGUI, pyttsx3, sounddevice, numpy, faster-whisper)...
python -m pip install --upgrade pip
python -m pip install --upgrade pillow pyautogui pyttsx3 sounddevice numpy faster-whisper pystray

where ollama >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [3/6] Installing Ollama for Windows 11 via WinGet...
    winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
) else (
    echo [3/6] Ollama for Windows detected.
)

echo [4/6] Starting Ollama server and pulling Llama 3.2...
start "" /B ollama serve >nul 2>nul
timeout /t 3 /nobreak >nul
ollama pull llama3.2

echo [5/6] Building personalized Bajrang AI Llama 3.2 Modelfile...
set "INSTALL_DIR=%LOCALAPPDATA%\BajrangAI"
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
copy /Y "%~dp0bajrang_windows.py" "%INSTALL_DIR%\bajrang_windows.py" >nul
python "%INSTALL_DIR%\bajrang_windows.py" --build-personalized-llama

echo [6/6] Creating Windows 11 Desktop & Start Menu Shortcuts...
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Bajrang AI Pro.lnk'); $s.TargetPath = 'pythonw.exe'; $s.Arguments = '\"%INSTALL_DIR%\bajrang_windows.py\"'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Save()"

echo.
echo ======================================================================
echo   Bajrang AI Pro Installed Successfully on Windows 11!
echo   - Desktop Shortcut : "Bajrang AI Pro" on your Windows 11 Desktop
echo   - Launch Now       : python "%INSTALL_DIR%\bajrang_windows.py"
echo ======================================================================
start "" pythonw "%INSTALL_DIR%\bajrang_windows.py"
pause
