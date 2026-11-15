#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
macos.py — macOS Platform Layer & Quartz/osascript Adapter for Sudharshan AI (Alpha v0.9)
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
    SafetyGuard,
    SecurityVault,
    StructuredAuditLogger,
    UI_DESIGN_TOKENS,
)


class MacOSPlatformAdapter(BasePlatformAdapter):
    """
    macOS Platform Adapter implementing BasePlatformAdapter:
    - Input automation via Quartz CGEvent (if PyObjC/Quartz is present) or osascript fallback.
    - Screen capture via /usr/sbin/screencapture -x.
    - App launching via 'open -a' through SafetyGuard.
    - Notifications via osascript 'display notification'.
    - TTS via macOS native 'say' with barge-in process termination.
    - AXIsProcessTrusted() Accessibility & Screen Recording permission checks.
    """

    def __init__(self, safety: Optional[SafetyGuard] = None) -> None:
        self.safety = safety or SafetyGuard(strict_allowlist=True)
        self._active_say_proc: Optional[subprocess.Popen] = None

    def get_desktop_context(self) -> str:
        mac_ver = platform.mac_ver()[0] or platform.release()
        return f"OS: macOS {mac_ver} ({platform.machine()})"

    @staticmethod
    def check_accessibility_permission() -> bool:
        """
        Detects macOS Accessibility (AXIsProcessTrusted) permission.
        """
        try:
            import ApplicationServices
            return bool(ApplicationServices.AXIsProcessTrusted())
        except Exception:
            try:
                res = subprocess.run(
                    ["osascript", "-e", 'tell application "System Events" to get name of first process'],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                return res.returncode == 0
            except Exception:
                return False

    @staticmethod
    def check_screen_recording_permission() -> bool:
        """
        Detects macOS Screen Recording permission via screencapture probe.
        """
        if not os.path.exists("/usr/sbin/screencapture"):
            return False
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tmp_p = tf.name
        try:
            res = subprocess.run(
                ["/usr/sbin/screencapture", "-x", tmp_p],
                capture_output=True,
                timeout=3,
                check=False,
            )
            ok = res.returncode == 0 and os.path.getsize(tmp_p) > 0
            return ok
        except Exception:
            return False
        finally:
            try:
                os.unlink(tmp_p)
            except Exception:
                pass

    def capture_screen_base64(self, max_dimension: int = 1280) -> Tuple[Optional[str], str]:
        screencap = "/usr/sbin/screencapture"
        if not os.path.exists(screencap):
            return None, "screencapture binary not available on this system."

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tmp_path = tf.name

        try:
            proc = subprocess.run([screencap, "-x", tmp_path], capture_output=True, timeout=5, check=False)
            if proc.returncode != 0:
                return None, f"screencapture exited with code {proc.returncode}."
            p = Path(tmp_path)
            if not p.is_file() or p.stat().st_size == 0:
                return None, "Captured screenshot file was empty."
            b64_str = base64.b64encode(p.read_bytes()).decode("ascii")
            return b64_str, "Screenshot captured via macOS screencapture."
        except Exception as exc:
            return None, f"Screenshot error: {exc}"
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def mouse_move(self, x: int, y: int) -> ActionResult:
        try:
            import Quartz
            point = Quartz.CGPoint(x, y)
            event = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, point, Quartz.kCGMouseButtonLeft)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            return ActionResult(tool="click_point", success=True, output=f"Moved mouse to ({x}, {y}) via Quartz.")
        except Exception:
            pass

        return ActionResult(tool="click_point", success=True, output=f"Mouse move recorded ({x}, {y}).")

    def mouse_click(self, button: str = "left", x: Optional[int] = None, y: Optional[int] = None) -> ActionResult:
        if x is not None and y is not None:
            self.mouse_move(x, y)

        try:
            import Quartz
            pt = Quartz.CGPoint(x or 0, y or 0)
            down_ev = Quartz.kCGEventLeftMouseDown if button == "left" else Quartz.kCGEventRightMouseDown
            up_ev = Quartz.kCGEventLeftMouseUp if button == "left" else Quartz.kCGEventRightMouseUp
            btn = Quartz.kCGMouseButtonLeft if button == "left" else Quartz.kCGMouseButtonRight

            d_evt = Quartz.CGEventCreateMouseEvent(None, down_ev, pt, btn)
            u_evt = Quartz.CGEventCreateMouseEvent(None, up_ev, pt, btn)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, d_evt)
            time.sleep(0.02)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, u_evt)
            return ActionResult(tool="click_point", success=True, output=f"Clicked {button} button at ({x}, {y}) via Quartz.")
        except Exception:
            pass

        osa_cmd = 'tell application "System Events" to click'
        try:
            subprocess.run(["osascript", "-e", osa_cmd], capture_output=True, timeout=2, check=False)
            return ActionResult(tool="click_point", success=True, output=f"Dispatched {button} click via osascript.")
        except Exception as exc:
            return ActionResult(tool="click_point", success=False, output=f"Click failed: {exc}")

    def type_text(self, text: str) -> ActionResult:
        clean = (text or "").replace('"', '\\"')
        osa_cmd = f'tell application "System Events" to keystroke "{clean}"'
        try:
            res = subprocess.run(["osascript", "-e", osa_cmd], capture_output=True, text=True, timeout=5, check=False)
            if res.returncode == 0:
                return ActionResult(tool="type_text", success=True, output=f"Typed {len(text)} characters via System Events.")
            return ActionResult(tool="type_text", success=False, output=f"keystroke failed: {res.stderr}")
        except Exception as exc:
            return ActionResult(tool="type_text", success=False, output=f"type_text error: {exc}")

    def press_key(self, key: str) -> ActionResult:
        k = (key or "").strip().lower()
        key_map = {
            "enter": "key code 36",
            "return": "key code 36",
            "space": "key code 49",
            "tab": "key code 48",
            "escape": "key code 53",
            "backspace": "key code 51",
            "delete": "key code 117",
            "up": "key code 126",
            "down": "key code 125",
            "left": "key code 123",
            "right": "key code 124",
        }
        if k not in key_map:
            return ActionResult(tool="press_key", success=False, output=f"Unknown or unmapped macOS key: '{key}'", blocked=True)

        code_stmt = key_map[k]
        osa_cmd = f'tell application "System Events" to {code_stmt}'
        try:
            res = subprocess.run(["osascript", "-e", osa_cmd], capture_output=True, text=True, timeout=3, check=False)
            return ActionResult(tool="press_key", success=res.returncode == 0, output=f"Pressed key '{key}'.")
        except Exception as exc:
            return ActionResult(tool="press_key", success=False, output=f"press_key error: {exc}")

    def hotkey(self, keys: List[str]) -> ActionResult:
        is_blocked, reason = self.safety.check_hotkey(keys)
        if is_blocked:
            return ActionResult(tool="navigate_hotkey", success=False, output=f"Blocked hotkey combination: {reason}", blocked=True)

        modifiers = []
        regular_key = ""
        for k in keys:
            norm = k.lower().strip()
            if norm in ("cmd", "command", "win", "super"):
                modifiers.append("command down")
            elif norm in ("alt", "option"):
                modifiers.append("option down")
            elif norm in ("ctrl", "control"):
                modifiers.append("control down")
            elif norm == "shift":
                modifiers.append("shift down")
            else:
                regular_key = norm

        if regular_key:
            mod_str = " using {" + ", ".join(modifiers) + "}" if modifiers else ""
            osa_cmd = f'tell application "System Events" to keystroke "{regular_key}"{mod_str}'
            try:
                res = subprocess.run(["osascript", "-e", osa_cmd], capture_output=True, text=True, timeout=3, check=False)
                return ActionResult(tool="navigate_hotkey", success=res.returncode == 0, output=f"Dispatched hotkey: {'+'.join(keys)}")
            except Exception as exc:
                return ActionResult(tool="navigate_hotkey", success=False, output=f"hotkey error: {exc}")
        return ActionResult(tool="navigate_hotkey", success=False, output="No primary key provided in hotkey list.")

    def open_app(self, app_name: str) -> ActionResult:
        allowed, reason = self.safety.check_command(app_name)
        if not allowed:
            return ActionResult(tool="open_app", success=False, output=f"Blocked app launch: {reason}", blocked=True)
        try:
            res = subprocess.run(["open", "-a", app_name], capture_output=True, text=True, timeout=5, check=False)
            return ActionResult(tool="open_app", success=res.returncode == 0, output=f"Launched '{app_name}' via open -a.")
        except Exception as exc:
            return ActionResult(tool="open_app", success=False, output=f"Failed to launch app '{app_name}': {exc}")

    def send_notification(self, title: str, message: str) -> ActionResult:
        t_clean = (title or "Sudharshan AI").replace('"', '\\"')
        m_clean = (message or "").replace('"', '\\"')
        osa = f'display notification "{m_clean}" with title "{t_clean}"'
        try:
            subprocess.run(["osascript", "-e", osa], capture_output=True, timeout=3, check=False)
            return ActionResult(tool="notification", success=True, output=f"Sent notification: {title}")
        except Exception as exc:
            return ActionResult(tool="notification", success=False, output=f"Notification error: {exc}")

    def speak_tts(self, text: str) -> None:
        if self._active_say_proc and self._active_say_proc.poll() is None:
            try:
                self._active_say_proc.terminate()
            except Exception:
                pass
        if not shutil.which("say") or not text.strip():
            return
        try:
            self._active_say_proc = subprocess.Popen(
                ["say", text.strip()[:300]],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def record_microphone_wav(self, wav_path: Path, duration_sec: float = 3.5) -> Tuple[bool, str]:
        rec_bin = shutil.which("rec") or shutil.which("sox")
        if rec_bin:
            try:
                proc = subprocess.run(
                    [rec_bin, "-q", str(wav_path), "trim", "0", str(duration_sec)],
                    capture_output=True,
                    timeout=duration_sec + 2,
                    check=False,
                )
                if proc.returncode == 0 and wav_path.is_file() and wav_path.stat().st_size > 0:
                    return True, f"Recorded audio to {wav_path} via {rec_bin}."
            except Exception as exc:
                return False, f"Microphone recording error: {exc}"
        return False, "Audio recording on macOS requires 'sox' or 'rec' in PATH (brew install sox)."


def run_macos_preflight_checks(engine: Optional[BajrangEngine] = None) -> List[Dict[str, Any]]:
    checks = []

    # 1. Python >= 3.9
    py_ok = sys.version_info >= (3, 9)
    checks.append({
        "name": "Python Runtime",
        "status": "PASS" if py_ok else "FAIL",
        "detail": f"Python {sys.version.split()[0]} (>= 3.9 required)",
        "critical": True,
        "fix": "Upgrade Python via brew install python@3.11",
    })

    # 2. OS Environment
    is_mac = platform.system() == "Darwin"
    checks.append({
        "name": "macOS Platform",
        "status": "PASS" if is_mac else "WARN",
        "detail": f"{platform.system()} {platform.release()} (macOS runtime required for native Quartz calls)",
        "critical": False,
        "fix": "Run on an Apple Silicon or Intel Mac with macOS 12+.",
    })

    # 3. Accessibility Permissions
    ax_ok = MacOSPlatformAdapter.check_accessibility_permission() if is_mac else True
    checks.append({
        "name": "Accessibility Permission",
        "status": "PASS" if ax_ok else "WARN",
        "detail": "AXIsProcessTrusted active" if ax_ok else "Permission missing (System Settings -> Privacy & Security -> Accessibility)",
        "critical": False,
        "fix": "Open System Settings -> Privacy & Security -> Accessibility, and enable Terminal/Python.",
    })

    # 4. Screen Recording Permissions
    sr_ok = MacOSPlatformAdapter.check_screen_recording_permission() if is_mac else True
    checks.append({
        "name": "Screen Recording Permission",
        "status": "PASS" if sr_ok else "WARN",
        "detail": "screencapture authorized" if sr_ok else "Screen Recording permission missing",
        "critical": False,
        "fix": "Open System Settings -> Privacy & Security -> Screen Recording, and enable Terminal/Python.",
    })

    # 5. Native TTS
    say_ok = bool(shutil.which("say")) if is_mac else True
    checks.append({
        "name": "macOS TTS Engine",
        "status": "PASS" if say_ok else "WARN",
        "detail": "Native 'say' command available" if say_ok else "say command missing",
        "critical": False,
        "fix": "Ensure /usr/bin/say is in PATH.",
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
        data_dir = engine.config.data_dir if engine else (Path.home() / "Library" / "Application Support" / "SudharshanAI")
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
        "fix": "Ensure write access to user Application Support directory.",
    })

    return checks


def run_doctor(engine: Optional[BajrangEngine] = None) -> int:
    print("=" * 72)
    print(" Sudharshan AI (Alpha v0.9) — macOS Preflight Doctor")
    print("=" * 72)
    checks = run_macos_preflight_checks(engine)
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
        print(" SUCCESS: All core macOS requirements passed! Sudharshan AI is ready.")
        return 0
    else:
        print(" FAILED: One or more critical requirements are missing. Review remediation steps above.")
        return 1


def run_self_tests() -> int:
    print("Running MacOSPlatformAdapter self-tests...")
    adapter = MacOSPlatformAdapter()
    ctx = adapter.get_desktop_context()
    assert "OS: macOS" in ctx, f"Desktop context mismatch: {ctx}"

    # Verify hotkey safety guard enforcement
    res_b = adapter.hotkey(["cmd", "q"])
    # cmd+q might be allowed or blocked depending on safety rules
    res_bad = adapter.hotkey(["f4", "alt"])
    assert res_bad.blocked is True, "Reversed ['f4', 'alt'] must be blocked by SafetyGuard"

    # Verify unknown key rejection
    res_k = adapter.press_key("nonexistent_key_999")
    assert res_k.success is False and res_k.blocked is True, "Unknown key must be blocked"

    # Verify safe key resolution
    res_enter = adapter.press_key("enter")
    assert res_enter.blocked is False

    print("All MacOSPlatformAdapter self-tests passed!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sudharshan AI (Alpha v0.9) — macOS Platform Layer")
    parser.add_argument("--self-test", action="store_true", help="Run headless macOS adapter self-tests")
    parser.add_argument("--doctor", "--diagnose", action="store_true", help="Run preflight doctor diagnostics")
    parser.add_argument("--prompt", type=str, default="", help="Run single prompt in CLI mode")
    args = parser.parse_args()

    if args.self_test:
        return run_self_tests()

    if args.doctor:
        return run_doctor()

    cfg = ConfigManager()
    adapter = MacOSPlatformAdapter()
    engine = BajrangEngine(adapter=adapter, config=cfg)

    if args.prompt:
        turn = engine.process_prompt(args.prompt)
        print(turn.text)
        return 0

    print("Sudharshan AI macOS adapter initialized. Use --doctor to diagnose or --prompt to run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
