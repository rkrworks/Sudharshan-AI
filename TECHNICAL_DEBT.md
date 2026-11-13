# SUDHARSHAN AI (Alpha v0.9) — TECHNICAL DEBT REGISTER & ARCHITECTURAL LOG

**Project**: Sudharshan AI (Alpha v0.9)  
**Maintained by**: Kaushik Ram Ravuru (B.E. IT, Section IT-1, CBIT Hyderabad)  
**Classification System**: Architectural, Dependency, Operational, Code Duplication

---

## Technical Debt Inventory

### 1. Code Duplication & Compatibility Aliases
- **Item**: Parallel Modules (`windows.py` &harr; `bajrang_windows.py`, `fedora.py` &harr; `bajrang_llama32.py`).
  - **Reason**: Maintained to preserve backward compatibility for automated tests and external scripts that import `bajrang_windows` or `bajrang_llama32`.
  - **Debt Score**: Medium.
  - **Mitigation Strategy**: Both modules are kept 100% byte-for-byte in sync. In a future major release (v1.0), `bajrang_windows.py` and `bajrang_llama32.py` can become thin forwarding stubs (`from windows import *`).

- **Item**: Duplicate Requirements Files (`requirements-windows.txt` vs `requirements_windows.txt`).
  - **Reason**: Different CI systems and installation scripts use hyphens or underscores.
  - **Debt Score**: Low.
  - **Mitigation Strategy**: Synchronize contents automatically during release packaging.

### 2. Large Pre-Built Bundle Archives in Repository Root
- **Item**: `BajrangAI_Fedora_Linux_Complete_Bundle.zip`, `BajrangAI_Windows11_Complete_Bundle.zip`, `bajrang_ai_git_repo.zip`.
  - **Reason**: Stored in repository root for convenience during initial development.
  - **Debt Score**: Medium.
  - **Mitigation Strategy**: Move large binary distributions to GitHub Releases (`v0.9-alpha`) to reduce git clone payload.

### 3. Desktop Automation Dependency Nuances
- **Item**: Wayland input synthesis requires `ydotoold` daemon and `/dev/uinput` permissions on Fedora Linux.
  - **Reason**: Modern Wayland security models explicitly disallow arbitrary unprivileged keystroke synthesis.
  - **Debt Score**: Medium.
  - **Mitigation Strategy**: `setup_fedora.sh` automates the udev rule (`80-uinput-bajrang.rules`) and user service creation.

### 4. Taste-Skill Asset Footprint
- **Item**: ~8,000 fine-grained JS/MJS modules in `assets/` for visual moments, components, and shader effects.
  - **Reason**: Taste-skill 2.5 framework provides standalone modular units for zero-bundler static serving.
  - **Debt Score**: Low.
  - **Mitigation Strategy**: All static assets validate without syntax errors. `vercel.json` and GitHub Pages serve them with caching headers.
