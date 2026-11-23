# SUDHARSHAN AI — ARCHITECTURE BASELINE SPECIFICATION
**Document Reference:** `ARCHITECTURE_BASELINE.md`  
**Ecosystem Version:** Project Nebula v2.0  
**Date:** November 23, 2026  
**Architectural Tier:** Commercial-Grade Local-First AI Ecosystem  

---

## 1. Architectural Principles

Project Nebula is built upon five foundational principles:
1. **Local-First & Offline Resilience:** Core inference, memory retrieval, filesystem automation, and system diagnostics run entirely on local consumer hardware without requiring internet connectivity.
2. **Fail-Closed Security & Least Privilege:** System interactions are mediated by schema-validated tools. Unrecognized, unvalidated, or unsafe commands are rejected before execution.
3. **Hardware-Aware Adaptability:** The system continuously monitors available CPU, RAM, and GPU resources, gracefully switching between model tiers (Native 1.5B, Qwen 4B, Qwen 2B, Qwen 0.8B) to prevent system starvation.
4. **Modular Wave Decoupling:** Subsystems are partitioned into cohesive, single-responsibility modules sharing standard interfaces, event channels, and data contracts.
5. **Unified Design Authority:** All user-facing surfaces (web portal, native desktop HUD, CLI output, technical documentation) strictly adhere to the Taste Skill v2.5.1 design system.

---

## 2. High-Level Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                            USER INTERACTION SURFACES                              |
|  +--------------------+  +----------------------+  +---------------------------+  |
|  | Web Portal & Docs  |  | GTK4 / Win32 Desktop |  | Interactive Terminal CLI  |  |
|  | (Taste Skill UI)   |  | (Libadwaita / UIA)   |  | (Obsidian / Orange ANSI)  |  |
|  +---------+----------+  +----------+-----------+  +-------------+-------------+  |
+------------|------------------------|----------------------------|----------------+
             |                        |                            |
             v                        v                            v
+-----------------------------------------------------------------------------------+
|                   CENTRAL ORCHESTRATION & SECURITY LAYER                          |
|  +-----------------------------------------------------------------------------+  |
|  | `bajrang_core.BajrangEngine`                                                |  |
|  | - Intent Router & Context Window Manager                                    |  |
|  | - SafetyGuard & Shell Execution Defense (C1, C4)                            |  |
|  | - ToolSchemaValidator & Argument Sanitizer (C3, H3)                          |  |
|  | - SecurityVault (AES-256 Secrets Encryption)                                 |  |
|  | - Session Safe Mode & Emergency Kill Switch (H2)                            |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
             |                                                     |
             v                                                     v
+----------------------------------+     +------------------------------------------+
|      MODEL INFERENCE LAYER       |     |        TEN-WAVE EXTENSION SUBSYSTEMS     |
| +------------------------------+ |     | +--------------------------------------+ |
| | `sudharshan_native` 1.5B     | |     | | Wave 1: Adaptive Intelligence Engine | |
| | - Pure NumPy Inference       | |     | | Wave 2: Memory & Vector RAG Engine   | |
| | - PyTorch GQA / RoPE / LoRA  | |     | | Wave 3: Voice & Multimodal Audio     | |
| | - Byte-Level BPE Tokenizer   | |     | | Wave 4: Security & Access Governance | |
| +------------------------------+ |     | | Wave 5: Staged Filesystem Engine     | |
| +------------------------------+ |     | | Wave 6: OS Ergonomics & Desktop HUD  | |
| | Multi-Model Adapters         | |     | | Wave 7: Developer & Diagnostic Suite | |
| | - Ollama (Qwen 4B/2B/0.8B)   | |     | | Wave 8: Productivity & Clipboard     | |
| | - llama.cpp / vLLM Backends  | |     | | Wave 9: Plugin & Tool Extension Bus  | |
| | - BYOK Cloud Fallback        | |     | | Wave 10: Packaging & WiX/RPM Tooling | |
| +------------------------------+ |     | +--------------------------------------+ |
+----------------------------------+     +------------------------------------------+
             |                                                     |
             +--------------------------+--------------------------+
                                        |
                                        v
+-----------------------------------------------------------------------------------+
|                         PLATFORM HARDWARE ABSTRACTION                             |
|  +------------------+  +-------------------+  +----------------+  +-------------+ |
|  | Fedora Workstation|  | Microsoft Windows |  | Generic Linux  |  | Apple macOS | |
|  | (GTK4 / Wayland) |  | (Win32 / UIA / PE)|  | (X11 / Wayland)|  | (AppleScript)| |
|  +------------------+  +-------------------+  +----------------+  +-------------+ |
+-----------------------------------------------------------------------------------+
```

---

## 3. Subsystem Breakdown

### 3.1 Sudharshan Native 1.5B LLM Subsystem

- **Mathematical Configuration (`sudharshan_native/config.py`):**
  - Parameter Target: 1.5 Billion parameters.
  - Actual Computed Parameters: **1,526,827,008** trainable parameters.
  - Vocabulary Size ($V$): 32,768.
  - Hidden Dimension ($d$): 2,048.
  - Intermediate FFN Dimension ($d_{\text{ff}}$): 8,192 (SwiGLU).
  - Number of Layers ($L$): 24.
  - Query Attention Heads ($h_q$): 16.
  - Key/Value Attention Heads ($h_{kv}$): 4 (Grouped Query Attention, 4:1 ratio).
  - Context Window ($T$): 2,048 tokens.
  - Normalization: RMSNorm ($\epsilon = 10^{-5}$) with zero learnable bias.
  - Positional Encoding: Rotary Positional Embeddings (RoPE, $\theta = 10000.0$).

- **Execution Engines:**
  - **`model_numpy.py`**: Completely dependency-free pure NumPy implementation. Implements causal multi-head self-attention, rotary embeddings, SwiGLU activation, and recurrent KV cache. Runs on any Python environment.
  - **`model_torch.py`**: Production PyTorch implementation supporting batched forward passes, FP16/BF16 mixed precision, LoRA adapter injection, and autoregressive generation.
  - **`tokenizer.py`**: Dedicated byte-level BPE tokenizer pre-configured with 13 special control tokens (`<|pad|>`, `<|bos|>`, `<|eos|>`, `<|system|>`, `<|user|>`, `<|assistant|>`, `<|tool_call|>`, `<|tool_response|>`, etc.).
  - **`trainer.py` & `datasets.py`**: Cosine learning rate scheduler with warmup, gradient accumulation, gradient norm clipping, dataset validation, deduplication, and SFT formatting.

---

### 3.2 Security & Governance Architecture

1. **SafetyGuard (`bajrang_core.SafetyGuard`):**
   - Implements regular expression guards against arbitrary bash/sh execution (`/bin/sh`, `/bin/bash`, `cmd.exe /c`, `powershell -enc`).
   - Validates command strings against allowlisted utility patterns.

2. **ToolSchemaValidator (`bajrang_core.ToolSchemaValidator`):**
   - Strictly enforces parameter types, required fields, and boundary constraints for all 12 core tools:
     - `file_search`, `read_file_head`, `list_directory`, `open_application`
     - `system_diagnostics`, `clipboard_read`, `clipboard_write`, `memory_store`
     - `memory_recall`, `undo_last_action`, `staged_organize_preview`, `staged_organize_commit`
   - Rejects unvalidated or unrecognized parameters fail-closed.

3. **SecurityVault (`bajrang_core.SecurityVault`):**
   - Securely stores user API keys (BYOK) using encrypted memory structures.
   - Zero keys are ever serialized to logs, disk traces, or client-side web bundles.

---

### 3.3 Feature Catalogues (`registry/`)

- **Web Registry (`web_features_1000.json`):** 1,000 distinct web capabilities structured across 30 categories (AI chat, model management, security dashboards, interactive playgrounds, API management, telemetry).
- **Desktop Registry (`desktop_features_1500.json`):** 1,500 distinct desktop capabilities structured across 15 categories (system intelligence, automation designer, developer tools, voice subsystem, productivity).
- **Integrity Validation:** Validated programmatically in `test_nebula_verification.py`. Zero duplicate IDs exist. 130 features are verified as `implemented_and_tested`, with the remaining 2,370 tracked as `planned_backlog`.

---

## 4. Verification & Quality Gates

The architecture enforces a strict four-layer testing hierarchy:
1. **Mathematical Verification:** Exact parameter count and weight shape matching (`test_sudharshan_native.py`).
2. **Remediation Regression:** Invariants C1-C6 and H1-H8 verified under fuzzing conditions (`test_bajrang_suite.py`).
3. **Wave-Based Integration:** All 10 extension waves tested with mock hardware drivers (`test_waves_1_to_10.py`).
4. **Ecosystem Integrity:** Web links, registry IDs, and security invariants validated end-to-end (`test_nebula_verification.py`).
