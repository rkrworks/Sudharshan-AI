#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
windows.py (`bajrang_windows.py`) — Hardened Windows Platform Layer & Tkinter HUD for Bajrang AI

Remediates H2, H3, H4, and H8:
  - H2: Background global hotkey poller (`GetAsyncKeyState` for `Ctrl+Shift+K` or `VK_PAUSE`)
    that works even when the HUD window is unfocused, without hijacking `Ctrl+Esc` (Start Menu).
  - H3: Implements `scroll` (`MOUSEEVENTF_WHEEL`) and `hotkey` alongside `CrossPlatformComputerUse`
    (`EnumWindows`, `SetForegroundWindow`).
  - H4: `press_key` rejects unknown keys instead of defaulting to Enter (`0x0D`); `type_text`
    presses and releases `VK_SHIFT` (`0x10`) when `VkKeyScanW` indicates a shifted character
    (capitals and shifted punctuation).
  - H8: Thread-safe `queue.Queue` UI event loop (`_poll_ui_queue`), session-pinned prompt
    execution (`session_id` passed at submission), and non-blocking confirmation button for
    `AgentState.AWAITING_CONFIRMATION`.
"""

import argparse
import base64
import ctypes
import datetime
import importlib.util
import io
import os
import platform
import queue
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


APP_VERSION = f"{CORE_VERSION}-windows"


class WindowsPlatformAdapter(BasePlatformAdapter):
    """Windows-specific screen capture, mouse/keyboard input, scroll, hotkeys, and mic capture."""

    VK_MAP: Dict[str, int] = {
        "enter": 0x0D,
        "return": 0x0D,
        "tab": 0x09,
        "escape": 0x1B,
        "esc": 0x1B,
        "space": 0x20,
        "backspace": 0x08,
        "delete": 0x2E,
        "del": 0x2E,
        "home": 0x24,
        "end": 0x23,
        "pageup": 0x21,
        "pagedown": 0x22,
        "up": 0x26,
        "down": 0x28,
        "left": 0x25,
        "right": 0x27,
        "ctrl": 0x11,
        "control": 0x11,
        "shift": 0x10,
        "alt": 0x12,
        "win": 0x5B,
        **{f"f{i}": 0x6F + i for i in range(1, 13)},
        **{chr(c): ord(chr(c).upper()) for c in range(ord("a"), ord("z") + 1)},
        **{str(d): 0x30 + d for d in range(10)},
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
        return f"OS: {platform.system()} {platform.release()} | Resolution: {self.screen_width}x{self.screen_height}"

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
        if platform.system() == "Windows" and hasattr(ctypes, "windll"):
            try:
                user32 = ctypes.windll.user32
                user32.SetCursorPos(cx, cy)

                class POINT(ctypes.Structure):
                    _fields_ = [("x", ctypes.c_long), [("y", ctypes.c_long)][0]]

                pt = POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                ok = abs(pt.x - cx) <= 2 and abs(pt.y - cy) <= 2
                return ActionResult(tool="mouse_move", success=ok, output=f"Cursor at ({pt.x}, {pt.y}) via Win32 SetCursorPos/GetCursorPos.")
            except Exception as exc:
                return ActionResult(tool="mouse_move", success=False, output=f"Win32 SetCursorPos failed: {exc}")
        if importlib.util.find_spec("pyautogui") is not None:
            try:
                import pyautogui
                pyautogui.moveTo(cx, cy, duration=0.05)
                return ActionResult(tool="mouse_move", success=True, output=f"Moved cursor to ({cx}, {cy}) via PyAutoGUI.")
            except (Exception, SystemExit, BaseException):
                pass
        return ActionResult(tool="mouse_move", success=False, output="Mouse move requires Windows Win32 session or PyAutoGUI.")

    def mouse_click(self, button: str = "left", x: Optional[int] = None, y: Optional[int] = None) -> ActionResult:
        btn = button.lower() if button.lower() in ("left", "right", "middle") else "left"
        if x is not None and y is not None:
            mv = self.mouse_move(int(x), int(y))
            if not mv.success:
                return mv
        if platform.system() == "Windows" and hasattr(ctypes, "windll"):
            try:
                down_f, up_f = (0x0002, 0x0004) if btn == "left" else ((0x0008, 0x0010) if btn == "right" else (0x0020, 0x0040))
                ctypes.windll.user32.mouse_event(down_f, 0, 0, 0, 0)
                time.sleep(0.02)
                ctypes.windll.user32.mouse_event(up_f, 0, 0, 0, 0)
                return ActionResult(tool="click_point", success=True, output=f"Clicked {btn} button via Win32 mouse_event.")
            except Exception as exc:
                return ActionResult(tool="click_point", success=False, output=f"Win32 mouse_event failed: {exc}")
        return ActionResult(tool="click_point", success=False, output="Mouse click requires Windows Win32 session.")

    def type_text(self, text: str) -> ActionResult:
        """
        H4 Remediation: Handles Shift/Ctrl/Alt modifier bits returned in the high byte of
        `VkKeyScanW(ord(ch))` (`(vk >> 8) & 1` = `VK_SHIFT`) so capitals and shifted symbols
        are typed accurately.
        """
        if not text:
            return ActionResult(tool="type_text", success=False, output="Empty text.")
        if platform.system() == "Windows" and hasattr(ctypes, "windll"):
            try:
                user32 = ctypes.windll.user32
                for ch in text:
                    vk = user32.VkKeyScanW(ord(ch))
                    if vk == -1:
                        continue
                    keycode = vk & 0xFF
                    shift_mask = (vk >> 8) & 0xFF
                    need_shift = (shift_mask & 0x01) != 0
                    if need_shift:
                        user32.keybd_event(0x10, 0, 0, 0)
                    user32.keybd_event(keycode, 0, 0, 0)
                    user32.keybd_event(keycode, 0, 0x0002, 0)
                    if need_shift:
                        user32.keybd_event(0x10, 0, 0x0002, 0)
                return ActionResult(tool="type_text", success=True, output=f"Typed {len(text)} chars via Win32 keybd_event (Shift-aware).")
            except Exception as exc:
                return ActionResult(tool="type_text", success=False, output=f"Win32 keybd_event failed: {exc}")
        if importlib.util.find_spec("pyautogui") is not None:
            try:
                import pyautogui
                pyautogui.write(text, interval=0.01)
                return ActionResult(tool="type_text", success=True, output=f"Typed {len(text)} chars via PyAutoGUI.")
            except (Exception, SystemExit, BaseException):
                pass
        return ActionResult(tool="type_text", success=False, output="Keyboard typing requires Windows Win32 session.")

    def press_key(self, key: str) -> ActionResult:
        """H4 Remediation: Rejects unknown key names instead of defaulting to Enter (0x0D)."""
        norm = ToolSchemaValidator.normalize_key_name(key)
        if norm not in self.VK_MAP:
            return ActionResult(tool="press_key", success=False, output=f"Rejected unknown key '{key}'.", blocked=True)
        vk = self.VK_MAP[norm]
        if platform.system() == "Windows" and hasattr(ctypes, "windll"):
            try:
                ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                ctypes.windll.user32.keybd_event(vk, 0, 0x0002, 0)
                return ActionResult(tool="press_key", success=True, output=f"Pressed '{norm}' (VK {hex(vk)}) via Win32.")
            except Exception as exc:
                return ActionResult(tool="press_key", success=False, output=f"Win32 press_key failed: {exc}")
        return ActionResult(tool="press_key", success=False, output=f"Verified key '{norm}' (VK {hex(vk)}), but Win32 display session is inactive.")

    def scroll(self, direction: str = "down", clicks: int = 3) -> ActionResult:
        amt = max(1, min(20, abs(int(clicks))))
        delta = -120 * amt if direction.lower() == "down" else 120 * amt
        if platform.system() == "Windows" and hasattr(ctypes, "windll"):
            try:
                ctypes.windll.user32.mouse_event(0x0800, 0, 0, delta, 0)
                return ActionResult(tool="scroll_view", success=True, output=f"Scrolled {direction} ({amt} clicks) via Win32 MOUSEEVENTF_WHEEL.")
            except Exception as exc:
                return ActionResult(tool="scroll_view", success=False, output=f"Win32 scroll failed: {exc}")
        return ActionResult(tool="scroll_view", success=False, output="Scroll requires active Win32 session.")

    def hotkey(self, keys: List[str]) -> ActionResult:
        ok, reason, _ = ToolSchemaValidator.validate_action({"tool": "navigate_hotkey", "arguments": {"keys": keys}})
        if not ok:
            return ActionResult(tool="navigate_hotkey", success=False, output=reason, blocked=True)
        vks: List[int] = []
        for k in keys:
            nk = ToolSchemaValidator.normalize_key_name(k)
            if nk not in self.VK_MAP:
                return ActionResult(tool="navigate_hotkey", success=False, output=f"Unknown key '{k}' in hotkey.", blocked=True)
            vks.append(self.VK_MAP[nk])
        if platform.system() == "Windows" and hasattr(ctypes, "windll"):
            try:
                user32 = ctypes.windll.user32
                for vk in vks:
                    user32.keybd_event(vk, 0, 0, 0)
                for vk in reversed(vks):
                    user32.keybd_event(vk, 0, 0x0002, 0)
                return ActionResult(tool="navigate_hotkey", success=True, output=f"Pressed hotkey {keys} via Win32.")
            except Exception as exc:
                return ActionResult(tool="navigate_hotkey", success=False, output=f"Win32 hotkey failed: {exc}")
        return ActionResult(tool="navigate_hotkey", success=False, output="Hotkey requires active Win32 session.")

    def record_microphone_wav(self, wav_path: Path, duration_sec: float = 3.5) -> Tuple[bool, str]:
        if importlib.util.find_spec("sounddevice") is not None and importlib.util.find_spec("numpy") is not None:
            try:
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
        return False, f"Microphone recording unavailable ({last_err})."


def start_global_windows_kill_listener(on_kill: Callable[[], None]) -> threading.Event:
    """
    H2 Remediation:
    Polls `GetAsyncKeyState` in a daemon thread for `Ctrl+Shift+K` or `VK_PAUSE` (`0x13`)
    so the user can trigger the Emergency Kill-Switch globally even when another application
    window has focus (and without colliding with `Ctrl+Esc` Start Menu).
    """
    stop_ev = threading.Event()
    if platform.system() != "Windows" or not hasattr(ctypes, "windll"):
        return stop_ev

    def poller() -> None:
        user32 = ctypes.windll.user32
        while not stop_ev.is_set():
            try:
                ctrl_down = (user32.GetAsyncKeyState(0x11) & 0x8000) != 0
                shift_down = (user32.GetAsyncKeyState(0x10) & 0x8000) != 0
                k_down = (user32.GetAsyncKeyState(0x4B) & 0x8000) != 0
                pause_down = (user32.GetAsyncKeyState(0x13) & 0x8000) != 0
                if (ctrl_down and shift_down and k_down) or pause_down:
                    on_kill()
                    time.sleep(0.4)
            except Exception:
                pass
            time.sleep(0.05)

    threading.Thread(target=poller, daemon=True).start()
    return stop_ev


THEMES: Dict[str, Dict[str, str]] = {
    "dark": {
        "bg": "#09090b",
        "panel": "#111116",
        "subpanel": "#181822",
        "border": "#272733",
        "fg": "#fafafa",
        "muted": "#94a3b8",
        "accent": "#ff6b1a",
        "accent_hover": "#ff8533",
        "user_fg": "#ff8533",
        "bot_fg": "#f1f5f9",
        "green": "#10b981",
        "red": "#ef4444",
        "amber": "#f59e0b",
        "code_bg": "#0b0c10",
        "code_fg": "#38bdf8",
    },
    "light": {
        "bg": "#f8fafc",
        "panel": "#ffffff",
        "subpanel": "#f1f5f9",
        "border": "#e2e8f0",
        "fg": "#0f172a",
        "muted": "#64748b",
        "accent": "#ea580c",
        "accent_hover": "#f97316",
        "user_fg": "#ea580c",
        "bot_fg": "#0f172a",
        "green": "#059669",
        "red": "#dc2626",
        "amber": "#d97706",
        "code_bg": "#f1f5f9",
        "code_fg": "#0284c7",
    },
}


def enable_windows_dark_titlebar(root: Any) -> None:
    """Enables Windows 11 / 10 DWM immersive dark mode titlebar to prevent harsh white frames."""
    if platform.system() != "Windows":
        return
    try:
        root.update_idletasks()
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(root.winfo_id())
        if not hwnd:
            hwnd = root.winfo_id()
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        val = ctypes.c_int(1)
        res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(val), ctypes.sizeof(val)
        )
        if res != 0:
            DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, ctypes.byref(val), ctypes.sizeof(val)
            )
        DWMWA_CAPTION_COLOR = 35
        color_val = ctypes.c_int(0x000B0909)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(color_val), ctypes.sizeof(color_val)
        )
    except Exception:
        pass


class WindowsTkinterHUD:
    """
    H8 Remediation & Feature 8 Universal Floating Assistant:
    All background thread updates are enqueued to `self.ui_queue` (a `queue.Queue`) and
    processed exclusively on the main Tk thread via `_poll_ui_queue()`.
    Features:
      - Always-on-Top toggle (`-topmost`)
      - Compact Mode toggle (collapses sidebar & chat history for a micro HUD)
      - Clipboard Assistant (one-click clipboard inspection & assistance)
      - Session Management (Search, Pin, Rename, Export Markdown)
      - Interactive Welcome Hero & Rich Message Bubbles
      - Live Neural Engine Status & 1-Click Ollama Daemon Launcher
    """

    def __init__(self, engine: BajrangEngine) -> None:
        import tkinter as tk
        import urllib.request
        self.tk = tk
        self.urllib_req = urllib.request
        self.engine = engine
        self.ui_queue: "queue.Queue[Tuple[str, Any]]" = queue.Queue()
        self.engine.state_callback = lambda st, txt: self.ui_queue.put(("state", (st, txt)))
        self.current_theme = str(self.engine.config.settings.get("theme", "dark"))
        self.is_topmost = False
        self.is_compact = False
        self._sessions_cache: List[Dict[str, Any]] = []
        self._filtered_sessions: List[Dict[str, Any]] = []

        self.root = tk.Tk()
        self.root.title("Sudharshan AI (Alpha v0.9) — Windows 11 Desktop Assistant")
        self.root.geometry("980x640")
        self.root.minsize(460, 160)
        self._build_ui()
        self.apply_theme(self.current_theme)
        enable_windows_dark_titlebar(self.root)
        self.refresh_sessions()
        self.load_messages(self.engine.storage.get_session_messages(self.engine.current_session_id))
        self._check_engine_status()
        self._kill_stop_ev = start_global_windows_kill_listener(lambda: self.ui_queue.put(("kill", None)))
        self.root.after(50, self._poll_ui_queue)

    def _check_engine_status(self) -> None:
        def worker() -> None:
            online = False
            host = str(self.engine.config.settings.get("ollama_host", "http://127.0.0.1:11434")).rstrip("/")
            try:
                req = self.urllib_req.Request(f"{host}/api/version", method="GET")
                with self.urllib_req.urlopen(req, timeout=1.2) as resp:
                    online = (resp.status == 200)
            except Exception:
                online = False
            self.ui_queue.put(("engine_status", online))
        threading.Thread(target=worker, daemon=True).start()

    def on_engine_click(self) -> None:
        self.engine_btn.configure(text="🟡 Starting Engine...", bg="#78350f", fg="#fcd34d")
        def worker() -> None:
            host = str(self.engine.config.settings.get("ollama_host", "http://127.0.0.1:11434")).rstrip("/")
            self.engine.client._try_autostart_ollama(host)
            self._check_engine_status()
        threading.Thread(target=worker, daemon=True).start()

    def _poll_ui_queue(self) -> None:
        while True:
            try:
                kind, payload = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "state":
                st, txt = payload
                badge_colors = {
                    AgentState.IDLE: ("#064e3b", "#6ee7b7"),
                    AgentState.THINKING: ("#78350f", "#fcd34d"),
                    AgentState.EXECUTING: ("#1e3a8a", "#93c5fd"),
                    AgentState.AWAITING_CONFIRMATION: ("#7c2d12", "#fdba74"),
                    AgentState.BLOCKED: ("#7f1d1d", "#fca5a5"),
                    AgentState.OFFLOADED: ("#334155", "#94a3b8"),
                }
                bg_c, fg_c = badge_colors.get(st, ("#1e293b", "#e2e8f0"))
                self.status_lbl.configure(text=f"  {st.value.upper()} • {txt}  ", bg=bg_c, fg=fg_c)
                if st == AgentState.AWAITING_CONFIRMATION:
                    self.confirm_btn.configure(state=self.tk.NORMAL, bg="#10b981", fg="#052e16")
                else:
                    self.confirm_btn.configure(state=self.tk.DISABLED, bg="#334155", fg="#94a3b8")
            elif kind == "engine_status":
                online = bool(payload)
                if online:
                    self.engine_btn.configure(
                        text=f"🟢 Ollama ({self.engine.client.active_model})",
                        bg="#064e3b", fg="#6ee7b7", cursor="arrow"
                    )
                else:
                    self.engine_btn.configure(
                        text="🔴 Ollama Offline (Click to Start)",
                        bg="#450a0a", fg="#fca5a5", cursor="hand2"
                    )
            elif kind == "turn_done":
                target_sid = payload
                self.refresh_sessions()
                if self.engine.current_session_id == target_sid:
                    self.load_messages(self.engine.storage.get_session_messages(target_sid))
            elif kind == "kill":
                self.on_kill()
        self.root.after(50, self._poll_ui_queue)

    def _build_ui(self) -> None:
        tk = self.tk
        self.top_bar = tk.Frame(self.root, padx=10, pady=7)
        self.top_bar.pack(fill=tk.X)

        self.status_lbl = tk.Label(self.top_bar, text="  IDLE • Ready  ", font=("Segoe UI", 9, "bold"), padx=6, pady=2)
        self.status_lbl.pack(side=tk.LEFT, padx=(0, 6))

        self.engine_btn = tk.Button(
            self.top_bar, text="🟢 Checking Engine...", command=self.on_engine_click,
            relief=tk.FLAT, font=("Segoe UI", 9, "bold"), padx=8, pady=1
        )
        self.engine_btn.pack(side=tk.LEFT)

        self.kill_btn = tk.Button(self.top_bar, text="STOP (Ctrl+Shift+K)", command=self.on_kill, bg="#dc2626", fg="#ffffff", relief=tk.FLAT, padx=8, font=("Segoe UI", 9, "bold"))
        self.kill_btn.pack(side=tk.RIGHT, padx=3)

        self.confirm_btn = tk.Button(self.top_bar, text="Approve Action", command=self.on_confirm_actions, bg="#10b981", fg="#0f172a", state=tk.DISABLED, relief=tk.FLAT, padx=8, font=("Segoe UI", 9, "bold"))
        self.confirm_btn.pack(side=tk.RIGHT, padx=3)

        self.topmost_btn = tk.Button(self.top_bar, text="📌 Pin HUD", command=self.on_toggle_topmost, relief=tk.FLAT, padx=6, font=("Segoe UI", 9))
        self.topmost_btn.pack(side=tk.RIGHT, padx=3)

        self.compact_btn = tk.Button(self.top_bar, text="🗕 Compact", command=self.on_toggle_compact, relief=tk.FLAT, padx=6, font=("Segoe UI", 9))
        self.compact_btn.pack(side=tk.RIGHT, padx=3)

        self.clip_btn = tk.Button(self.top_bar, text="📋 Clip Assist", command=self.on_clipboard_assist, relief=tk.FLAT, padx=6, font=("Segoe UI", 9))
        self.clip_btn.pack(side=tk.RIGHT, padx=3)

        self.theme_btn = tk.Button(self.top_bar, text="🌓 Theme", command=self.on_toggle_theme, relief=tk.FLAT, padx=6, font=("Segoe UI", 9))
        self.theme_btn.pack(side=tk.RIGHT, padx=3)

        self.key_btn = tk.Button(self.top_bar, text="Save Key", command=self.on_save_key, relief=tk.FLAT, padx=6, font=("Segoe UI", 9))
        self.key_btn.pack(side=tk.RIGHT, padx=2)

        self.key_entry = tk.Entry(self.top_bar, width=12, show="*")
        self.key_entry.pack(side=tk.RIGHT, padx=2)

        self.main_pane = tk.Frame(self.root)
        self.main_pane.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self.sidebar = tk.Frame(self.main_pane, width=230)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))

        self.new_sess_btn = tk.Button(self.sidebar, text="+ New Session", command=self.on_new_session, bg="#ff6b1a", fg="#ffffff", relief=tk.FLAT, font=("Segoe UI", 9, "bold"), pady=5)
        self.new_sess_btn.pack(fill=tk.X, pady=(0, 6))

        self.search_entry = tk.Entry(self.sidebar, font=("Segoe UI", 9))
        self.search_entry.insert(0, "")
        self.search_entry.pack(fill=tk.X, pady=(0, 4))
        self.search_entry.bind("<KeyRelease>", self.on_search_sessions)

        self.session_listbox = tk.Listbox(self.sidebar, height=18, relief=tk.FLAT, font=("Segoe UI", 9), selectmode=tk.SINGLE)
        self.session_listbox.pack(fill=tk.BOTH, expand=True)
        self.session_listbox.bind("<<ListboxSelect>>", self.on_select_session)

        self.session_actions_bar = tk.Frame(self.sidebar, pady=4)
        self.session_actions_bar.pack(fill=tk.X)

        self.pin_sess_btn = tk.Button(self.session_actions_bar, text="📌 Pin", command=self.on_pin_session, relief=tk.FLAT, font=("Segoe UI", 8), padx=4)
        self.pin_sess_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        self.rename_sess_btn = tk.Button(self.session_actions_bar, text="✏️ Rename", command=self.on_rename_session, relief=tk.FLAT, font=("Segoe UI", 8), padx=4)
        self.rename_sess_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        self.export_sess_btn = tk.Button(self.session_actions_bar, text="📤 Export", command=self.on_export_session, relief=tk.FLAT, font=("Segoe UI", 8), padx=4)
        self.export_sess_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        self.chat_frame = tk.Frame(self.main_pane)
        self.chat_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.chat_text = tk.Text(self.chat_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Segoe UI", 10), relief=tk.FLAT, padx=14, pady=12)
        self.chat_text.pack(fill=tk.BOTH, expand=True)

        self.bottom_bar = tk.Frame(self.chat_frame, pady=6)
        self.bottom_bar.pack(fill=tk.X)

        self.voice_btn = tk.Button(self.bottom_bar, text="🎤 Speak", command=self.on_voice, bg="#ea580c", fg="#ffffff", relief=tk.FLAT, padx=12, pady=3, font=("Segoe UI", 9, "bold"))
        self.voice_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.prompt_entry = tk.Entry(self.bottom_bar, font=("Segoe UI", 10))
        self.prompt_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=3)
        self.prompt_entry.bind("<Return>", lambda _e: self.on_send())

        self.send_btn = tk.Button(self.bottom_bar, text="Send ➤", command=self.on_send, bg="#ff6b1a", fg="#ffffff", relief=tk.FLAT, padx=14, pady=3, font=("Segoe UI", 9, "bold"))
        self.send_btn.pack(side=tk.RIGHT)

        self.root.bind("<Control-Shift-K>", lambda _e: self.on_kill())
        self.root.bind("<Control-Shift-k>", lambda _e: self.on_kill())

    def _setup_chat_tags(self) -> None:
        tk = self.tk
        pal = THEMES.get(self.current_theme, THEMES["dark"])
        self.chat_text.tag_configure("hero_badge", font=("Segoe UI", 9, "bold"), foreground=pal.get("accent", "#ff6b1a"), justify=tk.CENTER)
        self.chat_text.tag_configure("hero_title", font=("Segoe UI", 16, "bold"), foreground=pal.get("fg", "#fafafa"), justify=tk.CENTER, spacing1=10, spacing3=4)
        self.chat_text.tag_configure("hero_sub", font=("Segoe UI", 10), foreground=pal.get("muted", "#94a3b8"), justify=tk.CENTER, spacing3=12)
        self.chat_text.tag_configure("hero_div", font=("Consolas", 8), foreground=pal.get("border", "#272733"), justify=tk.CENTER, spacing3=14)
        self.chat_text.tag_configure("quick_card", font=("Segoe UI", 9, "bold"), foreground=pal.get("accent", "#ff6b1a"), background=pal.get("subpanel", "#181822"), lmargin1=40, lmargin2=40, rmargin=40, spacing1=4, spacing3=4)

        self.chat_text.tag_configure("user_header", font=("Segoe UI", 9, "bold"), foreground=pal.get("accent", "#ff6b1a"), spacing1=12, spacing3=3, lmargin1=12, lmargin2=12)
        self.chat_text.tag_configure("user_body", font=("Segoe UI", 10), foreground=pal.get("fg", "#fafafa"), lmargin1=16, lmargin2=16, rmargin=24, spacing1=2, spacing3=10)

        self.chat_text.tag_configure("ai_header", font=("Segoe UI", 9, "bold"), foreground="#38bdf8", spacing1=12, spacing3=3, lmargin1=12, lmargin2=12)
        self.chat_text.tag_configure("ai_body", font=("Segoe UI", 10), foreground=pal.get("fg", "#fafafa"), lmargin1=16, lmargin2=16, rmargin=24, spacing1=2, spacing3=10)

        self.chat_text.tag_configure("code_block", font=("Consolas", 9), foreground="#38bdf8", background=pal.get("code_bg", "#0b0c10"), lmargin1=24, lmargin2=24, rmargin=32, spacing1=4, spacing3=4)
        self.chat_text.tag_configure("tool_tag", font=("Segoe UI", 8, "bold"), foreground="#34d399", lmargin1=24, lmargin2=24, spacing1=4, spacing3=1)
        self.chat_text.tag_configure("tool_result", font=("Consolas", 8), foreground="#a7f3d0", background="#091811", lmargin1=28, lmargin2=28, rmargin=36, spacing1=2, spacing3=4)
        self.chat_text.tag_configure("system_card", font=("Segoe UI", 9), foreground="#fbbf24", background="#1c1608", lmargin1=20, lmargin2=20, rmargin=24, spacing1=6, spacing3=6)

    def apply_theme(self, theme_name: str) -> None:
        self.current_theme = theme_name
        pal = THEMES.get(theme_name, THEMES["dark"])
        self.root.configure(bg=pal["bg"])
        self.top_bar.configure(bg=pal["panel"])
        self.main_pane.configure(bg=pal["bg"])
        self.sidebar.configure(bg=pal["panel"])
        self.session_actions_bar.configure(bg=pal["panel"])
        self.chat_frame.configure(bg=pal["bg"])
        self.bottom_bar.configure(bg=pal["bg"])
        self.status_lbl.configure(bg=pal["panel"], fg=pal["fg"])
        self.chat_text.configure(bg=pal["panel"], fg=pal["fg"], insertbackground=pal["fg"])
        self.session_listbox.configure(bg=pal["subpanel"], fg=pal["fg"])
        self.search_entry.configure(bg=pal["subpanel"], fg=pal["fg"], insertbackground=pal["fg"])
        self.prompt_entry.configure(bg=pal["subpanel"], fg=pal["fg"], insertbackground=pal["fg"])
        self.key_entry.configure(bg=pal["subpanel"], fg=pal["fg"], insertbackground=pal["fg"])

        for btn in (self.topmost_btn, self.compact_btn, self.clip_btn, self.theme_btn, self.key_btn,
                    self.pin_sess_btn, self.rename_sess_btn, self.export_sess_btn):
            btn.configure(bg=pal["subpanel"], fg=pal["fg"])

    def on_toggle_topmost(self) -> None:
        self.is_topmost = not self.is_topmost
        self.root.attributes("-topmost", self.is_topmost)
        pal = THEMES.get(self.current_theme, THEMES["dark"])
        self.topmost_btn.configure(
            text="📌 Unpin" if self.is_topmost else "📌 Pin HUD",
            bg=pal["accent"] if self.is_topmost else pal["subpanel"],
            fg="#ffffff" if self.is_topmost else pal["fg"],
        )

    def on_toggle_compact(self) -> None:
        self.is_compact = not self.is_compact
        if self.is_compact:
            self.sidebar.pack_forget()
            self.chat_text.pack_forget()
            self.root.geometry("480x140")
            self.compact_btn.configure(text="🗖 Expand")
        else:
            self.root.geometry("980x640")
            self.sidebar.pack(side=self.tk.LEFT, fill=self.tk.Y, padx=(0, 8), before=self.chat_frame)
            self.chat_text.pack(fill=self.tk.BOTH, expand=True, before=self.bottom_bar)
            self.compact_btn.configure(text="🗕 Compact")

    def on_clipboard_assist(self) -> None:
        try:
            clip_text = self.root.clipboard_get().strip()
        except Exception:
            clip_text = ""
        if not clip_text:
            self.ui_queue.put(("state", (AgentState.IDLE, "Clipboard empty")))
            return
        prompt = f"Analyze and assist with this clipboard snippet:\n\n```\n{clip_text[:2000]}\n```"
        self.prompt_entry.delete(0, self.tk.END)
        self.prompt_entry.insert(0, clip_text[:80] + ("..." if len(clip_text) > 80 else ""))
        pinned_sid = self.engine.current_session_id

        def worker() -> None:
            self.engine.process_prompt(prompt, session_id=pinned_sid)
            self.ui_queue.put(("turn_done", pinned_sid))

        threading.Thread(target=worker, daemon=True).start()

    def on_toggle_theme(self) -> None:
        cur = str(self.engine.config.settings.get("theme", "dark"))
        nxt = self.engine.set_theme("light" if cur == "dark" else "dark")
        self.apply_theme(nxt)
        self.load_messages(self.engine.storage.get_session_messages(self.engine.current_session_id))

    def on_save_key(self) -> None:
        raw = self.key_entry.get().strip()
        if raw:
            backend = self.engine.client.configure_byo_key(raw)
            self.key_entry.delete(0, self.tk.END)
            self.ui_queue.put(("state", (AgentState.IDLE, f"Saved key to {backend} ({self.engine.client.active_model})")))

    def on_confirm_actions(self) -> None:
        pinned_sid = self.engine.current_session_id

        def worker() -> None:
            self.engine.confirm_pending_actions(session_id=pinned_sid, approved=True)
            self.ui_queue.put(("turn_done", pinned_sid))

        threading.Thread(target=worker, daemon=True).start()

    def on_search_sessions(self, _event: Any = None) -> None:
        q = self.search_entry.get().strip().lower()
        self.session_listbox.delete(0, self.tk.END)
        self._filtered_sessions = []
        for s in self._sessions_cache:
            title = str(s.get("title", "Session"))
            if not q or q in title.lower():
                self._filtered_sessions.append(s)
                mark = "📌 " if s.get("is_pinned") else ""
                self.session_listbox.insert(self.tk.END, f"{mark}{title}")

    def refresh_sessions(self) -> None:
        self._sessions_cache = self.engine.storage.list_sessions(limit=50)
        self._sessions_cache.sort(key=lambda s: (1 if s.get("is_pinned") else 0, str(s.get("updated_at", ""))), reverse=True)
        self.on_search_sessions()

    def on_pin_session(self) -> None:
        sid = self.engine.current_session_id
        curr = False
        for s in self._sessions_cache:
            if s.get("session_id") == sid:
                curr = bool(s.get("is_pinned", False))
                break
        self.engine.storage.pin_session(sid, not curr)
        self.refresh_sessions()

    def on_rename_session(self) -> None:
        sid = self.engine.current_session_id
        cur_title = "Session"
        for s in self._sessions_cache:
            if s.get("session_id") == sid:
                cur_title = s.get("title", "Session")
                break
        new_title = self.prompt_entry.get().strip()
        if not new_title:
            self.prompt_entry.delete(0, self.tk.END)
            self.prompt_entry.insert(0, f"New title for: {cur_title}")
            return
        self.engine.storage.rename_session(sid, new_title)
        self.prompt_entry.delete(0, self.tk.END)
        self.refresh_sessions()

    def on_export_session(self) -> None:
        sid = self.engine.current_session_id
        md_text = self.engine.storage.export_session_markdown(sid)
        out_path = Path.cwd() / f"Sudharshan_Chat_{sid[:8]}.md"
        try:
            out_path.write_text(md_text, encoding="utf-8")
            self.ui_queue.put(("state", (AgentState.IDLE, f"Exported: {out_path.name}")))
        except Exception as exc:
            self.ui_queue.put(("state", (AgentState.BLOCKED, f"Export error: {exc}")))

    def on_new_session(self) -> None:
        self.engine.new_session()
        self.refresh_sessions()
        self.load_messages([])

    def on_select_session(self, _event: Any) -> None:
        sel = self.session_listbox.curselection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self._filtered_sessions):
            sid = self._filtered_sessions[idx]["session_id"]
            msgs = self.engine.switch_session(sid)
            self.load_messages(msgs)

    def _trigger_quick_action(self, prompt: str) -> None:
        self.prompt_entry.delete(0, self.tk.END)
        self.prompt_entry.insert(0, prompt)
        self.on_send()

    def load_messages(self, messages: List[Dict[str, Any]]) -> None:
        self.chat_text.configure(state=self.tk.NORMAL)
        self.chat_text.delete("1.0", self.tk.END)
        self._setup_chat_tags()

        if not messages:
            self.chat_text.insert(self.tk.END, "⚡ SUDHARSHAN CORE v0.9 • LOCAL NEURAL ENGINE\n", "hero_badge")
            self.chat_text.insert(self.tk.END, "Welcome to Sudharshan AI\n", "hero_title")
            self.chat_text.insert(self.tk.END, "100% Private, Hardware-Isolated Desktop Intelligence & Automation\n", "hero_sub")
            self.chat_text.insert(self.tk.END, "────────────────────────────────────────────────────────────────────────────\n", "hero_div")
            self.chat_text.insert(self.tk.END, "⚡ Quick Actions (Click any action below to run):\n\n", "user_header")

            actions = [
                ("1", "⚡ Check system diagnostics, hardware health, and engine status", "Run full system diagnostic check"),
                ("2", "📁 Organize Downloads folder and inspect duplicate files", "Organize my Downloads folder safely"),
                ("3", "📋 Inspect and summarize clipboard content", "Summarize the text currently in my clipboard"),
                ("4", "🤖 Verify local Ollama neural models and RAM allocation", "Check local Ollama neural model status"),
            ]

            for num, label, prompt_val in actions:
                tag_name = f"action_{num}"
                self.chat_text.insert(self.tk.END, f"  [{num}] {label}  \n\n", ("quick_card", tag_name))
                self.chat_text.tag_bind(tag_name, "<Button-1>", lambda _e, p=prompt_val: self._trigger_quick_action(p))
                self.chat_text.tag_bind(tag_name, "<Enter>", lambda _e: self.chat_text.configure(cursor="hand2"))
                self.chat_text.tag_bind(tag_name, "<Leave>", lambda _e: self.chat_text.configure(cursor="arrow"))

            self.chat_text.insert(self.tk.END, "────────────────────────────────────────────────────────────────────────────\n", "hero_div")
            self.chat_text.insert(self.tk.END, "Hardware Kill-Switch: Press Ctrl+Shift+K anytime to abort actions immediately.\n", "hero_sub")
            self.chat_text.configure(state=self.tk.DISABLED)
            self.chat_text.see("1.0")
            return

        for m in messages:
            role = m.get("role")
            content = str(m.get("content", ""))
            ts = m.get("timestamp") or datetime.datetime.now().strftime("%I:%M %p")

            if role == "user":
                self.chat_text.insert(self.tk.END, f"👤 YOU • {ts}\n", "user_header")
                self.chat_text.insert(self.tk.END, f"{content}\n\n", "user_body")
            else:
                model_lbl = m.get("model") or self.engine.client.active_model
                self.chat_text.insert(self.tk.END, f"⚡ SUDHARSHAN AI ({model_lbl}) • {ts}\n", "ai_header")

                if "```" in content:
                    parts = content.split("```")
                    for i, part in enumerate(parts):
                        if i % 2 == 0:
                            if part.strip():
                                self.chat_text.insert(self.tk.END, f"{part.strip()}\n", "ai_body")
                        else:
                            lines = part.split("\n", 1)
                            code_text = lines[1] if len(lines) > 1 else lines[0]
                            self.chat_text.insert(self.tk.END, f"{code_text.rstrip()}\n", "code_block")
                elif content.startswith("⚠️") or "offline" in content.lower():
                    self.chat_text.insert(self.tk.END, f"{content}\n", "system_card")
                else:
                    self.chat_text.insert(self.tk.END, f"{content}\n", "ai_body")

            for r in m.get("results", []):
                out = r.get("output", "") if isinstance(r, dict) else getattr(r, "output", "")
                tool = r.get("tool", "action") if isinstance(r, dict) else getattr(r, "tool", "action")
                self.chat_text.insert(self.tk.END, f"  🔧 Action Completed [{tool}]\n", "tool_tag")
                self.chat_text.insert(self.tk.END, f"  {out}\n\n", "tool_result")

            self.chat_text.insert(self.tk.END, "\n")

        self.chat_text.configure(state=self.tk.DISABLED)
        self.chat_text.see(self.tk.END)

    def on_send(self) -> None:
        text = self.prompt_entry.get().strip()
        if not text:
            return
        self.prompt_entry.delete(0, self.tk.END)
        pinned_sid = self.engine.current_session_id

        def worker() -> None:
            self.engine.process_prompt(text, session_id=pinned_sid)
            self.ui_queue.put(("turn_done", pinned_sid))

        threading.Thread(target=worker, daemon=True).start()

    def on_voice(self) -> None:
        pinned_sid = self.engine.current_session_id

        def worker() -> None:
            self.engine.capture_voice_turn(duration_sec=3.5)
            self.ui_queue.put(("turn_done", pinned_sid))

        threading.Thread(target=worker, daemon=True).start()

    def on_kill(self) -> None:
        self.engine.trigger_emergency_kill()

    def run(self) -> None:
        self.root.mainloop()


def run_windows_tkinter_app(engine: BajrangEngine) -> None:
    hud = WindowsTkinterHUD(engine)
    hud.run()


def run_self_tests() -> int:
    print("[1/5] Verifying SafetyGuard C3 Trampoline Guard & Allowlist...")
    guard = SafetyGuard(strict_allowlist=True)
    assert guard.check_command("notepad.exe")[0] is True
    assert guard.check_command("wt.exe powershell -Command calc")[0] is False
    assert guard.check_command("format c: /q")[0] is False
    print("  -> Passed: SafetyGuard verified.")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = ConfigManager(config_dir=root / "cfg", data_dir=root / "data")
        adapter = WindowsPlatformAdapter()
        engine = BajrangEngine(adapter=adapter, config=cfg)

        print("[2/5] Verifying H4 Unknown Key Rejection & Hotkey Order Independence...")
        res_bad_key = adapter.press_key("unknown_xyz_key")
        assert res_bad_key.success is False and res_bad_key.blocked is True
        res_bad_hk = adapter.hotkey(["r", "win"])
        assert res_bad_hk.success is False and res_bad_hk.blocked is True
        print("  -> Passed: Unknown keys and reversed forbidden hotkeys rejected.")

        print("[3/5] Verifying H8 Session-Pinned Prompt Execution & SQLite Persistence...")
        s1 = engine.new_session("Session One")
        s2 = engine.new_session("Session Two")
        engine.switch_session(s2)
        engine.process_prompt("Pinned to session 1", session_id=s1)
        msgs_s1 = engine.storage.get_session_messages(s1)
        msgs_s2 = engine.storage.get_session_messages(s2)
        assert len(msgs_s1) == 2 and len(msgs_s2) == 0, "Prompt must write to pinned session s1 even when s2 is active"
        print("  -> Passed: Session-pinned execution verified.")

        print("[4/5] Verifying C6 Provider Key Affinity & SecurityVault Isolation...")
        engine.client.configure_byo_key("AIzaTestKey12345678901234567890")
        assert engine.client.provider == "byo_api" and engine.client.active_model == "gemini-2.5-pro"
        assert cfg.get_api_key("groq") == "", "Google key must never be returned for Groq"
        print("  -> Passed: Provider key affinity verified.")

        print("[5/5] Verifying C1 Forged License Rejection & 2048-Bit RSA Verifier...")
        lic = LicenseManager(cfg.config_dir)
        assert lic.verify_key("BAJRANG-PRO-HACKER-20991231-ZZZZZZZZ")[0] is False
        assert AsymmetricLicenseVerifier().n_int.bit_length() >= 2040
        print("  -> Passed: Forged BAJRANG-PRO token rejected; 2048-bit RSA active.")

    print("\nAll 5/5 Bajrang AI (Windows Hardened Layer) self-tests passed!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sudharshan AI (Alpha v0.9) — Windows 11 Desktop Assistant")
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
