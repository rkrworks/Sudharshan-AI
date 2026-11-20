# SUDHARSHAN AI (ALPHA v0.9) — TECHNICAL DEBT & ARCHITECTURAL LOG

**Document Version**: 1.0 (Alpha v0.9 Hardened)  
**Lead Architect**: Kaushik Ram Ravuru (B.E. IT, CBIT Hyderabad)  

---

### 1. Legacy Monolith Decomposition
* **Debt Item**: `bajrang_core.py` is an extensive module (~6,500 lines) containing security, database storage, audio DSP, tool validation, hardware monitoring, and engine routing.
* **Impact**: While functionally cohesive and zero-circular-dependency compliant, file size increases cognitive overhead.
* **Remediation Plan**: In future major release (v1.0), gradually factor submodules into `sudharshan/core/` package (`storage.py`, `safety.py`, `dsp.py`, `engine.py`) while preserving backward-compatible import shims in `bajrang_core.py`.

---

### 2. Physical Platform Verification Gaps
* **Debt Item**: macOS (`macos.py`) native capabilities are verified via mocked unit tests; physical execution on Apple Silicon / macOS Sonoma hardware is required for final notarization.
* **Impact**: Unverified edge cases in physical Quartz event tapping or macOS accessibility permission popups.
* **Remediation Plan**: Run manual QA pass on physical macOS hardware with Gatekeeper notarization.

---

### 3. Asynchronous Model Streaming — [RESOLVED IN PHASE 0]
* **Debt Item**: UnifiedModelClient handles HTTP calls synchronously within the background engine worker thread (`stream: False`).
* **Impact**: Token-by-token streaming is not displayed in the Tkinter HUD; replies appear as complete turns.
* **Remediation Plan**: Implement SSE (Server-Sent Events) generator in `UnifiedModelClient.chat_stream()` and wire token chunk callbacks to UI transcript views.

---

### 4. Audio Input Hardware Flexibility — [RESOLVED IN PHASE 0]
* **Debt Item**: `SpectralVoiceSpotter` and `CustomVoiceRecognizer` default to system default recording devices (`pw-record`, `arecord`, or PowerShell audio hooks).
* **Impact**: Users with multiple microphones (e.g. USB headset vs webcam) cannot select preferred device via GUI settings.
* **Remediation Plan**: Add device enum query to `HardwareProfiler` and add a dropdown selector in the desktop settings modal.
