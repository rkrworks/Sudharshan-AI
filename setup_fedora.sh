#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${BAJRANG_INSTALL_DIR:-$HOME/bajrang-ai}"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/bajrang-ai@fedora.local"
LOG_FILE="$PROJECT_DIR/install_diagnostics.log"

if [[ "${1:-}" == "--uninstall" ]]; then
    echo "[UNINSTALL] Disabling GNOME extension and removing Bajrang AI Pro v6.0 files..."
    if command -v gnome-extensions >/dev/null 2>&1; then
        gnome-extensions disable bajrang-ai@fedora.local 2>/dev/null || true
    fi
    rm -rf "$EXT_DIR"
    rm -f "$PROJECT_DIR/bajrang_core.py" "$PROJECT_DIR/bajrang_llama32.py" "$PROJECT_DIR/run.sh"
    echo "[UNINSTALL] Complete. User SQLite database (~/.local/share/bajrang-ai/history.db) preserved."
    exit 0
fi

mkdir -p "$PROJECT_DIR"
echo "[$(date -Iseconds)] Starting Bajrang AI Pro v6.0 Fedora Setup" > "$LOG_FILE"

echo "======================================================================"
echo "  Bajrang AI Pro (v6.0) — Fedora Workstation (GNOME / Wayland) Setup"
echo "  Diagnostic Log: $LOG_FILE"
echo "======================================================================"

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "[ERROR] setup_fedora.sh requires a Linux environment (detected $(uname -s))." | tee -a "$LOG_FILE"
    exit 1
fi

if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    echo "[1/6] Detected OS: ${PRETTY_NAME:-Linux} (Wayland=${WAYLAND_DISPLAY:-unset})" | tee -a "$LOG_FILE"
fi

echo "[2/6] Auditing required system binaries (non-root pre-flight scan)..."
MISSING_PKGS=()
for cmd_pkg in "python3:python3" "pip3:python3-pip" "sqlite3:sqlite" "pw-record:pipewire-utils" "spd-say:speech-dispatcher-utils" "ydotool:ydotool" "gnome-screenshot:gnome-screenshot"; do
    bin_name="${cmd_pkg%%:*}"
    pkg_name="${cmd_pkg##*:}"
    if command -v "$bin_name" >/dev/null 2>&1; then
        echo "  [FOUND OK] $bin_name" | tee -a "$LOG_FILE"
    else
        echo "  [MISSING]  $bin_name (package: $pkg_name)" | tee -a "$LOG_FILE"
        MISSING_PKGS+=("$pkg_name")
    fi
done

if [[ ${#MISSING_PKGS[@]} -gt 0 ]] && command -v dnf >/dev/null 2>&1; then
    if [[ "${BAJRANG_SKIP_SUDO:-0}" == "1" ]]; then
        echo "  [NOTICE] Skipping sudo dnf install (BAJRANG_SKIP_SUDO=1). Missing: ${MISSING_PKGS[*]}" | tee -a "$LOG_FILE"
    else
        echo "  -> Installing missing Fedora packages via sudo dnf: ${MISSING_PKGS[*]}"
        sudo dnf install -y "${MISSING_PKGS[@]}" python3-gobject python3-pillow gtk4 libadwaita
    fi
fi

echo "[3/6] Checking Python packages (user scope, non-root)..."
for py_mod in "PIL:Pillow" "numpy:numpy" "faster_whisper:faster-whisper" "keyring:keyring"; do
    mod_name="${py_mod%%:*}"
    pip_name="${py_mod##*:}"
    if python3 -c "import $mod_name" >/dev/null 2>&1; then
        echo "  [FOUND OK] Python module '$mod_name'" | tee -a "$LOG_FILE"
    else
        echo "  [INSTALL]  pip3 install --user $pip_name" | tee -a "$LOG_FILE"
        pip3 install --user --upgrade "$pip_name" || true
    fi
done

echo "[4/6] Deploying Bajrang AI Pro v6.0 to $PROJECT_DIR..."
cp -f bajrang_core.py "$PROJECT_DIR/bajrang_core.py" 2>/dev/null || true
cp -f bajrang_llama32.py "$PROJECT_DIR/bajrang_llama32.py"
chmod +x "$PROJECT_DIR/bajrang_llama32.py"

python3 "$PROJECT_DIR/bajrang_llama32.py" --export-project "$PROJECT_DIR" | tee -a "$LOG_FILE"
python3 "$PROJECT_DIR/bajrang_llama32.py" --install-gnome-extension | tee -a "$LOG_FILE"

echo "[5/6] Running self-test verification suite..."
python3 "$PROJECT_DIR/bajrang_llama32.py" --self-test | tee -a "$LOG_FILE"

echo "[6/6] Setup complete! Run '$PROJECT_DIR/run.sh' to launch the GTK4 HUD or '--uninstall' to remove."
