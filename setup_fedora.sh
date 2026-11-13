#!/usr/bin/env bash
set -euo pipefail

echo "=================================================================="
echo "  Sudharshan AI (Alpha v0.9) — Fedora Workstation Setup"
echo "  Engineered by Kaushik Ram Ravuru (B.E. IT, CBIT Hyderabad)"
echo "=================================================================="

# Safe resolution of script location (supports curl -fsSL ... | bash)
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

PROJECT_DIR="${SUDHARSHAN_INSTALL_DIR:-${BAJRANG_INSTALL_DIR:-$HOME/sudharshan-ai}}"
mkdir -p "$PROJECT_DIR"

RAW_BASE="https://raw.githubusercontent.com/rkrworks/Sudharshan-AI/main"
CORE_FILES=(
    bajrang_core.py
    fedora.py
    windows.py
    bajrang_llama32.py
    bajrang_windows.py
    requirements_common.txt
    requirements_fedora.txt
    README.md
    SECURITY.md
)

# Check if current directory or script directory has the core files
LOCAL_SRC=""
if [ -n "${SCRIPT_DIR:-}" ] && [ -f "$SCRIPT_DIR/bajrang_core.py" ]; then
    LOCAL_SRC="$SCRIPT_DIR"
elif [ -f "$(pwd)/bajrang_core.py" ]; then
    LOCAL_SRC="$(pwd)"
fi

echo "[1/6] Deploying Sudharshan AI application files into $PROJECT_DIR..."
for f in "${CORE_FILES[@]}"; do
    if [ -n "$LOCAL_SRC" ] && [ -f "$LOCAL_SRC/$f" ]; then
        cp -f "$LOCAL_SRC/$f" "$PROJECT_DIR/$f"
    else
        echo "  -> Fetching $f from repository..."
        curl -fsSL "$RAW_BASE/$f" -o "$PROJECT_DIR/$f" || true
    fi
done

if [ ! -f "$PROJECT_DIR/fedora.py" ] || [ ! -f "$PROJECT_DIR/bajrang_core.py" ]; then
    echo "ERROR: Failed to retrieve required application files (bajrang_core.py, fedora.py)." >&2
    exit 1
fi

chmod +x "$PROJECT_DIR/fedora.py"

# [2/6] Fedora System Dependencies
if [ "${BAJRANG_SKIP_SYSTEM_PKGS:-0}" != "1" ]; then
    echo "[2/6] Installing Fedora system packages (GTK4, Libadwaita, PipeWire, ydotool, grim, slurp, wl-clipboard)..."
    if command -v dnf >/dev/null 2>&1; then
        if [ "$(id -u)" -eq 0 ]; then
            dnf install -y python3 python3-pip python3-gobject gtk4 libadwaita pipewire-utils speech-dispatcher ydotool grim slurp wl-clipboard || true
        elif sudo -n true 2>/dev/null; then
            sudo dnf install -y python3 python3-pip python3-gobject gtk4 libadwaita pipewire-utils speech-dispatcher ydotool grim slurp wl-clipboard || true
        elif [ -t 0 ] || [ -t 1 ]; then
            sudo dnf install -y python3 python3-pip python3-gobject gtk4 libadwaita pipewire-utils speech-dispatcher ydotool grim slurp wl-clipboard || true
        else
            echo "  -> Sudo password required for system packages; skipping in non-interactive pipeline."
        fi
    fi
else
    echo "[2/6] Skipping dnf system packages (BAJRANG_SKIP_SYSTEM_PKGS=1)."
fi

# [3/6] Ollama Local AI Engine for Linux
echo "[3/6] Checking Ollama Local AI Engine..."
if ! command -v ollama >/dev/null 2>&1; then
    echo "  -> Ollama not detected. Installing official Ollama for Linux..."
    curl -fsSL https://ollama.com/install.sh | sh || true
else
    echo "  -> Ollama detected: $(command -v ollama)"
fi

# Verify and start Ollama daemon
echo "  -> Verifying Ollama neural service daemon..."
if command -v systemctl >/dev/null 2>&1; then
    sudo -n systemctl enable --now ollama 2>/dev/null || systemctl --user enable --now ollama 2>/dev/null || true
fi

if ! curl -s -f http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
    echo "  -> Starting background Ollama daemon..."
    nohup ollama serve >/dev/null 2>&1 &
    sleep 2
fi

# Pull Llama 3.2 model if missing
echo "  -> Checking Llama 3.2 neural model in Ollama..."
if ! curl -s http://127.0.0.1:11434/api/tags 2>/dev/null | grep -q "llama3.2"; then
    echo "  -> Pulling llama3.2 (~2.0 GB)..."
    ollama pull llama3.2 || true
else
    echo "  -> [OK] llama3.2 model is already installed."
fi

# [4/6] Python Virtual Environment
echo "[4/6] Setting up Python virtual environment..."
python3 -m venv --system-site-packages "$PROJECT_DIR/.venv"
source "$PROJECT_DIR/.venv/bin/activate"
pip install --upgrade pip >/dev/null 2>&1

if [ -f "$PROJECT_DIR/requirements_fedora.txt" ]; then
    pip install -r "$PROJECT_DIR/requirements_fedora.txt" >/dev/null 2>&1 || true
fi

# [5/6] Desktop Launcher & Application Menu Entry
echo "[5/6] Creating launcher script and GNOME Application Menu entry..."
cat << 'EOF' > "$PROJECT_DIR/run.sh"
#!/usr/bin/env bash
set -euo pipefail
DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    DIR="$(cd "$(dirname "$0")" && pwd)"
fi
if [ -f "$DIR/.venv/bin/activate" ]; then
    source "$DIR/.venv/bin/activate"
fi
exec python3 "$DIR/fedora.py" "$@"
EOF
chmod +x "$PROJECT_DIR/run.sh"

# Create GNOME .desktop entry
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cat << EOF > "$DESKTOP_DIR/sudharshan-ai.desktop"
[Desktop Entry]
Name=Sudharshan AI
Comment=Privacy-First Local AI Desktop Assistant (Alpha v0.9)
Exec=$PROJECT_DIR/run.sh
Icon=utilities-terminal
Terminal=false
Type=Application
Categories=Utility;Development;
StartupNotify=true
EOF
chmod +x "$DESKTOP_DIR/sudharshan-ai.desktop"

# [6/6] GNOME Shell Extension & Self-Test
echo "[6/6] Installing GNOME Shell quick-toggle extension and running self-test..."
python3 "$PROJECT_DIR/fedora.py" --install-extension "$PROJECT_DIR" >/dev/null 2>&1 || true
python3 "$PROJECT_DIR/fedora.py" --self-test

echo "=================================================================="
echo "  Sudharshan AI (Alpha v0.9) Setup Complete!"
echo "  Launch anytime with:       $PROJECT_DIR/run.sh"
echo "  Emergency Kill-Switch:     $PROJECT_DIR/run.sh --kill-running"
echo "  Or search for 'Sudharshan AI' in your GNOME application menu."
echo "=================================================================="
