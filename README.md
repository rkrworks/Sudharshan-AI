# Bajrang AI — Cross-Platform Desktop Assistant (Windows & Fedora Linux)

Bajrang AI is a local-first Python desktop assistant for **Windows 11** (`windows.py`) and **Fedora Linux (GNOME / Wayland)** (`fedora.py`), built around a single shared core library (`bajrang_core.py`).

## 1. Repository Structure
- **`bajrang_core.py`**: Shared core package containing configuration (`ConfigManager`), OS credential storage (`SecurityVault`), SQLite chat/memory persistence (`LocalChatStorage`), fail-closed command allowlisting (`SafetyGuard`, `ShellRunner`, `KillSwitchManager`), model client (`UnifiedModelClient` for local [Ollama Llama 3.2](https://ollama.com/library/llama3.2) and BYO cloud API keys), folder organization planner (`AutonomousTaskPlanner`), offline keyword spotter (`SpectralVoiceSpotter`), and the unified `BajrangEngine`.
- **`windows.py` (`bajrang_windows.py`)**: Thin Windows platform adapter (`WindowsPlatformAdapter` using [PyAutoGUI](https://pypi.org/project/PyAutoGUI/) / Win32 `ctypes.windll.user32`, `PIL.ImageGrab`, and `sounddevice` / `winmm.dll`) and Tkinter desktop HUD (`WindowsTkinterHUD`).
- **`fedora.py` (`bajrang_llama32.py`)**: Thin Fedora GNOME Wayland adapter (`FedoraWaylandAdapter` using [ydotool](https://github.com/ReimuNotMoe/ydotool), GNOME Shell D-Bus / `gnome-screenshot` / `grim`, and [PipeWire](https://pipewire.org/) `pw-record` / ALSA `arecord`), [GNOME Shell 45–49 ESM](https://gjs.guide/extensions/upgrading/gnome-shell-45.html) extension generator, and [PyGObject GTK4](https://pygobject.gnome.org/) HUD.
- **`requirements-common.txt` / `requirements-windows.txt` / `requirements-fedora.txt`**: Split dependency manifests.

## 2. What Works Today vs. Experimental / Optional Components

| Subsystem | Status | Honest Technical Scope & Requirements |
| :--- | :--- | :--- |
| **Shared Core, SQLite History & Memory (`bajrang_core.py`)** | **Working (Production)** | Stores chat sessions, messages, and categorized memories in SQLite3 (`WAL` mode) with schema migrations (`v1`→`v3`) and automatic API key redaction. |
| **Model Inference (`UnifiedModelClient`)** | **Working (Production)** | Connects to local [Ollama](https://ollama.com/library/llama3.2) (`http://127.0.0.1:11434`) or cloud endpoints (Google Gemini, Groq, OpenRouter, OpenAI) using keys stored in `SecurityVault`. |
| **Safety Allowlist & Kill-Switch (`SafetyGuard`, `KillSwitchManager`)** | **Working (Production)** | Fails closed (`strict_allowlist=True`, `shell=False`), blocks shell metacharacters and privilege escalation, and terminates child processes on `Ctrl+Escape`. |
| **Folder Organizer (`AutonomousTaskPlanner`)** | **Working (Production)** | Categorizes files in user directories, detects exact duplicates via SHA-256 hashing, and requires explicit confirmation (`user_confirmed=True`) before moving or deleting files. |
| **Voice Recognition (`SpectralVoiceSpotter`)** | **Experimental / Hybrid** | Requires `faster-whisper` or `vosk` for general speech-to-text transcription. When neither is installed, falls back to a lightweight 8-band Goertzel + DTW keyword spotter suitable only for matching short enrolled command templates. |
| **Wayland & Win32 Input Automation** | **Environment-Dependent** | Windows input uses `PyAutoGUI` or Win32 `user32.dll`. Fedora Wayland input requires `ydotool` and a running `ydotoold` daemon with `/dev/uinput` permissions. |
| **Licensing (`LicenseManager`)** | **Demo / Server-Dependent** | Supports RSA public-key verification (`BAJRANG-V6-...`) when paired with an external signing server (`razorpay_server.py`); local `generate_key()` tokens are explicitly marked `[DEMO_ONLY_UNVERIFIED]`. |

## 3. Installation & Running Self-Tests
Install the dependencies for your platform:
```bash
# Common only (headless / tests)
pip install -r requirements-common.txt

# Windows 11
pip install -r requirements-windows.txt

# Fedora Workstation
pip install -r requirements-fedora.txt
```

Run the headless self-tests (requires no audio hardware or display server):
```bash
python3 -m bajrang_core --self-test
python3 -m windows --self-test
python3 -m fedora --self-test
python3 test_bajrang_suite.py
```
