# SUDHARSHAN AI (ALPHA v0.9) — MASTER TASK LIST

**Repository**: `https://github.com/rkrworks/Sudharshan-AI`  
**Status**: Active Production Hardening  

---

## 1. Core Architecture & Safety (Phases 1, 2, 7, 11)
- [x] **Audit Codebase**: Eliminate dead legacy trees, obsolete symmetric hashing, and untracked code.
- [x] **Purge Credentials**: Eliminate all `.key`, `.pfx`, `.pem`, and certificate signing files from git working tree.
- [x] **Enforce RSA 2048-bit Licenses**: Verify all licenses using `AsymmetricLicenseVerifier` and reject `SECRET_SALT` tokens.
- [x] **Isolate API Keys**: Scope BYO API keys to providers (`gemini_argon`, `groq`, `openrouter`, `openai`) via `SecurityVault` and DPAPI/keyring.
- [x] **Enforce Action Allowlist**: Validate all desktop actions through `ToolSchemaValidator` and reject shell metacharacter trampolines.
- [x] **Platform Capability Registry**: Implement central `PlatformCapabilityMatrix` covering Windows, Fedora, generic Linux, and macOS.
- [x] **Structured Audit Logging**: Record local system audit events in SQLite WAL (`StructuredAuditLogger`) with digest generator.

## 2. Desktop Platforms & Reliability (Phases 3, 5, 6, 14)
- [x] **Fix Windows Ollama Connectivity**: Implement 10-point diagnostic check, autostart via `@staticmethod`, and friendly offline guidance card.
- [x] **Windows Tkinter HUD Redesign**: Integrate Solar Orange (`#ff6b1a`) / Obsidian Black (`#050505`), session management, and emergency stop.
- [x] **Eliminate Linux Windows Fallback**: Remove fallback Tkinter execution from `fedora.py`; provide explicit `--doctor` preflight report.
- [x] **Generic Linux Adapter (`linux_generic.py`)**: Distro detection for `dnf`, `apt`, `pacman`, `zypper`, `apk` across Wayland/X11.
- [x] **macOS Adapter (`macos.py`)**: Implement native Cocoa/Quartz/AppleScript hooks for screenshots, TTS, clipboard, and notifications.
- [x] **Real vs Mocked Validation**: Document real execution on Linux workstation vs mocked macOS/Windows environments.

## 3. Product Features & File Operations (Phases 8, 9, 10)
- [x] **Natural-Language File Engine**: Parse 20+ variations of user requests (move, copy, organize, deduplicate, rename) with structured plans.
- [x] **File Operation Safety Guard**: Prevent path traversal, protect system root/dotfiles, quarantine instead of permanent delete, and support full undo manifests.
- [x] **Session Safe Mode**: Enforce read-only assistant mode preventing mutating desktop actions.
- [x] **Multi-Step Task Chaining**: Sequential prompt planner for `"list windows then status"`.
- [x] **Session Markdown Export**: Export formatted conversation logs to `Downloads/`.
- [x] **Daily Activity Digest**: Summarize file modifications and system activities.
- [x] **Network-Aware Mode**: Offline vs online detection with graceful local degradation.
- [x] **First-Run Setup Wizard**: Onboarding presets (`local`, `byo_gemini`, `safe`).
- [x] **Global Dry-Run Mode**: Full tool simulation with detailed execution telemetry.
- [x] **Session Recovery**: Heartbeat tracking to detect unclean shutdowns.
- [x] **Automated Diagnostic Bug Report**: Generate sanitized markdown bug reports.

## 4. Web, Deployment & Distribution (Phases 4, 12, 13, 15)
- [x] **Vercel Schema Conformance**: Update `vercel.json` with clean `$schema`, `cleanUrls`, and `outputDirectory: web`.
- [x] **Downloads Portal**: Create `web/downloads.html` with honest platform readiness badges and direct GitHub download links.
- [x] **Checksum Integrity**: Maintain synced `SHA256SUMS` and `web/SHA256SUMS`.
- [x] **Automated Test Battery**: 20 comprehensive unit and integration tests passing in `test_bajrang_suite.py`.
- [x] **Documentation & Tracking**: Maintain `PROGRESS.md`, `ENGINEERING_DECISIONS.md`, and `KNOWN_LIMITATIONS.md`.
