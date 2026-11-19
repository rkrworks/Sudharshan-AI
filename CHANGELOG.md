# SUDHARSHAN AI — ENGINEERING CHANGELOG (`CHANGELOG.md`)

## v1.0.0-alpha — Wave 10: Packaging, Reliability, Diagnostics & Polish (2026-11-19)

### Wave 10 Deliverables (Features 91–100)
* **Feature 91: Fedora RPM Spec & Flatpak Manifest**: Built `FedoraPackagingGenerator` producing production-ready Fedora RPM `.spec` files and Flatpak sandbox manifests with Wayland/PipeWire permissions.
* **Feature 92: Windows MSI Installer Builder**: Created `WindowsInstallerBuilder` generating WiX XML installer definitions with clean uninstallation and Start Menu shortcut integration.
* **Feature 93: First-Run Onboarding Wizard**: Implemented `FirstRunOnboardingWizard` scanning system hardware (free RAM, GPU acceleration) to automatically configure the optimal model tier.
* **Feature 94: Automated 12-Point System Doctor**: Built `AutomatedSystemDoctor` implementing `sudharshan doctor` with a comprehensive 12-point health checklist across all subsystems.
* **Feature 95: Graceful Degradation Matrix**: Created `GracefulDegradationMatrix` automatically scaling operational features across 4 distinct memory tiers to prevent OOM crashes on $\le$ 4 GB machines.
* **Feature 96: Accessibility & Contrast Auditor**: Implemented `AccessibilityAuditor` verifying mathematical WCAG 2.1 AA compliance for text (17.9:1) and action buttons (6.31:1).
* **Feature 97: Release Asset Packager & Checksum Engine**: Built `ReleaseAssetPackager` scanning distribution builds and compiling cryptographic `SHA256SUMS` manifests.
* **Feature 98: Zero-Telemetry Privacy Dashboard**: Built `ZeroTelemetryDashboard` providing mathematical verification of zero third-party analytics, cookies, or phone-home requests.
* **Feature 99: Safe Minidump Crash Reporter**: Implemented `SafeCrashReporter` capturing local-only minidumps with automatic regex redaction of API keys, PII, and credentials.
* **Feature 100: Master Integration Suite Runner**: Implemented `MasterIntegrationSuiteRunner` executing automated validation across all 10 waves and 100 features in sub-second time.

## v1.0.0-alpha — Wave 9: Extensibility, MCP & Plugin Ecosystem (2026-11-19)

### Wave 9 Deliverables (Features 81–90)
* **Feature 81: Model Context Protocol (MCP) Client**: Built `MCPClient` supporting standard MCP JSON-RPC 2.0 communication over process stdio and SSE connections with tools listing and calling.
* **Feature 82: Sandboxed Plugin Runtime**: Implemented `SandboxedPluginRuntime` scoping filesystem reads and strictly restricting dangerous execution builtins.
* **Feature 83: Visual Workflow DAG Builder**: Built `VisualWorkflowDAGBuilder` constructing directed acyclic graphs, validating cycles, and generating topological execution sequences in JSON.
* **Feature 84: Plugin Security Scanner**: Implemented `PluginSecurityScanner` executing pre-load static AST inspections to block dangerous system, network, and compilation modules.
* **Feature 85: Localhost REST & WS API Bridge**: Built `LocalhostAPIServer` hosting a local developer bridge on loopback port 8769 for model chat completions and system diagnostics.
* **Feature 86: CLI Companion Tool Suite**: Built `CLICompanionInterface` executing `sudharshan ask`, `sudharshan pipe`, and `sudharshan run <workflow.json>`.
* **Feature 87: Declarative YAML Tool Loader**: Implemented `DeclarativeYAMLToolLoader` parsing declarative JSON/YAML schemas for external custom tools.
* **Feature 88: Webhook & MQTT Event Bridge**: Built `WebhookMQTTEventBridge` supporting pub/sub event routing across topics with wildcard listeners for IoT and automation.
* **Feature 89: Plugin Supervisor Daemon**: Created `PluginSupervisor` managing child processes with bounded auto-restart policies and crash containment.
* **Feature 90: Developer Plugin Sandbox**: Implemented `PluginDevSandbox` offering mock system APIs for developer plugin validation across `on_load`, `execute`, and `on_unload`.

## v1.0.0-alpha — Wave 8: Knowledge, Productivity & Daily Workflow (2026-11-19)

### Wave 8 Deliverables (Features 71–80)
* **Feature 71: Markdown Knowledge Vault**: Implemented `MarkdownKnowledgeVault` indexing `[[wikilinks]]`, generating bidirectional backlink networks, and rendering graph models.
* **Feature 72: Instant Paper & PDF Reader**: Built `InstantPaperReader` extracting key empirical findings, methodology summaries, and limitations from academic papers.
* **Feature 73: Natural-Language Task & Reminder Manager**: Built `NaturalLanguageTaskManager` parsing plain-English deadlines and priorities, stored in SQLite with `.ics` export.
* **Feature 74: Morning Briefing Generator**: Implemented `MorningBriefingGenerator` aggregating high-priority tasks, hardware health, and local model readiness into a morning digest.
* **Feature 75: SM-2 Spaced-Repetition Engine**: Implemented `SM2SpacedRepetitionEngine` with SuperMemo-2 mathematical scheduling, easiness factors, and review intervals.
* **Feature 76: Math & LaTeX Scratchpad**: Created `MathLaTeXScratchpad` executing AST-safe arithmetic, trigonometry, and powers with automatic KaTeX display rendering.
* **Feature 77: Distraction-Free Writing Assistant**: Built `WritingAssistant` with corporate buzzword detection ("delve", "testament", "tapestry"), word count, and reading time metrics.
* **Feature 78: Calendar & .ICS Manager**: Implemented `CalendarICSManager` parsing iCalendar formats and validating time windows to flag schedule conflicts.
* **Feature 79: Data Table Extractor**: Built `DataTableExtractor` parsing CSV, TSV, or unstructured tables into clean GitHub Flavored Markdown tables and JSON objects.
* **Feature 80: End-of-Day Activity Digest**: Implemented `EndOfDayDigestGenerator` generating engineering productivity scorecards with git commits and completed tasks.

## v1.0.0-alpha — Wave 7: Developer & Engineering Power Suite (2026-11-19)

### Wave 7 Deliverables (Features 61–70)
* **Feature 61: Local Git Assistant**: Built `LocalGitAssistant` creating conventional commit summaries (`feat(scope): ...`), staged file status, and merge conflict analyzers.
* **Feature 62: Terminal Error Explainer**: Implemented `TerminalErrorExplainer` diagnosing failed terminal command tracebacks (missing pip packages, permissions, port conflicts) and recommending exact fixes.
* **Feature 63: Codebase AST Symbol Indexer**: Implemented `CodebaseSymbolIndexer` parsing Python AST and multilingual symbols (Rust, Go, C, JS/TS) with line coordinates.
* **Feature 64: Container & Compose Inspector**: Created `ContainerInspector` checking Podman and Docker processes and validating `compose.yaml` syntax.
* **Feature 65: Offline API Tester & Schema Converter**: Built `OfflineAPITester` with robust `shlex`-based cURL command parsing and JSON-to-YAML converter.
* **Feature 66: Regex Builder & Live Test Bench**: Implemented `RegexTestBench` validating regular expressions against test samples with captured group highlighting.
* **Feature 67: Automated Unit Test Generator**: Built `UnitTestGenerator` generating structured pytest suites for Python classes and functions.
* **Feature 68: Localhost Service Radar**: Created `LocalhostServiceRadar` scanning 10 common developer ports (11434, 3000, 8000, 5432, 6379) to identify local servers.
* **Feature 69: Interactive Man-Page & Flag Translator**: Implemented `ManPageTranslator` converting English queries into shell syntax and explaining CLI flags.
* **Feature 70: Environment & PATH Doctor**: Built `EnvironmentPathDoctor` executing a 10-point diagnostic across runtimes, compilers, venv status, and duplicate PATH entries.

## v1.0.0-alpha — Wave 6: OS Control & Desktop Ergonomics (2026-11-19)

### Wave 6 Deliverables (Features 51–60)
* **Feature 51: Command Palette Launcher**: Built `CommandPaletteLauncher` offering Super+Space spotlight query resolution across system apps, automated tasks, and AI slash prompts.
* **Feature 52: Native Window Management**: Implemented `NativeWindowManager` with cross-platform window listing, workspace routing, tiling (left, right, maximize), and focus control.
* **Feature 53: Clipboard History Manager**: Built `ClipboardHistoryManager` storing SQLite history with automatic format classification (text, code, link), keyword search, and pinned snippets.
* **Feature 54: System Resource & Thermal HUD**: Implemented `ResourceThermalHUD` extracting CPU %, RAM/swap GB, disk %, and `/sys/class/thermal` hardware temperature sensors.
* **Feature 55: Natural-Language System Settings Controller**: Created `SystemSettingsController` controlling audio volume, display brightness, Wi-Fi, Bluetooth, and `powerprofilesctl` power tiers.
* **Feature 56: Smart Focus / Do-Not-Disturb Mode**: Implemented `SmartFocusController` silencing desktop notifications and managing timed Pomodoro productivity sessions.
* **Feature 57: Desktop Notification Triager**: Created `NotificationTriager` aggregating missed notifications and ranking them by urgency into executive briefings.
* **Feature 58: App-Aware Contextual Actions**: Built `ContextualActionEngine` dynamically discovering the active focused application and recommending relevant AI developer tools.
* **Feature 59: Scheduled Cron & Systemd-Timer Generator**: Implemented `CronSystemdTimerGenerator` translating English schedule descriptions into valid cron syntax and systemd `.timer` units.
* **Feature 60: Safe Process Manager**: Built `SafeProcessManager` discovering high-RAM processes with fail-closed protection for PID $\le 1$ and graceful SIGTERM/SIGKILL termination.

## v1.0.0-alpha — Wave 5: Intelligent File System & Automation Engine (2026-11-19)

### Wave 5 Deliverables (Features 41–50)
* **Feature 41: Natural-Language Batch File Organizer**: Built `BatchFileOrganizer` providing dry-run tree previews and reversible undo manifests for multi-folder sorting.
* **Feature 42: Smart Downloads Folder Daemon**: Implemented `SmartDownloadsDaemon` automatically classifying downloaded assets into Documents, Installers, Archives, Media, and Code.
* **Feature 43: Content-Aware Smart Renaming**: Implemented `ContentAwareRenamer` inspecting invoice headers, code classes, and document dates to generate standardized slug names.
* **Feature 44: Deduplication Sweep Engine**: Built `DeduplicationSweepEngine` executing fast SHA-256 sweeps across nested directories with quarantine or hardlink replacement.
* **Feature 45: Natural Archive Manager**: Implemented `NaturalArchiveManager` inspecting, compressing, and safely extracting `.zip`, `.tar.gz`, and `.tar.xz` archives with zip-slip path validation.
* **Feature 46: Disk Space Cleanup Analyzer**: Built `DiskSpaceAnalyzer` discovering orphaned build directories (`node_modules/`, `target/`, `__pycache__/`) and calculating reclaimable GB savings.
* **Feature 47: File Conversion Pipeline**: Implemented `FileConversionPipeline` handling bidirectional CSV-to-JSON and Markdown-to-HTML conversions.
* **Feature 48: Folder Watcher Trigger Engine**: Created `FolderWatcherTriggerEngine` executing automated reactive rules on newly created or modified files.
* **Feature 49: Safe Quarantine Trash Bin**: Built `SafeQuarantineTrashBin` maintaining an atomic JSON manifest with 30-day auto-purge retention and 1-click restore.
* **Feature 50: Cross-Folder Diff & Smart Sync**: Implemented `CrossFolderDiffSync` calculating directory deltas (added, modified, deleted) and executing collision-safe mirror sync.

## v1.0.0-alpha — Wave 4: Fail-Closed Security, Privacy & Governance (2026-11-19)

### Wave 4 Deliverables (Features 31–40)
* **Feature 31: Cryptographically Signed Audit Ledger**: Built `SignedAuditLedger` generating an append-only, tamper-evident HMAC-SHA256 hash-chained ledger with automated mathematical verification.
* **Feature 32: 4-Tier Security Permission Model**: Implemented `FourTierPermissionPolicy` classifying actions strictly into `READ_ONLY`, `SAFE_WRITE`, `ELEVATED_CONFIRM`, and `HARD_BLOCKED`.
* **Feature 33: Command Preview Diff Generator**: Built `CommandPreviewDiffGenerator` producing colored unified diffs and interactive permission modals prior to disk or system mutations.
* **Feature 34: Automatic Pre-Action Rollback Snapshots**: Built `PreActionRollbackManager` taking atomic SHA-256 verified snapshots of files before modification with instant 1-click restore.
* **Feature 35: Regex & AST Shell Sanitizer**: Implemented `ASTShellSanitizer` intercepting fork bombs, pipe-to-shell invocations, destructive globs, and unsafe Python imports.
* **Feature 36: Secret & PII Redaction Filter**: Created `SecretPIIRedactor` filtering sensitive API keys (OpenAI, Anthropic, Google, Groq, GitHub), private IP addresses, passwords, and credit cards.
* **Feature 37: Hardware/OS Keyring Vault**: Implemented `HardwareKeyringBridge` interfacing directly with Linux `secret-tool`/`libsecret` and Windows DPAPI with local AES-CTR encrypted fallback.
* **Feature 38: Network Egress Monitor & Airplane Switch**: Implemented `NetworkEgressMonitor` auditing outbound connections and enforcing a strict local loopback airplane-mode kill switch.
* **Feature 39: Automated SHA-256 Integrity Verifier**: Implemented `AutomatedIntegrityVerifier` verifying local binaries, scripts, and model weights against `SHA256SUMS`.
* **Feature 40: Panic Kill-Switch Hotkey**: Implemented `PanicKillSwitch` immediately terminating all active agent threads and child processes on emergency shortcut.

## v1.0.0-alpha — Wave 3: Voice, Audio & Multimodal Perception (2026-11-19)

### Wave 3 Deliverables (Features 21–30)
* **Feature 21: Hardened Offline Wake-Word Engine**: Built `HardenedWakeWordEngine` combining 8-band Goertzel filter bank with adaptive VAD noise floor subtraction and spectral flatness testing to kill false positives.
* **Feature 22: Local STT via Whisper.cpp**: Implemented `WhisperCppSTT` with automatic language detection, quantized model auto-selection, and graceful offline fallback.
* **Feature 23: Local Neural TTS with Barge-In**: Implemented `PiperNeuralTTS` with 4 selectable voices (`en_US-lessac-medium`, `en_US-amy-low`, `en_GB-alan-medium`, `hi_IN-hindi-medium`) and instant interrupt-on-speech.
* **Feature 24: Push-to-Talk & Hands-Free Mode**: Implemented `PushToTalkController` state machine managing global PTT hotkeys and continuous hands-free dialogue.
* **Feature 25: Screen Perception Pipeline**: Created `ScreenPerceptionPipeline` supporting Wayland (`grim`/`slurp`), X11 (`scrot`), and Windows active window and region capture.
* **Feature 26: Local Meeting Transcriber**: Built `MeetingTranscriber` recording multi-speaker meetings with local deterministic action-item and decision extraction.
* **Feature 27: Audio-Reactive Waveform Orb**: Implemented `AudioReactiveOrbRenderer` generating clean, zero-bloat HTML5 Canvas/CSS audio orb visualizations for Web and GTK4.
* **Feature 28: OCR-to-Clipboard Shortcut**: Built `OCRToClipboardService` extracting formatted code and tables directly from captured screen regions into the system clipboard.
* **Feature 29: Spoken Confirmation Gate**: Created `SpokenConfirmationGate` requiring explicit affirmative verbal authorization ("Yes execute", "Confirmed") for sensitive operations.
* **Feature 30: Offline Voice Command Macros**: Implemented `VoiceMacroManager` mapping spoken user phrases directly to multi-step workflow execution trees.

## v1.0.0-alpha — Wave 2: Persistent Local Memory & Semantic RAG (2026-11-19)

### Wave 2 Deliverables (Features 11–20)
* **Feature 11: Local Vector Store & SQLite**: Built `LocalVectorStore` storing dense 128/1024-float vector embeddings in SQLite WAL database with fast Top-K cosine similarity search.
* **Feature 12: Incremental Background File Indexer**: Implemented `BackgroundFileIndexer` with multi-format text extraction (PDF, DOCX, Markdown, Code, TXT), overlapping chunking, and SHA-256 change detection.
* **Feature 13: Hybrid BM25 & Dense Vector Search**: Implemented `HybridSearchEngine` fusing pure-Python Okapi BM25 keyword matching with dense vector cosine similarity via Reciprocal Rank Fusion (RRF).
* **Feature 14: Source-Cited Answers & Line Links**: Implemented `SourceCitationFormatter` generating clickable `file://...#Lstart-Lend` markdown citations and numbered verified reference footnotes.
* **Feature 15: Episodic User Memory Cards**: Built `EpisodicMemoryStore` managing inspectable, editable, and deletable memory cards with importance scores (1–5) and category tagging.
* **Feature 16: Project-Scoped Workspaces**: Created `ProjectWorkspaceManager` providing complete workspace isolation for RAG vectors, document caches, and episodic memories.
* **Feature 17: Instant Clipboard-to-Knowledge Capture**: Implemented `ClipboardKnowledgeCapture` enabling instant snippet ingestion with automated syntactic tagging (code, url, contact).
* **Feature 18: Smart Duplicate & Near-Duplicate Detector**: Implemented `DocumentDeduplicator` detecting both identical file duplicates (via SHA-256) and semantic near-duplicates (via vector cosine similarity $\ge 0.92$).
* **Feature 19: Ephemeral Incognito Chat Mode**: Built `IncognitoSessionManager` with auto-expiring in-memory conversation state guaranteeing zero disk writes to logs, vectors, or databases.
* **Feature 20: Encrypted Memory Backup & Restore**: Created `MemoryBackupManager` supporting JSON/Markdown exports and authenticated encryption (PBKDF2-HMAC-SHA256 + CTR/HMAC) backup and restore.

## v1.0.0-alpha — Wave 1: Core Intelligence & Multi-Model Orchestration (2026-11-19)

### Wave 1 Deliverables (Features 1–10)
* **Feature 1: Adaptive RAM-Aware Switcher**: Automatic live RAM monitoring with sub-second threshold auto-downgrade (Qwen 3.5 4B -> Qwen 3.5 2B when free memory < 2.5 GB).
* **Feature 2: Streaming Token Engine & Live Telemetry**: Token-by-token streaming with live TTFT (Time To First Token), tokens/sec, and real-time memory usage telemetry.
* **Feature 3: Fast Hybrid Intent Router**: Sub-50ms classifier routing queries across 5 specialized system domains (Vision/OCR, Reasoning/Math, Developer Tools, File Automation, System Control).
* **Feature 4: Strict JSON-Schema Constrained Tool Caller**: Robust JSON-schema tool caller with automatic retry-on-malformed-output, error feedback injection, and self-correction.
* **Feature 5: Autonomous Step Planner**: Multi-step dependency execution planner featuring dynamic pause, resume, step cancellation, and ASCII execution tree visualization.
* **Feature 6: Context Window Manager**: Rolling token window manager with automatic executive card summarization preventing OOM context saturation.
* **Feature 7: Prompt Template Library**: Modular prompt library with custom variable substitution (`{{variable}}`) and slash commands (`/code`, `/explain`, `/refactor`, `/audit`, `/plan`, `/fix`).
* **Feature 8: Side-by-Side Model Benchmark Runner**: In-situ benchmarking engine evaluating speed (tok/s), TTFT latency, RAM delta, and tool-calling schema compliance.
* **Feature 9: Offline-First Hybrid Egress Controller**: Fail-closed network boundary enforcing local loopback execution by default with gated, encrypted Cloud Burst toggle.
* **Feature 10: Per-Conversation System Personas**: 5 distinct, fully-typed personas (Coder, SysAdmin, Study Tutor, Writer, Minimalist) with fine-tuned temperature and tool scopes.

## v1.0.0-alpha — Phase 0: Repo Hygiene, Forensic Bug Fixes & Adaptive Multi-Model Local Engine (2026-11-19)

### Multi-Model Local Engine Upgrade (`sudharshan/core/models.py`)
* **Primary Engine Migration**: Replaced legacy `llama3.2` with **Qwen 3.5 4B** (`qwen3.5:4b`, Q4_K_M) providing precision structured JSON tool calling, 16k context window, and native multimodal vision.
* **Adaptive RAM-Aware Model Switcher**: Implemented `AdaptiveModelSwitcher` dynamically monitoring OS free memory (`/proc/meminfo`, `GlobalMemoryStatusEx`, `psutil`). Auto-downgrades 4B to **Qwen 3.5 2B** (`qwen3.5:2b-q4_K_M`) when available system RAM drops below 2.5 GB.
* **Reasoning Specialist**: Integrated **Phi-4 Mini** (`phi4-mini`, 3.8B) for deep mathematical reasoning, logic proofs, and complex algorithmic debugging.
* **Fast Intent Router**: Built sub-50ms `IntentRouter` combining fast keyword heuristics with **Qwen 3.5 0.8B** (`qwen3.5:0.8b`) for instant intent classification across 5 core domains prior to invoking the 4B brain.
* **Local Semantic Embeddings**: Implemented local dense embedding generator powered by **Qwen 3 Embedding 0.6B** (`qwen3-embedding:0.6b`) with cosine similarity vector math for local semantic RAG.
* **On-Demand OCR**: Wired **GLM OCR** (`glm-ocr`) pipeline for document, screen, table, and source code perception.
* **Asynchronous Streaming Telemetry**: Built `StreamingModelEngine` computing live Time To First Token (TTFT), tokens/sec throughput, and RAM telemetry.

### Asset Bundle Hygiene & Optimization
* **Demo & Lab Cleanup**: Pruned 142 unused demo and lab files (`_lab.html`, `demo.html`, `gallery.html`, `check.html`, `demo.css`, `demo.js`, `_demo/`, `_lab/`).
* **Shader Optimization**: Retained active `orb-sphere` shader and removed 24 unreferenced shader directories from `assets/effects/` and `web/assets/effects/`.
* **Unused Third-Party Brand SVGs**: Removed unreferenced brand SVGs (`visa.svg`, `mastercard.svg`, `si-mastercard.svg`, `linear.svg`, `figma.svg`, `gitlab.svg`).

### Taste-Skill UI & Design Token Alignment
* **Aesthetic Direction**: Aligned all surfaces with Precision Obsidian & Solar Orange engineering hardware:
  - Obsidian `#0B0B0D`
  - Surface `#141418`
  - Hairline `#24242B`
  - Solar Orange accent `#FF5A1F`
  - Crisp off-white `#F4F4F6`
* **Shape-Consistency Lock**: Enforced strict 10px radius for containers and panels, 8px for inputs, and full-pill (9999px) for primary action CTAs across web portal, Windows HUD, and Fedora GTK4/Libadwaita.

### Bug Fixes & Security Hardening
* **BUG-008**: Resolved read-only sandbox filesystem crash during quarantine folder creation and markdown transcript exports by scoping quarantine paths and adding safe temp directory fallbacks.
* **BUG-009**: Injected automatic `NO_PROXY` / `no_proxy` bypass for `127.0.0.1`, `localhost`, and `::1` to prevent containerized proxies from rejecting direct IP socket requests.
* **Verification**: All 20 automated tests in `test_bajrang_suite.py` and all 7 platform self-tests pass with 100% compliance.

---

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
