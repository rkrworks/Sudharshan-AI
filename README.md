# SUDHARSHAN AI (Alpha v0.9)
### Professional Cross-Platform Local Desktop AI Assistant (Windows 11 & Fedora Linux)

**Engineered by**: Kaushik Ram Ravuru (B.E. IT, Section IT-1, Chaitanya Bharathi Institute of Technology - CBIT Hyderabad)  
**Contact**: [kaushikramravuru@gmail.com](mailto:kaushikramravuru@gmail.com)  
**GitHub Repository**: [https://github.com/rkrworks/Sudharshan-AI](https://github.com/rkrworks/Sudharshan-AI)  
**Production Web Portal**: [https://sudharshan-ai.vercel.app](https://sudharshan-ai.vercel.app)  
**GitHub Pages Portal**: [https://rkrworks.github.io/Sudharshan-AI/](https://rkrworks.github.io/Sudharshan-AI/)  

---

## 🌟 Executive Summary

**Sudharshan AI (Alpha v0.9 • Sudharshan Core v0.9-alpha)** is an enterprise-grade, privacy-first desktop AI assistant engineered specifically for **Windows 11** and **Fedora Workstation (GNOME 45–49 / Wayland)**.

Unlike cloud-dependent assistants that transmit your private workspace data, telemetry, and keystrokes across external networks, Sudharshan AI runs **100% locally** on your workstation via Ollama and open-weights models (Llama 3.2 3B, Mistral 7B, Llama 3.1 8B). Cloud providers (Google Gemini, Groq, OpenAI) are supported strictly on a Bring-Your-Own-Key (BYOK) basis, with secrets safely isolated inside OS hardware vaults (Windows DPAPI, GNOME Keyring).

---

## 🚀 10 Core Architectural Features

1. **Intelligent Conversation Manager**:
   - SQLite3 with Write-Ahead Logging (`WAL`) mode and automatic schema migrations.
   - Session organization with categories, priority pinning, and full-text keyword search.
   - Comprehensive conversation export to clean GitHub-Flavored Markdown (`.md`) and JSON.

2. **Advanced Voice Studio**:
   - Zero-cloud offline voice detection using an 8-band Goertzel Spectral-DTW (Dynamic Time Warping) filter bank.
   - Spectral noise subtraction using ambient silence profiling.
   - Configurable wake-word spotter (`"hey sudharshan"`) and adjustable speech rate/pitch.

3. **Visual Automation Builder**:
   - Multi-step discrete workflow execution engine (`AutomationBuilder`, `WorkflowStep`).
   - Condition-gated execution steps (`file_exists`, `platform_is`).
   - Non-blocking human confirmation gates for sensitive actions.

4. **Advanced Memory Management**:
   - Persistent long-term user fact store categorized by domain.
   - Importance rating (1 to 5) for smart prompt injection.
   - Automated semantic deduplication with Jaccard word-overlap scoring.

5. **Local AI Model Manager**:
   - Dynamic auto-discovery of local Ollama daemons and installed model weights.
   - Curated catalog for Llama 3.2, Mistral, Gemma 2, and CodeLlama.
   - Hardware tier compatibility evaluator (Eco, Balanced, High, Workstation).

6. **System Intelligence Dashboard**:
   - 100% authentic hardware readings: CPU load, RAM allocation, GPU VRAM, storage, battery, and network.
   - Rolling 60-second time-series history buffer.
   - Automatic resource pressure warnings during intensive compilation or gaming.

7. **Intelligent Provider Dashboard**:
   - Multi-cloud routing between Local Ollama, Google Gemini, Groq, and OpenAI.
   - Live round-trip latency probing and automatic failover.
   - Cumulative token usage accounting and estimated cost tracking.

8. **Universal Floating Assistant**:
   - Responsive dark/light theme desktop HUD adhering to the Solar Orange & Obsidian Black design system.
   - Always-on-top toggle (`-topmost`) to float over IDEs, code editors, and browsers.
   - Compact mode toggle (480x140 micro-HUD) for unobtrusive desktop presence.
   - One-click Clipboard Assistant for instant code analysis, explanation, and bug fixing.

9. **Developer Copilot**:
   - Safe workspace directory inspection with directory traversal boundaries.
   - Unified diff generation via Python's standard `difflib`.
   - Traceback analyzer that parses errors to exact lines and source files.
   - Allowlist-guarded command suggestions.

10. **Diagnostics & Recovery Centre**:
    - 6-point pre-flight health check (Database, Vault, Platform, Memory, Voice, Network).
    - Database PRAGMA integrity validation.
    - Automated atomic SQLite backup and rollback mechanism.
    - Exportable diagnostic logs in JSON and Markdown formats.

---

## 🔒 Security Architecture & Invariants

Sudharshan AI enforces strict cryptographic and system security invariants:

- **C1 & H5 (Cryptographic License Enforcement)**: All Pro tier licenses verify 2048-bit RSA signatures (`BAJRANG-V6-<payload>.<sig>`). Insecure symmetric tokens (`BAJRANG-PRO-*`) are strictly rejected.
- **C2 (Zero Client Secrets)**: No hardcoded administrative credentials, hashes (`OWNER_EMAIL_HASH`), or client-side license generation routines exist anywhere in the frontend or client codebase.
- **C3 (Zero-Argument Trampoline Guard)**: `SafetyGuard` enforces a strict allowlist launcher that blocks arguments and prevents shell trampoline escapes.
- **C4 (Direct Binary Execution)**: Shell execution (`shell=True`, `shell_exec`) is prohibited. All actions invoke direct OS APIs or verified subprocess binaries.
- **C5 (Non-Destructive File Staging)**: File cleanup and organizational actions stage files to `.bajrang_trash/` with complete atomic rollback capability (`undo_plan()`).
- **C6 (Hardware Credential Isolation)**: BYO API keys are stored exclusively in OS credential vaults (`keyring`, DPAPI, `secret-tool`), never in plain-text configuration files.
- **H2 (Dual-Platform Global Kill-Switch)**: Emergency stop is instantly triggerable via `Ctrl+Shift+K` on Windows 11 or a dedicated UNIX domain socket on Fedora GNOME.

---

## 🛠️ Quick Start & Installation

### Windows 11 (22H2 or newer)
```cmd
:: Clone the repository
git clone https://github.com/rkrworks/Sudharshan-AI.git
cd Sudharshan-AI

:: Run the smart pre-flight installer
setup_windows.bat

:: Or launch directly with Python
python windows.py
```

### Fedora Workstation (GNOME 45–49 / Wayland)
```bash
# Clone the repository
git clone https://github.com/rkrworks/Sudharshan-AI.git
cd Sudharshan-AI

# Run the automated Fedora setup script
chmod +x setup_fedora.sh
./setup_fedora.sh

# Or launch directly with Python
python3 fedora.py
```

---

## 🧪 Comprehensive Verification Suite

Sudharshan AI includes a 14-point automated test suite with zero external display or audio dependencies:

```bash
# Core engine & feature manager tests
python3 -m bajrang_core --self-test

# Windows platform layer & Tkinter HUD tests
python3 -m windows --self-test

# Fedora platform layer & GTK4 HUD tests
python3 -m fedora --self-test

# Razorpay payment & RSA signing server tests
python3 razorpay_server.py --self-test

# Windows pre-flight installer tests
python3 installer_windows.py --self-test

# Complete 14-point integrated security & regression suite
python3 test_bajrang_suite.py
```

---

## ⚖️ License & Attribution

- **Engineered by**: Kaushik Ram Ravuru (B.E. Information Technology, Chaitanya Bharathi Institute of Technology - CBIT Hyderabad).
- **Core Engine**: Open Source Community Core.
- **Pro Tier**: ₹99/month commercial license with RSA server-signed certificates.
