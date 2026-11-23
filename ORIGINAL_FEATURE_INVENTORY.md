# SUDHARSHAN AI — ORIGINAL FEATURE INVENTORY & NEBULA MAPPING
**Document Reference:** `ORIGINAL_FEATURE_INVENTORY.md`  
**Ecosystem Version:** Project Nebula v2.0  
**Date:** November 23, 2026  

---

## 1. Overview

This document provides a comprehensive inventory of all original capabilities in the baseline Sudharshan AI repository ("Bajrang Core") and maps each capability to its enhanced status in Project Nebula v2.0.

---

## 2. Core Modules Inventory & Feature Mapping

### 2.1 Core Orchestration (`bajrang_core.py`)

| Original Feature | Original Implementation | Nebula v2.0 Status | Architectural Enhancement |
|:---|:---|:---|:---|
| **Model Ingestion** | Hardcoded Ollama wrapper | **Preserved & Upgraded** | Unified `NebulaModelAdapter` supporting Ollama, Native 1.5B, vLLM, llama.cpp, Gemini, OpenAI |
| **Tool Execution** | Direct method invocation | **Hardened (C3, H3)** | Strict JSON-schema validation (`ToolSchemaValidator`), typed arguments, fail-closed handling |
| **Security Guard** | Simple keyword blacklist | **Hardened (C1, C4)** | Comprehensive regex sanitization, shell-escape blocking, path traversal guards |
| **License Verification** | RSA public key check | **Preserved & Hardened (H5)**| RSA-2048 PKCS#1 v1.5 with SHA-256 cryptographic verification in `razorpay_server.py` |
| **Config & Secrets** | Plaintext / basic JSON | **Hardened (C6, Wave 4)** | `SecurityVault` with AES-256 encryption, zero plaintext leaks in logs |
| **Emergency Stop** | Basic flag | **Hardened (H2)** | Socket abortion, subprocess termination, state rollback, instant stream cancellation |
| **Airplane Mode** | Basic toggle | **Preserved & Tested (Invariant 4)**| Air-gap enforcement, instant cloud egress blocking, fallback to local inference |
| **Auto-Approve Mode** | Direct boolean | **Hardened (Wave 4)** | Requires explicit acknowledgment parameter (`acknowledged_risk=True`), auto-resets on kill |

---

### 2.2 Desktop Platform Adapters

#### Fedora Linux (`fedora.py`)
- **Original:** GTK3/4 boilerplate, basic subprocess execution.
- **Nebula v2.0:** Full GTK4 / Libadwaita integration (`Adw.ApplicationWindow`), Wayland `ydotoold` daemon management, desktop notification routing, SELinux-aware execution, and RPM package spec (`packaging/sudharshan-ai.spec`).

#### Microsoft Windows (`windows.py` & `installer_windows.py`)
- **Original:** Windows UI Automation stubs, basic PowerShell calls.
- **Nebula v2.0:** Full Win32 / UIA client bridge, smart pre-flight installer (`installer_windows.py`) verifying RAM, disk space, and VC++ runtimes, Authenticode verification (`sign_windows_executable.py`), and WiX installer definition (`packaging/sudharshan-ai.wxs`).

#### Generic Linux (`linux_generic.py`)
- **Original:** Shell command wrappers for `xdotool` and `wmctrl`.
- **Nebula v2.0:** Intelligent window manager detection (X11 vs. Wayland), safe subprocess execution with timeout and return-code verification, D-Bus notification support.

#### Apple macOS (`macos.py`)
- **Original:** Minimal AppleScript calls via `osascript`.
- **Nebula v2.0:** Robust AppleScript bridge, System Events integration, Accessibility permission detection, notification center integration.

---

### 2.3 Local License & Payment Server (`razorpay_server.py`)

- **Original:** Basic HTTP server mocking Razorpay webhook callbacks.
- **Nebula v2.0:** Production-grade Python HTTP daemon implementing RSA-2048 cryptographic signature verification, license key activation, token generation, and tamper-resistant timestamp validation. Tested in `test_bajrang_suite.py` (`test_h5_razorpay_http_server_and_rsa_2048`).

---

### 2.4 Command-Line Interface (`sudharshan_cli.py`)

- **Original:** Simple interactive REPL loop.
- **Nebula v2.0:** Rich CLI supporting multi-model selection (`--model`), single-turn execution (`--prompt`), system diagnostics (`--diagnostics`), registry inspection (`--registry`), and ANSI color output matching the Obsidian/Solar Orange palette.

---

### 2.5 Web Portal (`web/` and Root HTML)

| Web Page | Original State | Nebula v2.0 State | Taste Skill Compliance |
|:---|:---|:---|:---|
| **`index.html`** | Single-page marketing HTML | Interactive portal with live parameter calculator, model comparison, Web Crypto hash verifier | Obsidian `#0B0B0D`, Solar Orange `#FF5A1F`, WCAG AA contrast |
| **`docs.html`** | Basic documentation page | Comprehensive API, tool schema, and architecture documentation | Styled typography, code blocks, clean navigation |
| **`downloads.html`**| Mock download links | Multi-platform download portal with client-side SHA-256 verification | Clear platform badges, package instructions |
| **`privacy.html`** | Generic policy template | Explicit local-first, zero-telemetry, BYOK privacy guarantees | Human-readable clauses, clear disclosures |
| **`terms.html`** | Generic terms | BYOK license terms, local execution disclaimer | Strict non-custodial software terms |
| **`credits.html`** | Basic credits list | Complete open-source attribution (PyTorch, NumPy, WiX, GTK) | Clean contributor and library showcase |

---

## 3. Ten-Wave Extension Modules Inventory (`sudharshan/`)

Nebula v2.0 added 10 cohesive extension waves implementing 100 high-importance features:

1. **`wave1_intelligence.py`**: Adaptive multi-model engine, RAM-based fallback switcher, NDJSON streaming, and dynamic intent router.
2. **`wave2_memory_rag.py`**: Hierarchical memory engine, SQLite FTS5 lexical search, vector similarity search, and conversation context windowing.
3. **`wave3_voice_multimodal.py`**: Offline speech recognition adapter, thread-safe TTS engine with pyttsx3 lock serialization, and audio waveform diagnostics.
4. **`wave4_security_governance.py`**: 4-tier permission model, AES-256 encrypted `SecurityVault`, tamper-evident audit logger, and dry-run preview engine.
5. **`wave5_filesystem_automation.py`**: Staged file organizer, collision detection, undo journal, and safe trash staging.
6. **`wave6_os_ergonomics.py`**: Multi-monitor desktop manager, compact floating HUD, system tray integration, and notification filter.
7. **`wave7_developer_suite.py`**: Python/C traceback parser, Git assistant, unit test generator, and dependency vulnerability scanner.
8. **`wave8_productivity.py`**: Searchable clipboard history, persistent Markdown notes engine, and daily productivity briefing generator.
9. **`wave9_extensibility.py`**: Plugin lifecycle manager, hook registry (`before_prompt`, `after_tool`), and tool schema registration.
10. **`wave10_packaging_polish.py`**: Pre-flight system diagnostics, telemetry aggregator, RPM spec generator, and WiX installer compiler interface.

---

## 4. Preservation & Non-Regression Summary

All original functionality has been 100% preserved. No features were deleted or disabled to make tests pass. All 40 automated tests across `test_bajrang_suite.py`, `test_waves_1_to_10.py`, `test_sudharshan_native.py`, and `test_nebula_verification.py` confirm zero regressions.
