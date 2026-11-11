# Bajrang AI Pro (v6.0) — Installation & Troubleshooting Guide

## 1. System Requirements & Performance Profiles
Bajrang AI Pro v6.0 runs on ordinary consumer hardware (no dedicated GPU required) using three selectable performance profiles:
- **`eco` (Low-End / Battery Saver)**: Disables background local LLM loading, uses cloud BYO API or deterministic local command routing, limits context to 6 messages, and scales screenshots to 960px.
- **`balanced` (Default — Intel Core i5 / 8–12 GB RAM)**: Uses 6 CPU threads, 4096-token context window, 1280px screenshot framing, and 80ms voice polling.
- **`high` (Workstation / 16+ GB RAM)**: Uses up to all logical CPU threads, 8192-token context window, 1920px screenshot framing, and 45ms voice polling.

## 2. Windows 11 Installation & Uninstallation
### Option A — Smart `.EXE` Pre-Flight Scanner & Installer (`BajrangAI_Pro_Setup.exe`)
1. Download `BajrangAI_Pro_Setup.exe` from the web portal or release archive.
2. Double-click `BajrangAI_Pro_Setup.exe`. It automatically:
   - Extracts `bajrang_core.py`, `bajrang_windows.py`, `installer_windows.py`, `requirements_windows.txt`, and `setup_windows.bat` into `%LOCALAPPDATA%\BajrangAI`.
   - Scans your PC for `winget`, Python 3.10+, `pip`, [Ollama for Windows](https://ollama.com/download/windows), and all required Python libraries (`Pillow`, [PyAutoGUI](https://pypi.org/project/PyAutoGUI/), `pyttsx3`, `numpy`, `sounddevice`, `faster-whisper`, `pystray`, `keyring`).
   - Skips already-installed components and installs only the missing packages one by one.
   - Writes a detailed log to `%LOCALAPPDATA%\BajrangAI\install_diagnostics.log` and creates the `Bajrang AI Pro` Desktop shortcut.

### Option B — Python / Batch Setup & Clean Uninstallation
```powershell
.\setup_windows.bat
python installer_windows.py
```
To cleanly uninstall all application files and shortcuts (while preserving your `history.db` SQLite database):
```powershell
.\setup_windows.bat --uninstall
python installer_windows.py --uninstall
```

## 3. Fedora Workstation (GNOME / Wayland) Installation & Uninstallation
1. Run the non-root pre-flight installer script:
```bash
chmod +x setup_fedora.sh bajrang_llama32.py
./setup_fedora.sh
```
2. To run without `sudo` (if system packages are already installed):
```bash
BAJRANG_SKIP_SUDO=1 ./setup_fedora.sh
```
3. To cleanly uninstall the GNOME Shell extension (`bajrang-ai@fedora.local`) and application files:
```bash
./setup_fedora.sh --uninstall
```

## 4. Troubleshooting Common Issues
- **Vercel Deployment Shows `404: NOT_FOUND` or `Build output contains no "functions", "static", or "services" directory`**:
  - Ensure `index.html` (lowercase) and `vercel.json` are placed directly at the root of your GitHub repository (do not upload an unextracted `.zip` file).
- **Linux Wayland Mouse/Keyboard Automation (`ydotool`) Fails**:
  - Ensure the [ydotool](https://github.com/ReimuNotMoe/ydotool) daemon (`ydotoold`) is running and your user belongs to the `input` group (`ls -l /dev/uinput`).
- **Microphone Not Detected on Fedora [PipeWire](https://pipewire.org/) or Windows 11**:
  - Run `python3 -c "from bajrang_core import AdvancedVoiceEngine; print(AdvancedVoiceEngine().list_microphones())"` to inspect detected input devices and verify microphone privacy permissions in OS Settings.
