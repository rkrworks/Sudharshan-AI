# Bajrang AI Pro (v6.0) — System Architecture Documentation (`ARCHITECTURE.md`)

## 1. Layered Modular Architecture
Bajrang AI Pro v6.0 separates cross-platform intelligence, storage, voice DSP, and security from OS-specific desktop UIs and web presentation:

1. **Core Intelligence & Security Layer (`bajrang_core.py`)**:
   - **`SecurityVault`**: Abstracts OS-native secret storage (`keyring`, Windows DPAPI `System.Security.Cryptography.ProtectedData`, Linux `secret-tool` `libsecret`, and `0600` encrypted local vault fallback).
   - **`AsymmetricLicenseVerifier`**: Verifies `BAJRANG-V6-<PAYLOAD>.<SIG>` certificates using public-key modular exponentiation (`E = 65537`) without shipping private keys in client code.
   - **`DatabaseMigrationManager` & `LongTermMemoryStore`**: Manages versioned SQLite3 migrations (`v1` sessions/messages → `v2` categorized `memories` → `v3` `task_runs` and `security_audit_log`) with `WAL` journaling and automatic PII redaction (`redact_sensitive_text`).
   - **`ModularAIRouter`**: Classifies prompts into `SIMPLE`, `MODERATE`, `COMPLEX_REASONING`, or `MULTIMODAL_VISION`, selects the optimal model per provider (`gemini_argon`, `ollama`, `groq`, `openrouter`, `openai`) and `PerformanceProfile` (`eco`, `balanced`, `high`), probes provider health/latency, executes exponential-backoff retries across a configurable fallback chain, and validates tool calls via `ToolSchemaValidator`.
   - **`AutonomousTaskPlanner`**: Decomposes multi-step user goals (such as scanning `~/Downloads`, categorizing files into `Documents`, `Images`, `Installers`, `Archives`, `Code`, and identifying byte-exact duplicates via size bucketing + SHA-256 hashing), enforces an explicit `awaiting_permission` confirmation gate before destructive/file-moving steps, supports mid-run cancellation, and verifies post-action file integrity.
   - **`AdvancedVoiceEngine`**: Implements spectral noise floor subtraction, RMS dBFS + Zero-Crossing Rate (ZCR) Voice Activity Detection, continuous listening with a configurable wake word (`"hey bajrang"`), barge-in TTS interruption, 8-band Goertzel Spectral-DTW command matching (<8ms latency), neural STT (`faster-whisper`) + OS speech recognition fallback, microphone device enumeration, and configurable TTS voice/rate/language.
   - **`CrossPlatformComputerUse`**: Executes and verifies desktop actions (`list_open_windows`, `focus_window`, `launch_application`, `close_application`, `capture_and_analyze_screen`, `click_point_verified`, `type_text_verified`, `scroll_verified`) using Win32 `ctypes.windll.user32` / [PyAutoGUI](https://pypi.org/project/PyAutoGUI/) on Windows 11 and [ydotool](https://github.com/ReimuNotMoe/ydotool) / `gdbus` / `wmctrl` / `grim` on Fedora GNOME Wayland.

2. **Platform Desktop Applications**:
   - **Windows 11 Desktop Application (`bajrang_windows.py`)**: Commercial dark/light Floating HUD + Always-On-Top Mini Pill Overlay (`tkinter` / `ttk`) with Conversation Sidebar, Memory Manager, Autonomous Task Execution Panel, Provider Health Dashboard, Voice Activity Visualizer, and Performance Profile selector.
   - **Fedora Linux GNOME/Wayland Application (`bajrang_llama32.py`)**: Native [PyGObject GTK4](https://pygobject.gnome.org/) / Libadwaita desktop HUD + [GNOME Shell 45–49 ESM](https://gjs.guide/extensions/upgrading/gnome-shell-45.html) Top-Bar Extension generator (`bajrang-ai@fedora.local`) and [PipeWire](https://pipewire.org/) audio integration.

3. **Smart Installers & Server Backend**:
   - **Windows 11 Smart Installer (`installer_windows.py`, `BajrangAI_Pro_Setup.exe`, `setup_windows.bat`)**: Pre-flight dependency scanner, selective package installer, environment validator, diagnostic logger (`install_diagnostics.log`), Desktop shortcut creator, and clean uninstaller (`--uninstall`).
   - **Fedora Workstation Installer (`setup_fedora.sh`, `requirements_fedora.txt`)**: Non-root safe setup with OS/Wayland detection, PipeWire verification, optional `/dev/uinput` rule configuration, GNOME extension installation, and `--uninstall` support.
   - **Razorpay Order & License Signing Server (`razorpay_server.py`)**: Reference backend service integrating with the [Razorpay UPI & Orders API](https://razorpay.com/upi-payment-gateway-india/) (`POST /v1/orders` and `X-Razorpay-Signature` HMAC-SHA256 verification).

4. **Modular Product Web Portal (`index.html`, `portal_styles.css`, `portal_app.js`)**:
   - Clean, responsive product website with modular CSS and JavaScript assets, clear separation between interactive browser demos and desktop-only features, zero hardcoded personal data or fabricated revenue metrics, BYO API configuration generator, and real Razorpay Checkout order flow.
