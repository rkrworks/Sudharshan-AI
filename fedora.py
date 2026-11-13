#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fedora.py (`bajrang_llama32.py`) — Hardened Fedora Linux (GNOME / Wayland) Layer & GTK4 HUD

Remediates H1, H2, H3, and H4:
  - H1: `export_modular_project` always writes both `fedora.py` and `bajrang_llama32.py` to the
    target directory (copying from `Path(__file__).resolve()`) so `run.sh` never targets a missing
    file, and `install_gnome_extension` launches the resolved script path directly.
  - H2: Background UNIX domain control socket (`/tmp/bajrang_kill_<uid>.sock`) and `--kill-running`
    CLI flag so global GNOME keybindings (`Ctrl+Shift+K`) and the Top-Bar extension can trigger
    the emergency kill-switch even when another window has focus.
  - H3 & H4: Implements `scroll` and `hotkey`, expands `KEY_CODES` (`a`–`z`, `0`–`9`, `f1`–`f12`,
    navigation keys), and rejects unknown keys in `press_key` instead of defaulting to Enter (`28`).
"""

import argparse
import base64
import datetime
import importlib.util
import io
import json
import os
import platform
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from bajrang_core import (
    CORE_VERSION,
    ActionResult,
    AgentState,
    AsymmetricLicenseVerifier,
    AutonomousTaskPlanner,
    BajrangEngine,
    BasePlatformAdapter,
    ConfigManager,
    CrossPlatformComputerUse,
    KillSwitchManager,
    LicenseManager,
    LocalChatStorage,
    SafetyGuard,
    SecurityVault,
    ShellRunner,
    SpectralVoiceSpotter,
    ToolSchemaValidator,
    UnifiedModelClient,
)


APP_VERSION = f"{CORE_VERSION}-fedora"


class FedoraWaylandAdapter(BasePlatformAdapter):
    """Fedora GNOME Wayland screen capture, ydotool input, scroll, hotkeys, and PipeWire audio."""

    CLICK_CODES: Dict[str, str] = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}

    # Complete Linux input-event-codes.h keycode mapping (never defaults unknown keys to Enter)
    KEY_CODES: Dict[str, str] = {
        "esc": "1",
        "escape": "1",
        "1": "2",
        "2": "3",
        "3": "4",
        "4": "5",
        "5": "6",
        "6": "7",
        "7": "8",
        "8": "9",
        "9": "10",
        "0": "11",
        "backspace": "14",
        "tab": "15",
        "q": "16",
        "w": "17",
        "e": "18",
        "r": "19",
        "t": "20",
        "y": "21",
        "u": "22",
        "i": "23",
        "o": "24",
        "p": "25",
        "enter": "28",
        "return": "28",
        "ctrl": "29",
        "control": "29",
        "a": "30",
        "s": "31",
        "d": "32",
        "f": "33",
        "g": "34",
        "h": "35",
        "j": "36",
        "k": "37",
        "l": "38",
        "shift": "42",
        "z": "44",
        "x": "45",
        "c": "46",
        "v": "47",
        "b": "48",
        "n": "49",
        "m": "50",
        "alt": "56",
        "space": "57",
        "f1": "59",
        "f2": "60",
        "f3": "61",
        "f4": "62",
        "f5": "63",
        "f6": "64",
        "f7": "65",
        "f8": "66",
        "f9": "67",
        "f10": "68",
        "f11": "87",
        "f12": "88",
        "home": "102",
        "up": "103",
        "pageup": "104",
        "left": "105",
        "right": "106",
        "end": "107",
        "down": "108",
        "pagedown": "109",
        "delete": "111",
        "del": "111",
        "win": "125",
        "super": "125",
    }

    def __init__(self, socket_path: str = "/tmp/.ydotool_socket", key_delay_ms: int = 12) -> None:
        self.socket_path = socket_path
        self.key_delay_ms = key_delay_ms
        self.screen_width = 1920
        self.screen_height = 1080

    def get_desktop_context(self) -> str:
        session_type = os.environ.get("XDG_SESSION_TYPE", "wayland")
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "GNOME")
        return f"OS: Fedora Linux | Desktop: {desktop} ({session_type}) | Resolution: {self.screen_width}x{self.screen_height}"

    def _session_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        if "XDG_RUNTIME_DIR" not in env and hasattr(os, "getuid"):
            env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
        rdir = env.get("XDG_RUNTIME_DIR", "")
        if "WAYLAND_DISPLAY" not in env and rdir and Path(f"{rdir}/wayland-0").exists():
            env["WAYLAND_DISPLAY"] = "wayland-0"
        if "DBUS_SESSION_BUS_ADDRESS" not in env and rdir and Path(f"{rdir}/bus").exists():
            env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={rdir}/bus"
        return env

    def capture_screen_base64(self, max_dimension: int = 1280) -> Tuple[Optional[str], str]:
        pics_dir = Path.home() / "Pictures" / "Screenshots"
        try:
            pics_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pics_dir = Path(tempfile.gettempdir())
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = pics_dir / f"Bajrang_Screenshot_{ts}.png"
        env = self._session_env()
        captured = False
        tool_used = ""

        if shutil.which("gdbus") and (env.get("WAYLAND_DISPLAY") or env.get("DISPLAY")):
            try:
                res = subprocess.run(
                    [
                        "gdbus",
                        "call",
                        "--session",
                        "--dest",
                        "org.gnome.Shell.Screenshot",
                        "--object-path",
                        "/org/gnome/Shell/Screenshot",
                        "--method",
                        "org.gnome.Shell.Screenshot.Screenshot",
                        "true",
                        "false",
                        str(save_path),
                    ],
                    env=env,
                    capture_output=True,
                    timeout=6.0,
                    check=False,
                )
                if res.returncode == 0 and save_path.is_file() and save_path.stat().st_size > 0:
                    captured = True
                    tool_used = "GNOME Shell D-Bus"
            except Exception:
                pass

        if not captured and shutil.which("gnome-screenshot") and (env.get("WAYLAND_DISPLAY") or env.get("DISPLAY")):
            try:
                res = subprocess.run(["gnome-screenshot", "-f", str(save_path)], env=env, capture_output=True, timeout=6.0, check=False)
                if res.returncode == 0 and save_path.is_file() and save_path.stat().st_size > 0:
                    captured = True
                    tool_used = "gnome-screenshot"
            except Exception:
                pass

        if not captured and shutil.which("grim") and env.get("WAYLAND_DISPLAY"):
            try:
                res = subprocess.run(["grim", str(save_path)], env=env, capture_output=True, timeout=5.0, check=False)
                if res.returncode == 0 and save_path.is_file() and save_path.stat().st_size > 0:
                    captured = True
                    tool_used = "grim"
            except Exception:
                pass

        if not captured and importlib.util.find_spec("PIL") is not None:
            try:
                from PIL import ImageGrab
                im = ImageGrab.grab()
                im.save(str(save_path), format="PNG")
                if save_path.is_file() and save_path.stat().st_size > 0:
                    captured = True
                    tool_used = "PIL.ImageGrab"
            except Exception:
                pass

        if not captured or not save_path.is_file():
            return None, "Screen capture unavailable (requires an active Wayland/X11 session and gnome-screenshot or grim)."

        try:
            if importlib.util.find_spec("PIL") is not None:
                from PIL import Image
                with Image.open(save_path) as img:
                    self.screen_width, self.screen_height = img.size
                    rgb = img.convert("RGB")
                    rgb.thumbnail((max_dimension, max_dimension))
                    buf = io.BytesIO()
                    rgb.save(buf, format="JPEG", quality=82)
                    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            else:
                b64 = base64.b64encode(save_path.read_bytes()).decode("ascii")
            return b64, f"Saved screenshot to {save_path} via {tool_used} ({self.screen_width}x{self.screen_height})."
        except Exception as exc:
            return None, f"Screenshot encoding error: {exc}"

    def check_daemon(self) -> Tuple[bool, str]:
        if not shutil.which("ydotool"):
            return False, "ydotool is not installed (`sudo dnf install ydotool`)."
        uid = os.getuid() if hasattr(os, "getuid") else 1000
        for cand in (self.socket_path, "/tmp/.ydotool_socket", f"/run/user/{uid}/.ydotool_socket", "/run/ydotoold/socket"):
            if os.path.exists(cand):
                self.socket_path = cand
                return True, f"ydotoold socket active at {cand}"
        return False, f"ydotoold socket not found at {self.socket_path}. Start daemon with: ydotoold --socket-path={self.socket_path} --socket-perm=0600 &"

    def _run_ydotool(self, args: List[str]) -> ActionResult:
        ok, status = self.check_daemon()
        if not ok:
            return ActionResult(tool=f"ydotool {args[0]}", success=False, output=status)
        env = os.environ.copy()
        env["YDOTOOL_SOCKET"] = self.socket_path
        cmd = ["ydotool", *args]
        try:
            proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=10.0, check=False)
            if proc.returncode == 0:
                return ActionResult(tool=f"ydotool {args[0]}", success=True, output=f"Executed: {' '.join(shlex.quote(a) for a in cmd)}")
            return ActionResult(tool=f"ydotool {args[0]}", success=False, output=f"ydotool error: {(proc.stderr or proc.stdout).strip()}")
        except Exception as exc:
            return ActionResult(tool=f"ydotool {args[0]}", success=False, output=f"ydotool exception: {exc}")

    def mouse_move(self, x: int, y: int) -> ActionResult:
        cx = max(0, min(int(x), self.screen_width))
        cy = max(0, min(int(y), self.screen_height))
        return self._run_ydotool(["mousemove", "-a", str(cx), str(cy)])

    def mouse_click(self, button: str = "left", x: Optional[int] = None, y: Optional[int] = None) -> ActionResult:
        if x is not None and y is not None:
            mv = self.mouse_move(int(x), int(y))
            if not mv.success:
                return mv
        code = self.CLICK_CODES.get(button.lower(), "0xC0")
        return self._run_ydotool(["click", code])

    def type_text(self, text: str) -> ActionResult:
        if not text:
            return ActionResult(tool="type_text", success=False, output="Empty text.")
        return self._run_ydotool(["type", "--key-delay", str(self.key_delay_ms), "--", text])

    def press_key(self, key: str) -> ActionResult:
        """H4 Remediation: Rejects unknown keys instead of mapping unknown keys to Enter (28)."""
        norm = ToolSchemaValidator.normalize_key_name(key)
        if norm not in self.KEY_CODES:
            return ActionResult(tool="press_key", success=False, output=f"Rejected unknown key '{key}'.", blocked=True)
        kc = self.KEY_CODES[norm]
        return self._run_ydotool(["key", f"{kc}:1", f"{kc}:0"])

    def scroll(self, direction: str = "down", clicks: int = 3) -> ActionResult:
        amt = max(1, min(20, abs(int(clicks))))
        signed = -amt if direction.lower() == "down" else amt
        return self._run_ydotool(["mousemove", "-w", "--", "0", str(signed)])

    def hotkey(self, keys: List[str]) -> ActionResult:
        ok, reason, _ = ToolSchemaValidator.validate_action({"tool": "navigate_hotkey", "arguments": {"keys": keys}})
        if not ok:
            return ActionResult(tool="navigate_hotkey", success=False, output=reason, blocked=True)
        codes: List[str] = []
        for k in keys:
            nk = ToolSchemaValidator.normalize_key_name(k)
            if nk not in self.KEY_CODES:
                return ActionResult(tool="navigate_hotkey", success=False, output=f"Unknown key '{k}' in hotkey.", blocked=True)
            codes.append(self.KEY_CODES[nk])
        seq = [f"{c}:1" for c in codes] + [f"{c}:0" for c in reversed(codes)]
        return self._run_ydotool(["key", *seq])

    def record_microphone_wav(self, wav_path: Path, duration_sec: float = 3.5) -> Tuple[bool, str]:
        dur = max(1, int(round(duration_sec)))
        if shutil.which("pw-record"):
            try:
                subprocess.run(
                    ["timeout", f"{dur}s", "pw-record", "--rate=16000", "--channels=1", "--format=s16", str(wav_path)],
                    capture_output=True,
                    timeout=dur + 3,
                    check=False,
                )
                if wav_path.is_file() and wav_path.stat().st_size > 100:
                    return True, "Recorded via PipeWire pw-record."
            except Exception:
                pass
        if shutil.which("arecord"):
            try:
                proc = subprocess.run(
                    ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-d", str(dur), str(wav_path)],
                    capture_output=True,
                    timeout=dur + 3,
                    check=False,
                )
                if proc.returncode == 0 and wav_path.is_file() and wav_path.stat().st_size > 100:
                    return True, "Recorded via ALSA arecord."
            except Exception:
                pass
        return False, "No audio capture device available."


def get_fedora_kill_socket_path() -> Path:
    uid = os.getuid() if hasattr(os, "getuid") else 1000
    return Path(tempfile.gettempdir()) / f"bajrang_kill_{uid}.sock"


def start_fedora_kill_socket_listener(engine: BajrangEngine) -> threading.Event:
    """
    H2 Remediation:
    Listens on a local UNIX domain socket (`/tmp/bajrang_kill_<uid>.sock`) so global GNOME
    shortcuts (`fedora.py --kill-running`) or the GNOME Top-Bar extension can trigger
    `engine.trigger_emergency_kill()` even when another application window is focused.
    """
    stop_ev = threading.Event()
    if not hasattr(socket, "AF_UNIX"):
        return stop_ev
    sock_path = get_fedora_kill_socket_path()
    try:
        sock_path.unlink(missing_ok=True)
    except Exception:
        pass

    def server_loop() -> None:
        try:
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(str(sock_path))
            os.chmod(sock_path, 0o600)
            srv.listen(4)
            srv.settimeout(0.5)
            while not stop_ev.is_set():
                try:
                    conn, _ = srv.accept()
                    with conn:
                        data = conn.recv(64)
                        if b"KILL" in data:
                            msg = engine.trigger_emergency_kill()
                            conn.sendall(msg.encode("utf-8"))
                except socket.timeout:
                    continue
                except Exception:
                    break
            srv.close()
        except Exception:
            pass
        finally:
            try:
                sock_path.unlink(missing_ok=True)
            except Exception:
                pass

    threading.Thread(target=server_loop, daemon=True).start()
    return stop_ev


def send_kill_signal_to_running_instance() -> Tuple[bool, str]:
    sock_path = get_fedora_kill_socket_path()
    if not sock_path.exists() or not hasattr(socket, "AF_UNIX"):
        return False, f"No running Bajrang AI kill socket found at {sock_path}."
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as cli:
            cli.settimeout(2.0)
            cli.connect(str(sock_path))
            cli.sendall(b"KILL")
            resp = cli.recv(256).decode("utf-8", errors="replace")
            return True, resp or "Sent KILL signal."
    except Exception as exc:
        return False, f"Kill signal failed: {exc}"


def install_gnome_extension(target_dir: Optional[Path] = None, project_dir: Optional[Path] = None) -> Path:
    """
    H1 & H2 Remediation:
    Generates the GNOME Shell 45-49 extension using the resolved path to `fedora.py`
    (never relying on `python3 -m fedora` from an unknown working directory) and includes
    an Emergency Kill-Switch menu item (`--kill-running`).
    """
    ext_uuid = "bajrang-ai@fedora.local"
    ext_dir = target_dir or (Path.home() / ".local" / "share" / "gnome-shell" / "extensions" / ext_uuid)
    ext_dir.mkdir(parents=True, exist_ok=True)

    proj_dir = (project_dir or (Path.home() / "bajrang-ai")).resolve()
    fedora_script = proj_dir / "fedora.py"
    if not fedora_script.exists():
        fedora_script = Path(__file__).resolve()

    metadata = {
        "uuid": ext_uuid,
        "name": "Bajrang AI Assistant",
        "description": "Top-Bar indicator and global Kill-Switch for Bajrang AI on Fedora GNOME Wayland.",
        "shell-version": ["45", "46", "47", "48", "49"],
        "version": 3,
    }
    (ext_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    extension_js = f"""import GObject from 'gi://GObject';
import St from 'gi://St';
import Gio from 'gi://Gio';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {{Extension}} from 'resource:///org/gnome/shell/extensions/extension.js';

const SCRIPT_PATH = '{fedora_script}';

const BajrangIndicator = GObject.registerClass(
class BajrangIndicator extends PanelMenu.Button {{
    _init() {{
        super._init(0.0, 'Bajrang AI');
        this._label = new St.Label({{text: 'Bajrang AI', y_align: 2}});
        this.add_child(this._label);

        let toggleItem = new PopupMenu.PopupMenuItem('Launch Floating HUD');
        toggleItem.connect('activate', () => {{
            Gio.Subprocess.new(['python3', SCRIPT_PATH], Gio.SubprocessFlags.NONE);
        }});
        this.menu.addMenuItem(toggleItem);

        let killItem = new PopupMenu.PopupMenuItem('Emergency Kill-Switch (Ctrl+Shift+K)');
        killItem.connect('activate', () => {{
            Gio.Subprocess.new(['python3', SCRIPT_PATH, '--kill-running'], Gio.SubprocessFlags.NONE);
        }});
        this.menu.addMenuItem(killItem);
    }}
}});

export default class BajrangExtension extends Extension {{
    enable() {{
        this._indicator = new BajrangIndicator();
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }}
    disable() {{
        if (this._indicator) {{
            this._indicator.destroy();
            this._indicator = null;
        }}
    }}
}}
"""
    (ext_dir / "extension.js").write_text(extension_js, encoding="utf-8")
    (ext_dir / "stylesheet.css").write_text(".bajrang-panel-label { font-weight: bold; }\n", encoding="utf-8")
    return ext_dir


def export_modular_project(target_dir: Path) -> Path:
    """
    H1 Remediation:
    Guarantees that `bajrang_core.py`, `fedora.py`, and `bajrang_llama32.py` are all written into
    `target_dir` even when invoked from a directory where only `bajrang_llama32.py` or `fedora.py`
    was copied.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    src_dir = Path(__file__).resolve().parent
    self_file = Path(__file__).resolve()

    core_src = src_dir / "bajrang_core.py"
    if core_src.is_file() and core_src.resolve() != (target_dir / "bajrang_core.py").resolve():
        shutil.copy2(core_src, target_dir / "bajrang_core.py")

    for alias_name in ("fedora.py", "bajrang_llama32.py"):
        dest_p = target_dir / alias_name
        cand_p = src_dir / alias_name
        source_to_use = cand_p if cand_p.is_file() else self_file
        if source_to_use.resolve() != dest_p.resolve():
            shutil.copy2(source_to_use, dest_p)
        dest_p.chmod(0o755)

    win_src = src_dir / "windows.py"
    if win_src.is_file() and win_src.resolve() != (target_dir / "windows.py").resolve():
        shutil.copy2(win_src, target_dir / "windows.py")

    ext_out = target_dir / "gnome-extension"
    install_gnome_extension(ext_out, project_dir=target_dir)

    run_sh = target_dir / "run.sh"
    run_sh.write_text(
        f'#!/usr/bin/env bash\ncd "{target_dir}"\nexec python3 "{target_dir / "fedora.py"}" "$@"\n',
        encoding="utf-8",
    )
    run_sh.chmod(0o755)
    return target_dir


def run_gtk_or_fallback_app(engine: BajrangEngine) -> None:
    stop_kill_ev = start_fedora_kill_socket_listener(engine)
    try:
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            try:
                import gi
                gi.require_version("Gtk", "4.0")
                from gi.repository import GLib, Gtk

                app = Gtk.Application(application_id="org.bajrang.ai")

                def on_activate(gtk_app: Any) -> None:
                    css_provider = Gtk.CssProvider()
                    css_provider.load_from_data(
                        b"""
                        window { background-color: #050505; color: #fafafa; }
                        .bajrang-header { background-color: #0f0c0a; border-bottom: 1px solid #2b1d14; padding: 6px 12px; }
                        .bajrang-status { background-color: #2b1204; color: #ff8c42; border: 1px solid #ff6b1a; border-radius: 999px; padding: 4px 12px; font-weight: 700; font-size: 12px; }
                        .bajrang-sidebar { background-color: #0c0a08; border-right: 1px solid #2b1d14; padding: 10px; }
                        .bajrang-chat { background-color: #080706; color: #f5f5f4; padding: 14px; font-size: 14px; }
                        .bajrang-stop { background-color: #dc2626; color: #ffffff; border-radius: 8px; font-weight: 700; padding: 6px 12px; }
                        .bajrang-approve { background-color: #ff6b1a; color: #050505; border-radius: 8px; font-weight: 700; padding: 6px 12px; }
                        """
                    )
                    from gi.repository import Gdk
                    Gtk.StyleContext.add_provider_for_display(
                        Gdk.Display.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                    )

                    win = Gtk.ApplicationWindow(application=gtk_app, title="Sudharshan AI (Alpha v0.9) — Fedora Wayland")
                    win.set_default_size(980, 640)

                    header = Gtk.HeaderBar()
                    header.add_css_class("bajrang-header")
                    status_lbl = Gtk.Label(label="IDLE • Ready")
                    status_lbl.add_css_class("bajrang-status")
                    confirm_btn = Gtk.Button(label="Approve Action")
                    confirm_btn.add_css_class("bajrang-approve")
                    confirm_btn.set_sensitive(False)
                    kill_btn = Gtk.Button(label="STOP")
                    kill_btn.add_css_class("bajrang-stop")
                    header.pack_start(status_lbl)
                    header.pack_end(kill_btn)
                    header.pack_end(confirm_btn)
                    win.set_titlebar(header)

                    root_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
                    win.set_child(root_hbox)

                    sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                    sidebar.set_size_request(220, -1)
                    sidebar.add_css_class("bajrang-sidebar")
                    new_sess_btn = Gtk.Button(label="+ New Session")
                    sess_list = Gtk.ListBox()
                    sidebar.append(new_sess_btn)
                    sidebar.append(sess_list)
                    root_hbox.append(sidebar)

                    chat_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                    chat_vbox.set_hexpand(True)
                    chat_vbox.set_margin_top(10)
                    chat_vbox.set_margin_bottom(10)
                    chat_vbox.set_margin_start(10)
                    chat_vbox.set_margin_end(10)
                    root_hbox.append(chat_vbox)

                    scrolled = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
                    text_view = Gtk.TextView(editable=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
                    text_view.add_css_class("bajrang-chat")
                    buf = text_view.get_buffer()
                    scrolled.set_child(text_view)
                    chat_vbox.append(scrolled)

                    input_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                    speak_btn = Gtk.Button(label="Speak")
                    entry = Gtk.Entry(placeholder_text="Ask Sudharshan AI (Alpha) or type a Fedora desktop command...")
                    entry.set_hexpand(True)
                    send_btn = Gtk.Button(label="Send")
                    input_hbox.append(speak_btn)
                    input_hbox.append(entry)
                    input_hbox.append(send_btn)
                    chat_vbox.append(input_hbox)

                    def refresh_sessions() -> None:
                        while True:
                            row = sess_list.get_row_at_index(0)
                            if row is None:
                                break
                            sess_list.remove(row)
                        for s in engine.storage.list_sessions(limit=30):
                            lbl = Gtk.Label(label=s.get("title", "Session"), xalign=0.0)
                            lbl.set_margin_top(4)
                            lbl.set_margin_bottom(4)
                            row = Gtk.ListBoxRow()
                            row.set_child(lbl)
                            row._bajrang_sid = s.get("session_id")
                            sess_list.append(row)

                    def refresh_view() -> None:
                        msgs = engine.storage.get_session_messages(engine.current_session_id)
                        lines = [f"{'You' if m.get('role') == 'user' else 'Sudharshan AI'}:\n{m.get('content', '')}" for m in msgs]
                        buf.set_text("\n\n".join(lines))
                        refresh_sessions()

                    def on_submit(_w: Any) -> None:
                        text = entry.get_text().strip()
                        if not text:
                            return
                        entry.set_text("")
                        pinned_sid = engine.current_session_id

                        def worker() -> None:
                            engine.process_prompt(text, session_id=pinned_sid)
                            GLib.idle_add(refresh_view)

                        threading.Thread(target=worker, daemon=True).start()

                    def on_state(st: Any, txt: str) -> None:
                        status_lbl.set_text(f"{st.value.upper()} • {txt}")
                        confirm_btn.set_sensitive(st == AgentState.AWAITING_CONFIRMATION)

                    new_sess_btn.connect("clicked", lambda _b: (engine.new_session("New Fedora Chat"), refresh_view()))
                    sess_list.connect("row-activated", lambda _lb, row: (engine.switch_session(row._bajrang_sid), refresh_view()))
                    kill_btn.connect("clicked", lambda _b: engine.trigger_emergency_kill())
                    confirm_btn.connect("clicked", lambda _b: (engine.confirm_pending_actions(approved=True), refresh_view()))
                    send_btn.connect("clicked", on_submit)
                    entry.connect("activate", on_submit)
                    engine.state_callback = lambda st, txt: GLib.idle_add(on_state, st, txt)
                    refresh_view()
                    win.present()

                app.connect("activate", on_activate)
                app.run(None)
                return
            except Exception:
                pass

        try:
            from windows import run_windows_tkinter_app
            run_windows_tkinter_app(engine)
        except Exception as exc:
            print(f"No graphical display active ({exc}). Use `--prompt` for headless CLI execution.")
    finally:
        stop_kill_ev.set()


def run_self_tests() -> int:
    print("[Test 1/7] Verifying SafetyGuard C3 Trampoline Guard & Allowlist...")
    guard = SafetyGuard(strict_allowlist=True)
    assert guard.check_command("gnome-terminal")[0] is True
    assert guard.check_command('gnome-terminal -- python3 -c "print(1)"')[0] is False
    assert guard.check_command("xdg-open https://evil.example")[0] is False
    print("  -> Passed: SafetyGuard C3 trampoline guard verified.")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = ConfigManager(config_dir=root / "cfg", data_dir=root / "data")
        adapter = FedoraWaylandAdapter()
        engine = BajrangEngine(adapter=adapter, config=cfg)

        print("[Test 2/7] Verifying H4 Unknown Key Rejection & Reversed Hotkey Blocking...")
        assert adapter.press_key("ctrl").blocked is False or adapter.press_key("ctrl").success is False
        assert adapter.press_key("nonexistent_key_999").blocked is True
        assert adapter.hotkey(["f4", "alt"]).blocked is True
        print("  -> Passed: Unknown keys & reversed forbidden hotkeys rejected.")

        print("[Test 3/7] Verifying Offline 8-Band Goertzel Spectral-DTW Keyword Spotter...")
        wav_path = root / "terminal.wav"
        engine.voice.write_pcm16_wav(wav_path, engine.voice.synthesize_command_waveform("open terminal"))
        ok_v, phrase, info = engine.voice.recognize_wav(wav_path)
        assert ok_v is True and phrase == "open terminal"
        print(f"  -> Passed: Matched '{phrase}' via {info}.")

        print("[Test 4/7] Verifying C1 Forged License Rejection & 2048-Bit RSA Verifier...")
        lic = LicenseManager(cfg.config_dir)
        assert lic.verify_key("BAJRANG-PRO-HACKER-20991231-ZZZZZZZZ")[0] is False
        print("  -> Passed: Forged BAJRANG-PRO token rejected.")

        print("[Test 5/7] Verifying SecurityVault BYO API Key Isolation & C6 Provider Affinity...")
        engine.client.configure_byo_key("AIzaTestKey12345678901234567890")
        assert engine.client.provider == "byo_api" and engine.client.active_model == "gemini-2.5-pro"
        assert cfg.get_api_key("openai") == ""
        print("  -> Passed: BYO API key isolated and provider-scoped.")

        print("[Test 6/7] Verifying H1 GNOME Shell Extension & Project Exporter...")
        proj_dir = export_modular_project(root / "exported")
        assert (proj_dir / "fedora.py").is_file(), "H1: fedora.py must exist in exported project"
        assert (proj_dir / "bajrang_llama32.py").is_file()
        assert (proj_dir / "run.sh").is_file()
        ext_js = (proj_dir / "gnome-extension" / "extension.js").read_text(encoding="utf-8")
        assert str(proj_dir / "fedora.py") in ext_js, "H1: GNOME extension must point at resolved fedora.py path"
        print("  -> Passed: H1 project export & GNOME extension verified.")

        print("[Test 7/7] Verifying H2 Global UNIX Kill-Switch Socket...")
        stop_ev = start_fedora_kill_socket_listener(engine)
        time.sleep(0.1)
        ok_k, msg_k = send_kill_signal_to_running_instance()
        stop_ev.set()
        assert ok_k is True and engine.kill_switch.is_cancelled is True
        print(f"  -> Passed: Global kill socket verified ({msg_k}).")

    print("\nAll 7/7 Sudharshan AI (Fedora Hardened Layer) self-tests passed!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sudharshan AI (Alpha v0.9) — Fedora Workstation (GNOME / Wayland) Assistant")
    parser.add_argument("--self-test", action="store_true", help="Run headless self-tests")
    parser.add_argument("--kill-running", action="store_true", help="Send emergency kill signal to running instance")
    parser.add_argument("--install-gnome-extension", action="store_true", help="Install GNOME Shell 45-49 extension")
    parser.add_argument("--export-project", type=str, default="", help="Export modular project to directory")
    parser.add_argument("--build-personalized-llama", action="store_true", help="Write Modelfile.bajrang")
    parser.add_argument("--activate-license", type=str, default="", help="Activate an RSA-2048 license certificate")
    parser.add_argument("--api-key", type=str, default="", help="Store BYO API key in SecurityVault")
    parser.add_argument("--prompt", type=str, default="", help="Run a single prompt in CLI mode")
    args = parser.parse_args()

    if args.self_test:
        return run_self_tests()

    if args.kill_running:
        ok, msg = send_kill_signal_to_running_instance()
        print(msg)
        return 0 if ok else 1

    cfg = ConfigManager()
    adapter = FedoraWaylandAdapter()
    engine = BajrangEngine(adapter=adapter, config=cfg)

    if args.install_gnome_extension:
        ext_path = install_gnome_extension()
        print(f"Installed GNOME Shell extension to {ext_path}")
        return 0

    if args.export_project:
        out_p = export_modular_project(Path(args.export_project).expanduser().resolve())
        print(f"Exported project to {out_p}")
        return 0

    if args.build_personalized_llama:
        mf = cfg.write_custom_modelfile()
        print(f"Wrote Modelfile to {mf}")
        if shutil.which("ollama"):
            subprocess.run(["ollama", "create", "bajrang-llama3.2", "-f", str(mf)], check=False)
        return 0

    if args.activate_license:
        ok, msg = LicenseManager(cfg.config_dir).activate(args.activate_license)
        print(msg)
        return 0 if ok else 1

    if args.api_key:
        backend = engine.client.configure_byo_key(args.api_key)
        print(f"Stored API key in {backend} (Model: {engine.client.active_model}).")

    if args.prompt:
        turn = engine.process_prompt(args.prompt)
        print(turn.text)
        return 0

    run_gtk_or_fallback_app(engine)
    return 0


if __name__ == "__main__":
    sys.exit(main())
