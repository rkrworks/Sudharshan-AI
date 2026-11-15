#!/usr/bin/env bash
set -euo pipefail

echo "=================================================================="
echo "  Sudharshan AI (Alpha v0.9) — macOS Setup"
echo "  Engineered by Kaushik Ram Ravuru (B.E. IT, CBIT Hyderabad)"
echo "=================================================================="

# Safe resolution of script location (supports curl -fsSL ... | bash)
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

PROJECT_DIR="${SUDHARSHAN_INSTALL_DIR:-$HOME/sudharshan-ai}"
mkdir -p "$PROJECT_DIR"

RAW_BASE="https://raw.githubusercontent.com/rkrworks/Sudharshan-AI/main"
CORE_FILES=(
    bajrang_core.py
    macos.py
    linux_generic.py
    windows.py
    requirements-common.txt
    README.md
    SECURITY.md
)

LOCAL_SRC=""
if [ -n "${SCRIPT_DIR:-}" ] && [ -f "$SCRIPT_DIR/bajrang_core.py" ]; then
    LOCAL_SRC="$SCRIPT_DIR"
elif [ -f "$(pwd)/bajrang_core.py" ]; then
    LOCAL_SRC="$(pwd)"
fi

echo "[1/4] Deploying Sudharshan AI application files into $PROJECT_DIR..."
for f in "${CORE_FILES[@]}"; do
    if [ -n "$LOCAL_SRC" ] && [ -f "$LOCAL_SRC/$f" ]; then
        cp -f "$LOCAL_SRC/$f" "$PROJECT_DIR/$f"
    else
        echo "  -> Fetching $f from GitHub main..."
        curl -fsSL "$RAW_BASE/$f" -o "$PROJECT_DIR/$f" || true
    fi
done

echo "[2/4] Verifying Python runtime..."
PYTHON_BIN="python3"
if ! command -v python3 &>/dev/null; then
    echo "  -> Python 3 not found. If Homebrew is installed, run: brew install python"
fi

echo "[3/4] Installing Python common packages..."
if [ -f "$PROJECT_DIR/requirements-common.txt" ]; then
    $PYTHON_BIN -m pip install -q -r "$PROJECT_DIR/requirements-common.txt" --break-system-packages 2>/dev/null || \
    $PYTHON_BIN -m pip install -q -r "$PROJECT_DIR/requirements-common.txt" 2>/dev/null || true
fi

echo "[4/4] Running preflight system doctor..."
cd "$PROJECT_DIR"
$PYTHON_BIN -m macos --doctor || true

echo "=================================================================="
echo "  Sudharshan AI (Alpha v0.9) macOS Setup Complete!"
echo "  NOTE: Grant Accessibility & Screen Recording in System Settings:"
echo "    System Settings -> Privacy & Security -> Accessibility"
echo "    System Settings -> Privacy & Security -> Screen Recording"
echo "  To launch assistant: cd $PROJECT_DIR && python3 -m macos"
echo "=================================================================="
