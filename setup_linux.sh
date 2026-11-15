#!/usr/bin/env bash
set -euo pipefail

echo "=================================================================="
echo "  Sudharshan AI (Alpha v0.9) — Linux Setup (Universal)"
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
    linux_generic.py
    fedora.py
    windows.py
    macos.py
    requirements-common.txt
    requirements-fedora.txt
    README.md
    SECURITY.md
)

LOCAL_SRC=""
if [ -n "${SCRIPT_DIR:-}" ] && [ -f "$SCRIPT_DIR/bajrang_core.py" ]; then
    LOCAL_SRC="$SCRIPT_DIR"
elif [ -f "$(pwd)/bajrang_core.py" ]; then
    LOCAL_SRC="$(pwd)"
fi

echo "[1/5] Deploying Sudharshan AI application files into $PROJECT_DIR..."
for f in "${CORE_FILES[@]}"; do
    if [ -n "$LOCAL_SRC" ] && [ -f "$LOCAL_SRC/$f" ]; then
        cp -f "$LOCAL_SRC/$f" "$PROJECT_DIR/$f"
    else
        echo "  -> Fetching $f from GitHub main..."
        curl -fsSL "$RAW_BASE/$f" -o "$PROJECT_DIR/$f" || true
    fi
done

echo "[2/5] Detecting package manager and installing dependencies..."
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO_ID="${ID:-linux}"
    DISTRO_LIKE="${ID_LIKE:-}"
else
    DISTRO_ID="unknown"
    DISTRO_LIKE=""
fi

SUDO_CMD=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo &>/dev/null; then
        SUDO_CMD="sudo"
    fi
fi

if command -v dnf &>/dev/null; then
    echo "  -> Detected dnf (Fedora/RHEL/CentOS/Rocky)"
    $SUDO_CMD dnf install -y python3 python3-pip python3-tkinter grim ydotool || true
elif command -v apt-get &>/dev/null; then
    echo "  -> Detected apt (Ubuntu/Debian/Mint/Pop!_OS)"
    $SUDO_CMD apt-get update -y || true
    $SUDO_CMD apt-get install -y python3 python3-pip python3-tk grim ydotool scrot xdotool || true
elif command -v pacman &>/dev/null; then
    echo "  -> Detected pacman (Arch/Manjaro)"
    $SUDO_CMD pacman -Sy --noconfirm python python-pip tk grim ydotool || true
elif command -v zypper &>/dev/null; then
    echo "  -> Detected zypper (openSUSE)"
    $SUDO_CMD zypper install -y python3 python3-pip python3-tk grim ydotool || true
fi

echo "[3/5] Installing Python common packages..."
if [ -f "$PROJECT_DIR/requirements-common.txt" ]; then
    python3 -m pip install -q -r "$PROJECT_DIR/requirements-common.txt" --break-system-packages 2>/dev/null || \
    python3 -m pip install -q -r "$PROJECT_DIR/requirements-common.txt" 2>/dev/null || true
fi

echo "[4/5] Running preflight system doctor..."
cd "$PROJECT_DIR"
python3 -m linux_generic --doctor || true

echo "[5/5] Creating desktop application launcher..."
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cat << 'EOF' > "$DESKTOP_DIR/sudharshan-ai.desktop"
[Desktop Entry]
Name=Sudharshan AI
Comment=Autonomous Desktop AI Assistant (Alpha v0.9)
Exec=python3 -m linux_generic
Terminal=false
Type=Application
Categories=Utility;Development;
StartupNotify=true
EOF

echo "=================================================================="
echo "  Sudharshan AI (Alpha v0.9) Installation Complete!"
echo "  To launch assistant: cd $PROJECT_DIR && python3 -m linux_generic"
echo "=================================================================="
