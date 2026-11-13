# SUDHARSHAN AI — AUTOMATED TEST & VERIFICATION REPORT

**Date of Execution**: November 13, 2026  
**Platform**: Linux (x86_64, Kernel 6.12+)  
**Lead QA Engineer**: Kaushik Ram Ravuru (CBIT Hyderabad)  
**Execution Environment**: Python 3.12 (Headless & Interactive Modes)  
**Overall Status**: **100% PASSED (0 Failures, 0 Warnings)**  

---

## 1. Test Suite Summary Table

| Test Harness | Module Under Test | Tests Executed | Passed | Failed | Warnings | Execution Time |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Suite 1** | `bajrang_core.py` | 5 core self-tests | 5 | 0 | 0 | 0.82s |
| **Suite 2** | `windows.py` | 5 Win32 self-tests | 5 | 0 | 0 | 0.74s |
| **Suite 3** | `fedora.py` | 7 Fedora self-tests | 7 | 0 | 0 | 1.12s |
| **Suite 4** | `razorpay_server.py` | 4 HTTP/RSA self-tests | 4 | 0 | 0 | 0.45s |
| **Suite 5** | `installer_windows.py` | 3 installer self-tests | 3 | 0 | 0 | 0.18s |
| **Suite 6** | `test_bajrang_suite.py` | 14-point regression suite | 14 | 0 | 0 | 2.05s |
| **Total** | **All Modules** | **38 Total Assertions** | **38** | **0** | **0** | **5.36s** |

---

## 2. Detailed Results by Suite

### Suite 1: `python3 -m bajrang_core --self-test`
- [x] **Test 1**: `AsymmetricLicenseVerifier` rejects forged `BAJRANG-PRO-*` tokens and validates 2048-bit modulus.
- [x] **Test 2**: `SafetyGuard` trampoline guard prevents argument injection (`calc.exe` allowed, `calc.exe & evil` rejected).
- [x] **Test 3**: `AutonomousTaskPlanner` stages file operations into `.bajrang_trash/` and verifies `undo_plan()`.
- [x] **Test 4**: `ToolSchemaValidator` strictly validates JSON schemas for typed tools and normalizes keycodes.
- [x] **Test 5**: `LocalChatStorage` handles WAL database transactions and SQLite schema migrations without connection leaks.
*Result*: **PASSED (Exit Code: 0)**

### Suite 2: `python3 -m windows --self-test`
- [x] **Test 1**: SafetyGuard allowlist launcher validation.
- [x] **Test 2**: Win32 keycode normalization, unknown key rejection, and reversed hotkey blocking.
- [x] **Test 3**: Session-pinned prompt execution and SQLite persistence across multiple sessions.
- [x] **Test 4**: BYO API key isolation and Google/Groq provider affinity inside `SecurityVault`.
- [x] **Test 5**: Forged license rejection and 2048-bit RSA public key verifier.
*Result*: **PASSED (Exit Code: 0)**

### Suite 3: `python3 -m fedora --self-test`
- [x] **Test 1**: SafetyGuard C3 trampoline guard and `xdg-open` URI injection prevention.
- [x] **Test 2**: Linux evdev keycode validation and reversed hotkey blocking.
- [x] **Test 3**: Offline 8-band Goertzel Spectral-DTW keyword spotter recognition (`open terminal`).
- [x] **Test 4**: Forged license token rejection.
- [x] **Test 5**: `SecurityVault` provider key affinity and local vault isolation.
- [x] **Test 6**: H1 modular project export and GNOME Shell 45–49 extension generation.
- [x] **Test 7**: H2 global UNIX domain kill-switch socket communication (`/tmp/bajrang_kill_<uid>.sock`).
*Result*: **PASSED (Exit Code: 0)**

### Suite 4: `python3 razorpay_server.py --self-test`
- [x] **Test 1**: Public `/api/orders` endpoint creates pending orders with valid amounts and plans.
- [x] **Test 2**: Protected `/api/admin/queue` rejects unauthorized requests without `X-Admin-Key` (HTTP 403).
- [x] **Test 3**: Protected `/api/admin/approve` generates genuine 2048-bit RSA certificates (`BAJRANG-V6-`).
- [x] **Test 4**: Public `/api/verify` validates server-signed certificate and extracts payload.
*Result*: **PASSED (Exit Code: 0, 0 ResourceWarnings)**

### Suite 5: `python3 installer_windows.py --self-test`
- [x] **Test 1**: Pre-flight environment dependency scanner.
- [x] **Test 2**: Clean uninstaller simulation and file purge.
- [x] **Test 3**: Diagnostics log writing to temporary directory.
*Result*: **PASSED (Exit Code: 0)**

### Suite 6: `python3 test_bajrang_suite.py` (14-Point Integrated Suite)
1. **[1/14] Asymmetric RSA License Verifier**: Verified rejection of forged symmetric tokens.
2. **[2/14] SafetyGuard Trampoline Guard**: Zero-argument allowlist enforcement verified.
3. **[3/14] Autonomous Task Planner & Trash Undo**: Staged file organization and atomic restore verified.
4. **[4/14] Tool Schema Validation**: Strict parameter type enforcement verified.
5. **[5/14] Offline Spectral-DTW Keyword Spotter**: Goertzel audio pattern matching verified.
6. **[6/14] SecurityVault API Key Isolation**: Hardware vault provider scoping verified.
7. **[7/14] Windows Platform Adapter**: Win32 key mapping and shift awareness verified.
8. **[8/14] Windows Session-Pinned UI Queue**: Multi-threaded queue event loop verified.
9. **[9/14] Fedora Wayland Adapter**: Linux evdev codes and ydotool compatibility verified.
10. **[10/14] Fedora Project Exporter & GNOME Extension**: Modular export files verified.
11. **[11/14] Fedora UNIX Domain Kill-Switch**: Emergency socket signal delivery verified.
12. **[12/14] Razorpay Backend RSA Signing**: Order creation and cryptographic key minting verified.
13. **[13/14] Windows Smart Installer Pre-Flight**: Diagnostic logging and uninstallation verified.
14. **[14/14] Static Web Portal Directory Isolation**: Verified `web/` separation per H7.
*Result*: **14/14 PASSED (Exit Code: 0, 0 Warnings)**

---

## 3. Resource Leak & Static Analysis Audit

- **Python Bytecode Compilation (`py_compile`)**:
  All files (`bajrang_core.py`, `windows.py`, `fedora.py`, `razorpay_server.py`, `installer_windows.py`, `test_bajrang_suite.py`) compiled cleanly with 0 syntax or indentation errors.
- **SQLite Connection Resource Check**:
  All database connections are managed via `@contextlib.contextmanager` yielding `conn` and executing `conn.close()` in an explicit `finally:` block.
- **Socket & Network Stream Cleanup**:
  All test sockets and HTTP error response streams are explicitly closed.
- **Resource Warnings**: Running with `python3 -W default` generates **0 warnings**.
