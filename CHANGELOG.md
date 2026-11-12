# Bajrang AI Pro — Detailed Engineering Changelog (`CHANGELOG.md`)

## v6.0.0 — Argon Production Release (2026-11-11)

### Architectural & Core Engine Upgrades (`bajrang_core.py`)

* **Unified Zero-Duplication Core (`bajrang_core.py`)**: Extracted \~1,500 lines of duplicated logic from `bajrang_windows.py` and `bajrang_llama32.py` into a shared, strictly typed core module.

* **Modular AI Router (`ModularAIRouter`)**: Added task complexity classification (`SIMPLE`, `MODERATE`, `COMPLEX_REASONING`, `MULTIMODAL_VISION`), automatic model selection across Google Gemini Argon (`gemini-2.5-pro` / `gemini-2.5-flash`), [Ollama Llama 3.2](https://ollama.com/library/llama3.2), Groq (`llama-3.3-70b-versatile`), OpenRouter, and OpenAI, provider health/latency checks (`check_provider_health`), exponential backoff retries, and configurable provider fallback chains.

* **Long-Term SQLite Memory & Migrations (`DatabaseMigrationManager`, `LongTermMemoryStore`)**: Added versioned schema migrations (`v1` → `v3`) with `WAL` mode, categorized long-term memories (`preference`, `project`, `fact`, `task_history`), full CRUD and search, context window injection, and automatic PII redaction guardrails (`redact_sensitive_text`).

* **Autonomous Multi-Step Task Planner (`AutonomousTaskPlanner`)**: Implemented multi-step folder inspection, file categorization (`Documents`, `Images`, `Installers`, `Archives`, `Code`, `AudioVideo`), size-bucketed SHA-256 duplicate file detection, explicit `awaiting_permission` confirmation gates before destructive operations, mid-task cancellation, and post-action verification.

### Security & Privacy Remediation (`SECURITY_AUDIT.md`, `razorpay_server.py`)

* **Eliminated Hardcoded Client Secrets**: Removed `SECRET_SALT` from client code and replaced symmetric client-side key generation with `AsymmetricLicenseVerifier` (RSA public-key verification) and `razorpay_server.py` (server-side [Razorpay Orders & Webhook HMAC-SHA256](https://razorpay.com/upi-payment-gateway-india/) verification).

* **OS Credential Vault (`SecurityVault`)**: Replaced plaintext API key storage in `config.json` with `keyring`, Windows DPAPI (`ProtectedData`), Linux `secret-tool` (`libsecret`), and `0600` encrypted local vault fallback.

* **Restrictive Tool Allowlist (`ToolSchemaValidator`)**: Replaced `shell=True` command execution and substring blocklists with strict JSON Schema validation, `shell=False` execution, user-directory boundary enforcement, and forbidden hotkey blocking.

### Voice, Computer-Use, Installers & Web Portal

* **Advanced Voice Engine (`AdvancedVoiceEngine`)**: Added continuous listening mode, configurable wake word (`"hey bajrang"`), barge-in TTS interruption, spectral noise floor subtraction + RMS/ZCR VAD, preserved 8-band Goertzel Spectral-DTW command matching, microphone enumeration, and configurable TTS rate/language.

* **Verified Computer-Use (`CrossPlatformComputerUse`)**: Added Win32 `EnumWindows` / `SetForegroundWindow` / `GetCursorPos` verification on Windows 11 and [ydotool](https://github.com/ReimuNotMoe/ydotool) / `wmctrl` / `gdbus` / `grim` integration on Fedora GNOME Wayland.

* **Smart Installers (`installer_windows.py`, `BajrangAI_Pro_Setup.exe`, `setup_windows.bat`, `setup_fedora.sh`)**: Added `--uninstall` clean removal, diagnostic logs (`install_diagnostics.log`), and non-root execution defaults.

* **Modular Web Portal (`index.html`, `portal_styles.css`, `portal_app.js`)**: Removed hardcoded personal emails/UPI handles and fabricated subscriber/MRR claims, extracted modular CSS/JS assets, and added interactive demos for the v6.0 Autonomous Task Planner and Long-Term Memory Inspector.