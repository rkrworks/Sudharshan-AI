#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
linux_generic.py — Generic Linux Platform Layer (Debian, Ubuntu, Arch, openSUSE, Alpine, etc.)
Engineered by Kaushik Ram Ravuru (B.E. IT, Section IT-1, CBIT Hyderabad)
"""

import argparse
import base64
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bajrang_core import (
    ActionResult,
    AgentState,
    BasePlatformAdapter,
    BajrangEngine,
    ConfigManager,
    KillSwitchManager,
    PlatformCapabilityMatrix,
    SafetyGuard,
    SecurityVault,
    StructuredAuditLogger,
    ToolSchemaValidator,
    UI_DESIGN_TOKENS,
)


class GenericLinuxAdapter(BasePlatformAdapter):
    """
    Cross-Distro Linux Platform Adapter implementing BasePlatformAdapter:
    - Distro auto-detection from /etc/os-release.
    - Wayland vs X11 display server detection.
    - Input injection via ydotool (Wayland) or xdotool (X11).
    - Screen capture via grim, scrot, import, or gnome-screenshot.
    - Clipboard via wl-copy (Wayland) or xclip/xsel (X11).
    - Notifications via notify-send or kdialog.
    """

    KEY_CODES_YDO: Dict[str, str] = {
        "enter": "28", "return": "28", "space": "57", "tab": "15",
        "escape": "1", "backspace": "14", "up": "103", "down": "108",
        "left": "105", "right": "106", "ctrl": "29", "alt": "56",
        "shift": "42", "win": "125", "super": "125",
    }

    def __init__(self, safety: Optional[SafetyGuard] = None) -> None:
        self.safety = safety or SafetyGuard(strict_allowlist=True)
        self.distro_id, self.pkg_mgr, self.install_hint = self.detect_distro()
        self.display_server = "wayland" if os.environ.get("WAYLAND_DISPLAY") else ("x11" if os.environ.get("DISPLAY") else "headless")

    @staticmethod
    def detect_distro(os_rel_path: Optional[Path] = None, os_rel_content: Optional[str] = None) -> Tuple[str, str, str]:
        distro_id = "linux"
        id_like = ""
        lines = []
        if os_rel_content is not None:
            lines = os_rel_content.splitlines()
        else:
            os_rel = os_rel_path or Path("/etc/os-release")
            if os_rel.is_file():
                lines = os_rel.read_text(encoding="utf-8", errors="replace").splitlines()

        for line in lines:
            if line.startswith("ID="):
                distro_id = line.split("=", 1)[1].strip().strip('"').strip("'").lower()
            elif line.startswith("ID_LIKE="):
                id_like = line.split("=", 1)[1].strip().strip('"').strip("'").lower()

        if distro_id in ("fedora", "rhel", "centos") or "fedora" in id_like or "rhel" in id_like:
            return distro_id, "dnf", "sudo dnf install -y gtk4 libadwaita python3-gobject ydotool pipewire-utils"
        elif distro_id in ("ubuntu", "debian", "pop", "mint") or "debian" in id_like or "ubuntu" in id_like:
            return distro_id, "apt", "sudo apt-get update && sudo apt-get install -y libgtk-4-dev gir1.2-gtk-4.0 gir1.2-adw-1 python3-gi ydotool pipewire"
        elif distro_id in ("arch", "manjaro") or "arch" in id_like:
            return distro_id, "pacman", "sudo pacman -S --needed gtk4 libadwaita python-gobject ydotool pipewire"
        elif distro_id in ("opensuse", "suse", "opensuse-tumbleweed", "opensuse-leap") or "suse" in id_like:
            return distro_id, "zypper", "sudo zypper install -y gtk4-devel typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 python3-gobject ydotool pipewire-tools"
        elif distro_id == "alpine":
            return distro_id, "apk", "sudo apk add gtk4.0 libadwaita py3-gobject ydotool pipewire"
        return distro_id, "package_manager", "Install GTK4, Libadwaita, and ydotool via your system package manager."

    def get_desktop_context(self) -> str:
        return f"OS: Linux ({self.distro_id.capitalize()}) • Display: {self.display_server.upper()} • Pkg: {self.pkg_mgr}"

    def capture_screen_base64(self, max_dimension: int = 1280) -> Tuple[Optional[str], str]:
        tools = ["grim", "scrot", "import", "gnome-screenshot"]
        available = [t for t in tools if shutil.which(t)]
        if not available:
            return None, "No screen capture utility found (install grim, scrot, or imagemagick)."

        chosen = available[0]
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tmp_path = tf.name

        cmd = [chosen, tmp_path]
        if chosen == "gnome-screenshot":
            cmd = [chosen, "-f", tmp_path]

        try:
            res = subprocess.run(cmd, capture_output=True, timeout=5, check=False)
            if res.returncode != 0:
                return None, f"Screenshot capture failed via '{chosen}': exited {res.returncode}"
            p = Path(tmp_path)
            if not p.is_file() or p.stat().st_size == 0:
                return None, "Captured screenshot file was empty."
            b64_str = base64.b64encode(p.read_bytes()).decode("ascii")
            return b64_str, f"Captured screenshot via {chosen}."
        except Exception as exc:
            return None, f"Screenshot error: {exc}"
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def mouse_move(self, x: int, y: int) -> ActionResult:
        if self.display_server == "wayland" and shutil.which("ydotool"):
            res = subprocess.run(["ydotool", "mousemove", "-a", str(x), str(y)], capture_output=True, timeout=3, check=False)
            return ActionResult(tool="click_point", success=res.returncode == 0, output=f"Moved mouse to ({x}, {y}) via ydotool.")
        elif shutil.which("xdotool"):
            res = subprocess.run(["xdotool", "mousemove", str(x), str(y)], capture_output=True, timeout=3, check=False)
            return ActionResult(tool="click_point", success=res.returncode == 0, output=f"Moved mouse to ({x}, {y}) via xdotool.")
        return ActionResult(tool="click_point", success=False, output="No input injection tool (ydotool/xdotool) available.")

    def mouse_click(self, button: str = "left", x: Optional[int] = None, y: Optional[int] = None) -> ActionResult:
        if x is not None and y is not None:
            self.mouse_move(x, y)

        btn_num = "1" if button == "left" else ("3" if button == "right" else "2")
        if self.display_server == "wayland" and shutil.which("ydotool"):
            res = subprocess.run(["ydotool", "click", f"0x11{btn_num}"], capture_output=True, timeout=3, check=False)
            return ActionResult(tool="click_point", success=res.returncode == 0, output=f"Dispatched {button} click via ydotool.")
        elif shutil.which("xdotool"):
            res = subprocess.run(["xdotool", "click", btn_num], capture_output=True, timeout=3, check=False)
            return ActionResult(tool="click_point", success=res.returncode == 0, output=f"Dispatched {button} click via xdotool.")
        return ActionResult(tool="click_point", success=False, output="No input injection tool available.")

    def type_text(self, text: str) -> ActionResult:
        if self.display_server == "wayland" and shutil.which("ydotool"):
            res = subprocess.run(["ydotool", "type", "--", text], capture_output=True, timeout=5, check=False)
            return ActionResult(tool="type_text", success=res.returncode == 0, output=f"Typed text via ydotool.")
        elif shutil.which("xdotool"):
            res = subprocess.run(["xdotool", "type", "--", text], capture_output=True, timeout=5, check=False)
            return ActionResult(tool="type_text", success=res.returncode == 0, output=f"Typed text via xdotool.")
        return ActionResult(tool="type_text", success=False, output="No input injection tool available.")

    def press_key(self, key: str) -> ActionResult:
        k = (key or "").strip().lower()
        if k not in self.KEY_CODES_YDO:
            return ActionResult(tool="press_key", success=False, output=f"Unknown or unmapped Linux key: '{key}'", blocked=True)

        if self.display_server == "wayland" and shutil.which("ydotool"):
            code = self.KEY_CODES_YDO[k]
            res = subprocess.run(["ydotool", "key", f"{code}:1", f"{code}:0"], capture_output=True, timeout=3, check=False)
            return ActionResult(tool="press_key", success=res.returncode == 0, output=f"Pressed '{key}' via ydotool.")
        elif shutil.which("xdotool"):
            res = subprocess.run(["xdotool", "key", key], capture_output=True, timeout=3, check=False)
            return ActionResult(tool="press_key", success=res.returncode == 0, output=f"Pressed '{key}' via xdotool.")
        return ActionResult(tool="press_key", success=False, output="No input injection tool available.")

    def hotkey(self, keys: List[str]) -> ActionResult:
        is_blocked, reason = self.safety.check_hotkey(keys)
        if is_blocked:
            return ActionResult(tool="navigate_hotkey", success=False, output=f"Blocked hotkey combination: {reason}", blocked=True)

        if self.display_server == "wayland" and shutil.which("ydotool"):
            codes = [self.KEY_CODES_YDO.get(k.lower(), "") for k in keys if k.lower() in self.KEY_CODES_YDO]
            if not codes:
                return ActionResult(tool="navigate_hotkey", success=False, output="No valid key codes for hotkey.", blocked=True)
            seq = [f"{c}:1" for c in codes] + [f"{c}:0" for c in reversed(codes)]
            res = subprocess.run(["ydotool", "key", *seq], capture_output=True, timeout=3, check=False)
            return ActionResult(tool="navigate_hotkey", success=res.returncode == 0, output=f"Dispatched hotkey: {'+'.join(keys)}")
        elif shutil.which("xdotool"):
            combo = "+".join(keys)
            res = subprocess.run(["xdotool", "key", combo], capture_output=True, timeout=3, check=False)
            return ActionResult(tool="navigate_hotkey", success=res.returncode == 0, output=f"Dispatched hotkey: {combo}")
        return ActionResult(tool="navigate_hotkey", success=False, output="No input injection tool available.")

    def send_notification(self, title: str, message: str) -> ActionResult:
        if shutil.which("notify-send"):
            res = subprocess.run(["notify-send", title, message], capture_output=True, timeout=3, check=False)
            return ActionResult(tool="notification", success=res.returncode == 0, output=f"Sent notification via notify-send.")
        elif shutil.which("kdialog"):
            res = subprocess.run(["kdialog", "--passivepopup", message, "5", "--title", title], capture_output=True, timeout=3, check=False)
            return ActionResult(tool="notification", success=res.returncode == 0, output=f"Sent notification via kdialog.")
        return ActionResult(tool="notification", success=False, output="Neither notify-send nor kdialog is installed.")

    def record_microphone_wav(self, wav_path: Path, duration_sec: float = 3.5) -> Tuple[bool, str]:
        dur = max(1, int(round(duration_sec)))
        tools = ["pw-record", "parecord", "arecord"]
        available = [t for t in tools if shutil.which(t)]
        if not available:
            return False, "No audio recording tool found (install pipewire-utils or alsa-utils)."

        tool = available[0]
        cmd = [tool, str(wav_path)]
        if tool == "pw-record":
            cmd = ["timeout", f"{dur}s", "pw-record", "--rate=16000", "--channels=1", "--format=s16", str(wav_path)]
        elif tool == "parecord":
            cmd = ["timeout", f"{dur}s", "parecord", "--rate=16000", "--channels=1", "--format=s16le", str(wav_path)]
        elif tool == "arecord":
            cmd = ["arecord", "-d", str(dur), "-f", "cd", "-t", "wav", str(wav_path)]

        try:
            subprocess.run(cmd, capture_output=True, timeout=dur + 3, check=False)
            if wav_path.is_file() and wav_path.stat().st_size > 0:
                return True, f"Recorded audio via {tool}."
        except Exception as exc:
            return False, f"Audio recording error: {exc}"
        return False, f"Failed to record audio with {tool}."


def run_linux_preflight_checks(engine: Optional[BajrangEngine] = None) -> List[Dict[str, Any]]:
    checks = []

    # 1. Python >= 3.9
    py_ok = sys.version_info >= (3, 9)
    checks.append({
        "name": "Python Runtime",
        "status": "PASS" if py_ok else "FAIL",
        "detail": f"Python {sys.version.split()[0]} (>= 3.9 required)",
        "critical": True,
        "fix": "Upgrade Python via your system package manager.",
    })

    # 2. Distro & Package Manager
    distro, pkg_mgr, hint = GenericLinuxAdapter.detect_distro()
    checks.append({
        "name": "Linux Distribution",
        "status": "PASS",
        "detail": f"Detected {distro.capitalize()} (Package manager: {pkg_mgr})",
        "critical": False,
        "fix": "",
    })

    # 3. Display Server
    disp = "Wayland" if os.environ.get("WAYLAND_DISPLAY") else ("X11" if os.environ.get("DISPLAY") else "Headless")
    disp_ok = disp in ("Wayland", "X11")
    checks.append({
        "name": "Display Server",
        "status": "PASS" if disp_ok else "WARN",
        "detail": f"Active session: {disp}",
        "critical": False,
        "fix": "Ensure an active graphical desktop session is running if GUI is required.",
    })

    # 4. Input Injection Tool
    input_tool = shutil.which("ydotool") or shutil.which("xdotool")
    checks.append({
        "name": "Input Injection Tool",
        "status": "PASS" if input_tool else "WARN",
        "detail": f"Found: {input_tool}" if input_tool else "Neither ydotool nor xdotool found in PATH",
        "critical": False,
        "fix": hint,
    })

    # 5. Screen Capture Tool
    capture_tool = shutil.which("grim") or shutil.which("scrot") or shutil.which("import")
    checks.append({
        "name": "Screen Capture Tool",
        "status": "PASS" if capture_tool else "WARN",
        "detail": f"Found: {capture_tool}" if capture_tool else "No capture utility found (install grim or scrot)",
        "critical": False,
        "fix": hint,
    })

    # 6. Local Ollama Reachability
    ollama_ok = False
    host = "http://127.0.0.1:11434"
    if engine:
        host = str(engine.config.settings.get("ollama_host", host)).rstrip("/")
    try:
        req = urllib.request.Request(f"{host}/api/version", method="GET")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                ollama_ok = True
    except Exception:
        pass
    checks.append({
        "name": "Local Ollama Daemon",
        "status": "PASS" if ollama_ok else "WARN",
        "detail": f"Online at {host}" if ollama_ok else f"Offline at {host} (Start via 'ollama serve' or enter BYO API key)",
        "critical": False,
        "fix": "Run: ollama serve (or configure a Gemini/Groq API key in top bar)",
    })

    # 7. SQLite Storage
    db_ok = True
    try:
        data_dir = engine.config.data_dir if engine else (Path.home() / ".local" / "share" / "bajrang-ai")
        data_dir.mkdir(parents=True, exist_ok=True)
        test_db = data_dir / "doctor_probe.db"
        conn = sqlite3.connect(str(test_db), timeout=2.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("CREATE TABLE IF NOT EXISTS doctor_probe (id INTEGER PRIMARY KEY);")
        conn.commit()
        conn.close()
        test_db.unlink(missing_ok=True)
    except Exception:
        db_ok = False
    checks.append({
        "name": "SQLite WAL Storage",
        "status": "PASS" if db_ok else "FAIL",
        "detail": "Local WAL storage writable" if db_ok else "Storage initialization error",
        "critical": True,
        "fix": "Ensure write access to user ~/.local/share directory.",
    })

    return checks


def run_doctor(engine: Optional[BajrangEngine] = None) -> int:
    print("=" * 72)
    print(" Sudharshan AI (Alpha v0.9) — Generic Linux Preflight Doctor")
    print("=" * 72)
    checks = run_linux_preflight_checks(engine)
    all_critical_passed = True
    for c in checks:
        status_tag = f"[{c['status']}]"
        print(f" {status_tag:<8} {c['name']:<28} {c['detail']}")
        if c.get("fix") and c["status"] in ("FAIL", "WARN"):
            print(f"          -> Remediation: {c['fix']}")
        if c["critical"] and c["status"] == "FAIL":
            all_critical_passed = False
    print("-" * 72)
    if all_critical_passed:
        print(" SUCCESS: All core Linux requirements passed! Sudharshan AI is ready.")
        return 0
    else:
        print(" FAILED: One or more critical requirements are missing. Review remediation steps above.")
        return 1


def run_self_tests() -> int:
    print("Running GenericLinuxAdapter self-tests...")
    adapter = GenericLinuxAdapter()
    ctx = adapter.get_desktop_context()
    assert "OS: Linux" in ctx, f"Desktop context mismatch: {ctx}"

    # Verify hotkey safety guard enforcement
    res_bad = adapter.hotkey(["f4", "alt"])
    assert res_bad.blocked is True, "Reversed ['f4', 'alt'] must be blocked by SafetyGuard"

    # Verify unknown key rejection
    res_k = adapter.press_key("nonexistent_key_999")
    assert res_k.success is False and res_k.blocked is True, "Unknown key must be blocked"

    # Verify distro detection and package managers across distributions
    distro, pkg_mgr, hint = GenericLinuxAdapter.detect_distro()
    assert distro and pkg_mgr and hint, "Distro detection must return non-empty strings"

    # Simulated distro checks
    assert GenericLinuxAdapter.detect_distro(os_rel_content='ID=ubuntu\nID_LIKE=debian')[1] == "apt"
    assert GenericLinuxAdapter.detect_distro(os_rel_content='ID=arch\n')[1] == "pacman"
    assert GenericLinuxAdapter.detect_distro(os_rel_content='ID=opensuse-tumbleweed\nID_LIKE="suse opensuse"')[1] == "zypper"
    assert GenericLinuxAdapter.detect_distro(os_rel_content='ID=alpine\n')[1] == "apk"
    assert GenericLinuxAdapter.detect_distro(os_rel_content='ID=fedora\n')[1] == "dnf"

    print("All GenericLinuxAdapter self-tests passed!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sudharshan AI (Alpha v0.9) — Generic Linux Platform Layer")
    parser.add_argument("--self-test", action="store_true", help="Run headless Linux adapter self-tests")
    parser.add_argument("--doctor", "--diagnose", action="store_true", help="Run preflight doctor diagnostics")
    parser.add_argument("--prompt", type=str, default="", help="Run single prompt in CLI mode")
    args = parser.parse_args()

    if args.self_test:
        return run_self_tests()

    if args.doctor:
        return run_doctor()

    cfg = ConfigManager()
    adapter = GenericLinuxAdapter()
    engine = BajrangEngine(adapter=adapter, config=cfg)

    if args.prompt:
        turn = engine.process_prompt(args.prompt)
        print(turn.text)
        return 0

    print("Sudharshan AI generic Linux adapter initialized. Use --doctor to diagnose or --prompt to run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
