#!/usr/bin/env bash
# ==============================================================================
# Bajrang AI Pro — Complete Fresh Fedora Workstation (GNOME / Wayland) Installer
# ==============================================================================
# Installs and configures everything from scratch on a brand-new Fedora Linux
# installation:
#   1. System update & core build tools
#   2. GTK4, Libadwaita, PyGObject, SQLite3, Pillow
#   3. PipeWire (`pw-record`), ALSA (`arecord`), Speech-Dispatcher (`spd-say`),
#      espeak-ng, and optional faster-whisper for Voice Mode
#   4. Wayland automation (`ydotool`, `grim`, `gnome-screenshot`, `wl-clipboard`)
#      + `/dev/uinput` non-root udev rule + `ydotoold` systemd user service
#   5. Ollama local LLM service + `llama3.2` model pull
#   6. Bajrang AI Pro modular project (`~/bajrang-ai`) + systemd user daemon
#   7. Native GNOME Shell 45-49 Top-Bar Extension (`bajrang-ai@fedora.local`)
#   8. GNOME Custom Keyboard Shortcuts (`Super+Space` HUD, `Super+V` Voice,
#      `Ctrl+Escape` Emergency Kill-Switch)
# ==============================================================================

set -euo pipefail

PROJECT_DIR="${BAJRANG_DIR:-$HOME/bajrang-ai}"
MODEL_NAME="${BAJRANG_MODEL:-llama3.2}"
YDOTOOL_SOCK="/tmp/.ydotool_socket"
EXTENSION_UUID="bajrang-ai@fedora.local"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "======================================================================"
echo "  Bajrang AI Pro (v3.0) — Fresh Fedora GNOME/Wayland Full Installer"
echo "======================================================================"

# 1. Core Fedora DNF Packages (GUI, Audio/PipeWire, Wayland Automation, Extensions)
echo "[1/8] Installing Fedora system packages via DNF..."
sudo dnf install -y \
    python3 \
    python3-pip \
    python3-gobject \
    python3-pillow \
    sqlite \
    gtk4 \
    libadwaita \
    pipewire-utils \
    alsa-utils \
    speech-dispatcher \
    speech-dispatcher-utils \
    espeak-ng \
    ydotool \
    grim \
    gnome-screenshot \
    wl-clipboard \
    gnome-extensions-app \
    gnome-shell-extension-common \
    curl \
    git

# Optional local Whisper STT acceleration (falls back to built-in Bajrang DSP Spectral-DTW recognizer if skipped)
echo "[2/8] Installing optional faster-whisper Python package for open-ended dictation..."
pip3 install --user --upgrade faster-whisper 2>/dev/null || true

# 2. Configure /dev/uinput udev rule for non-root Wayland input automation
echo "[3/8] Configuring /dev/uinput permissions for Wayland ydotool automation..."
UDEV_RULE_FILE="/etc/udev/rules.d/80-uinput-bajrang.rules"
echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' | sudo tee "$UDEV_RULE_FILE" >/dev/null
sudo usermod -aG input,pipewire,audio "$USER" || true
sudo udevadm control --reload-rules
sudo udevadm trigger

# 3. Start ydotoold daemon & create systemd user service
echo "[4/8] Setting up ydotoold daemon on $YDOTOOL_SOCK..."
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/ydotoold-bajrang.service" <<EOF
[Unit]
Description=Bajrang AI ydotoold Wayland Input Daemon
After=graphical-session.target

[Service]
ExecStart=/usr/bin/ydotoold --socket-path=$YDOTOOL_SOCK --socket-perm=0600
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload || true
systemctl --user enable --now ydotoold-bajrang.service 2>/dev/null || (
    ydotoold --socket-path="$YDOTOOL_SOCK" --socket-perm=0600 >/dev/null 2>&1 &
    disown || true
)

# 4. Install & Start Ollama + Pull Llama 3.2
echo "[5/8] Installing Ollama and pulling '$MODEL_NAME'..."
if ! command -v ollama >/dev/null 2>&1; then
    curl -fsSL https://ollama.com/install.sh | sh
fi

sudo systemctl enable --now ollama 2>/dev/null || (
    ollama serve >/dev/null 2>&1 &
    disown || true
)
sleep 2
ollama pull "$MODEL_NAME"

# 5. Export Modular Bajrang AI Pro Project & Local SQLite Storage
echo "[6/8] Deploying Bajrang AI Pro to $PROJECT_DIR..."
python3 "$SCRIPT_DIR/bajrang_llama32.py" --export-project "$PROJECT_DIR"
cp -f "$SCRIPT_DIR/bajrang_llama32.py" "$PROJECT_DIR/bajrang_llama32.py"
chmod +x "$PROJECT_DIR/bajrang_llama32.py" "$PROJECT_DIR/run.sh"

# 6. Install & Enable Native GNOME Shell Extension (bajrang-ai@fedora.local)
echo "[7/8] Installing GNOME Shell Top-Bar Extension ($EXTENSION_UUID)..."
python3 "$PROJECT_DIR/bajrang_llama32.py" --install-gnome-extension
gnome-extensions enable "$EXTENSION_UUID" 2>/dev/null || true

# 7. Register Desktop Launcher & GNOME Custom Keyboard Shortcuts
echo "[8/8] Configuring GNOME Application Launcher & Global Hotkeys..."
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/org.fedora.BajrangAI.desktop" <<EOF
[Desktop Entry]
Name=Bajrang AI Pro (Llama 3.2)
Comment=Fedora GNOME/Wayland Local AI Assistant with Voice Mode & Local Chat History
Exec=$PROJECT_DIR/run.sh --toggle
Icon=audio-input-microphone-symbolic
Terminal=false
Type=Application
Categories=Utility;ArtificialIntelligence;GNOME;GTK;
StartupNotify=false
EOF

# Bind Super+Space (Toggle HUD), Super+V (Voice Mode), Ctrl+Escape (Kill-Switch) in GNOME
if command -v gsettings >/dev/null 2>&1; then
    BASE_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
    gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings \
        "['$BASE_PATH/bajrang-toggle/', '$BASE_PATH/bajrang-voice/', '$BASE_PATH/bajrang-kill/']" 2>/dev/null || true

    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$BASE_PATH/bajrang-toggle/ name "Bajrang AI Toggle HUD" 2>/dev/null || true
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$BASE_PATH/bajrang-toggle/ command "$PROJECT_DIR/run.sh --toggle" 2>/dev/null || true
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$BASE_PATH/bajrang-toggle/ binding "<Super>space" 2>/dev/null || true

    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$BASE_PATH/bajrang-voice/ name "Bajrang AI Voice Mode" 2>/dev/null || true
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$BASE_PATH/bajrang-voice/ command "$PROJECT_DIR/run.sh --voice" 2>/dev/null || true
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$BASE_PATH/bajrang-voice/ binding "<Super>v" 2>/dev/null || true

    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$BASE_PATH/bajrang-kill/ name "Bajrang AI Kill Switch" 2>/dev/null || true
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$BASE_PATH/bajrang-kill/ command "$PROJECT_DIR/run.sh --kill" 2>/dev/null || true
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$BASE_PATH/bajrang-kill/ binding "<Control>Escape" 2>/dev/null || true
fi

echo ""
echo "======================================================================"
echo "  ✅ Bajrang AI Pro Installed Successfully on Fedora!"
echo "  • Launch Floating HUD     : $PROJECT_DIR/run.sh"
echo "  • Trigger Voice Mode      : $PROJECT_DIR/run.sh --voice   (or Super+V)"
echo "  • Enroll Voice Command    : python3 $PROJECT_DIR/bajrang_llama32.py --enroll-voice 'open terminal'"
echo "  • Generate ₹100/mo Key    : python3 $PROJECT_DIR/bajrang_llama32.py --generate-license 'CUSTOMER_EMAIL'"
echo "  • GNOME Extension Path    : ~/.local/share/gnome-shell/extensions/$EXTENSION_UUID"
echo "======================================================================"