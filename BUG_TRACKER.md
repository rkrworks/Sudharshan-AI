# SUDHARSHAN AI (Alpha v0.9) — BUG TRACKER & DEFECT LOG

**Project**: Sudharshan AI (Alpha v0.9)  
**Maintained by**: Kaushik Ram Ravuru (B.E. IT, Section IT-1, CBIT Hyderabad)  
**Last Updated**: November 2026

---

## Active & Resolved Bug Register

| Bug ID | Severity | Component | Summary | Status | Resolution / Verification |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BUG-001** | **CRITICAL** | `index.html` / `web/` | Download links pointed to non-existent root files on Vercel (`404 Not Found`) | **RESOLVED** | Switched links to GitHub Releases canonical endpoint (`https://github.com/rkrworks/Sudharshan-AI/releases`) |
| **BUG-002** | **CRITICAL** | `setup_fedora.bash` | Legacy setup script contained deprecated `--generate-license` minting code (violating C2) | **RESOLVED** | Decommissioned `setup_fedora.bash` in favor of hardened `setup_fedora.sh` |
| **BUG-003** | **HIGH** | `bajrang_core.py` | SQLite connection leak in `DatabaseMigrationManager.connect()` (`ResourceWarning: unclosed database`) | **RESOLVED** | Refactored `connect()` to `@contextlib.contextmanager` with explicit `conn.close()` in `finally:` block |
| **BUG-004** | **HIGH** | `razorpay_server.py` | SQLite connection leak in `FulfillmentDatabase._connect()` (`ResourceWarning: unclosed database`) | **RESOLVED** | Refactored `_connect()` to `@contextlib.contextmanager` with explicit `conn.close()` |
| **BUG-005** | **HIGH** | `razorpay_server.py` | Unclosed HTTPError response stream in self-test causing garbage-collection warning | **RESOLVED** | Added `e.close()` in exception handler |
| **BUG-006** | **MEDIUM** | `.github/workflows/deploy.yml` | Workflow title retained legacy "Bajrang AI Pro" name | **RESOLVED** | Updated workflow title to "Deploy Sudharshan AI Static Web Portal" |
| **BUG-007** | **MEDIUM** | `setup_windows.bat` | Batch title and paths retained old v6.0 Bajrang branding | **RESOLVED** | Updated titles and messages to Sudharshan AI (Alpha v0.9) |
| **BUG-008** | **MEDIUM** | `windows.py` | Missing `AgentState.OFFLOADED` status badge color in desktop HUD | **RESOLVED** | Added `AgentState.OFFLOADED: ("#334155", "#94a3b8")` to `badge_colors` map |
| **BUG-009** | **LOW** | `terms.html`, `credits.html` | Stale contact email (`kaushik@example.com`) and missing CBIT Hyderabad affiliation | **RESOLVED** | Updated to `kaushikramravuru@gmail.com` and credited CBIT Hyderabad across all legal pages |
| **BUG-010** | **LOW** | `privacy.html`, `terms.html` | Cyan color tokens (`#93f1f7`) inconsistent with Taste-Skill Solar Orange identity | **RESOLVED** | Unified `:root` color tokens to Obsidian Black (`#050505`) and Solar Orange (`#ff6b1a`) |
| **BUG-011** | **CRITICAL** | `vercel.json` | Vercel build failed: `schema validation failed: should NOT have additional property 'public'` | **RESOLVED** | Removed deprecated `"public": false` from `vercel.json` root configuration |

---

## Defect Severity Definitions

- **CRITICAL**: Threatens security invariants, breaks production deployments, or causes 404s/data loss.
- **HIGH**: Memory leaks, unclosed sockets/file handles, race conditions, or unhandled exceptions under load.
- **MEDIUM**: Branding inconsistencies, missing status state mappings, or redundant configuration files.
- **LOW**: Minor formatting, cosmetic styling, or stale comments.
