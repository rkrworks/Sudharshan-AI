# SUDHARSHAN AI (ALPHA v0.9) — KNOWN LIMITATIONS & ENVIRONMENT BOUNDARIES

**Project**: Sudharshan AI  
**Lead Architect**: Kaushik Ram Ravuru (B.E. IT, CBIT Hyderabad)  
**Document Version**: 1.0 (Alpha v0.9 Hardened)  

---

### 1. Hardware & Platform Testing Boundaries
* **macOS Physical Hardware**: `macos.py` is fully implemented using AppleScript, `screencapture`, `say`, and Quartz bindings, and passes mocked unit testing. However, live end-to-end execution on physical Apple Silicon / Intel hardware cannot be conducted inside this Linux development container. Real macOS testing must be validated on physical macOS devices.
* **Windows 11 Live Desktop**: `windows.py` passes all unit tests, hotkey validations, and headless Tkinter tests. Live GUI rendering and native DPAPI storage were verified via unit mocks on Linux; production verification requires a physical Windows machine.
* **Wayland Key Injection (`ydotool`)**: Under Wayland on Fedora/Linux, global input injection requires `ydotoold` daemon running with socket access (`/tmp/.ydotool_socket`). If the daemon is not active, `press_key` and `type_text` gracefully report blocked status via `ActionResult`.

---

### 2. Ollama Local AI Constraints
* **Model Availability**: If Ollama is installed but the user has not pulled a model (e.g. `llama3.2`), requests will present the guided setup card. Downloading large LLMs (~2-4 GB) requires user consent and an active internet connection.
* **GPU Acceleration**: Ollama automatically detects NVIDIA CUDA and AMD ROCm, but fallbacks to CPU inference on legacy hardware may result in higher latency per token.

---

### 3. Vercel & Cloud Deployment
* **Vercel Static Hosting**: The marketing website and downloads portal are statically deployed via Vercel (`outputDirectory: web`). Payment and RSA certificate issuance endpoints require running `razorpay_server.py` as an independent backend service or container.
* **GitHub Secret Rotation**: The compromised code signing certificates were expunged from the live tree. Code signing for Windows binaries (`signtool.exe`) requires injecting valid certificates into GitHub Actions secrets or signing on a secure release build machine.
