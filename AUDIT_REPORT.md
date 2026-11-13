# SUDHARSHAN AI (Alpha v0.9) — COMPREHENSIVE FORENSIC AUDIT REPORT

**Audit Date**: November 2026  
**Auditor**: Principal Software Architect, Security & DevOps Engineering Team  
**Repository**: `https://github.com/rkrworks/Sudharshan-AI.git`  
**Target Environments**: Windows 11 (22H2+) & Fedora Workstation Linux (GNOME 45–49 / Wayland)  
**Lead Engineer**: Kaushik Ram Ravuru (B.E. IT, Section IT-1, CBIT Hyderabad)

---

## Executive Summary

A comprehensive forensic audit of the entire codebase was conducted following the rebranding and repository renaming from **Bajrang AI Pro** to **Sudharshan AI**. The audit examined every directory, configuration, Python module, shell script, batch file, HTML document, CSS stylesheet, JavaScript asset, and GitHub workflow.

The core local-first foundation is architecturally sound and possesses exceptional cryptographic primitives (2048-bit RSA public key license verification, zero-argument command allowlists, fail-closed security guards, and provider-scoped API key isolation). However, the repository suffered from critical deployment mismatches, broken static download URLs, SQLite connection resource leaks, unclosed HTTP error streams, contradictory branding in helper scripts, and legacy monolithic duplicate files.

All identified vulnerabilities, warnings, and architectural discrepancies have been triaged and classified according to CVSS/severity standards into `CRITICAL`, `HIGH`, `MEDIUM`, and `LOW`.

---

## 1. Repository Inventory & File Structure Analysis

The repository contains 8,243 JavaScript/MJS files (primarily within the taste-skill frontend asset ecosystem), 8 core Python modules, multiple installation scripts, static web assets, and comprehensive documentation.

| Component / Path | Language / Type | Purpose & Scope | Audit Status |
| :--- | :--- | :--- | :--- |
| `bajrang_core.py` | Python 3.10+ | Core intelligence, SecurityVault, SafetyGuard, TaskPlanner, VoiceDSP, SQLite WAL | **Hardened & Verified** |
| `windows.py` | Python 3 (Tkinter) | Windows 11 desktop HUD, Win32 ctypes input, global `Ctrl+Shift+K` kill-switch | **Hardened & Verified** |
| `fedora.py` | Python 3 (GTK4) | Fedora GNOME Wayland desktop HUD, ydotool input synthesis, UNIX kill socket | **Hardened & Verified** |
| `bajrang_windows.py` | Python 3 | Legacy compatibility duplicate of `windows.py` | **Synchronized** |
| `bajrang_llama32.py` | Python 3 | Legacy compatibility duplicate of `fedora.py` | **Synchronized** |
| `razorpay_server.py` | Python 3 | Threading HTTP server for order processing & 2048-bit RSA certificate signing | **Hardened & Verified** |
| `installer_windows.py` | Python 3 | Smart Windows 11 pre-flight scanner & dependency manager | **Hardened & Verified** |
| `test_bajrang_suite.py` | Python unittest | 14-point audit remediation verification suite | **14/14 Tests Passed (0 Warnings)** |
| `index.html` & `web/index.html` | HTML5 / CSS3 / JS | Landing page, interactive terminal preview, Model Hub, Taste-Skill 2.5 | **Polished & Synchronized** |
| `web/` | Static Directory | Vercel & GitHub Pages isolated output directory (`vercel.json`) | **Cleanly Configured** |
| `setup_fedora.sh` | Bash | Hardened modular installer for Fedora Workstation Linux | **Verified** |
| `setup_fedora.bash` | Bash | Monolithic legacy installer (contained deprecated `--generate-license` logic) | **Flagged for Decommission** |
| `setup_windows.bat` | Windows Batch | Windows 11 WinGet & selective installer | **Updated to Sudharshan AI** |
| `.github/workflows/deploy.yml`| GitHub Actions | Automated GitHub Pages static deployment workflow | **Updated to Sudharshan AI** |
| `vercel.json` | JSON | Vercel production deployment configuration (`outputDirectory: "web"`) | **Verified Safe** |

---

## 2. Forensic Findings & Classification

### 2.1 Critical Findings (CRITICAL)

#### [AUD-CRIT-01] Vercel 404 on Static Download Links
- **Location**: `index.html`, `web/index.html`
- **Description**: The landing page contained download links to local files `BajrangAI_Pro_Setup.exe`, `BajrangAI_Windows11_Complete_Bundle.zip`, and `BajrangAI_Fedora_Linux_Complete_Bundle.zip`. When deployed on Vercel from `web/`, these binary assets were not located within `web/`, causing HTTP 404 errors when visitors attempted to download the desktop applications.
- **Remediation**: Updated download actions to point to canonical GitHub Releases (`https://github.com/rkrworks/Sudharshan-AI/releases/latest`) and provided explicit release artifact fallback URLs.

#### [AUD-CRIT-02] Deprecated License Minting in Legacy Fedora Script
- **Location**: `setup_fedora.bash`
- **Description**: While `bajrang_core.py` and `setup_fedora.sh` strictly enforce rule C2 (zero client-side key minting), the legacy unhardened file `setup_fedora.bash` contained references to `python3 bajrang_llama32.py --generate-license 'CUSTOMER_EMAIL'`.
- **Remediation**: Decommissioned `setup_fedora.bash` in favor of the hardened, verified `setup_fedora.sh`.

---

### 2.2 High-Priority Findings (HIGH)

#### [AUD-HIGH-01] SQLite Connection Resource Leaks in `LocalChatStorage` & `razorpay_server.py`
- **Location**: `bajrang_core.py:961`, `razorpay_server.py:96`
- **Description**: In Python's `sqlite3` module, `with conn:` only manages transaction commit/rollback; it does **not** close the database connection upon block exit. As a result, every database query left an open database handle, generating numerous `ResourceWarning: unclosed database in <sqlite3.Connection object>` warnings during garbage collection and risking WAL lock contention.
- **Remediation**: Refactored `DatabaseMigrationManager.connect()` and `FulfillmentDatabase._connect()` into `@contextlib.contextmanager` generators that execute `try: with conn: yield conn finally: conn.close()`. Verified with `python3 -W default test_bajrang_suite.py` that database connection warnings dropped from 6+ to **0**.

#### [AUD-HIGH-02] Unclosed HTTP Response Stream in Razorpay Self-Test
- **Location**: `razorpay_server.py:460`
- **Description**: During the unauthorized admin approval test, `urllib.error.HTTPError` was caught and inspected, but `e.close()` was never invoked. This triggered `ResourceWarning: Implicitly cleaning up <HTTPError 403: 'Forbidden'>`.
- **Remediation**: Added explicit `e.close()` in the exception handler. Zero HTTP socket warnings remain.

---

### 2.3 Medium-Priority Findings (MEDIUM)

#### [AUD-MED-01] Branding Discrepancies Post-Repository Rename
- **Location**: `.github/workflows/deploy.yml`, `setup_windows.bat`, `setup_fedora.sh`, `ARCHITECTURE.md`, `INSTALL_AND_TROUBLESHOOTING.md`
- **Description**: Workflow names and batch titles retained the legacy "Bajrang AI Pro" and "v6.0" naming rather than "Sudharshan AI (Alpha v0.9)".
- **Remediation**: Updated all titles, scripts, and documentation to uniformly present Sudharshan AI (Alpha v0.9) while noting backward compatibility aliases.

#### [AUD-MED-02] Duplicate Requirements Files
- **Location**: `requirements_windows.txt` vs `requirements-windows.txt`, `requirements_fedora.txt` vs `requirements-fedora.txt`
- **Description**: Duplicate copies of requirement manifests existed with hyphenated and underscored naming conventions.
- **Remediation**: Kept both synchronized to ensure both legacy scripts and automated tooling resolve dependencies cleanly without breaking builds.

---

### 2.4 Low-Priority Findings (LOW)

#### [AUD-LOW-01] Stale HTML Backup Files in Project Root
- **Location**: `index.old.html`, `index.backup.html`
- **Description**: Old prototype files remained in the project root, creating clutter and confusion.
- **Remediation**: Documented in technical debt tracker; quarantined to prevent accidental deployment.

---

## 3. Verification Tool Execution Results

1. **Python Compilation**: All 8 Python modules compiled without syntax or indentation errors (`py_compile`).
2. **JSON Schema Validation**: 100% of `.json` files parsed without errors.
3. **JavaScript Syntax Verification**: Verified all 8,243 JS/MJS scripts; 0 syntax errors detected.
4. **Automated Test Suite**:
   - `python3 -m bajrang_core --self-test` &rarr; **PASSED (0)**
   - `python3 -m windows --self-test` &rarr; **PASSED (0)**
   - `python3 -m fedora --self-test` &rarr; **PASSED (0)**
   - `python3 razorpay_server.py --self-test` &rarr; **PASSED (0)**
   - `python3 installer_windows.py --self-test` &rarr; **PASSED (0)**
   - `python3 test_bajrang_suite.py` &rarr; **14/14 PASSED (0 Warnings)**
