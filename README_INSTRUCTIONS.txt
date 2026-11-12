========================================================================
  BAJRANG AI PRO — COMPLETE INSTALLATION & QUICK-START INSTRUCTIONS
  Created by Kaushik Ram Ravuru (@rkrworks) | CBIT Hyderabad
========================================================================

Thank you for downloading the Bajrang AI Pro Complete Bundle (.zip)!
Because modern browsers block downloading multiple individual files at
once, this single .zip archive contains every required script, installer,
dependency manifest, and configuration file for your system.

------------------------------------------------------------------------
1. HOW TO EXTRACT THIS .ZIP FILE
------------------------------------------------------------------------
- On Windows 11: Right-click the downloaded .zip file and click
  "Extract All...", then open the extracted folder.
- On Fedora Linux: Right-click the .zip file and select "Extract Here"
  (or run `unzip BajrangAI_*.zip -d ~/bajrang-ai && cd ~/bajrang-ai`).

------------------------------------------------------------------------
2. WINDOWS 11 INSTALLATION (ALL PACKAGES INCLUDED)
------------------------------------------------------------------------
Option A (Recommended — Smart Pre-Flight .EXE Installer):
  1. Double-click `BajrangAI_Pro_Setup.exe`.
  2. It automatically scans your PC first for Python 3.12, Winget,
     Ollama, and all required libraries (Pillow, PyAutoGUI, pyttsx3,
     numpy, sounddevice, faster-whisper, pystray, keyring).
  3. It skips anything already installed, installs ONLY the missing
     packages one by one, and creates a "Bajrang AI Pro" Desktop shortcut.

Option B (Batch or Python Setup Wizard):
  1. Double-click `setup_windows.bat` OR run in PowerShell/Terminal:
       pip install -r requirements-windows.txt
       python windows.py
  2. To run headless self-tests without audio hardware:
       python -m windows --self-test

------------------------------------------------------------------------
3. FEDORA WORKSTATION (GNOME / WAYLAND) INSTALLATION
------------------------------------------------------------------------
  1. Open a terminal inside the extracted folder and run:
       chmod +x setup_fedora.sh fedora.py
       ./setup_fedora.sh
  2. Or install the Python dependencies manually:
       pip3 install --user -r requirements-fedora.txt
       python3 fedora.py
  3. To install the GNOME Shell 45-49 Top-Bar Extension:
       python3 fedora.py --install-gnome-extension
  4. To run headless self-tests:
       python3 -m fedora --self-test

------------------------------------------------------------------------
4. USING YOUR OWN PRIVATE API KEY (100% FREE CLOUD MODE)
------------------------------------------------------------------------
- You can paste your own Google Gemini (`AIza...`), Groq (`gsk_...`),
  OpenRouter (`sk-or-...`), or OpenAI (`sk-...`) API key in the app top
  bar or via CLI:
    python windows.py --api-key YOUR_KEY
    python3 fedora.py --api-key YOUR_KEY
- Your API key is stored in your OS SecurityVault (Keyring / Windows
  DPAPI / Linux libsecret / 0600 local vault) and is NEVER written to
  plaintext settings.json.
========================================================================
