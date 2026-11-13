# SUDHARSHAN AI — FORENSIC SECURITY & TECHNICAL AUDIT REPORT

**System**: Sudharshan AI (Alpha v0.9 • Sudharshan Core v0.9-alpha)  
**Lead Engineer**: Kaushik Ram Ravuru (B.E. IT, Section IT-1, CBIT Hyderabad)  
**Repository**: `https://github.com/rkrworks/Sudharshan-AI.git`  
**Audit Scope**: Complete line-by-line inspection of Python, JavaScript, HTML, CSS, JSON, Shell, and Batch files.

---

## 1. Executive Summary

This forensic security audit verifies the transition from Bajrang AI Pro to **Sudharshan AI (Alpha v0.9)**. The audit independently validated all security claims, identified and remediated 10 active bugs (BUG-001 to BUG-010), resolved all unclosed SQLite database connection leaks, eliminated HTTP response stream leaks, and confirmed that zero sensitive client credentials exist across public-facing static assets.

All 6 automated test harnesses pass with 100% compliance and zero `ResourceWarning` notices.

---

## 2. Security Invariants (C1–C6 & H1–H8)

| Invariant | Description | Verification Method | Status |
| :--- | :--- | :--- | :--- |
| **C1 / H5** | 2048-bit RSA Asymmetric Signature Verification (`BAJRANG-V6-<payload>.<sig>`). Symmetric `BAJRANG-PRO-*` tokens rejected. | `test_bajrang_suite.py` (Test 1) & `bajrang_core.py:LicenseManager.verify_key` | **VERIFIED** |
| **C2** | Zero client-side owner credentials (`OWNER_EMAIL_HASH`, `OWNER_DEFAULT_PASSKEY`) or client-side key minting (`generateBajrangLicenseKey`) in HTML/JS. | Grep audit across `index.html`, `web/`, `portal_app.js` | **VERIFIED** |
| **C3** | Zero-argument allowlist launcher (`len(tokens) > 1` blocked). Blocks shell metacharacters and argument injection. | `windows.py --self-test` (Test 1) & `fedora.py --self-test` (Test 1) | **VERIFIED** |
| **C4** | `shell_exec` excluded from tool dispatch. Subprocesses run with `shell=False`. | `bajrang_core.py:execute_action` schema validation | **VERIFIED** |
| **C5** | Non-destructive file ops with `.bajrang_trash/<plan_id>/` staging and atomic `undo_plan()`. | `test_bajrang_suite.py` (Test 3) | **VERIFIED** |
| **C6** | `SecurityVault` isolates BYO API keys in OS hardware credential managers (DPAPI/Keyring). Keys stripped from `settings.json`. | `fedora.py --self-test` (Test 5) & `windows.py --self-test` (Test 4) | **VERIFIED** |
| **H1** | Modular project exporter copies both `fedora.py` and `bajrang_llama32.py`. `run.sh` always points to resolved path. | `fedora.py --self-test` (Test 6) | **VERIFIED** |
| **H2** | Dual-platform emergency kill-switch (`Ctrl+Shift+K` on Win32, UNIX socket on Fedora). Works even when unfocused. | `fedora.py --self-test` (Test 7) & `windows.py:start_global_windows_kill_listener` | **VERIFIED** |
| **H7** | Deployment boundary: static portal served strictly from `web/` directory. | `vercel.json` & `.github/workflows/deploy.yml` | **VERIFIED** |
| **H8** | Thread-safe UI marshaling via `queue.Queue` and session-pinned prompt execution (`session_id=pinned_sid`). | `windows.py --self-test` (Test 3) | **VERIFIED** |

---

## 3. Vulnerability Register & Audit Findings

| Finding ID | Severity | File(s) Affected | Description | Status & Remediation |
| :--- | :--- | :--- | :--- | :--- |
| **AUD-01** | **CRITICAL** | `index.html`, `web/index.html` | Download links pointed to local `.exe` and `.zip` files not present in `web/` deployment, returning 404. | **RESOLVED**: Replaced with canonical GitHub Releases endpoints (`https://github.com/rkrworks/Sudharshan-AI/releases`). |
| **AUD-02** | **CRITICAL** | `setup_fedora.bash` | Stale setup script contained unhardened `--generate-license` minting code. | **RESOLVED**: Replaced with lightweight forwarder executing verified, hardened `setup_fedora.sh`. |
| **AUD-03** | **HIGH** | `bajrang_core.py` | `DatabaseMigrationManager.connect()` left SQLite connection open after schema migrations. | **RESOLVED**: Refactored to `@contextlib.contextmanager` with explicit `conn.close()` in `finally:` block. |
| **AUD-04** | **HIGH** | `razorpay_server.py` | `FulfillmentDatabase._connect()` leaked database handles. | **RESOLVED**: Refactored to `@contextlib.contextmanager` with explicit `conn.close()`. |
| **AUD-05** | **HIGH** | `razorpay_server.py` | Dangling `urllib.error.HTTPError` response stream in self-test caused GC ResourceWarning. | **RESOLVED**: Added explicit `e.close()` in error handler. |
| **AUD-06** | **MEDIUM** | `deploy.yml`, `setup_windows.bat` | Stale "Bajrang AI Pro" legacy naming created confusion after GitHub repo rename. | **RESOLVED**: Synchronized workflow titles and batch script banners to "Sudharshan AI (Alpha v0.9)". |
| **AUD-07** | **MEDIUM** | `windows.py` | `badge_colors` lacked `AgentState.OFFLOADED` mapping. | **RESOLVED**: Added `("#334155", "#94a3b8")` color mapping. |
| **AUD-08** | **LOW** | `privacy.html`, `terms.html`, `credits.html` | Color tokens (`#93f1f7`) conflicted with Taste-Skill Solar Orange identity. | **RESOLVED**: Aligned with Solar Orange (`#ff6b1a`) and Obsidian Black (`#050505`). |

---

## 4. Verification Harness Summary

- **Static Linter / py_compile**: 100% clean, zero syntax errors.
- **ResourceWarning Audit**: Python execution with `-W default` yields **0 warnings**.
- **Automated Test Results**:
  1. `bajrang_core.py --self-test` -> **PASSED (0)**
  2. `windows.py --self-test` -> **PASSED (0)**
  3. `fedora.py --self-test` -> **PASSED (0)**
  4. `razorpay_server.py --self-test` -> **PASSED (0)**
  5. `installer_windows.py --self-test` -> **PASSED (0)**
  6. `test_bajrang_suite.py` -> **14/14 PASSED (0)**
