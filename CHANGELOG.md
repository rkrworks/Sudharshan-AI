# SUDHARSHAN AI — ENGINEERING CHANGELOG (`CHANGELOG.md`)

## v1.0.0 — Full 10-Wave Release (Features 1–100) (2026-11-19)

* **Waves 1–3**: Added `sudharshan/wave1_intelligence.py`, `sudharshan/wave2_memory_rag.py`, and `sudharshan/wave3_voice_multimodal.py` (RAM-aware Qwen 3.5/Phi-4 orchestration, NDJSON streaming, SQLite hybrid BM25+vector RAG, encrypted memory vault, Goertzel+VAD wake word, whisper.cpp, Piper TTS barge-in, OCR-to-clipboard).
* **Waves 4–6**: Added `sudharshan/wave4_security_governance.py`, `sudharshan/wave5_filesystem_automation.py`, and `sudharshan/wave6_os_ergonomics.py` (hash-chained audit log, 4-tier permissions, rollback snapshots, shell sanitizer, secret/PII redactor, airplane-mode egress, ZipSlip-safe archives, quarantine trash, command palette, thermal HUD, cron/systemd generator).
* **Waves 7–9**: Added `sudharshan/wave7_developer_suite.py`, `sudharshan/wave8_productivity.py`, `sudharshan/wave9_extensibility.py`, and `sudharshan_cli.py` (Git assistant, AST symbol indexer, compose validator, backlink vault, SM-2 flashcards, MCP JSON-RPC client, sandboxed plugin SDK, AST security scanner, localhost bearer API, CLI companion).
* **Wave 10**: Added `sudharshan/wave10_packaging_polish.py`, native Fedora RPM (`packaging/sudharshan-ai.spec`), Flatpak (`packaging/com.rkrworks.SudharshanAI.yml`), Windows WiX MSI (`packaging/sudharshan-ai.wxs`), Precision Obsidian & Solar Orange interactive docs portal (`web/docs.html`, `docs.html`), updated `SHA256SUMS`, and full 100-feature test suite (`test_waves_1_to_10.py`).

## v1.0.0-phase0 — Repo Hygiene, Bug Fixes & Adaptive Multi-Model Engine (2026-11-19)

### Asset Hygiene & Bundle Slimming
* Audited and pruned `assets/` and `web/assets/` from 1,616 files (33.02 MB) each down to 50 actively imported files (774.7 KB) each — removing 3,132 unused demo/lab/gallery files, third-party brand SVGs, and unreferenced shaders (64.52 MB total reduction) with zero broken references.

### Adaptive Multi-Model Local Engine (`bajrang_core.py`)
* Replaced `llama3.2` as the default LLM with `AdaptiveModelEngine`:
  - Primary Model: `qwen3.5:4b` (Q4_K_M, structured JSON tool calling + native vision)
  - Low-RAM Fallback: `qwen3.5:2b-q4_K_M` (automatic downgrade when free RAM < 2.5 GB via `HardwareProfiler.get_free_ram_gb()`)
  - Reasoning Alternate: `phi4-mini`
  - Fast Intent Router: `qwen3.5:0.8b`
  - Local Semantic Embeddings: `qwen3-embedding:0.6b` (low-RAM fallback: `embeddinggemma-2:270m`)
  - On-Demand OCR: `glm-ocr`
* Updated `LocalAIModelManager.CURATED_CATALOG`, `HardwareProfiler.TIER_SPECS`, `ModularAIRouter`, `fedora.py`, `installer_windows.py`, `setup_fedora.sh`, `setup_windows.bat`, and static web portals to default to `qwen3.5:4b`.

### Bug Fixes, Technical Debt & Design Tokens
* **BUG-008**: Fixed `NetworkConnectivityDetector.is_online()` mutating global `socket.setdefaulttimeout()` and added RFC 5737 TEST-NET rejection.
* **Tech Debt #3**: Implemented `UnifiedModelClient.chat_stream()` for real-time NDJSON streaming with TTFT (ms), tokens/sec, and free RAM telemetry.
* **Tech Debt #4**: Implemented `HardwareProfiler.list_audio_input_devices()` for cross-platform microphone discovery.
* **Design Tokens**: Exported Precision Obsidian & Solar Orange tokens (`#0B0B0D`, `#141418`, `#24242B`, `#FF5A1F`, `#F4F4F6`, 10px/8px/9999px radii) into `design_tokens.json`, `bajrang_core.py`, `windows.py`, `fedora.py`, and `assets/system.css`.

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
* **BUG-011**: Fixed Vercel schema validation failure by removing deprecated `"public": false` from `vercel.json`.

---

## v6.0.0 — Argon Release (2026-11-11)

### Architectural & Core Engine Upgrades
* Unified Zero-Duplication Core (`bajrang_core.py`) extracting shared logic.
* Modular AI Router (`ModularAIRouter`) with task classification and fallback chains.
* Long-Term SQLite Memory & Migrations (`DatabaseMigrationManager`, `LongTermMemoryStore`).
* Autonomous Multi-Step Task Planner (`AutonomousTaskPlanner`) with `.bajrang_trash/` staging.
* Asymmetric RSA-2048 Cryptographic License Verification (`AsymmetricLicenseVerifier`).
* SecurityVault hardware credential storage with Windows DPAPI and Linux libsecret.
