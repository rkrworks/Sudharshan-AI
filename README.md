# Sudharshan AI (Alpha v0.9 • Hardened Core) — Cross-Platform Desktop Assistant

Sudharshan AI (Alpha Edition, formerly Bajrang AI Pro) is a modular, security-hardened desktop AI assistant for **Windows 11** (`windows.py`, Tkinter + Win32 `ctypes`) and **Fedora Linux** (`fedora.py`, GTK4/Libadwaita + Wayland/PipeWire) built on a single shared core (`bajrang_core.py`).

## Architecture Overview

- **`bajrang_core.py` (Shared Core Package)**:
  - `AsymmetricLicenseVerifier` & `LicenseManager`: 2048-bit RSA public-key certificate verification (`BAJRANG-V6-<payload>.<sig>`).
  - `SecurityVault` & `ConfigManager`: OS keyring / Windows DPAPI / `secret-tool` per-provider API key storage; strips secrets from `settings.json`.
  - `SafetyGuard` & `ShellRunner`: Zero-argument application launcher allowlist (`shell=False`) and order-independent hotkey blocklist.
  - `ToolSchemaValidator` & `BajrangEngine`: Strict schema validation, confirmation queue (`pending_actions` / `confirm_pending_actions()`), and session-pinned prompt execution.
  - `AutonomousTaskPlanner`: Non-destructive file organizer with collision-free renaming (`report_1.pdf`), `.bajrang_trash/<plan_id>/` staging, `undo_plan()`, and per-file cancellation checks.
  - `ModularAIRouter`: Provider-scoped API key affinity (`is_key_compatible_with_provider`) and `x-goog-api-key` header authentication for Gemini.
- **`windows.py` (`bajrang_windows.py`)**:
  - Windows 11 adapter and Tkinter HUD with `queue.Queue` main-thread UI dispatching, global `GetAsyncKeyState` kill-switch polling (`Ctrl+Shift+K` / `Pause`), `VK_SHIFT` typing support, and non-blocking SAPI5 barge-in TTS.
- **`fedora.py` (`bajrang_llama32.py`)**:
  - Fedora Workstation (GNOME / Wayland) adapter with PipeWire audio capture, UNIX domain kill-switch socket (`/tmp/bajrang_kill_<uid>.sock`), complete evdev keycode mapping, and GNOME Shell 45–49 extension installer.
- **`razorpay_server.py`**:
  - Multi-threaded HTTP server (`ThreadingHTTPServer`) for order creation, HMAC-SHA256 payment verification, server-authenticated admin approvals, and 2048-bit RSA `BAJRANG-V6-` certificate signing.
- **`installer_windows.py`**:
  - Consent-gated Windows pre-flight scanner, dependency installer, and clean uninstaller (`--uninstall` purges `SecurityVault` secrets and user configuration).
- **`web/index.html`**:
  - Isolated static web portal (`vercel.json` / `deploy.yml` serve only `web/`).

## Running Self-Tests

Every module includes a headless self-test suite that runs on any machine without audio or display hardware:

```bash
python3 -m bajrang_core --self-test
python3 -m windows --self-test
python3 -m fedora --self-test
python3 razorpay_server.py --self-test
python3 installer_windows.py --self-test
python3 test_bajrang_suite.py
```
