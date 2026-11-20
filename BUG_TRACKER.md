# SUDHARSHAN AI (ALPHA v0.9) — COMPREHENSIVE BUG TRACKER

**Audit & Remediation Date**: 2026-11-15T21:49:00+05:30  
**Evaluator**: Principal Software Architect & QA Lead  

---

### BUG-001: Ollama Watchdog Autostart Instance Method Crash (Phase A)
* **Severity**: CRITICAL (Fatal Crash)
* **Affected File**: `bajrang_core.py` (Line ~2593)
* **Root Cause**: `OllamaWatchdogManager.ensure_running()` called `UnifiedModelClient._try_autostart_ollama(self.ollama_host)` on the class directly, while `_try_autostart_ollama` was defined as an instance method `(self, host: str)`. When Ollama was stopped and no cloud key was configured, free-form queries crashed with `TypeError: missing 1 required positional argument: 'host'`.
* **Reproduction**: Call `engine.process_prompt("hello")` with Ollama stopped and empty vault.
* **Correction**: Marked `UnifiedModelClient._try_autostart_ollama` and `_find_ollama_binary` as `@staticmethod`s and updated all call sites.
* **Verification**: `test_phase_a_regression_ollama_autostart_and_offline_card` in `test_bajrang_suite.py` passed cleanly.

---

### BUG-002: Re-entrant Turn Lock Self-Deadlock in Multi-Step Task Chaining
* **Severity**: HIGH (Deadlock)
* **Affected File**: `bajrang_core.py` (Line ~5467)
* **Root Cause**: `BajrangEngine._turn_lock` was initialized as `threading.Lock()`. In chained executions (e.g., `"list windows then status"`), the nested call to `process_prompt` attempted to acquire the same lock on the same thread, causing permanent execution hang.
* **Reproduction**: Execute `engine.process_prompt("list windows then status")`.
* **Correction**: Changed `self._turn_lock = threading.RLock()`.
* **Verification**: `test_phase_c_10_features` verified chaining execution across 2 steps without deadlock.

---

### BUG-003: Fedora Setup Script Abort Under `curl ... | bash` (BASH_SOURCE[0] Unbound)
* **Severity**: HIGH (Installer Failure)
* **Affected File**: `setup_fedora.sh`, `setup_linux.sh`, `setup_mac.sh`
* **Root Cause**: Scripts utilized `set -euo pipefail` and evaluated `$(dirname "${BASH_SOURCE[0]}")`. When piped via `curl | bash`, `${BASH_SOURCE[0]}` was empty or unset, resulting in `bash: line 8: BASH_SOURCE[0]: unbound variable`.
* **Reproduction**: Run `curl -fsSL <url>/setup_fedora.sh | bash` in a fresh shell.
* **Correction**: Utilized `${BASH_SOURCE[0]:-}` guarded parameter expansion and added direct repository download logic for non-cloned piped invocations.
* **Verification**: Tested `bash -n setup_fedora.sh` and simulated execution.

---

### BUG-004: Vercel Schema Validation Rejection (`public` Property)
* **Severity**: HIGH (Deployment Failure)
* **Affected File**: `vercel.json`
* **Root Cause**: Vercel configuration contained `"public": false`, which was deprecated and rejected by Vercel's latest schema validator (`should NOT have additional property 'public'`).
* **Reproduction**: Push commit containing `"public"` property to Vercel connected repo.
* **Correction**: Removed `"public"` property, added `$schema: https://openapi.vercel.sh/vercel.json`, and set `"outputDirectory": "web"`.
* **Verification**: Schema valid against official OpenAPI specification.

---

### BUG-005: Raw WinError 10061 Exposed in Desktop Chat UI
* **Severity**: MEDIUM (User Experience Defect)
* **Affected File**: `bajrang_core.py`, `windows.py`
* **Root Cause**: Unhandled socket connection refusal when local Ollama server was offline resulted in raw Python exception string formatting into the chat transcript.
* **Reproduction**: Launch Windows HUD with Ollama stopped and ask a general question.
* **Correction**: Added interceptor rendering an actionable markdown card: "⚠️ Local Ollama AI Engine Offline" with 1-click startup command and instant BYO key options.
* **Verification**: `test_phase_a_regression_ollama_autostart_and_offline_card` verified card text.

---

### BUG-006: Hardcoded Secret Salt & Forgeable Symmetric License Backdoor (C1)
* **Severity**: CRITICAL (Security Vulnerability)
* **Affected File**: Legacy directories `bajrang_ai_git_repo/` and `bajrang_ai_windows_and_fedora_pro/`
* **Root Cause**: Used symmetric MD5/SHA256 hashing with `BAJRANG-PRO-2025-SECRET-SALT-HYDERABAD`, allowing client-side license forgery.
* **Reproduction**: Generate key with `generate_key("ANY_USER", 30)`.
* **Correction**: Purged legacy trees and implemented 2048-bit RSA asymmetric signature verification.
* **Verification**: `test_c1_license_forgery_blocked_and_rsa2048_verified` verified that symmetric tokens are rejected.

---

### BUG-007: Compromised Code Signing Certificates in Repository (Phase 2)
* **Severity**: CRITICAL (Credential Exposure)
* **Affected File**: `certificates/Sudharshan_AI_CodeSigning.*`
* **Root Cause**: Private RSA key and PFX files were committed to the repository tree.
* **Reproduction**: Inspect `certificates/` directory.
* **Correction**: Removed certificate files from working tree, added strict exclusion rules in `.gitignore` and `.vercelignore`, and documented key rotation.
* **Verification**: `find . -name "*.key" -o -name "*.pfx"` returns zero files in working tree.

---

### BUG-008: Global Socket Timeout Mutation & RFC 5737 Probe False-Positive in `NetworkConnectivityDetector`
* **Severity**: HIGH (Thread-Safety & Offline Detection Defect)
* **Affected File**: `bajrang_core.py` (`NetworkConnectivityDetector.is_online`)
* **Root Cause**: `is_online()` called `socket.setdefaulttimeout(timeout_sec)`, mutating global interpreter socket timeouts across all threads, and did not reject non-routable RFC 5737 TEST-NET addresses (`192.0.2.0/24`) when running behind transparent proxies.
* **Correction**: Switched to per-socket `s.settimeout(timeout_sec)` and added RFC 5737 TEST-NET rejection guard.
* **Verification**: `test_phase_c_10_features` and `test_phase0_adaptive_multimodel_streaming_and_asset_hygiene` pass with zero timeout mutation.
