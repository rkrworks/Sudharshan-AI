# SUDHARSHAN AI (Alpha v0.9) — INSTALLATION & TROUBLESHOOTING GUIDE

**Product**: Sudharshan AI (Alpha v0.9 • Sudharshan Core v0.9-alpha)  
**Author**: Kaushik Ram Ravuru (B.E. IT, Section IT-1, CBIT Hyderabad)  
**Repository**: `https://github.com/rkrworks/Sudharshan-AI.git`  
**Web Portals**: `https://sudharshan-ai.vercel.app` & `https://rkrworks.github.io/Sudharshan-AI/`  

---

## 1. System Requirements & Hardware Profiles

Sudharshan AI runs efficiently across a wide variety of hardware configurations:

| Profile | Target Specifications | Local Model | Screenshot Resolution | Context Depth |
| :--- | :--- | :--- | :--- | :--- |
| **Eco** | Dual-core CPU, 8 GB RAM, Integrated GPU | Llama 3.2 (3B) Q4 | 960px | 6 messages |
| **Balanced** (Default) | Quad-core CPU, 12–16 GB RAM | Mistral (7B) / Llama 3.2 | 1280px | 20 messages |
| **High** | 8+ core CPU, 16–32 GB RAM, Dedicated GPU | Llama 3.1 (8B) Q5 | 1920px | 40 messages |
| **Workstation** | 12+ cores, 32–64 GB RAM, RTX 3080/4080+ | CodeLlama (70B) / Qwen 2.5 | 1920px Native | 100+ messages |

---

## 2. Windows 11 Installation & Trust Verification

### Why Does Windows SmartScreen Flag New Apps?
Microsoft Defender SmartScreen blocks newly downloaded executables by default if they lack accumulated download reputation or if downloaded via browser (Mark-of-the-Web `Zone.Identifier`). Sudharshan AI includes an official **2048-bit RSA X.509 Code-Signing Certificate** (`Sudharshan_AI_CodeSigning.cer`) and a valid Microsoft Authenticode digital signature embedded into all executables.

### Method A — One-Click Trusted Installation (Recommended)
1. Download the Windows Release archive (`Sudharshan_AI_Windows_v0.9-alpha.zip`) and extract it.
2. **Step 1 (Register Certificate)**: Right-click `install_certificate.bat` and select **Run as Administrator**.
   - This registers `Sudharshan AI Desktop Authority` into your Windows **Trusted Root** and **Trusted Publishers** store via `certutil`.
3. **Step 2 (Unblock Files)**: Double-click `unblock_files.bat` to remove browser download locks.
4. **Step 3 (Launch Setup)**: Run `setup_windows.bat` or `Sudharshan_AI_Setup.exe`.
   - Windows Defender and SmartScreen will recognize the trusted publisher and execute cleanly without warnings!

### Method B — Direct Smart Batch Setup
Run `setup_windows.bat`. It automatically unblocks downloaded files, verifies Python 3.10+, installs required libraries via WinGet/pip, configures Ollama, and launches the Windows Assistant HUD.

### Method C — Standalone Python Execution
```cmd
pip install -r requirements_windows.txt
python windows.py
```

### Uninstallation (Windows)
```cmd
setup_windows.bat --uninstall
```
*Note*: The SQLite database (`history.db`) is safely preserved so you never lose conversation history or memory facts.

---

## 3. Fedora Workstation (GNOME 45–49 / Wayland)

### Automated Setup
1. Clone the repository and execute `setup_fedora.sh`:
   ```bash
   git clone https://github.com/rkrworks/Sudharshan-AI.git
   cd Sudharshan-AI
   chmod +x setup_fedora.sh fedora.py
   ./setup_fedora.sh
   ```
2. Launch the desktop assistant:
   ```bash
   python3 fedora.py
   ```
   Or use the exported runtime script:
   ```bash
   ~/sudharshan-ai/run.sh
   ```

### Emergency Stop (Kill-Switch)
- Press `Ctrl+Shift+K` on Windows.
- On Fedora, execute:
  ```bash
  python3 fedora.py --kill-running
  ```

---

## 4. Web Portal Deployment (Vercel & GitHub Pages)

- **Vercel Deployment**:
  The repository is configured via `vercel.json` with `"outputDirectory": "web"`.
  Ensure your Vercel project root directory is set to repository root. All static assets (`index.html`, `privacy.html`, `terms.html`, `credits.html`, `share.jpg`, `favicon.svg`, `portal_app.js`, and `assets/`) reside in the isolated `web/` folder.
- **GitHub Pages**:
  The `.github/workflows/deploy.yml` workflow automatically builds and uploads the `web/` directory on every push to `main`.

---

## 5. Troubleshooting Common Issues

### Issue 1: Vercel 404 on Download Links
- **Root Cause**: Old links targeted root `.exe` or `.zip` files not bundled in the static web deployment.
- **Fix**: All links in `web/index.html` now point canonically to `https://github.com/rkrworks/Sudharshan-AI/releases/latest`.

### Issue 2: Wayland Input Automation (`ydotool`) Fails
- **Root Cause**: User lacks `/dev/uinput` write permissions or `ydotoold` daemon is stopped.
- **Fix**: Ensure your user is in the `input` group:
  ```bash
  sudo usermod -aG input $USER
  sudo systemctl --user start ydotoold-bajrang.service
  ```

### Issue 3: Microphones Not Detected
- **Verification**: Check microphone availability:
  ```bash
  python3 -c "from bajrang_core import SpectralVoiceSpotter; print(SpectralVoiceSpotter.SAMPLE_RATE)"
  ```
  Ensure microphone permissions are granted in Windows Privacy Settings or GNOME Control Center.

### Issue 4: SQLite Database Locked
- **Fix**: Sudharshan AI uses Write-Ahead Logging (`WAL`) mode to support concurrent reads. If a lock occurs after a hard reboot, run the self-test diagnostics to recover:
  ```bash
  python3 -m bajrang_core --self-test
  ```
