# ⚡ Bajrang AI Pro (Argon v6.0) — Cross-Platform Voice & Autonomous Desktop AI Assistant

**Bajrang AI Pro v6.0** is a privacy-first, security-hardened personal AI desktop assistant engineered for **Windows 11** and **Fedora Workstation (GNOME / Wayland)**.

## 🌟 What's New in v6.0
1. **Modular Multi-Provider AI Router (`bajrang_core.py`)**:
   - Automatic task-complexity routing (`SIMPLE`, `MODERATE`, `COMPLEX_REASONING`, `MULTIMODAL_VISION`) across **Google Gemini Argon** (`gemini-2.5-pro` / `gemini-2.5-flash`), local [Ollama Llama 3.2](https://ollama.com/library/llama3.2) (`bajrang-llama3.2`), **Groq**, **OpenRouter**, and **OpenAI** with automatic provider fallback, health checks, and exponential-backoff retries.
2. **Long-Term SQLite3 Memory with Schema Migrations (`v1` → `v3`)**:
   - Stores searchable `preference`, `project`, `fact`, and `task_history` memories in `history.db` (`WAL` mode, `0600` permissions) with automatic PII/credential redaction guardrails.
3. **Autonomous Multi-Step Task Planner & Restrictive Executor**:
   - Plans and executes multi-step workflows (such as scanning `~/Downloads`, separating `Documents`, `Images`, `Installers`, `Archives`, and `Code`, and identifying exact duplicates via SHA-256 hashing), pauses at an explicit permission gate before moving or deleting files, and verifies post-action integrity.
4. **Advanced Hybrid Voice Engine**:
   - Continuous listening mode with configurable wake word (`"hey bajrang"`), barge-in TTS interruption, spectral noise floor subtraction + RMS/ZCR VAD, 8-band Goertzel Spectral-DTW command recognition, `faster-whisper` / Windows SAPI / [PipeWire](https://pipewire.org/) STT, microphone selection, and configurable TTS speed/language.
5. **Verified Computer-Use & Security Hardening**:
   - Genuine window enumeration, focus switching, screen analysis, and input automation via Win32 `user32.dll` + [PyAutoGUI](https://pypi.org/project/PyAutoGUI/) on Windows 11 and [PyGObject GTK4](https://pygobject.gnome.org/) + [ydotool](https://github.com/ReimuNotMoe/ydotool) + [GNOME Shell 45–49 ESM](https://gjs.guide/extensions/upgrading/gnome-shell-45.html) on Fedora Wayland.
   - OS credential storage (`SecurityVault` via `keyring` / Windows DPAPI / Linux `libsecret`), strict JSON Schema tool validation (`shell=False`), and server-side [Razorpay Orders & RSA Public-Key License Verification](https://razorpay.com/upi-payment-gateway-india/) (`razorpay_server.py`).

## 🚀 Quick Start
- **Windows 11**: Run `BajrangAI_Pro_Setup.exe` or `python installer_windows.py` (or `.\setup_windows.bat`).
- **Fedora Workstation**: Run `chmod +x setup_fedora.sh && ./setup_fedora.sh`.
- **Run Automated 15-Domain Test Suite**:
```bash
python3 test_bajrang_suite.py
```
