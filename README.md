# Bajrang AI Pro — Fedora Linux GNOME Assistant & Portal

Locally-run and cloud-powered AI desktop assistant tailored for Fedora Linux (GNOME / Wayland).
Integrates with Ollama Llama 3.2 or custom API keys, featuring a custom PipeWire 8-band Spectral-DTW Voice Recognizer, SQLite3 local chat history, GNOME Shell 45-49 ESM Top-Bar extension, and a commercial storefront with Razorpay checkout.

## Features
- **Flexible Intelligence**: Run 100% offline via local Ollama `llama3.2` or enter your own OpenAI / Groq / OpenRouter API key for free cloud inference.
- **Dynamic Themes**: Bright Mode & Dark Mode switch in both the GTK4/Libadwaita HUD and web portal.
- **Voice Mode**: Pure-Python DSP (VAD + 8-band Goertzel Spectral-DTW acoustic template matcher) recording 16kHz mono PCM via PipeWire (`pw-record`).
- **Local Storage**: Persistent SQLite3 history (`~/.local/share/bajrang-ai/history.db`) with full-text search.
- **GNOME Shell Extension**: Native top-bar status pill and control menu (`bajrang-ai@fedora.local`) communicating over local IPC (`127.0.0.1:17420`).
- **Safety Guardrail**: Built-in blocklist preventing root escalation and destructive commands, plus instant Emergency Kill-Switch (`Ctrl+Escape`).

## How to Host on GitHub Pages
1. Initialize repository and push to GitHub:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Bajrang AI Pro for Fedora Linux"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/bajrang-ai.git
   git push -u origin main
   ```
2. Enable GitHub Pages in your repo:
   - Go to **Settings → Pages**
   - Under **Build and deployment**, select **GitHub Actions** (or **Deploy from a branch → main / root**)
   - Your website will be live at `https://YOUR_USERNAME.github.io/bajrang-ai/`

## Quick Start on Fedora Workstation
```bash
chmod +x setup_fedora.sh bajrang_llama32.py
./setup_fedora.sh
```
