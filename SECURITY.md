# Security Architecture & Remediation Report — Bajrang AI Pro (Hardened v3.0)

This document details the security controls enforced in **Bajrang AI Pro** and maps each of the 14 Critical (`C1`–`C6`) and High-Priority (`H1`–`H8`) audit findings to its code-level remediation.

## 1. Critical Audit Remediations (`C1`–`C6`)

### C1 — Asymmetric 2048-Bit RSA License Verification (`LicenseManager.verify_key`)
- **Vulnerability**: `LicenseManager.verify_key` previously accepted any 8-character suffix (`if sig != expected_chk and len(sig) != 8`) and relied on a public symmetric checksum (`BAJRANG-PRO-*`).
- **Remediation**:
  - Removed all `BAJRANG-PRO-*` symmetric checksum acceptance from `LicenseManager.verify_key` (`bajrang_core.py`) and the web verifier (`web/index.html`).
  - `AsymmetricLicenseVerifier` verifies only `BAJRANG-V6-<base64url_payload>.<hex_rsa2048_sig>` certificates signed with the server's 2048-bit RSA private key (`RSA_2048_MODULUS`, 2048 bits, `e = 65537`).
  - Forged tokens such as `BAJRANG-PRO-HACKER-20991231-ZZZZZZZZ` are unconditionally rejected.

### C2 — Server-Side Admin Authentication & Key Minting (`razorpay_server.py` & `web/index.html`)
- **Vulnerability**: `index.html` and `portal_app.js` exposed `OWNER_EMAIL_HASH`, `OWNER_DEFAULT_PASSKEY`, and `generateBajrangLicenseKey` in client-side JavaScript.
- **Remediation**:
  - Removed `OWNER_EMAIL_HASH`, `OWNER_DEFAULT_PASSKEY`, and `generateBajrangLicenseKey` from `web/index.html`, `index.html`, and `portal_app.js`.
  - Admin authentication and license minting are enforced server-side in `razorpay_server.py` (`/api/admin/queue` and `/api/admin/approve`) using `hmac.compare_digest` against `BAJRANG_ADMIN_TOKEN_SHA256`.

### C3 — Strict Zero-Argument Application Launcher Allowlist (`SafetyGuard.check_command`)
- **Vulnerability**: `SafetyGuard.check_command` checked only `tokens[0]`, allowing argument-trampoline execution (`gnome-terminal -- python3 -c ...`, `wt.exe powershell -Command ...`, `xdg-open <url>`).
- **Remediation**:
  - Removed `xdg-open` from `ALLOWED_BINARIES`.
  - Enforced a strict **zero-argument policy** (`len(tokens) > 1` -> rejected) for all application launchers in `SafetyGuard.check_command`, alongside explicit interpreter and subshell flag blocking (`--`, `-c`, `-e`, `-command`, `-enc`, `python`, `powershell`, `bash`, `sh`, `cmd`).

### C4 — Mandatory Schema Validation, Removal of AI `shell_exec`, & Confirmation Gate (`BajrangEngine`)
- **Vulnerability**: `BajrangEngine.process_prompt` passed model-proposed actions directly to `execute_action` without `ToolSchemaValidator.validate_action` or user confirmation.
- **Remediation**:
  - Removed `shell_exec` from `ToolSchemaValidator.SCHEMAS` so the AI model can never invoke arbitrary shell commands.
  - Every model-proposed action in `BajrangEngine.process_prompt` is validated through `ToolSchemaValidator.validate_action(action)` before execution.
  - Mutating and input-injection tools (`type_text`, `press_key`, `click_point`, `navigate_hotkey`, `close_app`, `organize_directory`) are held in `engine.pending_actions` until explicitly approved via `engine.confirm_pending_actions()` (or `auto_confirm_actions=True`).

### C5 — Non-Destructive File Organizer with Collision Renaming, Trash & Undo (`AutonomousTaskPlanner`)
- **Vulnerability**: `AutonomousTaskPlanner.execute_approved_plan` overwrote existing destination files via `shutil.move`, deleted duplicates with `unlink()`, and only checked cancellation before the loop.
- **Remediation**:
  - Checks `cancel_ev.is_set()` on every iteration before touching a file.
  - Allocates collision-free paths (`report_1.pdf`, `report_2.pdf`, ...) via `_resolve_collision_free_destination` so existing files are never overwritten.
  - Moves duplicate files into `.bajrang_trash/<plan_id>/` instead of calling `unlink()`, records a reversible manifest (`manifest.json`), and implements `undo_plan(plan_id)` to restore all moved and trashed files.

### C6 — Provider-Scoped API Key Affinity & Header Authentication (`ModularAIRouter`)
- **Vulnerability**: On provider fallback, `ModularAIRouter` sent a single `byo_api_key` across all vendors (leaking Google `AIza*` keys to Groq/OpenAI) and passed Gemini keys in the `?key=` URL query string.
- **Remediation**:
  - Implemented `ModularAIRouter.is_key_compatible_with_provider(api_key, provider_id)`: `AIza*` keys are restricted strictly to `gemini`, `gsk_*` to `groq`, `sk-or-*` to `openrouter`, and standard `sk-*` to `openai`.
  - `_call_gemini` sends the API key exclusively in the `x-goog-api-key` HTTP request header with zero `?key=` URL query parameters.

## 2. High-Priority Audit Remediations (`H1`–`H8`)

- **H1 (Fedora Setup & GNOME Extension Paths)**: `setup_fedora.sh` copies `bajrang_core.py`, `fedora.py`, `windows.py`, and requirements into `$PROJECT_DIR` and verifies `$PROJECT_DIR/fedora.py` exists before writing `run.sh`. `FedoraWaylandAdapter.export_modular_project` writes all modules and configures the GNOME extension to invoke the resolved `fedora.py` path.
- **H2 (Global Emergency Kill-Switch & Stream Abort)**: `KillSwitchManager` tracks active HTTP streams (`register_active_stream`) and closes them immediately on `trigger_emergency_stop()`. `windows.py` polls `GetAsyncKeyState` globally for `Ctrl+Shift+K` / `VK_PAUSE` regardless of window focus, and `fedora.py` listens on `/tmp/bajrang_kill_<uid>.sock` (`python3 fedora.py --kill-running`).
- **H3 (Complete Tool Execution Coverage)**: `BajrangEngine.execute_action` implements all 11 schema tools (`open_app`, `list_windows`, `window_focus`, `close_app`, `type_text`, `press_key`, `click_point`, `scroll_view`, `navigate_hotkey`, `inspect_directory`, `organize_directory`, `memory_store`).
- **H4 (Strict Key Validation, Order-Independent Hotkey Guard & Shift Handling)**: Unknown keys in `press_key` return `(False, ...)` instead of defaulting to Enter (`0x0D` / `"28"`). `SafetyGuard.check_hotkey` compares normalized `frozenset` combinations so `["f4", "alt"]` and `["r", "win"]` are blocked regardless of order. Windows `type_text` emits `VK_SHIFT` (`0x10`) for uppercase letters and shifted symbols.
- **H5 (Live HTTP Payment Server & 2048-Bit RSA)**: `razorpay_server.py` runs a multi-threaded HTTP server (`ThreadingHTTPServer`) exposing `/api/health`, `/api/orders`, `/api/verify-payment`, `/api/webhook`, `/api/admin/queue`, `/api/admin/approve`, and `/api/license/verify` backed by 2048-bit RSA signing.
- **H6 (Honest Installer Status, Explicit Consent Gates & Full Uninstall Purge)**: `installer_windows.py` returns `False` for unhandled items (`python_runtime`), requires explicit `consent_winget=True` and `consent_model_pull=True` before invoking `winget` or pulling ~2 GB models, and purges `SecurityVault` credentials and `~/.bajrang_ai` on `--uninstall`.
- **H7 (Static Web Asset Isolation)**: `vercel.json` (`"outputDirectory": "web"`), `.vercelignore`, and `.github/workflows/deploy.yml` (`path: "web"`) publish only the isolated `web/` directory and strip inlined Base64 source archives from `web/index.html`.
- **H8 (Thread-Safe Tkinter Queue, Session-Pinned Turns & Non-Deadlocking TTS)**: `WindowsTkinterHUD` marshals all background updates through a `queue.Queue` polled by `root.after(40, ...)`, `BajrangEngine.process_prompt` pins `target_sid` at turn start so mid-flight session switches never corrupt history, and `speak_tts` releases `_tts_lock` before calling `engine.runAndWait()`.
