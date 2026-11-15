# SUDHARSHAN AI (ALPHA v0.9) — ARCHITECTURAL & ENGINEERING DECISIONS

**Project**: Sudharshan AI  
**Lead Architect**: Kaushik Ram Ravuru (B.E. IT, CBIT Hyderabad)  
**Document Version**: 1.0 (Alpha v0.9 Hardened)  

---

### ADR-001: Unified Platform Adapter Pattern (`BasePlatformAdapter`)
* **Context**: Multiple platforms (Fedora, generic Linux, Windows, macOS) require native desktop hooks (clipboard, notifications, TTS, hotkeys, screenshot capture).
* **Decision**: Extend `BasePlatformAdapter` in `bajrang_core.py`. Rather than creating competing platform layers, `WindowsPlatformAdapter` (`windows.py`), `FedoraWaylandAdapter` (`fedora.py`), `GenericLinuxAdapter` (`linux_generic.py`), and `MacOSPlatformAdapter` (`macos.py`) all inherit from the same canonical interface.
* **Consequences**: Standardized response types (`ActionResult`), uniform hotkey validation, and centralized capability queries via `PlatformCapabilityMatrix`.

---

### ADR-002: Asymmetric 2048-Bit RSA License Verification (C1 / H5)
* **Context**: The legacy project used client-side symmetric MD5/SHA256 hashing with a hardcoded `SECRET_SALT` (`BAJRANG-PRO-2025-SECRET-SALT-HYDERABAD`), allowing any user to generate valid licenses offline.
* **Decision**: Completely removed the symmetric key generator and salt. License verification now uses an asymmetric 2048-bit RSA public key embedded in `bajrang_core.py`. Private key signing occurs exclusively on the remote server (`razorpay_server.py`).
* **Consequences**: Zero client-side license forgery possible. Forged tokens are rejected deterministically.

---

### ADR-003: Re-entrant Lock for Chained Prompt Planning
* **Context**: `BajrangEngine.process_prompt` initially held a standard `threading.Lock()`. When executing multi-step chained queries (e.g. `"list windows then status"`), internal dispatch of sub-steps back through `process_prompt` resulted in a thread self-deadlock.
* **Decision**: Changed `self._turn_lock` to `threading.RLock()`.
* **Consequences**: Enables safe recursive/nested prompt evaluations within the same thread while preserving concurrency boundaries across background voice and UI threads.

---

### ADR-004: Static Autostart Methods for Ollama Watchdog (Phase A Fix)
* **Context**: `OllamaWatchdogManager.ensure_running()` invoked `UnifiedModelClient._try_autostart_ollama()` on the class object. Because `_try_autostart_ollama` was an instance method, Python raised `TypeError: missing 1 required positional argument: 'host'`.
* **Decision**: Converted `_try_autostart_ollama` and `_find_ollama_binary` into `@staticmethod`s that take the explicit host string and execute independent binary discovery across `%LOCALAPPDATA%`, `/usr/bin/ollama`, and `/usr/local/bin/ollama`.
* **Consequences**: Guaranteed clean fallback without unhandled exceptions when Ollama daemon is offline.

---

### ADR-005: Destructive File Operation Safety Invariants (Phase 9)
* **Context**: Desktop assistants executing file operations run the risk of catastrophic data loss, accidental dotfile destruction, or directory escapes.
* **Decision**: 
  1. No permanent deletion (`os.remove` / `shutil.rmtree` forbidden); files are moved to a versioned `.quarantine` / trash folder.
  2. Mandatory reversibility: all operations generate a JSON undo manifest.
  3. Symlink resolution and path boundary checks prevent path traversal outside authorized user directories (`Downloads`, `Documents`, `Desktop`).
  4. Auto-approve mode requires explicit risk acknowledgment, is scoped to the session, and resets to `False` on application exit.

---

### ADR-006: Taste-Skill Design Token Architecture
* **Context**: UI previously suffered from disparate styling, harsh high-contrast backgrounds, and inconsistent component edges.
* **Decision**: Consolidated UI tokens around Obsidian Black (`#050505`), Card Surface (`#0f0c0a`), Border (`#26201c`), and Solar Orange (`#ff6b1a`). Standardized typography across platforms to `Instrument Sans` and `DM Mono`.
* **Consequences**: Aesthetic harmony across the Windows HUD, GTK modern widgets, web landing page, and downloads portal.
