# SUDHARSHAN AI — ENGINEERING CHANGELOG (`CHANGELOG.md`)

## v0.9.0-alpha — Sudharshan Alpha Release (2026-11-13)

### Rebranding & Repository Recovery
* **Brand Evolution**: Rebranded project to **Sudharshan AI (Alpha v0.9)** by Kaushik Ram Ravuru (CBIT Hyderabad).
* **Remote Synchronization**: Recovered repository after rename to `https://github.com/rkrworks/Sudharshan-AI.git`.
* **Vercel & Pages Recovery**: Synced isolated `web/` directory with `vercel.json` (`outputDirectory: "web"`) and GitHub Actions workflow (`deploy.yml`). Replaced non-existent local file download links with canonical GitHub Release links.

### Core Architectural Features (`bajrang_core.py`)
* **Feature 1: Intelligent Conversation Manager**: Added SQLite migration v4 (`category`, `is_pinned`), full-text search (`search_conversations`), session pinning (`pin_session`), session renaming (`rename_session`), and structured export/import in Markdown and JSON.
* **Feature 2: Advanced Voice Studio**: Implemented 8-band Goertzel Spectral-DTW filter bank, spectral noise floor subtraction via ambient profiling, configurable wake words (`set_wake_word`), and variable TTS speech rate.
* **Feature 3: Visual Automation Builder**: Built `AutomationBuilder`, `Workflow`, and `WorkflowStep` with condition evaluation (`file_exists`, `platform_is`), confirmation gating, and SQLite run audit logs in `workflow_runs`.
* **Feature 4: Advanced Memory Management**: Added Jaccard similarity memory deduplication (`find_duplicate_memories`), JSON export, importance scoring (1–5), and contextual prompt retrieval.
* **Feature 5: Local AI Model Manager**: Implemented `LocalAIModelManager` with curated open-weights catalog, Ollama daemon probing (`/api/tags`), and hardware tier compatibility checking (Eco, Balanced, High, Workstation).
* **Feature 6: System Intelligence Dashboard**: Implemented authentic hardware telemetry (`SystemIntelligenceDashboard`) capturing CPU, RAM, GPU, storage, battery, network, rolling history buffer, and high-load alerts without data fabrication.
* **Feature 7: Intelligent Provider Dashboard**: Added multi-cloud router with live round-trip latency probing, token accounting, and cost-optimized routing recommendations.
* **Feature 9: Developer Copilot**: Built `DeveloperCopilot` with safe directory traversal inspection, unified diff generation via `difflib`, and traceback error analysis.
* **Feature 10: Diagnostics & Recovery Centre**: Implemented `DiagnosticsRecoveryCentre` with 6-point pre-flight health checks, PRAGMA database integrity checks, safe backup/restore, and exportable reports.

### Desktop HUDs (`windows.py` & `fedora.py`)
* **Feature 8: Universal Floating Assistant**:
  - Added Always-on-Top toggle (`-topmost`) on Windows Tkinter HUD.
  - Added Compact Mode toggle (collapses window into 480x140 floating micro-HUD).
  - Added Clipboard Assistant (`on_clipboard_assist`) for instant code explanation, summary, and bug fixing.
  - Added Session Search bar, Pin toggle, Rename prompt, and Markdown Export button.
* **Branding & Theme Alignment**: Aligned color tokens with Obsidian Black (`#050505` / `#0f0c0a`) and Solar Orange (`#ff6b1a`).

### Forensic Bug Fixes & Hygiene
* **BUG-001**: Resolved broken local download links causing 404s on Vercel; mapped to GitHub Releases.
* **BUG-002**: Replaced legacy `setup_fedora.bash` with a clean wrapper redirecting to hardened `setup_fedora.sh`.
* **BUG-003 & BUG-004**: Eliminated SQLite connection resource leaks in `DatabaseMigrationManager` and `FulfillmentDatabase` using `@contextlib.contextmanager` with explicit `conn.close()`.
* **BUG-005**: Closed dangling HTTPError response stream in `razorpay_server.py`.
* **BUG-006 & BUG-007**: Updated deployment workflows and Windows batch scripts with Sudharshan AI branding.
* **BUG-008**: Added missing `AgentState.OFFLOADED` status badge color to desktop HUD.
* **BUG-009 & BUG-010**: Unified taste-skill color tokens and author credits across `privacy.html`, `terms.html`, and `credits.html`.

---

## v6.0.0 — Argon Release (2026-11-11)

### Architectural & Core Engine Upgrades
* Unified Zero-Duplication Core (`bajrang_core.py`) extracting shared logic.
* Modular AI Router (`ModularAIRouter`) with task classification and fallback chains.
* Long-Term SQLite Memory & Migrations (`DatabaseMigrationManager`, `LongTermMemoryStore`).
* Autonomous Multi-Step Task Planner (`AutonomousTaskPlanner`) with `.bajrang_trash/` staging.
* Asymmetric RSA-2048 Cryptographic License Verification (`AsymmetricLicenseVerifier`).
* SecurityVault hardware credential storage with Windows DPAPI and Linux libsecret.
