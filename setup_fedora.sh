#!/usr/bin/env bash
set -euo pipefail

echo "=================================================================="
echo "  Bajrang AI Pro (Hardened v3.0) — Fedora Workstation Setup"
echo "=================================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${BAJRANG_INSTALL_DIR:-$HOME/bajrang-ai-pro}"
mkdir -p "$PROJECT_DIR"

echo "[1/5] Copying Bajrang AI Pro core & Fedora modules into $PROJECT_DIR..."
for f in bajrang_core.py fedora.py windows.py bajrang_llama32.py bajrang_windows.py requirements_common.txt requirements_fedora.txt README.md SECURITY.md; do
    if [ -f "$SCRIPT_DIR/$f" ]; then
        cp -f "$SCRIPT_DIR/$f" "$PROJECT_DIR/$f"
    fi
done

if [ ! -f "$PROJECT_DIR/fedora.py" ] || [ ! -f "$PROJECT_DIR/bajrang_core.py" ]; then
    echo "ERROR: Required files (bajrang_core.py, fedora.py) were not found in $SCRIPT_DIR." >&2
    exit 1
fi

chmod +x "$PROJECT_DIR/fedora.py"

if [ "${BAJRANG_SKIP_SYSTEM_PKGS:-0}" != "1" ]; then
    echo "[2/5] Installing Fedora system dependencies (GTK4, Libadwaita, PipeWire, ydotool, grim)..."
    sudo dnf install -y \
        python3 python3-pip python3-gobject gtk4 libadwaita \
        pipewire-utils speech-dispatcher ydotool grim slurp wl-clipboard
else
    echo "[2/5] Skipping dnf system packages (BAJRANG_SKIP_SYSTEM_PKGS=1)."
fi

echo "[3/5] Setting up Python virtual environment..."
python3 -m venv --system-site-packages "$PROJECT_DIR/.venv"
source "$PROJECT_DIR/.venv/bin/activate"
pip install --upgrade pip

if [ -f "$PROJECT_DIR/requirements_fedora.txt" ]; then
    pip install -r "$PROJECT_DIR/requirements_fedora.txt" || true
fi

echo "[4/5] Writing verified launcher script ($PROJECT_DIR/run.sh)..."
cat << 'EOF' > "$PROJECT_DIR/run.sh"
#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$DIR/.venv/bin/activate" ]; then
    source "$DIR/.venv/bin/activate"
fi
exec python3 "$DIR/fedora.py" "$@"
EOF
chmod +x "$PROJECT_DIR/run.sh"

echo "[5/5] Installing GNOME Shell extension & running self-tests..."
python3 "$PROJECT_DIR/fedora.py" --install-extension "$PROJECT_DIR"
python3 "$PROJECT_DIR/fedora.py" --self-test

echo "=================================================================="
echo "  Setup Complete! Launch with: $PROJECT_DIR/run.sh"
echo "  Emergency Kill-Switch: $PROJECT_DIR/run.sh --kill-running"
echo "=================================================================="
