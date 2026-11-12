#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
windows.py (`bajrang_windows.py`) — Thin Windows Platform Layer & Tkinter HUD for Bajrang AI

Depends directly on `bajrang_core` for configuration, SecurityVault credential storage,
SQLite persistence, safety allowlisting, model routing, task planning, and keyword spotting.
Contains only:
  1. `WindowsPlatformAdapter(BasePlatformAdapter)`: Win32 (`ctypes.windll.user32`) / `PyAutoGUI`
     input, `PIL.ImageGrab` screen capture, and `sounddevice` / `winmm.dll` audio recording.
  2. `WindowsTkinterHUD`: Dark/Light Tkinter desktop interface + mini overlay pill calling
     the unified `BajrangEngine` API.
"""

import argparse
import base64
import ctypes
import datetime
import importlib.util
import io
import os
import platform
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


APP_VERSION = f"{CORE_VERSION}-windows"


class WindowsPlatformAdapter(BasePlatformAdapter):
    """Windows-specific screen capture, mouse/keyboard input, and microphone recording."""

    VK_MAP: Dict[str, int] = {
        "enter": 0x0D,
        "return": 0x0D,
        "tab": 0x09,
        "escape": 0x1B,
        "esc": 0x1B,
        "space": 0x20,
        "backspace": 0x08,
        "up": 0x26,
        "down": 0x28,
        "left": 0x25,
        "right": 0x27,
    }

    def __init__(self) -> None:
        self.screen_width = 1920
        self.screen_height = 1080
        self._detect_screen_size()

    def _detect_screen_size(self) -> None:
        if platform.system() == "Windows" and hasattr(ctypes, "windll"):
            try:
                user32 = ctypes.windll.user32
                w = int(user32.GetSystemMetrics(0))
                h = int(user32.GetSystemMetrics(1))
                if w > 0 and h > 0:
                    self.screen_width, self.screen_height = w, h
            except Exception:
                pass

    def get_desktop_context(self) -> str:
        return (
            f"OS: {platform.system()} {platform.release()} | "
            f"Resolution: {self.screen_width}x{self.screen_height}"
        )

    def capture_screen_base64(self, max_dimension: int = 1280) -> Tuple[Optional[str], str]:
        if importlib.util.find_spec("PIL") is None:
            return None, "Pillow (PIL) is not installed (`pip install Pillow`)."
        pics_dir = Path.home() / "Pictures" / "Screenshots"
        try:
            pics_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pics_dir = Path(tempfile.gettempdir())
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = pics_dir / f"Bajrang_Screenshot_{ts}.png"
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            self.screen_width, self.screen_height = img.size
            img.save(str(save_path), format="PNG")
            img_rgb = img.convert("RGB")
            img_rgb.thumbnail((max_dimension, max_dimension))
            buf = io.BytesIO()
            img_rgb.save(buf, format="JPEG", quality=82)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return b64, f"Saved screenshot to {save_path} ({self.screen_width}x{self.screen_height})."
        except Exception as exc:
            return None, f"Screen capture unavailable in current display session: {exc}"

    def mouse_move(self, x: int, y: int) -> ActionResult:
        cx = max(0, min(int(x), self.screen_width))
        cy = max(0, min(int(y), self.screen_height))
        if importlib.util.find_spec("pyautogui") is not None:
            try:
                import pyautogui
                pyautogui.moveTo(cx, cy, duration=0.1)
                return ActionResult(tool="mouse_move", success=True, output=f"Moved cursor to ({cx}, {cy}) via PyAutoGUI.")
            except Exception:
                pass
        if platform.system() == "Windows" and hasattr(ctypes, "windll"):
            try:
                ctypes.windll.user32.SetCursorPos(cx, cy)
                return ActionResult(tool="mouse_move", success=True, output=f"Moved cursor to ({cx}, {cy}) via Win32 SetCursorPos.")
            except Exception as exc:
                return ActionResult(tool="mouse_move", success=False, output=f"Win32 SetCursorPos failed: {exc}")
        return ActionResult(tool="mouse_move", success=False, output="Mouse move requires Windows Win32 session or PyAutoGUI.")

    def mouse_click(self, button: str = "left", x: Optional[int] = None, y: Optional[int] = None) -> ActionResult:
        btn = button.lower() if button.lower() in ("left", "right", "middle") else "left"
        if x is not None and y is not None:
            mv = self.mouse_move(int(x), int(y))
            if not mv.success:
                return mv
        if importlib.util.find_spec("pyautogui") is not None:
            try:
                import pyautogui
                pyautogui.click(button=btn)
                return ActionResult(tool="mouse_click", success=True, output=f"Clicked {btn} mouse button via PyAutoGUI.")
            except Exception:
                pass
        if platform.system() == "Windows" and hasattr(ctypes, "windll"):
            try:
                down_f, up_f = (0x0002, 0x0004) if btn == "left" else ((0x0008, 0x0010) if btn == "right" else (0x0020, 0x0040))
                ctypes.windll.user32.mouse_event(down_f, 0, 0, 0, 0)
                time.sleep(0.02)
                ctypes.windll.user32.mouse_event(up_f, 0, 0, 0, 0)
                return ActionResult(tool="mouse_click", success=True, output=f"Clicked {btn} button via Win32 mouse_event.")
            except Exception as exc:
                return ActionResult(tool="mouse_click", success=False, output=f"Win32 mouse_event failed: {exc}")
        return ActionResult(tool="mouse_click", success=False, output="Mouse click requires Windows Win32 session or PyAutoGUI.")

    def type_text(self, text: str) -> ActionResult:
        if not text:
            return ActionResult(tool="type_text", success=False, output="Empty text.")
        if importlib.util.find_spec("pyautogui") is not None:
            try:
                import pyautogui
                pyautogui.write(text, interval=0.01)
                return ActionResult(tool="type_text", success=True, output=f"Typed {len(text)} chars via PyAutoGUI.")
            except Exception:
                pass
        if platform.system() == "Windows" and hasattr(ctypes, "windll"):
            try:
                user32 = ctypes.windll.user32
                for ch in text:
                    vk = user32.VkKeyScanW(ord(ch))
                    if vk != -1:
                        code = vk & 0xFF
                        user32.keybd_event(code, 0, 0, 0)
                        user32.keybd_event(code, 0, 0x0002, 0)
                return ActionResult(tool="type_text", success=True, output=f"Typed {len(text)} chars via Win32 keybd_event.")
            except Exception as exc:
                return ActionResult(tool="type_text", success=False, output=f"Win32 keybd_event failed: {exc}")
        return ActionResult(tool="type_text", success=False, output="Keyboard typing requires Windows Win32 session or PyAutoGUI.")

    def press_key(self, key: str) -> ActionResult:
        k = (key or "enter").strip().lower()
        if importlib.util.find_spec("pyautogui") is not None:
            try:
                import pyautogui
                pyautogui.press(k)
                return ActionResult(tool="press_key", success=True, output=f"Pressed '{k}' via PyAutoGUI.")
            except Exception:
                pass
        if platform.system() == "Windows" and hasattr(ctypes, "windll"):
            vk = self.VK_MAP.get(k, 0x0D)
            try:
                ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                ctypes.windll.user32.keybd_event(vk, 0, 0x0002, 0)
                return ActionResult(tool="press_key", success=True, output=f"Pressed VK {hex(vk)} via Win32.")
            except Exception as exc:
                return ActionResult(tool="press_key", success=False, output=f"Win32 press_key failed: {exc}")
        return ActionResult(tool="press_key", success=False, output="Key press requires Windows Win32 session or PyAutoGUI.")

    def record_microphone_wav(self, wav_path: Path, duration_sec: float = 3.5) -> Tuple[bool, str]:
        if importlib.util.find_spec("sounddevice") is not None and importlib.util.find_spec("numpy") is not None:
            try:
                import numpy as np
                import sounddevice as sd
                frames = int(duration_sec * SpectralVoiceSpotter.SAMPLE_RATE)
                rec = sd.rec(frames, samplerate=SpectralVoiceSpotter.SAMPLE_RATE, channels=1, dtype="int16")
                sd.wait()
                samples = [int(x) for x in rec.flatten().tolist()]
                SpectralVoiceSpotter.write_pcm16_wav(wav_path, samples, SpectralVoiceSpotter.SAMPLE_RATE)
                return True, "Recorded via sounddevice (16 kHz mono)."
            except Exception as exc:
                last_err = str(exc)
        else:
            last_err = "sounddevice not installed"

        if platform.system() == "Windows" and hasattr(ctypes, "windll"):
            try:
                winmm = ctypes.windll.winmm
                alias = f"bajrang_{os.getpid()}"
                winmm.mciSendStringW(f"open new type waveaudio alias {alias}", None, 0, 0)
                winmm.mciSendStringW(f"set {alias} time format ms bitspersample 16 channels 1 samplespersec 16000", None, 0, 0)
                winmm.mciSendStringW(f"record {alias}", None, 0, 0)
                time.sleep(max(0.5, duration_sec))
                winmm.mciSendStringW(f"stop {alias}", None, 0, 0)
                winmm.mciSendStringW(f'save {alias} "{wav_path}"', None, 0, 0)
                winmm.mciSendStringW(f"close {alias}", None, 0, 0)
                if wav_path.is_file() and wav_path.stat().st_size > 44:
                    return True, "Recorded via Windows WinMM (mciSendStringW)."
            except Exception as exc:
                last_err = f"WinMM error: {exc}"

        return False, f"Microphone recording unavailable ({last_err})."


THEMES: Dict[str, Dict[str, str]] = {
    "dark": {
        "bg": "#090b11",
        "panel": "#121521",
        "subpanel": "#1a1f30",
        "fg": "#f8fafc",
        "muted": "#94a3b8",
        "accent": "#4f46e5",
    },
    "light": {
        "bg": "#f4f6fb",
        "panel": "#ffffff",
        "subpanel": "#e2e8f0",
        "fg": "#0f172a",
        "muted": "#475569",
        "accent": "#4f46e5",
    },
}


class WindowsTkinterHUD:
    """Tkinter front-end calling the shared `BajrangEngine` API."""

    def __init__(self, engine: BajrangEngine) -> None:
        import tkinter as tk
        self.tk = tk
        self.engine = engine
        self.engine.state_callback = self.on_engine_state_change

        self.root = tk.Tk()
        self.root.title("Bajrang AI — Windows Desktop Assistant")
        self.root.geometry("920x600")
        self._build_ui()
        self.apply_theme(str(self.engine.config.settings.get("theme", "dark")))
        self.refresh_sessions()
        self.load_messages(self.engine.storage.get_session_messages(self.engine.current_session_id))

    def _build_ui(self) -> None:
        tk = self.tk
        self.top_bar = tk.Frame(self.root, padx=12, pady=8)
        self.top_bar.pack(fill=tk.X)

        self.status_lbl = tk.Label(self.top_bar, text="Idle", font=("Segoe UI", 10, "bold"))
        self.status_lbl.pack(side=tk.LEFT)

        self.kill_btn = tk.Button(self.top_bar, text="STOP (Ctrl+Esc)", command=self.on_kill, bg="#dc2626", fg="#ffffff", relief=tk.FLAT, padx=10)
        self.kill_btn.pack(side=tk.RIGHT, padx=4)

        self.theme_btn = tk.Button(self.top_bar, text="Toggle Theme", command=self.on_toggle_theme, relief=tk.FLAT, padx=10)
        self.theme_btn.pack(side=tk.RIGHT, padx=4)

        self.key_entry = tk.Entry(self.top_bar, width=28, show="*")
        self.key_entry.pack(side=tk.RIGHT, padx=4)
        self.key_btn = tk.Button(self.top_bar, text="Save API Key to Vault", command=self.on_save_key, relief=tk.FLAT, padx=8)
        self.key_btn.pack(side=tk.RIGHT, padx=4)

        self.main_pane = tk.Frame(self.root)
        self.main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)

        self.sidebar = tk.Frame(self.main_pane, width=210)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))

        tk.Button(self.sidebar, text="+ New Session", command=self.on_new_session, bg="#4f46e5", fg="#ffffff", relief=tk.FLAT).pack(fill=tk.X, pady=(0, 6))
        self.session_listbox = tk.Listbox(self.sidebar, height=22, relief=tk.FLAT)
        self.session_listbox.pack(fill=tk.BOTH, expand=True)
        self.session_listbox.bind("<<ListboxSelect>>", self.on_select_session)

        self.chat_frame = tk.Frame(self.main_pane)
        self.chat_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.chat_text = tk.Text(self.chat_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Segoe UI", 10), relief=tk.FLAT, padx=10, pady=10)
        self.chat_text.pack(fill=tk.BOTH, expand=True)

        self.bottom_bar = tk.Frame(self.chat_frame, pady=6)
        self.bottom_bar.pack(fill=tk.X)

        self.voice_btn = tk.Button(self.bottom_bar, text="Speak", command=self.on_voice, bg="#7c3aed", fg="#ffffff", relief=tk.FLAT, padx=12)
        self.voice_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.prompt_entry = tk.Entry(self.bottom_bar, font=("Segoe UI", 10))
        self.prompt_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.prompt_entry.bind("<Return>", lambda _e: self.on_send())

        self.send_btn = tk.Button(self.bottom_bar, text="Send", command=self.on_send, bg="#4f46e5", fg="#ffffff", relief=tk.FLAT, padx=14)
        self.send_btn.pack(side=tk.RIGHT)

        self.root.bind("<Control-Escape>", lambda _e: self.on_kill())

    def apply_theme(self, theme_name: str) -> None:
        pal = THEMES.get(theme_name, THEMES["dark"])
        self.root.configure(bg=pal["bg"])
        self.top_bar.configure(bg=pal["panel"])
        self.main_pane.configure(bg=pal["bg"])
        self.sidebar.configure(bg=pal["panel"])
        self.chat_frame.configure(bg=pal["bg"])
        self.bottom_bar.configure(bg=pal["bg"])
        self.status_lbl.configure(bg=pal["panel"], fg=pal["fg"])
        self.chat_text.configure(bg=pal["panel"], fg=pal["fg"], insertbackground=pal["fg"])
        self.session_listbox.configure(bg=pal["panel"], fg=pal["fg"])
        self.prompt_entry.configure(bg=pal["subpanel"], fg=pal["fg"], insertbackground=pal["fg"])

    def on_toggle_theme(self) -> None:
        cur = str(self.engine.config.settings.get("theme", "dark"))
        nxt = self.engine.set_theme("light" if cur == "dark" else "dark")
        self.apply_theme(nxt)

    def on_save_key(self) -> None:
        raw = self.key_entry.get().strip()
        if raw:
            backend = self.engine.client.configure_byo_key(raw)
            self.key_entry.delete(0, self.tk.END)
            self.on_engine_state_change(AgentState.IDLE, f"Saved API key to {backend} ({self.engine.client.active_model})")

    def on_engine_state_change(self, state: AgentState, status_text: str) -> None:
        self.root.after(0, lambda: self.status_lbl.configure(text=f"[{state.value.upper()}] {status_text}"))

    def refresh_sessions(self) -> None:
        self._sessions_cache = self.engine.storage.list_sessions(limit=40)
        self.session_listbox.delete(0, self.tk.END)
        for s in self._sessions_cache:
            self.session_listbox.insert(self.tk.END, s["title"])

    def on_new_session(self) -> None:
        self.engine.new_session()
        self.refresh_sessions()
        self.load_messages([])

    def on_select_session(self, _event: Any) -> None:
        sel = self.session_listbox.curselection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self._sessions_cache):
            sid = self._sessions_cache[idx]["session_id"]
            msgs = self.engine.switch_session(sid)
            self.load_messages(msgs)

    def load_messages(self, messages: List[Dict[str, Any]]) -> None:
        self.chat_text.configure(state=self.tk.NORMAL)
        self.chat_text.delete("1.0", self.tk.END)
        for m in messages:
            prefix = "You" if m.get("role") == "user" else "Bajrang AI"
            self.chat_text.insert(self.tk.END, f"{prefix}: {m.get('content', '')}\n")
            for r in m.get("results", []):
                out = r.get("output", "") if isinstance(r, dict) else getattr(r, "output", "")
                self.chat_text.insert(self.tk.END, f"  -> {out}\n")
            self.chat_text.insert(self.tk.END, "\n")
        self.chat_text.configure(state=self.tk.DISABLED)
        self.chat_text.see(self.tk.END)

    def on_send(self) -> None:
        text = self.prompt_entry.get().strip()
        if not text:
            return
        self.prompt_entry.delete(0, self.tk.END)

        def worker() -> None:
            self.engine.process_prompt(text)
            msgs = self.engine.storage.get_session_messages(self.engine.current_session_id)
            self.root.after(0, lambda: (self.refresh_sessions(), self.load_messages(msgs)))

        threading.Thread(target=worker, daemon=True).start()

    def on_voice(self) -> None:
        def worker() -> None:
            self.engine.capture_voice_turn(duration_sec=3.5)
            msgs = self.engine.storage.get_session_messages(self.engine.current_session_id)
            self.root.after(0, lambda: (self.refresh_sessions(), self.load_messages(msgs)))

        threading.Thread(target=worker, daemon=True).start()

    def on_kill(self) -> None:
        self.engine.trigger_emergency_kill()

    def run(self) -> None:
        self.root.mainloop()


def run_windows_tkinter_app(engine: BajrangEngine) -> None:
    hud = WindowsTkinterHUD(engine)
    hud.run()


def run_self_tests() -> int:
    print("[1/5] Verifying Windows + Linux SafetyGuard (Strict Allowlist & Metacharacter Blocking)...")
    guard = SafetyGuard(strict_allowlist=True)
    ok_safe, _ = guard.check_command("notepad.exe")
    assert ok_safe is True
    ok_bad1, _ = guard.check_command("format c: /q")
    assert ok_bad1 is False
    ok_bad2, _ = guard.check_command("sudo rm -rf /")
    assert ok_bad2 is False
    ok_bad3, _ = guard.check_command("notepad.exe & calc.exe")
    assert ok_bad3 is False
    print("  -> Passed: SafetyGuard fail-closed allowlist verified.")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = ConfigManager(config_dir=root / "cfg", data_dir=root / "data")
        adapter = WindowsPlatformAdapter()
        engine = BajrangEngine(adapter=adapter, config=cfg)

        print("[2/5] Verifying Offline 8-Band Goertzel Spectral-DTW Keyword Spotter (Headless WAV)...")
        wav_path = root / "cmd.wav"
        samples = engine.voice.synthesize_command_waveform("open notepad")
        engine.voice.write_pcm16_wav(wav_path, samples)
        ok_v, phrase, info = engine.voice.recognize_wav(wav_path)
        assert ok_v is True and phrase == "open notepad", f"Got {phrase} ({info})"
        print(f"  -> Passed: Matched '{phrase}' ({info}).")

        print("[3/5] Verifying Local SQLite3 Storage & Session Switching...")
        s1 = engine.new_session("Session One")
        engine.storage.add_message(s1, "user", "Hello session 1")
        s2 = engine.new_session("Session Two")
        engine.storage.add_message(s2, "user", "Hello session 2")
        loaded_s1 = engine.switch_session(s1)
        assert len(loaded_s1) == 1 and loaded_s1[0]["content"] == "Hello session 1"
        print("  -> Passed: SQLite3 persistence & session switching verified.")

        print("[4/5] Verifying SecurityVault API Key Isolation (Never in settings.json)...")
        engine.client.configure_byo_key("AIzaTestKey12345678901234567890", preset_name="gemini_argon")
        assert engine.client.provider == "byo_api" and engine.client.active_model == "gemini-2.5-pro"
        assert "AIzaTestKey" not in cfg.settings_path.read_text(encoding="utf-8")
        print("  -> Passed: API key stored in SecurityVault and excluded from settings.json.")

        print("[5/5] Verifying LicenseManager (Asymmetric Verifier + Demo Token Mode)...")
        lic = LicenseManager(cfg.config_dir)
        demo_key = lic.generate_key("WINUSER", valid_days=30)
        ok_l, msg_l = lic.verify_key(demo_key)
        assert ok_l is True and "DEMO_ONLY_UNVERIFIED" in msg_l
        print(f"  -> Passed: {msg_l}")

    print("\nAll 5/5 Bajrang AI (Windows Layer + Shared Core) self-tests passed!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bajrang AI — Windows Desktop Assistant")
    parser.add_argument("--self-test", action="store_true", help="Run headless self-tests")
    parser.add_argument("--api-key", type=str, default="", help="Store BYO API key in SecurityVault")
    parser.add_argument("--prompt", type=str, default="", help="Run a single prompt in CLI mode")
    args = parser.parse_args()

    if args.self_test:
        return run_self_tests()

    cfg = ConfigManager()
    adapter = WindowsPlatformAdapter()
    engine = BajrangEngine(adapter=adapter, config=cfg)

    if args.api_key:
        backend = engine.client.configure_byo_key(args.api_key)
        print(f"Stored API key in {backend} (Model: {engine.client.active_model}).")

    if args.prompt:
        turn = engine.process_prompt(args.prompt)
        print(turn.text)
        return 0

    run_windows_tkinter_app(engine)
    return 0


if __name__ == "__main__":
    sys.exit(main())
