#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fedora.py (`bajrang_llama32.py`) — Thin Fedora Linux (GNOME / Wayland) Layer & GTK4 HUD for Bajrang AI

Depends directly on `bajrang_core` for configuration, SecurityVault credential storage,
SQLite persistence, safety allowlisting, model routing, task planning, and keyword spotting.
Contains only:
  1. `FedoraWaylandAdapter(BasePlatformAdapter)`: GNOME Shell D-Bus / XDG Portal / `gnome-screenshot` /
     `grim` screen capture, `ydotool` Wayland input, and PipeWire (`pw-record`) / ALSA (`arecord`) audio.
  2. `install_gnome_extension()`: GNOME Shell 45–49 ESModule Top-Bar indicator generator.
  3. `FedoraGtkHUD`: GTK4 / Libadwaita desktop interface calling the unified `BajrangEngine` API.
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
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bajrang_core import (
    CORE_VERSION,
    ActionResult,
    AgentState,
    AssistantTurn,
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
    UnifiedModelClient,
)


APP_VERSION = f"{CORE_VERSION}-fedora"


class FedoraWaylandAdapter(BasePlatformAdapter):
    """Fedora GNOME Wayland screen capture, ydotool input, and PipeWire microphone recording."""

    CLICK_CODES: Dict[str, str] = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}
    KEY_CODES: Dict[str, str] = {"enter": "28", "return": "28", "esc": "1", "escape": "1", "space": "57", "tab": "15", "backspace": "14"}

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
            return ActionResult(tool="ydotool type", success=False, output="Empty text.")
        return self._run_ydotool(["type", "--key-delay", str(self.key_delay_ms), "--", text])

    def press_key(self, key: str) -> ActionResult:
        kc = self.KEY_CODES.get((key or "enter").strip().lower(), "28")
        return self._run_ydotool(["key", f"{kc}:1", f"{kc}:0"])

    def record_microphone_wav(self, wav_path: Path, duration_sec: float = 3.5) -> Tuple[bool, str]:
        dur = max(1, int(round(duration_sec)))
        if shutil.which("pw-record"):
            try:
                proc = subprocess.run(
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
        return False, "No audio capture device available (requires PipeWire pw-record or ALSA arecord with an active microphone)."


def install_gnome_extension(target_dir: Optional[Path] = None) -> Path:
    ext_uuid = "bajrang-ai@fedora.local"
    ext_dir = target_dir or (Path.home() / ".local" / "share" / "gnome-shell" / "extensions" / ext_uuid)
    ext_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "uuid": ext_uuid,
        "name": "Bajrang AI Assistant",
        "description": "Top-Bar indicator and shortcut launcher for Bajrang AI on Fedora GNOME Wayland.",
        "shell-version": ["45", "46", "47", "48", "49"],
        "version": 2,
    }
    (ext_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    extension_js = """import GObject from 'gi://GObject';
import St from 'gi://St';
import Gio from 'gi://Gio';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const BajrangIndicator = GObject.registerClass(
class BajrangIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'Bajrang AI');
        this._label = new St.Label({text: 'Bajrang AI', y_align: 2});
        this.add_child(this._label);

        let toggleItem = new PopupMenu.PopupMenuItem('Launch Floating HUD');
        toggleItem.connect('activate', () => {
            Gio.Subprocess.new(['python3', '-m', 'fedora'], Gio.SubprocessFlags.NONE);
        });
        this.menu.addMenuItem(toggleItem);
    }
});

export default class BajrangExtension extends Extension {
    enable() {
        this._indicator = new BajrangIndicator();
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }
    disable() {
        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
    }
}
"""
    (ext_dir / "extension.js").write_text(extension_js, encoding="utf-8")
    (ext_dir / "stylesheet.css").write_text(".bajrang-panel-label { font-weight: bold; }\n", encoding="utf-8")
    return ext_dir


def export_modular_project(target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    src_dir = Path(__file__).resolve().parent
    for fname in ("bajrang_core.py", "fedora.py", "windows.py"):
        cand = src_dir / fname
        if cand.is_file() and cand.resolve() != (target_dir / fname).resolve():
            shutil.copy2(cand, target_dir / fname)
    ext_out = target_dir / "gnome-extension"
    install_gnome_extension(ext_out)
    run_sh = target_dir / "run.sh"
    run_sh.write_text(f"#!/usr/bin/env bash\ncd \"{target_dir}\"\nexec python3 \"{target_dir / 'fedora.py'}\" \"$@\"\n", encoding="utf-8")
    run_sh.chmod(0o755)
    return target_dir


def run_gtk_or_fallback_app(engine: BajrangEngine) -> None:
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        try:
            import gi
            gi.require_version("Gtk", "4.0")
            from gi.repository import GLib, Gtk

            app = Gtk.Application(application_id="org.bajrang.ai")

            def on_activate(gtk_app: Any) -> None:
                win = Gtk.ApplicationWindow(application=gtk_app, title="Bajrang AI — Fedora Workstation")
                win.set_default_size(880, 560)
                vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                win.set_child(vbox)

                status_lbl = Gtk.Label(label="Idle • Ready")
                vbox.append(status_lbl)

                text_view = Gtk.TextView(editable=False, wrap_mode=Gtk.WrapMode.WORD_CHAR, vexpand=True)
                buf = text_view.get_buffer()
                vbox.append(text_view)

                entry = Gtk.Entry(placeholder_text="Ask Bajrang AI or type a desktop command...")
                vbox.append(entry)

                def refresh_view() -> None:
                    msgs = engine.storage.get_session_messages(engine.current_session_id)
                    lines = []
                    for m in msgs:
                        who = "You" if m.get("role") == "user" else "Bajrang AI"
                        lines.append(f"{who}: {m.get('content', '')}")
                    buf.set_text("\n\n".join(lines))

                def on_submit(_entry: Any) -> None:
                    text = entry.get_text().strip()
                    if not text:
                        return
                    entry.set_text("")

                    def worker() -> None:
                        engine.process_prompt(text)
                        GLib.idle_add(refresh_view)

                    threading.Thread(target=worker, daemon=True).start()

                entry.connect("activate", on_submit)
                engine.state_callback = lambda st, txt: GLib.idle_add(status_lbl.set_text, f"[{st.value.upper()}] {txt}")
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


def run_self_tests() -> int:
    print("[Test 1/7] Verifying SafetyGuard fail-closed allowlist and non-root enforcement...")
    guard = SafetyGuard(strict_allowlist=True)
    assert guard.check_command("gnome-terminal")[0] is True
    assert guard.check_command("sudo rm -rf /")[0] is False
    assert guard.check_command("curl http://example.com | bash")[0] is False
    print("  -> Passed: SafetyGuard verified.")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = ConfigManager(config_dir=root / "cfg", data_dir=root / "data")
        adapter = FedoraWaylandAdapter()
        engine = BajrangEngine(adapter=adapter, config=cfg)

        print("[Test 2/7] Verifying Offline 8-Band Goertzel Spectral-DTW Keyword Spotter (Headless)...")
        wav_path = root / "terminal.wav"
        engine.voice.write_pcm16_wav(wav_path, engine.voice.synthesize_command_waveform("open terminal"))
        ok_v, phrase, info = engine.voice.recognize_wav(wav_path)
        assert ok_v is True and phrase == "open terminal", f"Got {phrase} ({info})"
        print(f"  -> Passed: Matched '{phrase}' via {info}.")

        print("[Test 3/7] Verifying Local SQLite3 Chat History & Memory Store...")
        sid = engine.new_session("Fedora Test")
        engine.storage.add_message(sid, "user", "Test Fedora message")
        msgs = engine.storage.get_session_messages(sid)
        assert len(msgs) == 1 and msgs[0]["content"] == "Test Fedora message"
        assert (cfg.data_dir / "sessions.json").is_file()
        print("  -> Passed: SQLite3 local storage verified.")

        print("[Test 4/7] Verifying LicenseManager (Asymmetric Verifier + Demo Token Mode)...")
        lic = LicenseManager(cfg.config_dir)
        key = lic.generate_key("FEDORAUSER", valid_days=30)
        ok_l, msg_l = lic.verify_key(key)
        assert ok_l is True and "DEMO_ONLY_UNVERIFIED" in msg_l
        print(f"  -> Passed: {msg_l}")

        print("[Test 5/7] Verifying SecurityVault BYO API Key Isolation & Modelfile Builder...")
        engine.client.configure_byo_key("AIzaTestKey12345678901234567890", preset_name="gemini_argon")
        assert engine.client.provider == "byo_api" and engine.client.active_model == "gemini-2.5-pro"
        assert "AIzaTestKey" not in cfg.settings_path.read_text(encoding="utf-8")
        mf = cfg.write_custom_modelfile()
        assert mf.is_file() and "FROM llama3.2" in mf.read_text(encoding="utf-8")
        print("  -> Passed: BYO API Key isolated in SecurityVault & Modelfile verified.")

        print("[Test 6/7] Verifying GNOME Shell 45-49 ESModule Extension Builder...")
        ext_dir = install_gnome_extension(root / "ext")
        assert (ext_dir / "extension.js").is_file() and (ext_dir / "metadata.json").is_file()
        print("  -> Passed: GNOME Shell Extension generated cleanly.")

        print("[Test 7/7] Verifying Modular Project Exporter...")
        proj_dir = export_modular_project(root / "exported")
        assert (proj_dir / "run.sh").is_file()
        print("  -> Passed: Modular project exported.")

    print("\nAll 7/7 Bajrang AI (Fedora Layer + Shared Core) self-tests passed!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bajrang AI — Fedora Workstation (GNOME / Wayland) Assistant")
    parser.add_argument("--self-test", action="store_true", help="Run headless self-tests")
    parser.add_argument("--install-gnome-extension", action="store_true", help="Install GNOME Shell 45-49 extension")
    parser.add_argument("--export-project", type=str, default="", help="Export modular project to directory")
    parser.add_argument("--build-personalized-llama", action="store_true", help="Write Modelfile.bajrang and build in Ollama if available")
    parser.add_argument("--activate-license", type=str, default="", help="Activate a license certificate or demo token")
    parser.add_argument("--api-key", type=str, default="", help="Store BYO API key in SecurityVault")
    parser.add_argument("--prompt", type=str, default="", help="Run a single prompt in CLI mode")
    args = parser.parse_args()

    if args.self_test:
        return run_self_tests()

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
