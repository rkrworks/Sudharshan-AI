#!/usr/bin/env python3
"""
Bajrang AI Pro — Fedora Linux (GNOME / Wayland) Local Desktop Assistant & GNOME Extension Backend
Powered by Ollama (llama3.2 / llama3.2-vision / qwen2.5-vl:3b), GTK4 + Libadwaita, PipeWire Voice DSP,
SQLite3 Local Chat History Storage, ydotool Wayland Automation, and GNOME Shell 45-49 ESM Extension.

Super Features Included:
1. Custom Built-In Voice Recognizer & Voice Mode (`CustomVoiceRecognizer`):
   - Native Fedora PipeWire (`pw-record`) & ALSA (`arecord`) 16kHz 16-bit mono PCM audio capture
   - Pure-Python DSP Voice Activity Detector (RMS dBFS + Zero-Crossing Rate speech segmentation)
   - 8-Band Spectral Envelope + Dynamic Time Warping (DTW) Acoustic Template Recognizer for 100% offline
     wake-word ("Hey Bajrang") and voice command recognition + custom voice enrollment (`--enroll-voice`)
   - Seamless cascade to local Whisper (`faster-whisper` / `whisper`) or `vosk` for open-ended dictation
   - Native spoken responses via Fedora `speech-dispatcher` (`spd-say`) or `espeak-ng`

2. Persistent Local Chat History (`LocalChatStorage`):
   - Dual SQLite3 (`~/.local/share/bajrang-ai/history.db`) + JSON (`sessions.json`) local storage
   - Multi-session management, full-text history search, session switching, and GTK4 sidebar history drawer

3. GNOME Shell Extension (`bajrang-ai@fedora.local`) & Local IPC Bridge (`127.0.0.1:17420`):
   - Generates & installs a native GNOME Shell 45/46/47/48/49 ESModule extension (`--install-gnome-extension`)
   - Top-bar indicator with HUD toggle, Voice Mode toggle, Recent Chat History menu, Pro License badge, and Kill-Switch

4. Commercial ₹100/Month Pro Subscription License Engine (`LicenseManager`):
   - HMAC-SHA256 license generator & validator (`BAJRANG-PRO-...`) for selling at ₹100/month

References:
- Ollama Llama 3.2: https://ollama.com/library/llama3.2
- ydotool Wayland Automation: https://github.com/ReimuNotMoe/ydotool
- PyGObject GTK4 / Libadwaita: https://pygobject.gnome.org/
- PipeWire Audio: https://pipewire.org/
- GNOME Shell 45+ ESM Extensions: https://gjs.guide/extensions/upgrading/gnome-shell-45.html
"""

from __future__ import annotations

import argparse
import array
import base64
import dataclasses
import datetime
import enum
import hashlib
import hmac
import http.server
import io
import json
import math
import os
import re
import shlex
import shutil
import signal
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


# ============================================================================
# 1. CONFIGURATION, SYSTEM PROMPT & SAFETY BLOCKLIST SCHEMAS
# ============================================================================

APP_ID = "org.fedora.BajrangAI"
EXTENSION_UUID = "bajrang-ai@fedora.local"
APP_TITLE = "Bajrang AI Pro"
APP_VERSION = "3.0.0-fedora-gnome-pro"
IPC_PORT = int(os.environ.get("BAJRANG_IPC_PORT", "17420"))

DEFAULT_SETTINGS: Dict[str, Any] = {
    "ollama_host": os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
    "model": os.environ.get("BAJRANG_MODEL", "llama3.2"),
    "fallback_models": [
        "llama3.2",
        "llama3.2:3b",
        "llama3.2:1b",
        "llama3.2-vision",
        "qwen2.5-vl:3b",
    ],
    "ydotool_socket": os.environ.get("YDOTOOL_SOCKET", "/tmp/.ydotool_socket"),
    "shell_timeout_sec": 15,
    "shell_max_output_bytes": 16384,
    "key_delay_ms": 12,
    "kill_switch_grace_ms": 500,
    "voice_enabled": False,
    "tts_enabled": True,
    "voice_record_seconds": 4.0,
    "voice_vad_threshold_db": -38.0,
    "ipc_port": IPC_PORT,
    "license_key": os.environ.get("BAJRANG_LICENSE_KEY", "BAJRANG-PRO-TRIAL-ACTIVE"),
    "subscription_price_inr": 100,
    "hotkeys": {
        "toggle_hud": "<Super>space",
        "voice_mode": "<Super>v",
        "kill_switch": "<Control>Escape",
    },
    "attach_screen_context": False,
}

DEFAULT_BLOCKLIST: Dict[str, Any] = {
    "forbidden_substrings": [
        "rm -rf /",
        "rm -rf /*",
        "rm -rf ~",
        ":(){ :|:& };:",
        "> /dev/sda",
        "> /dev/nvme",
        "mkfs",
        "dd if=",
        "chmod -R 777 /",
        "chown -R",
        "wipefs",
        "fdisk",
        "parted",
        "dnf remove -y systemd",
        "setenforce 0",
        "curl | sh",
        "curl | bash",
        "wget | sh",
        "wget | bash",
    ],
    "forbidden_regex": [
        r"^\s*sudo\s+rm\s+-rf",
        r"^\s*sudo\s+dd\b",
        r"^\s*>+\s*/dev/sd[a-z]",
        r"^\s*>+\s*/dev/nvme\d+n\d+",
        r"(?:^|[;&|]\s*)sudo\b",
        r"(?:^|[;&|]\s*)pkexec\b",
        r"(?:^|[;&|]\s*)su\s+-",
        r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/(?:\s|$|\*)",
        r"\b(?:curl|wget)\b.*\|\s*(?:ba)?sh\b",
    ],
    "enforce_no_root": True,
}

SYSTEM_PROMPT = """You are Bajrang AI Pro, a fast, intelligent, voice-enabled desktop assistant running locally on Fedora Linux (GNOME/Wayland) powered by Llama 3.2.

OPERATIONAL RULES:
1. By default, engage in clear, direct conversation and answer questions without invoking tools.
2. ONLY emit executable actions or shell commands when the user explicitly commands an action (e.g., "open", "type", "click", "run", "search", "close", "launch", "press").
3. When actions are required, respond ONLY with valid, raw JSON matching the defined schema. Never wrap JSON in conversational commentary.
4. If the user's intent is ambiguous, conversational, or educational, respond in normal markdown text (or with "type": "conversation" and an empty "actions": [] list) without generating action payloads.
5. Never output dangerous, root-level, or system-destructive commands.

JSON ACTION SCHEMA:
{
  "type": "conversation" | "action",
  "text": "<Markdown response to display to the user>",
  "actions": [
    {
      "tool": "ydotool_click" | "ydotool_move" | "ydotool_type" | "ydotool_key" | "shell_exec",
      "params": {
        "x": 500,
        "y": 300,
        "button": "left" | "right" | "middle",
        "text": "string to type",
        "key": "enter" | "backspace" | "tab" | "esc" | "super" | "28:1 28:0",
        "command": "non-root bash command (e.g. gtk-launch org.gnome.Terminal.desktop)"
      }
    }
  ]
}
"""

EVDEV_KEYMAP: Dict[str, str] = {
    "esc": "1:1 1:0",
    "escape": "1:1 1:0",
    "1": "2:1 2:0",
    "2": "3:1 3:0",
    "3": "4:1 4:0",
    "4": "5:1 5:0",
    "5": "6:1 6:0",
    "6": "7:1 7:0",
    "7": "8:1 8:0",
    "8": "9:1 9:0",
    "9": "10:1 10:0",
    "0": "11:1 11:0",
    "backspace": "14:1 14:0",
    "tab": "15:1 15:0",
    "enter": "28:1 28:0",
    "return": "28:1 28:0",
    "space": "57:1 57:0",
    "up": "103:1 103:0",
    "left": "105:1 105:0",
    "right": "106:1 106:0",
    "down": "108:1 108:0",
    "delete": "111:1 111:0",
    "super": "125:1 125:0",
    "meta": "125:1 125:0",
    "ctrl+c": "29:1 46:1 46:0 29:0",
    "ctrl+v": "29:1 47:1 47:0 29:0",
    "ctrl+w": "29:1 17:1 17:0 29:0",
    "ctrl+t": "29:1 20:1 20:0 29:0",
    "ctrl+l": "29:1 38:1 38:0 29:0",
    "alt+f4": "56:1 62:1 62:0 56:0",
    "alt+tab": "56:1 15:1 15:0 56:0",
}

MODIFIER_KEYCODES_TO_RELEASE: List[int] = [29, 42, 54, 56, 97, 100, 125, 126]


class AgentState(enum.Enum):
    IDLE = "idle"               # Green dot
    LISTENING = "listening"     # Purple/Cyan dot (Voice Mode active)
    THINKING = "thinking"       # Blue dot
    EXECUTING = "executing"     # Orange dot
    BLOCKED = "blocked"         # Red dot


@dataclasses.dataclass
class ActionResult:
    tool: str
    success: bool
    output: str
    blocked: bool = False


@dataclasses.dataclass
class AssistantTurn:
    response_type: str
    text: str
    actions: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    results: List[ActionResult] = dataclasses.field(default_factory=list)
    session_id: str = ""


class ConfigManager:
    """Manages `~/.config/bajrang-ai/settings.json` and `blocklist.json`."""

    def __init__(self, config_dir: Optional[Path] = None, data_dir: Optional[Path] = None) -> None:
        xdg_cfg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        xdg_data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        self.config_dir = Path(config_dir) if config_dir else Path(xdg_cfg) / "bajrang-ai"
        self.data_dir = Path(data_dir) if data_dir else Path(xdg_data) / "bajrang-ai"
        self.settings_path = self.config_dir / "settings.json"
        self.blocklist_path = self.config_dir / "blocklist.json"
        self.settings: Dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.blocklist: Dict[str, Any] = dict(DEFAULT_BLOCKLIST)
        self.load()

    def load(self) -> None:
        if self.settings_path.is_file():
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    self.settings.update(json.load(f))
            except Exception as exc:
                sys.stderr.write(f"[BajrangAI] Warning: could not load {self.settings_path}: {exc}\n")

        if self.blocklist_path.is_file():
            try:
                with open(self.blocklist_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    for key in ("forbidden_substrings", "forbidden_regex"):
                        if key in loaded and isinstance(loaded[key], list):
                            self.blocklist[key] = list(dict.fromkeys(self.blocklist[key] + loaded[key]))
                    if "enforce_no_root" in loaded:
                        self.blocklist["enforce_no_root"] = bool(loaded["enforce_no_root"])
            except Exception as exc:
                sys.stderr.write(f"[BajrangAI] Warning: could not load {self.blocklist_path}: {exc}\n")

    def save_defaults(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.settings_path.exists():
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        if not self.blocklist_path.exists():
            with open(self.blocklist_path, "w", encoding="utf-8") as f:
                json.dump(self.blocklist, f, indent=2)

    def save_settings(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=2)


# ============================================================================
# 2. COMMERCIAL ₹100/MONTH PRO LICENSE ENGINE (`LicenseManager`)
# ============================================================================

class LicenseManager:
    """
    Issues and verifies ₹100/month Bajrang AI Pro subscription keys (`BAJRANG-PRO-<USER>-<EXP>-<SIG>`).
    Allows commercial distribution of the GNOME Extension + Voice Mode Pro bundle.
    """

    SECRET_SALT = b"BajrangAI-Fedora-Pro-100INR-2026"

    @classmethod
    def generate_key(cls, subscriber_id: str, valid_days: int = 30) -> str:
        clean_id = re.sub(r"[^A-Z0-9]", "", subscriber_id.upper())[:8] or "USER01"
        exp_date = (datetime.date.today() + datetime.timedelta(days=valid_days)).strftime("%Y%m%d")
        payload = f"{clean_id}-{exp_date}".encode("ascii")
        sig = hmac.new(cls.SECRET_SALT, payload, hashlib.sha256).hexdigest()[:8].upper()
        return f"BAJRANG-PRO-{clean_id}-{exp_date}-{sig}"

    @classmethod
    def verify_key(cls, key: str) -> Tuple[bool, str]:
        cleaned = (key or "").strip().upper()
        if cleaned == "BAJRANG-PRO-TRIAL-ACTIVE":
            return True, "Pro Trial Active (₹100/mo plan)"
        parts = cleaned.split("-")
        if len(parts) != 5 or parts[0] != "BAJRANG" or parts[1] != "PRO":
            return False, "Invalid license key format. Expected BAJRANG-PRO-XXXX-YYYYMMDD-SIGNATURE."
        sub_id, exp_str, sig = parts[2], parts[3], parts[4]
        expected_sig = hmac.new(
            cls.SECRET_SALT, f"{sub_id}-{exp_str}".encode("ascii"), hashlib.sha256
        ).hexdigest()[:8].upper()
        if not hmac.compare_digest(sig, expected_sig):
            return False, "License signature verification failed."
        try:
            exp_date = datetime.datetime.strptime(exp_str, "%Y%m%d").date()
            if exp_date < datetime.date.today():
                return False, f"Subscription expired on {exp_date.isoformat()} (Renew for ₹100/month)."
            return True, f"Bajrang AI Pro Active (Subscriber {sub_id} • Valid thru {exp_date.isoformat()})"
        except ValueError:
            return False, "Malformed expiry date in license key."


# ============================================================================
# 3. PERSISTENT LOCAL CHAT HISTORY STORAGE (`LocalChatStorage`)
# ============================================================================

class LocalChatStorage:
    """
    Stores all chat sessions, messages, voice transcripts, and executed action logs locally
    in SQLite3 (`~/.local/share/bajrang-ai/history.db`) AND mirrors to JSON (`sessions.json`).
    """

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        xdg_data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        self.data_dir = Path(data_dir) if data_dir else Path(xdg_data) / "bajrang-ai"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "history.db"
        self.json_mirror_path = self.data_dir / "sessions.json"
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    actions_json TEXT NOT NULL DEFAULT '[]',
                    results_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
                """
            )

    def create_session(self, title: str = "New Conversation", model: str = "llama3.2") -> str:
        session_id = f"sess_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, title, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, title, model, now, now),
            )
        self._sync_json_mirror()
        return session_id

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        actions: Optional[List[Dict[str, Any]]] = None,
        results: Optional[List[ActionResult]] = None,
        model: str = "llama3.2",
    ) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        actions_str = json.dumps(actions or [])
        results_str = json.dumps([dataclasses.asdict(r) for r in (results or [])])

        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT title FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                auto_title = (content.strip()[:42] + "...") if len(content.strip()) > 42 else content.strip()
                conn.execute(
                    "INSERT INTO sessions (session_id, title, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (session_id, auto_title or "Conversation", model, now, now),
                )
            else:
                if row["title"] == "New Conversation" and role == "user" and content.strip():
                    auto_title = (content.strip()[:42] + "...") if len(content.strip()) > 42 else content.strip()
                    conn.execute(
                        "UPDATE sessions SET title = ?, updated_at = ? WHERE session_id = ?",
                        (auto_title, now, session_id),
                    )
                else:
                    conn.execute(
                        "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                        (now, session_id),
                    )

            conn.execute(
                """
                INSERT INTO messages (session_id, role, content, actions_json, results_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, role, content, actions_str, results_str, now),
            )
        self._sync_json_mirror()

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT s.session_id, s.title, s.model, s.created_at, s.updated_at,
                       COUNT(m.id) AS message_count
                FROM sessions s
                LEFT JOIN messages m ON s.session_id = m.session_id
                GROUP BY s.session_id
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, role, content, actions_json, results_json, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
            result: List[Dict[str, Any]] = []
            for r in rows:
                item = dict(r)
                item["actions"] = json.loads(item.pop("actions_json", "[]"))
                item["results"] = json.loads(item.pop("results_json", "[]"))
                result.append(item)
            return result

    def search_messages(self, query: str, limit: int = 25) -> List[Dict[str, Any]]:
        pattern = f"%{query.strip()}%"
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT m.session_id, s.title, m.role, m.content, m.created_at
                FROM messages m
                JOIN sessions s ON m.session_id = s.session_id
                WHERE m.content LIKE ? OR s.title LIKE ?
                ORDER BY m.id DESC
                LIMIT ?
                """,
                (pattern, pattern, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_session(self, session_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        self._sync_json_mirror()

    def _sync_json_mirror(self) -> None:
        try:
            sessions = self.list_sessions(limit=25)
            export_data = {
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "sessions": sessions,
            }
            self.json_mirror_path.write_text(json.dumps(export_data, indent=2), encoding="utf-8")
        except Exception:
            pass


# ============================================================================
# 4. CUSTOM BUILT-IN PYTHON VOICE RECOGNIZER & TTS (`CustomVoiceRecognizer`)
# ============================================================================

class CustomVoiceRecognizer:
    """
    Custom Voice Activity Detector (VAD) + Spectral Envelope / Dynamic Time Warping (DTW)
    Acoustic Recognizer built from scratch in pure Python (`wave`, `struct`, `math`, `array`),
    with native Fedora PipeWire (`pw-record`) / ALSA (`arecord`) capture and automatic
    cascade to local `faster-whisper` / `whisper` / `vosk` for open-ended speech dictation.
    """

    SAMPLE_RATE = 16000
    FRAME_MS = 25
    HOP_MS = 10
    NUM_BANDS = 8

    DEFAULT_VOICE_TEMPLATES: Dict[str, List[List[float]]] = {
        "open terminal": [
            [0.35, 0.42, 0.18, 0.05, 0.12, 0.08, 0.04, 0.02],
            [0.28, 0.51, 0.24, 0.10, 0.15, 0.09, 0.05, 0.03],
            [0.19, 0.38, 0.44, 0.22, 0.11, 0.06, 0.04, 0.02],
            [0.25, 0.46, 0.31, 0.14, 0.09, 0.05, 0.03, 0.02],
        ],
        "take screenshot": [
            [0.12, 0.22, 0.48, 0.35, 0.28, 0.18, 0.12, 0.08],
            [0.30, 0.44, 0.26, 0.18, 0.14, 0.10, 0.06, 0.04],
            [0.15, 0.20, 0.42, 0.38, 0.30, 0.22, 0.14, 0.09],
            [0.26, 0.40, 0.30, 0.16, 0.10, 0.06, 0.04, 0.02],
        ],
        "clear chat": [
            [0.18, 0.28, 0.46, 0.32, 0.20, 0.12, 0.06, 0.04],
            [0.32, 0.48, 0.25, 0.12, 0.08, 0.05, 0.03, 0.02],
            [0.22, 0.36, 0.40, 0.24, 0.14, 0.08, 0.04, 0.02],
        ],
        "kill switch": [
            [0.14, 0.24, 0.50, 0.36, 0.26, 0.18, 0.10, 0.06],
            [0.20, 0.32, 0.44, 0.30, 0.22, 0.14, 0.08, 0.05],
            [0.16, 0.26, 0.48, 0.34, 0.24, 0.16, 0.09, 0.05],
        ],
    }

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        vad_threshold_db: float = -38.0,
        tts_enabled: bool = True,
    ) -> None:
        xdg_data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        self.data_dir = Path(data_dir) if data_dir else Path(xdg_data) / "bajrang-ai"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.templates_path = self.data_dir / "voice_templates.json"
        self.vad_threshold_db = vad_threshold_db
        self.tts_enabled = tts_enabled
        self.templates: Dict[str, List[List[float]]] = dict(self.DEFAULT_VOICE_TEMPLATES)
        self._load_templates()

    def _load_templates(self) -> None:
        if self.templates_path.is_file():
            try:
                loaded = json.loads(self.templates_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.templates.update(loaded)
            except Exception:
                pass

    def save_templates(self) -> None:
        self.templates_path.write_text(json.dumps(self.templates, indent=2), encoding="utf-8")

    @staticmethod
    def generate_synthetic_speech_wav(
        output_path: Path,
        phrase: str = "open terminal",
        duration_sec: float = 1.2,
    ) -> Path:
        num_samples = int(CustomVoiceRecognizer.SAMPLE_RATE * duration_sec)
        samples = array.array("h")
        seed = sum((i + 1) * ord(ch) for i, ch in enumerate(phrase.lower()))
        f1 = 220.0 + (seed % 180)
        f2 = 680.0 + ((seed * 3) % 620)
        f3 = 1550.0 + ((seed * 7) % 950)

        for n in range(num_samples):
            t = n / CustomVoiceRecognizer.SAMPLE_RATE
            if t < 0.12 or t > (duration_sec - 0.12):
                samples.append(0)
                continue
            env = 0.65 + 0.35 * math.sin(2.0 * math.pi * 4.5 * t)
            mod = 1.0 + 0.08 * math.sin(2.0 * math.pi * 12.0 * t)
            val = env * (
                0.55 * math.sin(2.0 * math.pi * f1 * mod * t)
                + 0.30 * math.sin(2.0 * math.pi * f2 * t)
                + 0.15 * math.sin(2.0 * math.pi * f3 * t)
            )
            pcm16 = max(-32767, min(32767, int(val * 18000)))
            samples.append(pcm16)

        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(CustomVoiceRecognizer.SAMPLE_RATE)
            wf.writeframes(samples.tobytes())
        return output_path

    def record_microphone_wav(self, duration_sec: float = 4.0) -> Tuple[Optional[Path], str]:
        tmp_wav = Path(tempfile.gettempdir()) / f"bajrang_voice_{os.getpid()}_{int(time.time())}.wav"

        if shutil.which("pw-record"):
            cmd = [
                "pw-record",
                "--rate",
                str(self.SAMPLE_RATE),
                "--channels",
                "1",
                "--format",
                "s16",
                str(tmp_wav),
            ]
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                time.sleep(max(0.5, float(duration_sec)))
                proc.send_signal(signal.SIGINT)
                proc.wait(timeout=2.0)
                if tmp_wav.is_file() and tmp_wav.stat().st_size > 44:
                    return tmp_wav, "Recorded audio via Fedora PipeWire (`pw-record`)."
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        if shutil.which("arecord"):
            cmd = [
                "arecord",
                "-q",
                "-f",
                "S16_LE",
                "-r",
                str(self.SAMPLE_RATE),
                "-c",
                "1",
                "-d",
                str(max(1, int(math.ceil(duration_sec)))),
                str(tmp_wav),
            ]
            try:
                res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=duration_sec + 3.0)
                if res.returncode == 0 and tmp_wav.is_file() and tmp_wav.stat().st_size > 44:
                    return tmp_wav, "Recorded audio via ALSA (`arecord`)."
            except Exception:
                pass

        return None, "No microphone capture tool available (install `pipewire-utils` or `alsa-utils`)."

    def read_pcm16_wav(self, wav_path: Path) -> List[float]:
        with wave.open(str(wav_path), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        if sampwidth != 2 or n_frames == 0:
            return []

        total_shorts = len(raw) // 2
        shorts = struct.unpack(f"<{total_shorts}h", raw[: total_shorts * 2])
        if n_channels > 1:
            shorts = shorts[::n_channels]
        return [s / 32768.0 for s in shorts]

    def extract_vad_and_features(self, samples: List[float]) -> Tuple[bool, List[List[float]], Dict[str, float]]:
        if not samples:
            return False, [], {"rms_db": -100.0, "active_frames": 0, "zcr": 0.0}

        frame_len = int(self.SAMPLE_RATE * (self.FRAME_MS / 1000.0))
        hop_len = int(self.SAMPLE_RATE * (self.HOP_MS / 1000.0))

        emphasized = [samples[0]] + [
            samples[i] - 0.97 * samples[i - 1] for i in range(1, len(samples))
        ]

        band_freqs = [180.0, 320.0, 520.0, 820.0, 1250.0, 1850.0, 2650.0, 3700.0]
        coeffs = [2.0 * math.cos(2.0 * math.pi * f / self.SAMPLE_RATE) for f in band_freqs]

        active_features: List[List[float]] = []
        peak_db = -100.0
        zcr_sum = 0.0
        total_frames = 0

        for start in range(0, max(1, len(emphasized) - frame_len + 1), hop_len):
            frame = emphasized[start : start + frame_len]
            if len(frame) < frame_len:
                break
            total_frames += 1

            mean_sq = sum(x * x for x in frame) / frame_len
            rms = math.sqrt(mean_sq + 1e-12)
            rms_db = 20.0 * math.log10(rms + 1e-9)
            if rms_db > peak_db:
                peak_db = rms_db

            zero_crossings = sum(
                1 for i in range(1, len(frame)) if (frame[i] >= 0) != (frame[i - 1] >= 0)
            )
            zcr = zero_crossings / float(frame_len)
            zcr_sum += zcr

            if rms_db >= self.vad_threshold_db:
                band_energies: List[float] = []
                for coeff in coeffs:
                    s_prev = 0.0
                    s_prev2 = 0.0
                    for idx, sample in enumerate(frame):
                        win = 0.54 - 0.46 * math.cos(2.0 * math.pi * idx / (frame_len - 1))
                        s = (sample * win) + coeff * s_prev - s_prev2
                        s_prev2 = s_prev
                        s_prev = s
                    power = max(1e-9, s_prev2 * s_prev2 + s_prev * s_prev - coeff * s_prev * s_prev2)
                    band_energies.append(math.log1p(power))

                norm = math.sqrt(sum(e * e for e in band_energies)) or 1.0
                active_features.append([round(e / norm, 4) for e in band_energies])

        if len(active_features) > 12:
            step = len(active_features) / 12.0
            active_features = [active_features[int(i * step)] for i in range(12)]

        has_speech = len(active_features) >= 2 and peak_db >= self.vad_threshold_db
        metrics = {
            "rms_db": round(peak_db, 2),
            "active_frames": float(len(active_features)),
            "zcr": round(zcr_sum / max(1, total_frames), 4),
        }
        return has_speech, active_features, metrics

    @staticmethod
    def _dtw_distance(seq_a: List[List[float]], seq_b: List[List[float]]) -> float:
        if not seq_a or not seq_b:
            return float("inf")
        n, m = len(seq_a), len(seq_b)
        dp = [[float("inf")] * (m + 1) for _ in range(n + 1)]
        dp[0][0] = 0.0

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                vec_a, vec_b = seq_a[i - 1], seq_b[j - 1]
                cost = math.sqrt(sum((a - b) ** 2 for a, b in zip(vec_a, vec_b)))
                dp[i][j] = cost + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])

        return dp[n][m] / float(n + m)

    def enroll_phrase_from_wav(self, phrase: str, wav_path: Path) -> Tuple[bool, str]:
        samples = self.read_pcm16_wav(wav_path)
        has_speech, features, metrics = self.extract_vad_and_features(samples)
        if not has_speech or not features:
            return False, f"No clear voice detected (peak {metrics['rms_db']} dB)."
        clean_phrase = phrase.strip().lower()
        self.templates[clean_phrase] = features
        self.save_templates()
        return True, f"Enrolled voice template '{clean_phrase}' ({len(features)} spectral frames, {metrics['rms_db']} dB)."

    def recognize_wav(self, wav_path: Path) -> Tuple[bool, str, str]:
        samples = self.read_pcm16_wav(wav_path)
        has_speech, features, metrics = self.extract_vad_and_features(samples)
        if not has_speech:
            return False, "", f"Silence / below VAD threshold ({metrics['rms_db']} dB)"

        try:
            from faster_whisper import WhisperModel  # type: ignore
            if not hasattr(self, "_whisper_model"):
                self._whisper_model = WhisperModel("base.en", device="cpu", compute_type="int8")
            segments, _ = self._whisper_model.transcribe(str(wav_path), beam_size=1)
            text = " ".join(seg.text.strip() for seg in segments).strip()
            if text:
                return True, text, "faster-whisper (local CPU)"
        except Exception:
            pass

        try:
            import vosk  # type: ignore
            model_dir = self.data_dir / "vosk-model-small-en-us"
            if model_dir.is_dir():
                vmodel = vosk.Model(str(model_dir))
                rec = vosk.KaldiRecognizer(vmodel, self.SAMPLE_RATE)
                with open(wav_path, "rb") as wf:
                    wf.seek(44)
                    rec.AcceptWaveform(wf.read())
                res_json = json.loads(rec.FinalResult())
                if res_json.get("text"):
                    return True, str(res_json["text"]).strip(), "vosk (offline)"
        except Exception:
            pass

        best_phrase = ""
        best_dist = float("inf")
        for phrase, tmpl in self.templates.items():
            dist = self._dtw_distance(features, tmpl)
            if dist < best_dist:
                best_dist = dist
                best_phrase = phrase

        if best_phrase and best_dist <= 0.45:
            confidence = max(0, min(99, int((1.0 - best_dist) * 100)))
            return (
                True,
                best_phrase,
                f"Bajrang DSP Spectral-DTW Recognizer ({confidence}% match, {metrics['rms_db']} dB)",
            )

        return (
            False,
            "",
            f"Voice detected ({metrics['rms_db']} dB), no matching template (best DTW={best_dist:.2f}). "
            "Enroll phrases with `--enroll-voice` or install `faster-whisper`.",
        )

    def listen_and_recognize(self, duration_sec: float = 4.0) -> Tuple[bool, str, str]:
        wav_path, cap_msg = self.record_microphone_wav(duration_sec=duration_sec)
        if wav_path is None:
            return False, "", cap_msg
        try:
            return self.recognize_wav(wav_path)
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass

    def speak_tts(self, text: str) -> None:
        if not self.tts_enabled or not text.strip():
            return
        clean = re.sub(r"[`*_#>~]", "", text).strip()[:320]
        if shutil.which("spd-say"):
            subprocess.Popen(
                ["spd-say", "--wait", clean],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif shutil.which("espeak-ng"):
            subprocess.Popen(
                ["espeak-ng", clean],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


# ============================================================================
# 5. SAFETY GUARDRAILS & EMERGENCY KILL-SWITCH (`src/execution/safety.py`)
# ============================================================================

class SafetyGuard:
    """Validates shell commands and input payloads against the Bajrang AI blocklist."""

    def __init__(self, blocklist: Optional[Dict[str, Any]] = None) -> None:
        cfg = blocklist or DEFAULT_BLOCKLIST
        self.forbidden_substrings: List[str] = [
            s.lower() for s in cfg.get("forbidden_substrings", DEFAULT_BLOCKLIST["forbidden_substrings"])
        ]
        self.forbidden_regex: List[re.Pattern[str]] = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in cfg.get("forbidden_regex", DEFAULT_BLOCKLIST["forbidden_regex"])
        ]
        self.enforce_no_root: bool = bool(cfg.get("enforce_no_root", True))

    def validate_command(self, command: str) -> Tuple[bool, str]:
        if not command or not command.strip():
            return False, "Empty shell command rejected."

        normalized = " ".join(command.strip().split())
        lower_cmd = normalized.lower()

        if self.enforce_no_root:
            tokens = re.split(r"[;&|()\s]+", lower_cmd)
            if any(tok in ("sudo", "pkexec", "doas", "su") for tok in tokens):
                return False, "Blocked by Safety Guardrail: root escalation ('sudo'/'pkexec'/'su') is prohibited."

        for sub in self.forbidden_substrings:
            if sub in lower_cmd:
                return False, f"Blocked by Safety Guardrail: prohibited token '{sub}' detected."

        for regex in self.forbidden_regex:
            if regex.search(normalized):
                return False, f"Blocked by Safety Guardrail: matched destructive pattern '{regex.pattern}'."

        return True, "Command passed safety checks."


class KillSwitchManager:
    """
    Emergency Kill-Switch (`Ctrl + Escape` or `--kill`):
    - Sends SIGTERM, followed by SIGKILL after 500ms, to any active subprocesses.
    - Dispatches an instant key-release reset payload to `ydotoold` so no keys remain stuck.
    """

    def __init__(self, grace_ms: int = 500, ydotool_socket: str = "/tmp/.ydotool_socket") -> None:
        self.grace_ms = grace_ms
        self.ydotool_socket = ydotool_socket
        self._lock = threading.Lock()
        self._active_procs: Dict[int, subprocess.Popen[Any]] = {}
        self._cancel_event = threading.Event()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def reset_cancel_flag(self) -> None:
        self._cancel_event.clear()

    def register_process(self, proc: subprocess.Popen[Any]) -> None:
        with self._lock:
            self._active_procs[proc.pid] = proc

    def unregister_process(self, pid: int) -> None:
        with self._lock:
            self._active_procs.pop(pid, None)

    def release_stuck_keys(self) -> None:
        ydotool_bin = shutil.which("ydotool")
        if not ydotool_bin:
            return
        env = os.environ.copy()
        env["YDOTOOL_SOCKET"] = self.ydotool_socket
        release_args = [f"{code}:0" for code in MODIFIER_KEYCODES_TO_RELEASE]
        try:
            subprocess.run(
                [ydotool_bin, "key", *release_args],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
                check=False,
            )
        except Exception:
            pass

    def trigger(self) -> str:
        self._cancel_event.set()
        killed_pids: List[int] = []

        with self._lock:
            procs = list(self._active_procs.values())

        for proc in procs:
            if proc.poll() is None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    killed_pids.append(proc.pid)
                except Exception:
                    try:
                        proc.terminate()
                        killed_pids.append(proc.pid)
                    except Exception:
                        pass

        deadline = time.monotonic() + (self.grace_ms / 1000.0)
        for proc in procs:
            remaining = max(0.01, deadline - time.monotonic())
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

        with self._lock:
            self._active_procs.clear()

        self.release_stuck_keys()

        if killed_pids:
            return f"Emergency Kill-Switch activated: terminated PIDs {killed_pids} and reset ydotool key states."
        return "Emergency Kill-Switch activated: cancelled active operation and reset ydotool key states."


# ============================================================================
# 6. PERCEPTION & EXECUTION LAYERS (`WaylandPerception`, `YdotoolController`, `ShellRunner`)
# ============================================================================

class WaylandPerception:
    """Wayland screen capture and display resolution detector for Fedora GNOME."""

    def __init__(self) -> None:
        self.screen_width: int = 1920
        self.screen_height: int = 1080
        self._detect_display_resolution()

    def _detect_display_resolution(self) -> None:
        try:
            import gi
            gi.require_version("Gdk", "4.0")
            from gi.repository import Gdk
            display = Gdk.Display.get_default()
            if display is not None:
                monitors = display.get_monitors()
                if monitors.get_n_items() > 0:
                    monitor = monitors.get_item(0)
                    geom = monitor.get_geometry()
                    if geom.width > 0 and geom.height > 0:
                        self.screen_width = geom.width
                        self.screen_height = geom.height
                        return
        except Exception:
            pass

    def capture_screen_base64(self, max_dimension: int = 1280) -> Tuple[Optional[str], str]:
        tmp_path = Path(tempfile.gettempdir()) / f"bajrang_capture_{os.getpid()}.png"
        captured = False
        tool_used = ""

        commands: List[Tuple[str, List[str]]] = [
            ("gnome-screenshot", ["gnome-screenshot", "-f", str(tmp_path)]),
            ("grim", ["grim", str(tmp_path)]),
        ]

        for name, cmd in commands:
            if shutil.which(name):
                try:
                    res = subprocess.run(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        timeout=5.0,
                        check=False,
                    )
                    if res.returncode == 0 and tmp_path.is_file() and tmp_path.stat().st_size > 0:
                        captured = True
                        tool_used = name
                        break
                except Exception:
                    continue

        if not captured or not tmp_path.is_file():
            return None, "Screen capture unavailable (install `gnome-screenshot` or `grim` on Fedora Wayland)."

        try:
            try:
                from PIL import Image
                with Image.open(tmp_path) as img:
                    self.screen_width, self.screen_height = img.size
                    img_rgb = img.convert("RGB")
                    img_rgb.thumbnail((max_dimension, max_dimension))
                    buf = io.BytesIO()
                    img_rgb.save(buf, format="JPEG", quality=82)
                    b64_data = base64.b64encode(buf.getvalue()).decode("ascii")
            except ImportError:
                raw_bytes = tmp_path.read_bytes()
                b64_data = base64.b64encode(raw_bytes).decode("ascii")

            return b64_data, f"Captured Wayland screen via {tool_used} ({self.screen_width}x{self.screen_height})."
        except Exception as exc:
            return None, f"Failed to encode screenshot: {exc}"
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def get_desktop_context_summary(self) -> str:
        session_type = os.environ.get("XDG_SESSION_TYPE", "wayland")
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "GNOME")
        return (
            f"OS: Fedora Linux | Desktop: {desktop} ({session_type}) | "
            f"Display Resolution: {self.screen_width}x{self.screen_height}"
        )


class YdotoolController:
    """Wayland input automation via `ydotool` and `ydotoold` writing to `/dev/uinput`."""

    CLICK_CODES: Dict[str, str] = {
        "left": "0xC0",
        "right": "0xC1",
        "middle": "0xC2",
    }

    def __init__(
        self,
        socket_path: str = "/tmp/.ydotool_socket",
        key_delay_ms: int = 12,
        perception: Optional[WaylandPerception] = None,
    ) -> None:
        self.socket_path = socket_path
        self.key_delay_ms = key_delay_ms
        self.perception = perception or WaylandPerception()

    def check_daemon(self) -> Tuple[bool, str]:
        ydotool_bin = shutil.which("ydotool")
        if not ydotool_bin:
            return False, "ydotool is not installed (`sudo dnf install ydotool`)."

        fallback_sockets = [
            self.socket_path,
            "/tmp/.ydotool_socket",
            f"/run/user/{os.getuid()}/.ydotool_socket",
            "/run/ydotoold/socket",
        ]
        for sock in fallback_sockets:
            if os.path.exists(sock):
                self.socket_path = sock
                return True, f"ydotoold socket active at {sock}"

        return (
            False,
            f"ydotoold socket not found at {self.socket_path}. Start daemon with: "
            f"`ydotoold --socket-path={self.socket_path} --socket-perm=0600 &`",
        )

    def _run_ydotool(self, args: List[str]) -> ActionResult:
        ok, status = self.check_daemon()
        if not ok:
            return ActionResult(tool=f"ydotool {args[0]}", success=False, output=status)

        env = os.environ.copy()
        env["YDOTOOL_SOCKET"] = self.socket_path
        cmd = ["ydotool", *args]
        try:
            proc = subprocess.run(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10.0,
                check=False,
            )
            if proc.returncode == 0:
                return ActionResult(
                    tool=f"ydotool {args[0]}",
                    success=True,
                    output=f"Executed: {' '.join(shlex.quote(a) for a in cmd)}",
                )
            err = (proc.stderr or proc.stdout or "").strip()
            return ActionResult(
                tool=f"ydotool {args[0]}",
                success=False,
                output=f"ydotool error (exit {proc.returncode}): {err}",
            )
        except Exception as exc:
            return ActionResult(tool=f"ydotool {args[0]}", success=False, output=f"ydotool exception: {exc}")

    def mouse_move(self, x: int, y: int) -> ActionResult:
        clamped_x = max(0, min(int(x), self.perception.screen_width))
        clamped_y = max(0, min(int(y), self.perception.screen_height))
        return self._run_ydotool(["mousemove", "-a", str(clamped_x), str(clamped_y)])

    def mouse_click(
        self,
        button: str = "left",
        x: Optional[int] = None,
        y: Optional[int] = None,
    ) -> ActionResult:
        logs: List[str] = []
        if x is not None and y is not None:
            move_res = self.mouse_move(int(x), int(y))
            logs.append(move_res.output)
            if not move_res.success:
                return move_res

        code = self.CLICK_CODES.get(str(button).lower(), "0xC0")
        click_res = self._run_ydotool(["click", code])
        if logs:
            click_res.output = " -> ".join(logs + [click_res.output])
        return click_res

    def type_text(self, text: str) -> ActionResult:
        if not text:
            return ActionResult(tool="ydotool_type", success=False, output="Empty text payload.")
        return self._run_ydotool(["type", "--key-delay", str(self.key_delay_ms), text])

    def press_key(self, key_spec: str) -> ActionResult:
        cleaned = str(key_spec).strip().lower()
        evdev_seq = EVDEV_KEYMAP.get(cleaned, key_spec.strip())
        tokens = evdev_seq.split()
        if not tokens:
            return ActionResult(tool="ydotool_key", success=False, output="Empty key sequence.")
        return self._run_ydotool(["key", *tokens])


class ShellRunner:
    """Executes validated non-root shell commands with timeout & output size caps."""

    def __init__(
        self,
        safety: SafetyGuard,
        kill_switch: KillSwitchManager,
        timeout_sec: int = 15,
        max_output_bytes: int = 16384,
    ) -> None:
        self.safety = safety
        self.kill_switch = kill_switch
        self.timeout_sec = timeout_sec
        self.max_output_bytes = max_output_bytes

    def run(self, command: str) -> ActionResult:
        is_safe, reason = self.safety.validate_command(command)
        if not is_safe:
            return ActionResult(
                tool="shell_exec",
                success=False,
                output=reason,
                blocked=True,
            )

        try:
            needs_shell = any(op in command for op in ("|", "&&", "||", ";", ">", "<", "$"))
            if needs_shell:
                popen_args: Any = ["bash", "--noprofile", "--norc", "-c", command]
            else:
                popen_args = shlex.split(command)

            proc = subprocess.Popen(
                popen_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            self.kill_switch.register_process(proc)
            try:
                stdout, stderr = proc.communicate(timeout=self.timeout_sec)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    proc.kill()
                return ActionResult(
                    tool="shell_exec",
                    success=False,
                    output=f"Command timed out after {self.timeout_sec}s: `{command}`",
                )
            finally:
                self.kill_switch.unregister_process(proc.pid)

            combined = (stdout or "") + (f"\n[stderr]\n{stderr}" if stderr else "")
            combined = combined.strip()
            if len(combined.encode("utf-8")) > self.max_output_bytes:
                combined = combined[: self.max_output_bytes] + "\n...[output truncated]..."

            if proc.returncode == 0:
                return ActionResult(
                    tool="shell_exec",
                    success=True,
                    output=combined or f"Command completed successfully (exit 0): `{command}`",
                )
            return ActionResult(
                tool="shell_exec",
                success=False,
                output=f"Command exited with status {proc.returncode}:\n{combined}",
            )
        except Exception as exc:
            return ActionResult(
                tool="shell_exec",
                success=False,
                output=f"Execution failed for `{command}`: {exc}",
            )


# ============================================================================
# 7. INTELLIGENCE LAYER (`OllamaLlamaClient`)
# ============================================================================

class OllamaLlamaClient:
    """Local Ollama API client tailored for `llama3.2` on Fedora Linux."""

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "llama3.2",
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.system_prompt = system_prompt
        self.history: List[Dict[str, Any]] = []

    def clear_history(self) -> None:
        self.history.clear()

    def load_session_messages(self, stored_messages: List[Dict[str, Any]]) -> None:
        self.history = [
            {"role": m["role"], "content": m["content"]}
            for m in stored_messages
            if m.get("role") in ("user", "assistant")
        ]

    def check_health(self) -> Tuple[bool, List[str], str]:
        url = f"{self.host}/api/tags"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
                return True, models, f"Connected to Ollama at {self.host} ({len(models)} models available)."
        except Exception as exc:
            return (
                False,
                [],
                f"Ollama unreachable at {self.host} ({exc}). Run `systemctl start ollama` or `ollama serve`.",
            )

    @staticmethod
    def _looks_like_action_intent(user_prompt: str) -> bool:
        action_verbs = (
            r"\b(open|launch|start|run|execute|type|write|click|press|move|close|kill|search|browse)\b"
        )
        return bool(re.search(action_verbs, user_prompt.strip(), re.IGNORECASE))

    @staticmethod
    def parse_structured_output(raw_text: str) -> AssistantTurn:
        cleaned = raw_text.strip()
        fenced_match = re.match(r"^```(?:json)?\s*(\{.*?\})\s*```$", cleaned, re.DOTALL)
        candidate = fenced_match.group(1).strip() if fenced_match else cleaned

        if not candidate.startswith("{"):
            brace_start = candidate.find("{")
            brace_end = candidate.rfind("}")
            if brace_start != -1 and brace_end > brace_start:
                possible_json = candidate[brace_start : brace_end + 1]
                try:
                    parsed = json.loads(possible_json)
                    if isinstance(parsed, dict) and ("type" in parsed or "actions" in parsed):
                        candidate = possible_json
                except Exception:
                    pass

        if candidate.startswith("{") and candidate.endswith("}"):
            try:
                payload = json.loads(candidate)
                if isinstance(payload, dict) and ("type" in payload or "actions" in payload):
                    resp_type = str(payload.get("type", "conversation")).lower()
                    text = str(payload.get("text", "")).strip()
                    actions = payload.get("actions", [])
                    if not isinstance(actions, list):
                        actions = []
                    if actions and resp_type != "action":
                        resp_type = "action"
                    return AssistantTurn(
                        response_type=resp_type,
                        text=text or ("Executing requested actions..." if actions else ""),
                        actions=actions,
                    )
            except json.JSONDecodeError:
                pass

        return AssistantTurn(response_type="conversation", text=cleaned, actions=[])

    def chat(
        self,
        user_prompt: str,
        desktop_context: Optional[str] = None,
        screenshot_b64: Optional[str] = None,
    ) -> AssistantTurn:
        messages: List[Dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        if desktop_context:
            messages.append(
                {
                    "role": "system",
                    "content": f"CURRENT DESKTOP ENVIRONMENT CONTEXT:\n{desktop_context}",
                }
            )

        messages.extend(self.history[-12:])

        user_msg: Dict[str, Any] = {"role": "user", "content": user_prompt}
        if screenshot_b64 and ("vision" in self.model.lower() or "vl" in self.model.lower()):
            user_msg["images"] = [screenshot_b64]
        messages.append(user_msg)

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.2 if self._looks_like_action_intent(user_prompt) else 0.6,
            },
        }

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                assistant_content = body.get("message", {}).get("content", "")
        except urllib.error.HTTPError as http_err:
            err_body = http_err.read().decode("utf-8", errors="replace")
            return AssistantTurn(
                response_type="conversation",
                text=(
                    f"**Ollama HTTP {http_err.code} Error** for model `{self.model}`: {err_body}\n\n"
                    f"Ensure the model is pulled via `ollama pull {self.model}`."
                ),
            )
        except Exception as exc:
            return AssistantTurn(
                response_type="conversation",
                text=(
                    f"**Could not reach local Ollama server** at `{self.host}` (`{exc}`).\n\n"
                    f"Start Ollama with `sudo systemctl start ollama` or `ollama serve`, and pull "
                    f"Llama 3.2 with `ollama pull {self.model}`."
                ),
            )

        turn = self.parse_structured_output(assistant_content)
        self.history.append({"role": "user", "content": user_prompt})
        self.history.append({"role": "assistant", "content": assistant_content})
        return turn


# ============================================================================
# 8. ORCHESTRATOR ENGINE + LOCAL IPC SERVER FOR GNOME EXTENSION (`BajrangEngine`)
# ============================================================================

class BajrangEngine:
    """
    Coordinates Perception, Voice Mode DSP, Local SQLite Chat History,
    Llama 3.2 Intelligence, `ydotool` / Shell Execution, and GNOME Extension IPC.
    """

    def __init__(
        self,
        config: Optional[ConfigManager] = None,
        state_callback: Optional[Callable[[AgentState, str], None]] = None,
        ui_toggle_callback: Optional[Callable[[], None]] = None,
        ui_turn_callback: Optional[Callable[[str, AssistantTurn], None]] = None,
    ) -> None:
        self.config = config or ConfigManager()
        self.state_callback = state_callback
        self.ui_toggle_callback = ui_toggle_callback
        self.ui_turn_callback = ui_turn_callback
        self.state = AgentState.IDLE

        self.storage = LocalChatStorage(data_dir=self.config.data_dir)
        existing_sessions = self.storage.list_sessions(limit=1)
        if existing_sessions:
            self.current_session_id = existing_sessions[0]["session_id"]
        else:
            self.current_session_id = self.storage.create_session(
                title="Fedora Desktop Session",
                model=str(self.config.settings.get("model", "llama3.2")),
            )

        self.voice = CustomVoiceRecognizer(
            data_dir=self.config.data_dir,
            vad_threshold_db=float(self.config.settings.get("voice_vad_threshold_db", -38.0)),
            tts_enabled=bool(self.config.settings.get("tts_enabled", True)),
        )
        self.voice_loop_active = False

        self.safety = SafetyGuard(self.config.blocklist)
        self.kill_switch = KillSwitchManager(
            grace_ms=int(self.config.settings.get("kill_switch_grace_ms", 500)),
            ydotool_socket=str(self.config.settings.get("ydotool_socket", "/tmp/.ydotool_socket")),
        )
        self.perception = WaylandPerception()
        self.input_controller = YdotoolController(
            socket_path=str(self.config.settings.get("ydotool_socket", "/tmp/.ydotool_socket")),
            key_delay_ms=int(self.config.settings.get("key_delay_ms", 12)),
            perception=self.perception,
        )
        self.shell_runner = ShellRunner(
            safety=self.safety,
            kill_switch=self.kill_switch,
            timeout_sec=int(self.config.settings.get("shell_timeout_sec", 15)),
            max_output_bytes=int(self.config.settings.get("shell_max_output_bytes", 16384)),
        )
        self.client = OllamaLlamaClient(
            host=str(self.config.settings.get("ollama_host", "http://localhost:11434")),
            model=str(self.config.settings.get("model", "llama3.2")),
        )
        self.client.load_session_messages(self.storage.get_session_messages(self.current_session_id))

    def set_state(self, new_state: AgentState, status_text: str = "") -> None:
        self.state = new_state
        if self.state_callback:
            self.state_callback(new_state, status_text)

    def new_session(self, title: str = "New Conversation") -> str:
        self.current_session_id = self.storage.create_session(title=title, model=self.client.model)
        self.client.clear_history()
        return self.current_session_id

    def switch_session(self, session_id: str) -> List[Dict[str, Any]]:
        self.current_session_id = session_id
        msgs = self.storage.get_session_messages(session_id)
        self.client.load_session_messages(msgs)
        return msgs

    def trigger_emergency_kill(self) -> str:
        self.voice_loop_active = False
        msg = self.kill_switch.trigger()
        self.set_state(AgentState.BLOCKED, "Blocked / Killed (Emergency Stop)")
        return msg

    def execute_action(self, action: Dict[str, Any]) -> ActionResult:
        if self.kill_switch.is_cancelled:
            return ActionResult(
                tool=str(action.get("tool", "unknown")),
                success=False,
                output="Skipped: Emergency Kill-Switch is active.",
                blocked=True,
            )

        tool = str(action.get("tool", "")).strip().lower()
        params = action.get("params", {}) or {}
        if not isinstance(params, dict):
            params = {}

        if tool == "ydotool_move":
            return self.input_controller.mouse_move(
                x=int(params.get("x", 0)),
                y=int(params.get("y", 0)),
            )
        if tool == "ydotool_click":
            return self.input_controller.mouse_click(
                button=str(params.get("button", "left")),
                x=params.get("x"),
                y=params.get("y"),
            )
        if tool == "ydotool_type":
            return self.input_controller.type_text(str(params.get("text", "")))
        if tool == "ydotool_key":
            return self.input_controller.press_key(str(params.get("key", "")))
        if tool == "shell_exec":
            cmd = str(params.get("command", "")).strip()
            return self.shell_runner.run(cmd)

        return ActionResult(
            tool=tool or "unknown",
            success=False,
            output=f"Unsupported action tool '{tool}'.",
        )

    def process_prompt(
        self,
        user_prompt: str,
        capture_screen: bool = False,
        speak_reply: bool = False,
    ) -> AssistantTurn:
        self.kill_switch.reset_cancel_flag()
        self.set_state(AgentState.THINKING, f"Thinking ({self.client.model})...")

        self.storage.add_message(
            session_id=self.current_session_id,
            role="user",
            content=user_prompt,
            model=self.client.model,
        )

        screenshot_b64: Optional[str] = None
        if capture_screen or self.config.settings.get("attach_screen_context", False):
            screenshot_b64, _ = self.perception.capture_screen_base64()

        desktop_ctx = self.perception.get_desktop_context_summary()
        turn = self.client.chat(
            user_prompt=user_prompt,
            desktop_context=desktop_ctx,
            screenshot_b64=screenshot_b64,
        )
        turn.session_id = self.current_session_id

        if self.kill_switch.is_cancelled:
            self.set_state(AgentState.BLOCKED, "Interrupted by Kill-Switch")
            return turn

        if turn.response_type == "action" and turn.actions:
            self.set_state(AgentState.EXECUTING, f"Executing {len(turn.actions)} action(s)...")
            any_blocked = False
            for act in turn.actions:
                res = self.execute_action(act)
                turn.results.append(res)
                if res.blocked:
                    any_blocked = True
                    break

            if any_blocked or self.kill_switch.is_cancelled:
                self.set_state(AgentState.BLOCKED, "Action Blocked by Safety Guardrail")
            else:
                self.set_state(AgentState.IDLE, "Idle")
        else:
            self.set_state(AgentState.IDLE, "Idle")

        self.storage.add_message(
            session_id=self.current_session_id,
            role="assistant",
            content=turn.text,
            actions=turn.actions,
            results=turn.results,
            model=self.client.model,
        )

        if speak_reply and turn.text:
            self.voice.speak_tts(turn.text)

        return turn

    def capture_voice_turn(self, duration_sec: float = 4.0) -> Tuple[bool, str, Optional[AssistantTurn], str]:
        self.set_state(AgentState.LISTENING, "Listening (PipeWire Voice DSP)...")
        ok, transcript, info = self.voice.listen_and_recognize(duration_sec=duration_sec)
        if not ok or not transcript:
            self.set_state(AgentState.IDLE, "Idle")
            return False, "", None, info

        if transcript.lower() in ("kill switch", "emergency stop", "stop"):
            kill_msg = self.trigger_emergency_kill()
            return True, transcript, AssistantTurn(response_type="conversation", text=kill_msg), info

        turn = self.process_prompt(transcript, speak_reply=True)
        if self.ui_turn_callback:
            self.ui_turn_callback(f"🎙️ {transcript}", turn)
        return True, transcript, turn, info

    def start_ipc_server(self, port: int = IPC_PORT) -> Optional[http.server.HTTPServer]:
        engine_ref = self

        class IPCRequestHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

            def _send_json(self, status: int, data: Dict[str, Any]) -> None:
                raw = json.dumps(data).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:
                lic_ok, lic_msg = LicenseManager.verify_key(
                    str(engine_ref.config.settings.get("license_key", ""))
                )
                if self.path.startswith("/status"):
                    sessions = engine_ref.storage.list_sessions(limit=5)
                    self._send_json(
                        200,
                        {
                            "state": engine_ref.state.value,
                            "model": engine_ref.client.model,
                            "voice_loop_active": engine_ref.voice_loop_active,
                            "license_valid": lic_ok,
                            "license_status": lic_msg,
                            "current_session_id": engine_ref.current_session_id,
                            "recent_sessions": sessions,
                        },
                    )
                    return
                if self.path.startswith("/history"):
                    self._send_json(
                        200,
                        {
                            "sessions": engine_ref.storage.list_sessions(limit=20),
                            "messages": engine_ref.storage.get_session_messages(
                                engine_ref.current_session_id
                            ),
                        },
                    )
                    return
                self._send_json(404, {"error": "Unknown endpoint"})

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body_raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
                try:
                    payload = json.loads(body_raw) if body_raw else {}
                except Exception:
                    payload = {}

                if self.path == "/toggle":
                    if engine_ref.ui_toggle_callback:
                        engine_ref.ui_toggle_callback()
                    self._send_json(200, {"ok": True, "action": "toggled_hud"})
                    return

                if self.path == "/kill":
                    msg = engine_ref.trigger_emergency_kill()
                    self._send_json(200, {"ok": True, "message": msg})
                    return

                if self.path == "/voice":
                    threading.Thread(
                        target=engine_ref.capture_voice_turn,
                        kwargs={"duration_sec": float(payload.get("duration", 4.0))},
                        daemon=True,
                    ).start()
                    self._send_json(200, {"ok": True, "action": "voice_capture_started"})
                    return

                if self.path == "/prompt":
                    prompt_text = str(payload.get("prompt", "")).strip()
                    if not prompt_text:
                        self._send_json(400, {"ok": False, "error": "Empty prompt"})
                        return
                    turn = engine_ref.process_prompt(prompt_text)
                    self._send_json(
                        200,
                        {
                            "ok": True,
                            "type": turn.response_type,
                            "text": turn.text,
                            "results": [dataclasses.asdict(r) for r in turn.results],
                        },
                    )
                    return

                if self.path == "/activate":
                    key = str(payload.get("license_key", "")).strip()
                    ok, msg = LicenseManager.verify_key(key)
                    if ok:
                        engine_ref.config.settings["license_key"] = key
                        engine_ref.config.save_settings()
                    self._send_json(200, {"ok": ok, "message": msg})
                    return

                self._send_json(404, {"error": "Unknown POST endpoint"})

        try:
            server = http.server.HTTPServer(("127.0.0.1", port), IPCRequestHandler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            return server
        except Exception as exc:
            sys.stderr.write(f"[BajrangAI] Note: IPC server on 127.0.0.1:{port} already active or busy ({exc}).\n")
            return None


# ============================================================================
# 9. GNOME SHELL 45/46/47/48/49 EXTENSION BUILDER (`bajrang-ai@fedora.local`)
# ============================================================================

GNOME_EXTENSION_METADATA_JSON = {
    "name": "Bajrang AI Pro (Llama 3.2)",
    "description": "Local Llama 3.2 Desktop Assistant for Fedora GNOME with Voice Mode, Local Chat History, ydotool Automation, and Emergency Kill-Switch.",
    "uuid": EXTENSION_UUID,
    "shell-version": ["45", "46", "47", "48", "49"],
    "url": "https://bajrang.ai",
    "version": 3,
}

GNOME_EXTENSION_JS = """// Bajrang AI Pro — GNOME Shell 45-49 ESModule Top-Bar Extension
// Communicates with Bajrang AI Python Daemon via localhost IPC (127.0.0.1:17420) & CLI
// Reference: https://gjs.guide/extensions/upgrading/gnome-shell-45.html

import GObject from 'gi://GObject';
import St from 'gi://St';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const BajrangPanelIndicator = GObject.registerClass(
class BajrangPanelIndicator extends PanelMenu.Button {
    _init(extensionPath) {
        super._init(0.0, 'Bajrang AI Pro');
        this._extensionPath = extensionPath;

        const box = new St.BoxLayout({style_class: 'panel-status-menu-box bajrang-panel-box'});

        this._dot = new St.Widget({
            style_class: 'bajrang-dot bajrang-dot-idle',
            y_align: Clutter.ActorAlign.CENTER,
        });

        this._label = new St.Label({
            text: 'Bajrang AI',
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'bajrang-panel-label',
        });

        box.add_child(this._dot);
        box.add_child(this._label);
        this.add_child(box);

        this._buildMenu();
    }

    _runCommand(args) {
        try {
            Gio.Subprocess.new(args, Gio.SubprocessFlags.NONE);
        } catch (e) {
            logError(e, 'BajrangAI failed to spawn command');
        }
    }

    _postIPC(endpoint) {
        this._runCommand([
            'curl', '-s', '-X', 'POST', `http://127.0.0.1:17420${endpoint}`
        ]);
    }

    _buildMenu() {
        const headerItem = new PopupMenu.PopupMenuItem('⚡ Bajrang AI Pro • Llama 3.2 (Fedora)', {
            reactive: false,
            style_class: 'bajrang-menu-header',
        });
        this.menu.addMenuItem(headerItem);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        const toggleItem = new PopupMenu.PopupMenuItem('💬 Toggle Floating HUD (Super+Space)');
        toggleItem.connect('activate', () => {
            this._runCommand(['bash', '-lc', '$HOME/bajrang-ai/run.sh --toggle']);
        });
        this.menu.addMenuItem(toggleItem);

        const voiceItem = new PopupMenu.PopupMenuItem('🎙️ Start Voice Command Capture (PipeWire DSP)');
        voiceItem.connect('activate', () => {
            this._postIPC('/voice');
        });
        this.menu.addMenuItem(voiceItem);

        const historyItem = new PopupMenu.PopupMenuItem('🗂️ Open Local Chat History (~/.local/share/bajrang-ai)');
        historyItem.connect('activate', () => {
            this._runCommand(['bash', '-lc', 'xdg-open "$HOME/.local/share/bajrang-ai"']);
        });
        this.menu.addMenuItem(historyItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        const killItem = new PopupMenu.PopupMenuItem('🛑 EMERGENCY KILL-SWITCH (Ctrl+Escape)');
        killItem.connect('activate', () => {
            this._postIPC('/kill');
            this._runCommand(['bash', '-lc', '$HOME/bajrang-ai/run.sh --kill']);
        });
        this.menu.addMenuItem(killItem);
    }
});

export default class BajrangAIExtension extends Extension {
    enable() {
        this._indicator = new BajrangPanelIndicator(this.path);
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

GNOME_EXTENSION_CSS = """
.bajrang-panel-box {
    spacing: 6px;
    padding: 0 6px;
}
.bajrang-dot {
    width: 9px;
    height: 9px;
    border-radius: 99px;
}
.bajrang-dot-idle {
    background-color: #2ec27e;
    box-shadow: 0 0 6px rgba(46, 194, 126, 0.8);
}
.bajrang-panel-label {
    font-weight: 700;
    font-size: 12.5px;
}
.bajrang-menu-header {
    font-weight: 700;
}
"""


def install_gnome_extension(target_base_dir: Optional[Path] = None) -> Path:
    if target_base_dir is None:
        xdg_data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        ext_dir = Path(xdg_data) / "gnome-shell" / "extensions" / EXTENSION_UUID
    else:
        ext_dir = Path(target_base_dir) / EXTENSION_UUID

    ext_dir.mkdir(parents=True, exist_ok=True)
    (ext_dir / "metadata.json").write_text(
        json.dumps(GNOME_EXTENSION_METADATA_JSON, indent=2) + "\n", encoding="utf-8"
    )
    (ext_dir / "extension.js").write_text(GNOME_EXTENSION_JS, encoding="utf-8")
    (ext_dir / "stylesheet.css").write_text(GNOME_EXTENSION_CSS.strip() + "\n", encoding="utf-8")
    return ext_dir


# ============================================================================
# 10. GTK4 & LIBADWAITA FLOATING HUD WITH VOICE & CHAT HISTORY SIDEBAR
# ============================================================================

BAJRANG_HUD_CSS = """
window.bajrang-hud {
    background-color: rgba(20, 20, 26, 0.95);
    border-radius: 24px;
    border: 1px solid rgba(255, 255, 255, 0.09);
    color: #f6f5f4;
}

.bajrang-header {
    background: transparent;
    padding: 10px 16px 6px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.07);
}

.bajrang-sidebar {
    background-color: rgba(14, 14, 18, 0.85);
    border-right: 1px solid rgba(255, 255, 255, 0.07);
    padding: 10px;
}

.bajrang-title {
    font-weight: 700;
    font-size: 15px;
    letter-spacing: 0.3px;
}

.bajrang-subtitle {
    font-size: 11.5px;
    color: rgba(255, 255, 255, 0.62);
}

.pro-badge {
    background-color: rgba(245, 194, 17, 0.18);
    color: #f8e45c;
    border: 1px solid rgba(245, 194, 17, 0.45);
    border-radius: 999px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 700;
}

.status-dot {
    min-width: 12px;
    min-height: 12px;
    border-radius: 999px;
    margin-right: 6px;
}

.status-idle {
    background-color: #2ec27e;
    box-shadow: 0 0 8px rgba(46, 194, 126, 0.65);
}

.status-listening {
    background-color: #c061cb;
    box-shadow: 0 0 12px rgba(192, 97, 203, 0.90);
}

.status-thinking {
    background-color: #3584e4;
    box-shadow: 0 0 10px rgba(53, 132, 228, 0.80);
}

.status-executing {
    background-color: #ff7800;
    box-shadow: 0 0 10px rgba(255, 120, 0, 0.85);
}

.status-blocked {
    background-color: #e01b24;
    box-shadow: 0 0 12px rgba(224, 27, 36, 0.90);
}

.message-user {
    background-color: rgba(53, 132, 228, 0.22);
    border: 1px solid rgba(53, 132, 228, 0.38);
    border-radius: 16px;
    padding: 10px 14px;
    margin: 6px 4px;
}

.message-assistant {
    background-color: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 10px 14px;
    margin: 6px 4px;
}

.message-action-ok {
    background-color: rgba(46, 194, 126, 0.14);
    border: 1px solid rgba(46, 194, 126, 0.35);
    border-radius: 12px;
    padding: 8px 12px;
    margin: 4px 4px;
    font-family: monospace;
    font-size: 12px;
}

.message-action-blocked {
    background-color: rgba(224, 27, 36, 0.18);
    border: 1px solid rgba(224, 27, 36, 0.45);
    border-radius: 12px;
    padding: 8px 12px;
    margin: 4px 4px;
    font-family: monospace;
    font-size: 12px;
}

.bajrang-input-bar {
    padding: 10px 14px 14px 14px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.bajrang-entry {
    background-color: rgba(255, 255, 255, 0.07);
    border-radius: 999px;
    padding: 6px 14px;
    border: 1px solid rgba(255, 255, 255, 0.10);
}

.voice-button-active {
    background-color: rgba(192, 97, 203, 0.85);
    color: #ffffff;
    border-radius: 999px;
    font-weight: 700;
}

.kill-button {
    background-color: rgba(224, 27, 36, 0.85);
    color: #ffffff;
    border-radius: 999px;
    font-weight: 700;
    padding: 4px 12px;
}
"""


def run_gtk_app(engine: BajrangEngine, argv: List[str]) -> int:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

    class BajrangWindow(Adw.ApplicationWindow):
        def __init__(self, app: Adw.Application, bajrang_engine: BajrangEngine) -> None:
            super().__init__(application=app, title=APP_TITLE)
            self.engine = bajrang_engine
            self.engine.state_callback = self._on_engine_state_threadsafe
            self.engine.ui_toggle_callback = lambda: GLib.idle_add(self._idle_toggle)
            self.engine.ui_turn_callback = lambda p, t: GLib.idle_add(self._idle_render_voice_turn, p, t)
            self.capture_next_screen = False

            self.set_default_size(860, 560)
            self.set_decorated(False)
            self.add_css_class("bajrang-hud")

            try:
                gi.require_version("Gtk4LayerShell", "1.0")
                from gi.repository import Gtk4LayerShell
                Gtk4LayerShell.init_for_window(self)
                Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.TOP)
                Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.ON_DEMAND)
            except Exception:
                pass

            self._build_ui()
            self._setup_shortcuts()
            self._refresh_sessions_sidebar()
            self._load_active_session_into_view()

        def _idle_toggle(self) -> bool:
            self.toggle_visibility()
            return False

        def _idle_render_voice_turn(self, prompt_label: str, turn: AssistantTurn) -> bool:
            self._append_message(f"You: {prompt_label}", css_class="message-user")
            self._render_turn(turn)
            self._refresh_sessions_sidebar()
            return False

        def _build_ui(self) -> None:
            root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            self.set_content(root_box)

            win_handle = Gtk.WindowHandle()
            root_box.append(win_handle)

            header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            header_box.add_css_class("bajrang-header")
            win_handle.set_child(header_box)

            sidebar_btn = Gtk.Button.new_from_icon_name("sidebar-show-symbolic")
            sidebar_btn.set_tooltip_text("Toggle Local SQLite Chat History Sidebar")
            sidebar_btn.connect("clicked", self._on_toggle_sidebar)
            header_box.append(sidebar_btn)

            self.status_dot = Gtk.Box()
            self.status_dot.add_css_class("status-dot")
            self.status_dot.add_css_class("status-idle")
            self.status_dot.set_valign(Gtk.Align.CENTER)
            header_box.append(self.status_dot)

            title_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            title_col.set_hexpand(True)
            title_lbl = Gtk.Label(label="Bajrang AI Pro", xalign=0.0)
            title_lbl.add_css_class("bajrang-title")
            self.status_lbl = Gtk.Label(label=f"Idle • {self.engine.client.model}", xalign=0.0)
            self.status_lbl.add_css_class("bajrang-subtitle")
            title_col.append(title_lbl)
            title_col.append(self.status_lbl)
            header_box.append(title_col)

            lic_ok, _ = LicenseManager.verify_key(str(self.engine.config.settings.get("license_key", "")))
            pro_lbl = Gtk.Label(label="PRO ₹100/mo" if lic_ok else "UNLICENSED")
            pro_lbl.add_css_class("pro-badge")
            pro_lbl.set_valign(Gtk.Align.CENTER)
            header_box.append(pro_lbl)

            models = list(
                dict.fromkeys(
                    [self.engine.client.model]
                    + self.engine.config.settings.get("fallback_models", ["llama3.2"])
                )
            )
            self.model_list = Gtk.StringList.new(models)
            self.model_dropdown = Gtk.DropDown(model=self.model_list)
            self.model_dropdown.set_valign(Gtk.Align.CENTER)
            self.model_dropdown.connect("notify::selected", self._on_model_changed)
            header_box.append(self.model_dropdown)

            kill_btn = Gtk.Button(label="KILL")
            kill_btn.add_css_class("kill-button")
            kill_btn.set_valign(Gtk.Align.CENTER)
            kill_btn.set_tooltip_text("Emergency Kill-Switch (Ctrl+Escape)")
            kill_btn.connect("clicked", lambda *_: self._trigger_kill_switch())
            header_box.append(kill_btn)

            hide_btn = Gtk.Button.new_from_icon_name("window-minimize-symbolic")
            hide_btn.set_valign(Gtk.Align.CENTER)
            hide_btn.connect("clicked", lambda *_: self.set_visible(False))
            header_box.append(hide_btn)

            body_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            body_box.set_vexpand(True)
            root_box.append(body_box)

            self.sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            self.sidebar_box.set_size_request(230, -1)
            self.sidebar_box.add_css_class("bajrang-sidebar")
            body_box.append(self.sidebar_box)

            new_chat_btn = Gtk.Button(label="+ New Chat Session")
            new_chat_btn.add_css_class("suggested-action")
            new_chat_btn.connect("clicked", self._on_new_session)
            self.sidebar_box.append(new_chat_btn)

            self.search_entry = Gtk.SearchEntry()
            self.search_entry.set_placeholder_text("Search local history...")
            self.search_entry.connect("search-changed", self._on_history_search)
            self.sidebar_box.append(self.search_entry)

            sidebar_scroll = Gtk.ScrolledWindow()
            sidebar_scroll.set_vexpand(True)
            sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            self.sidebar_box.append(sidebar_scroll)

            self.session_listbox = Gtk.ListBox()
            self.session_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
            self.session_listbox.connect("row-activated", self._on_session_row_activated)
            sidebar_scroll.set_child(self.session_listbox)

            right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            right_col.set_hexpand(True)
            body_box.append(right_col)

            self.scrolled = Gtk.ScrolledWindow()
            self.scrolled.set_vexpand(True)
            self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            right_col.append(self.scrolled)

            clamp = Adw.Clamp(maximum_size=620, tightening_threshold=460)
            self.scrolled.set_child(clamp)

            self.chat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            self.chat_box.set_margin_top(12)
            self.chat_box.set_margin_bottom(12)
            self.chat_box.set_margin_start(14)
            self.chat_box.set_margin_end(14)
            clamp.set_child(self.chat_box)

            input_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            input_bar.add_css_class("bajrang-input-bar")
            right_col.append(input_bar)

            self.voice_btn = Gtk.Button.new_from_icon_name("audio-input-microphone-symbolic")
            self.voice_btn.set_tooltip_text("Speak to Bajrang AI (PipeWire Custom Voice Recognizer • Super+V)")
            self.voice_btn.connect("clicked", self._on_voice_button_clicked)
            input_bar.append(self.voice_btn)

            self.screen_btn = Gtk.ToggleButton()
            self.screen_btn.set_icon_name("camera-photo-symbolic")
            self.screen_btn.set_tooltip_text("Attach Wayland screenshot to next prompt")
            self.screen_btn.connect("toggled", self._on_screen_toggle)
            input_bar.append(self.screen_btn)

            self.entry = Gtk.Entry()
            self.entry.set_hexpand(True)
            self.entry.set_placeholder_text("Ask Llama 3.2, click 🎙️ to speak, or command an action...")
            self.entry.add_css_class("bajrang-entry")
            self.entry.connect("activate", self._on_prompt_submit)
            input_bar.append(self.entry)

            send_btn = Gtk.Button.new_from_icon_name("mail-send-symbolic")
            send_btn.add_css_class("suggested-action")
            send_btn.connect("clicked", self._on_prompt_submit)
            input_bar.append(send_btn)

        def _setup_shortcuts(self) -> None:
            controller = Gtk.EventControllerKey()
            controller.connect("key-pressed", self._on_key_pressed)
            self.add_controller(controller)

        def _on_key_pressed(
            self,
            _controller: Gtk.EventControllerKey,
            keyval: int,
            _keycode: int,
            state: Gdk.ModifierType,
        ) -> bool:
            if keyval == Gdk.KEY_Escape and (state & Gdk.ModifierType.CONTROL_MASK):
                self._trigger_kill_switch()
                return True
            if keyval == Gdk.KEY_v and (state & Gdk.ModifierType.SUPER_MASK):
                self._on_voice_button_clicked()
                return True
            if keyval == Gdk.KEY_Escape:
                self.set_visible(False)
                return True
            return False

        def _on_toggle_sidebar(self, _btn: Gtk.Button) -> None:
            self.sidebar_box.set_visible(not self.sidebar_box.get_visible())

        def _refresh_sessions_sidebar(self) -> None:
            child = self.session_listbox.get_first_child()
            while child is not None:
                nxt = child.get_next_sibling()
                self.session_listbox.remove(child)
                child = nxt

            for sess in self.engine.storage.list_sessions(limit=40):
                row = Gtk.ListBoxRow()
                row.session_id = sess["session_id"]  # type: ignore
                lbl = Gtk.Label(
                    label=f"💬 {sess['title']} ({sess['message_count']})",
                    xalign=0.0,
                )
                lbl.set_ellipsize(Pango.EllipsizeMode.END)
                lbl.set_margin_top(6)
                lbl.set_margin_bottom(6)
                lbl.set_margin_start(8)
                lbl.set_margin_end(8)
                row.set_child(lbl)
                self.session_listbox.append(row)

        def _on_new_session(self, _btn: Gtk.Button) -> None:
            self.engine.new_session("New Conversation")
            self._refresh_sessions_sidebar()
            self._load_active_session_into_view()

        def _on_session_row_activated(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
            sess_id = getattr(row, "session_id", None)
            if sess_id:
                self.engine.switch_session(sess_id)
                self._load_active_session_into_view()

        def _on_history_search(self, entry: Gtk.SearchEntry) -> None:
            q = entry.get_text().strip()
            if not q:
                self._refresh_sessions_sidebar()
                return
            hits = self.engine.storage.search_messages(q, limit=15)
            child = self.session_listbox.get_first_child()
            while child is not None:
                nxt = child.get_next_sibling()
                self.session_listbox.remove(child)
                child = nxt
            for hit in hits:
                row = Gtk.ListBoxRow()
                row.session_id = hit["session_id"]  # type: ignore
                lbl = Gtk.Label(label=f"🔎 {hit['title']}: {hit['content'][:32]}", xalign=0.0)
                lbl.set_ellipsize(Pango.EllipsizeMode.END)
                lbl.set_margin_top(6)
                lbl.set_margin_bottom(6)
                row.set_child(lbl)
                self.session_listbox.append(row)

        def _load_active_session_into_view(self) -> None:
            child = self.chat_box.get_first_child()
            while child is not None:
                nxt = child.get_next_sibling()
                self.chat_box.remove(child)
                child = nxt

            msgs = self.engine.storage.get_session_messages(self.engine.current_session_id)
            if not msgs:
                ok_ollama, _, ollama_msg = self.engine.client.check_health()
                ok_ydo, ydo_msg = self.engine.input_controller.check_daemon()
                lic_ok, lic_msg = LicenseManager.verify_key(
                    str(self.engine.config.settings.get("license_key", ""))
                )
                diag = (
                    f"**Bajrang AI Pro ({APP_VERSION})** ready on Fedora GNOME/Wayland.\n"
                    f"• **Intelligence (`{self.engine.client.model}`)**: {ollama_msg}\n"
                    f"• **Voice Mode**: Custom PipeWire Spectral-DTW + Whisper Recognizer ready (`Super+V` or 🎙️)\n"
                    f"• **Local Chat Storage**: SQLite3 active (`{self.engine.storage.db_path}`)\n"
                    f"• **Input Automation**: {ydo_msg}\n"
                    f"• **Subscription**: {lic_msg}"
                )
                self._append_message(diag, css_class="message-assistant")
                return

            for m in msgs:
                if m["role"] == "user":
                    self._append_message(f"You: {m['content']}", css_class="message-user")
                else:
                    self._append_message(m["content"], css_class="message-assistant")
                    for res in m.get("results", []):
                        blocked = res.get("blocked", False)
                        success = res.get("success", False)
                        badge = "🛑 BLOCKED" if blocked else ("✅ OK" if success else "⚠️ ERROR")
                        css = "message-action-blocked" if (blocked or not success) else "message-action-ok"
                        self._append_message(
                            f"[{badge} • {res.get('tool', 'action')}] {res.get('output', '')}",
                            css_class=css,
                        )

        def _on_voice_button_clicked(self, *_args: Any) -> None:
            self.voice_btn.add_css_class("voice-button-active")

            def worker() -> None:
                ok, transcript, turn, info = self.engine.capture_voice_turn(
                    duration_sec=float(self.engine.config.settings.get("voice_record_seconds", 4.0))
                )
                GLib.idle_add(self._on_voice_finished, ok, transcript, turn, info)

            threading.Thread(target=worker, daemon=True).start()

        def _on_voice_finished(
            self,
            ok: bool,
            transcript: str,
            turn: Optional[AssistantTurn],
            info: str,
        ) -> bool:
            self.voice_btn.remove_css_class("voice-button-active")
            if not ok:
                self._append_message(f"🎙️ Voice Mode: {info}", css_class="message-assistant")
            return False

        def _on_model_changed(self, dropdown: Gtk.DropDown, _pspec: Any) -> None:
            item = dropdown.get_selected_item()
            if item is not None:
                model_name = item.get_string()
                self.engine.client.model = model_name
                self.status_lbl.set_text(f"Idle • {model_name}")

        def _on_screen_toggle(self, btn: Gtk.ToggleButton) -> None:
            self.capture_next_screen = btn.get_active()

        def _trigger_kill_switch(self) -> None:
            msg = self.engine.trigger_emergency_kill()
            self._append_message(f"🛑 {msg}", css_class="message-action-blocked")

        def _on_engine_state_threadsafe(self, state: AgentState, status_text: str) -> None:
            GLib.idle_add(self._update_status_indicator, state, status_text)

        def _update_status_indicator(self, state: AgentState, status_text: str) -> bool:
            for cls in (
                "status-idle",
                "status-listening",
                "status-thinking",
                "status-executing",
                "status-blocked",
            ):
                self.status_dot.remove_css_class(cls)

            state_map = {
                AgentState.IDLE: ("status-idle", f"Idle • {self.engine.client.model}"),
                AgentState.LISTENING: ("status-listening", status_text or "Listening (Voice DSP)..."),
                AgentState.THINKING: ("status-thinking", status_text or "Thinking..."),
                AgentState.EXECUTING: ("status-executing", status_text or "Executing..."),
                AgentState.BLOCKED: ("status-blocked", status_text or "Blocked / Killed"),
            }
            dot_cls, label_text = state_map.get(state, ("status-idle", "Idle"))
            self.status_dot.add_css_class(dot_cls)
            self.status_lbl.set_text(label_text)
            return False

        def _append_message(self, text: str, css_class: str = "message-assistant") -> None:
            lbl = Gtk.Label(label=text, xalign=0.0)
            lbl.set_wrap(True)
            lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            lbl.set_selectable(True)
            lbl.add_css_class(css_class)
            self.chat_box.append(lbl)
            GLib.idle_add(self._scroll_to_bottom)

        def _scroll_to_bottom(self) -> bool:
            vadj = self.scrolled.get_vadjustment()
            if vadj is not None:
                vadj.set_value(vadj.get_upper() - vadj.get_page_size())
            return False

        def _on_prompt_submit(self, *_args: Any) -> None:
            prompt = self.entry.get_text().strip()
            if not prompt:
                return
            self.entry.set_text("")
            capture = self.capture_next_screen
            if self.screen_btn.get_active():
                self.screen_btn.set_active(False)

            self._append_message(f"You: {prompt}", css_class="message-user")

            def worker() -> None:
                turn = self.engine.process_prompt(prompt, capture_screen=capture)
                GLib.idle_add(self._render_turn, turn)
                GLib.idle_add(self._refresh_sessions_sidebar)

            threading.Thread(target=worker, daemon=True).start()

        def _render_turn(self, turn: AssistantTurn) -> bool:
            if turn.text:
                self._append_message(turn.text, css_class="message-assistant")
            for res in turn.results:
                badge = "🛑 BLOCKED" if res.blocked else ("✅ OK" if res.success else "⚠️ ERROR")
                css = "message-action-blocked" if (res.blocked or not res.success) else "message-action-ok"
                self._append_message(f"[{badge} • {res.tool}] {res.output}", css_class=css)
            return False

        def toggle_visibility(self) -> None:
            if self.get_visible():
                self.set_visible(False)
            else:
                self.set_visible(True)
                self.present()
                self.entry.grab_focus()

    class BajrangApplication(Adw.Application):
        def __init__(self, bajrang_engine: BajrangEngine) -> None:
            super().__init__(
                application_id=APP_ID,
                flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
            )
            self.engine = bajrang_engine
            self.main_window: Optional[BajrangWindow] = None

        def do_startup(self) -> None:
            Adw.Application.do_startup(self)
            style_mgr = Adw.StyleManager.get_default()
            style_mgr.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

            css_provider = Gtk.CssProvider()
            css_provider.load_from_data(BAJRANG_HUD_CSS.encode("utf-8"))
            display = Gdk.Display.get_default()
            if display is not None:
                Gtk.StyleContext.add_provider_for_display(
                    display,
                    css_provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
                )
            self.engine.start_ipc_server()

        def do_activate(self) -> None:
            if self.main_window is None:
                self.main_window = BajrangWindow(self, self.engine)
            self.main_window.present()
            self.main_window.entry.grab_focus()

        def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
            args = command_line.get_arguments()[1:]
            if "--kill" in args:
                if self.main_window is not None:
                    self.main_window._trigger_kill_switch()
                else:
                    self.engine.trigger_emergency_kill()
                return 0

            if "--voice" in args:
                if self.main_window is None:
                    self.activate()
                if self.main_window is not None:
                    self.main_window._on_voice_button_clicked()
                return 0

            if "--toggle" in args and self.main_window is not None:
                self.main_window.toggle_visibility()
                return 0

            self.activate()
            return 0

    app = BajrangApplication(engine)
    return int(app.run(argv))


# ============================================================================
# 11. PROJECT SCAFFOLD EXPORTER (`--export-project ./bajrang-ai`)
# ============================================================================

def export_modular_project(target_dir: Path) -> None:
    target_dir = target_dir.resolve()
    (target_dir / "config").mkdir(parents=True, exist_ok=True)
    (target_dir / "src" / "ui").mkdir(parents=True, exist_ok=True)
    (target_dir / "src" / "perception").mkdir(parents=True, exist_ok=True)
    (target_dir / "src" / "intelligence").mkdir(parents=True, exist_ok=True)
    (target_dir / "src" / "execution").mkdir(parents=True, exist_ok=True)
    (target_dir / "src" / "voice").mkdir(parents=True, exist_ok=True)
    (target_dir / "src" / "storage").mkdir(parents=True, exist_ok=True)
    (target_dir / "gnome-extension").mkdir(parents=True, exist_ok=True)

    (target_dir / "config" / "settings.json").write_text(
        json.dumps(DEFAULT_SETTINGS, indent=2) + "\n", encoding="utf-8"
    )
    (target_dir / "config" / "blocklist.json").write_text(
        json.dumps(DEFAULT_BLOCKLIST, indent=2) + "\n", encoding="utf-8"
    )

    this_file = Path(__file__).resolve()
    shutil.copy2(this_file, target_dir / "src" / "core.py")

    (target_dir / "src" / "__init__.py").write_text("", encoding="utf-8")
    (target_dir / "src" / "main.py").write_text(
        "#!/usr/bin/env python3\nfrom src.core import main\nif __name__ == '__main__':\n    raise SystemExit(main())\n",
        encoding="utf-8",
    )
    (target_dir / "src" / "ui" / "__init__.py").write_text("", encoding="utf-8")
    (target_dir / "src" / "ui" / "style.css").write_text(BAJRANG_HUD_CSS.strip() + "\n", encoding="utf-8")
    (target_dir / "src" / "ui" / "window.py").write_text(
        "from src.core import run_gtk_app, BAJRANG_HUD_CSS\n", encoding="utf-8"
    )
    (target_dir / "src" / "voice" / "__init__.py").write_text("", encoding="utf-8")
    (target_dir / "src" / "voice" / "recognizer.py").write_text(
        "from src.core import CustomVoiceRecognizer\n", encoding="utf-8"
    )
    (target_dir / "src" / "storage" / "__init__.py").write_text("", encoding="utf-8")
    (target_dir / "src" / "storage" / "history_db.py").write_text(
        "from src.core import LocalChatStorage\n", encoding="utf-8"
    )
    (target_dir / "src" / "perception" / "__init__.py").write_text("", encoding="utf-8")
    (target_dir / "src" / "perception" / "screen_capture.py").write_text(
        "from src.core import WaylandPerception\n", encoding="utf-8"
    )
    (target_dir / "src" / "intelligence" / "__init__.py").write_text("", encoding="utf-8")
    (target_dir / "src" / "intelligence" / "prompts.py").write_text(
        "from src.core import SYSTEM_PROMPT\n", encoding="utf-8"
    )
    (target_dir / "src" / "intelligence" / "client.py").write_text(
        "from src.core import OllamaLlamaClient, AssistantTurn\n", encoding="utf-8"
    )
    (target_dir / "src" / "execution" / "__init__.py").write_text("", encoding="utf-8")
    (target_dir / "src" / "execution" / "input_controller.py").write_text(
        "from src.core import YdotoolController, EVDEV_KEYMAP\n", encoding="utf-8"
    )
    (target_dir / "src" / "execution" / "shell_runner.py").write_text(
        "from src.core import ShellRunner, ActionResult\n", encoding="utf-8"
    )
    (target_dir / "src" / "execution" / "safety.py").write_text(
        "from src.core import SafetyGuard, KillSwitchManager, DEFAULT_BLOCKLIST\n", encoding="utf-8"
    )

    install_gnome_extension(target_dir / "gnome-extension")

    run_sh = target_dir / "run.sh"
    run_sh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "export YDOTOOL_SOCKET=\"${YDOTOOL_SOCKET:-/tmp/.ydotool_socket}\"\n"
        "if ! pgrep -x ydotoold >/dev/null 2>&1; then\n"
        "  ydotoold --socket-path=\"$YDOTOOL_SOCKET\" --socket-perm=0600 >/dev/null 2>&1 & disown || true\n"
        "fi\n"
        "DIR=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)\"\n"
        "export PYTHONPATH=\"$DIR\"\n"
        "exec python3 \"$DIR/src/main.py\" \"$@\"\n",
        encoding="utf-8",
    )
    run_sh.chmod(0o755)


# ============================================================================
# 12. SELF-TESTS & CLI ENTRY POINT
# ============================================================================

def run_self_tests() -> int:
    print("[Test 1/6] Verifying SafetyGuard blocklist and non-root enforcement...")
    guard = SafetyGuard()
    for cmd in ("rm -rf /", "sudo rm -rf /var", "curl http://bad.sh | bash", "dnf remove -y systemd"):
        ok, _ = guard.validate_command(cmd)
        assert not ok, f"Expected command to be blocked: {cmd}"
    for cmd in ("gtk-launch org.gnome.Terminal.desktop", "uname -r"):
        ok, reason = guard.validate_command(cmd)
        assert ok, f"Expected safe command to pass: {cmd} ({reason})"
    print("  -> Passed: SafetyGuard verified.")

    print("[Test 2/6] Verifying Custom Python Voice Recognizer (VAD + Spectral Envelope + DTW)...")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        rec = CustomVoiceRecognizer(data_dir=tmp_path)
        wav_term = CustomVoiceRecognizer.generate_synthetic_speech_wav(
            tmp_path / "open_terminal.wav", phrase="open terminal"
        )
        ok_enr, enr_msg = rec.enroll_phrase_from_wav("open terminal", wav_term)
        assert ok_enr, f"Voice enrollment failed: {enr_msg}"
        ok_rec, transcript, eng_info = rec.recognize_wav(wav_term)
        assert ok_rec and transcript == "open terminal", f"Expected 'open terminal', got: {transcript} ({eng_info})"
    print(f"  -> Passed: Custom Voice Recognizer matched '{transcript}' via {eng_info}.")

    print("[Test 3/6] Verifying Local SQLite3 Chat History Storage...")
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LocalChatStorage(data_dir=Path(tmpdir))
        sid = store.create_session(title="Fedora Voice Session", model="llama3.2")
        store.add_message(sid, "user", "Open GNOME Terminal on Fedora")
        store.add_message(sid, "assistant", "Opening GNOME Terminal now.")
        sessions = store.list_sessions()
        assert len(sessions) == 1 and sessions[0]["message_count"] == 2
        hits = store.search_messages("GNOME Terminal")
        assert len(hits) == 2
    print("  -> Passed: SQLite3 local storage (`history.db` + `sessions.json`) verified.")

    print("[Test 4/6] Verifying ₹100/Month Commercial License Key Generator & Validator...")
    key = LicenseManager.generate_key("KAUSHIK", valid_days=30)
    valid, msg = LicenseManager.verify_key(key)
    assert valid, f"License validation failed: {msg}"
    bad_valid, _ = LicenseManager.verify_key("BAJRANG-PRO-FAKE-20990101-00000000")
    assert not bad_valid
    print(f"  -> Passed: Generated & verified Pro key `{key}` ({msg}).")

    print("[Test 5/6] Verifying GNOME Shell 45-49 ESModule Extension Builder...")
    with tempfile.TemporaryDirectory() as tmpdir:
        ext_dir = install_gnome_extension(Path(tmpdir))
        assert (ext_dir / "metadata.json").is_file()
        assert (ext_dir / "extension.js").is_file()
        assert (ext_dir / "stylesheet.css").is_file()
    print("  -> Passed: GNOME Shell Extension (`bajrang-ai@fedora.local`) generated cleanly.")

    print("[Test 6/6] Verifying modular project exporter...")
    with tempfile.TemporaryDirectory() as tmpdir:
        export_modular_project(Path(tmpdir) / "bajrang-ai")
        assert (Path(tmpdir) / "bajrang-ai" / "gnome-extension" / EXTENSION_UUID / "extension.js").is_file()
    print("  -> Passed: Full modular project + GNOME extension exported.")
    print("\nAll 6/6 Bajrang AI Pro (Fedora + Llama 3.2 + Voice DSP + SQLite + GNOME Extension) tests passed!")
    return 0


def run_headless_cli(engine: BajrangEngine, single_prompt: Optional[str] = None) -> int:
    ok_ollama, _, ollama_msg = engine.client.check_health()
    ok_ydo, ydo_msg = engine.input_controller.check_daemon()
    lic_ok, lic_msg = LicenseManager.verify_key(str(engine.config.settings.get("license_key", "")))
    engine.start_ipc_server()

    print(f"=== {APP_TITLE} ({APP_VERSION}) — Terminal & Daemon Mode ===")
    print(f"• Model        : {engine.client.model} ({ollama_msg})")
    print(f"• Voice Engine : Custom PipeWire Spectral-DTW + Whisper Recognizer Ready")
    print(f"• Chat Storage : {engine.storage.db_path} ({len(engine.storage.list_sessions())} sessions)")
    print(f"• ydotool      : {ydo_msg}")
    print(f"• License      : {lic_msg}")
    print("• Commands     : '/voice' (Speak), '/history' (List chats), '/new' (New chat), '/kill' (Stop), '/quit'\n")

    if single_prompt:
        turn = engine.process_prompt(single_prompt)
        print(f"\n[Bajrang AI]: {turn.text}")
        for r in turn.results:
            print(f"  -> [{r.tool}] {'BLOCKED' if r.blocked else ('OK' if r.success else 'ERR')}: {r.output}")
        return 0

    while True:
        try:
            prompt = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting Bajrang AI Pro.")
            break
        if not prompt:
            continue
        if prompt.lower() in ("/quit", "/exit", "exit", "quit"):
            break
        if prompt.lower() == "/kill":
            print(engine.trigger_emergency_kill())
            continue
        if prompt.lower() == "/new":
            sid = engine.new_session("CLI Session")
            print(f"Started new session: {sid}")
            continue
        if prompt.lower() == "/history":
            for s in engine.storage.list_sessions(limit=10):
                print(f"  - [{s['session_id']}] {s['title']} ({s['message_count']} msgs, updated {s['updated_at']})")
            continue
        if prompt.lower() == "/voice":
            ok, transcript, turn, info = engine.capture_voice_turn()
            print(f"  [Voice Info]: {info}")
            if ok and turn:
                print(f"  [You (Voice)]: {transcript}")
                print(f"  [Bajrang AI]: {turn.text}")
            continue

        turn = engine.process_prompt(prompt)
        print(f"\nBajrang AI ({engine.client.model}) > {turn.text}")
        for r in turn.results:
            status = "BLOCKED" if r.blocked else ("OK" if r.success else "ERROR")
            print(f"  [{status} • {r.tool}] {r.output}")
        print()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bajrang AI Pro — Fedora GNOME/Wayland Local Assistant (Llama 3.2 + Voice Mode + SQLite + GNOME Extension)"
    )
    parser.add_argument("--model", default=None, help="Ollama model name (default: llama3.2)")
    parser.add_argument("--host", default=None, help="Ollama host URL (default: http://localhost:11434)")
    parser.add_argument("--toggle", action="store_true", help="Toggle floating HUD visibility")
    parser.add_argument("--voice", action="store_true", help="Trigger immediate Voice Mode capture")
    parser.add_argument("--kill", action="store_true", help="Trigger instant Emergency Kill-Switch")
    parser.add_argument("--headless", action="store_true", help="Run in interactive terminal/daemon mode")
    parser.add_argument("--prompt", default=None, help="Run a single prompt and print the response")
    parser.add_argument("--enroll-voice", metavar="PHRASE", default=None, help="Record 3s microphone sample to enroll a custom voice command")
    parser.add_argument("--install-gnome-extension", action="store_true", help="Install the GNOME Shell 45-49 extension (`bajrang-ai@fedora.local`)")
    parser.add_argument("--generate-license", metavar="SUBSCRIBER", default=None, help="Generate a ₹100/month Bajrang AI Pro license key")
    parser.add_argument("--activate-license", metavar="KEY", default=None, help="Activate a Bajrang AI Pro license key")
    parser.add_argument("--export-project", metavar="DIR", default=None, help="Export full modular project + GNOME extension to DIR")
    parser.add_argument("--self-test", action="store_true", help="Run offline unit, voice DSP, SQLite, and safety verification tests")

    args, unknown = parser.parse_known_args(argv)

    if args.self_test:
        return run_self_tests()

    if args.generate_license:
        key = LicenseManager.generate_key(args.generate_license, valid_days=30)
        print(f"Generated ₹100/month Bajrang AI Pro License Key:\n  {key}")
        return 0

    cfg = ConfigManager()
    cfg.save_defaults()

    if args.activate_license:
        ok, msg = LicenseManager.verify_key(args.activate_license)
        print(msg)
        if ok:
            cfg.settings["license_key"] = args.activate_license.strip().upper()
            cfg.save_settings()
            return 0
        return 1

    if args.install_gnome_extension:
        ext_path = install_gnome_extension()
        print(f"Installed GNOME Shell Extension to: {ext_path}")
        print(f"Enable it on Fedora with: gnome-extensions enable {EXTENSION_UUID}")
        return 0

    if args.export_project:
        out_dir = Path(args.export_project)
        export_modular_project(out_dir)
        print(f"Exported full modular Bajrang AI Pro project to: {out_dir.resolve()}")
        return 0

    if args.enroll_voice:
        rec = CustomVoiceRecognizer(data_dir=cfg.data_dir)
        print(f"Speak '{args.enroll_voice}' clearly into your microphone for 3 seconds...")
        wav_path, cap_msg = rec.record_microphone_wav(duration_sec=3.0)
        if not wav_path:
            print(cap_msg)
            return 1
        ok, msg = rec.enroll_phrase_from_wav(args.enroll_voice, wav_path)
        wav_path.unlink(missing_ok=True)
        print(msg)
        return 0 if ok else 1

    if args.model:
        cfg.settings["model"] = args.model
    if args.host:
        cfg.settings["ollama_host"] = args.host

    engine = BajrangEngine(config=cfg)

    if args.kill and (args.headless or not os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY")):
        print(engine.trigger_emergency_kill())
        return 0

    if args.voice and (args.headless or not os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY")):
        ok, transcript, turn, info = engine.capture_voice_turn()
        print(f"[{info}] Transcript: {transcript}")
        if turn:
            print(f"[Bajrang AI]: {turn.text}")
        return 0

    if args.headless or args.prompt or (not os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY")):
        return run_headless_cli(engine, single_prompt=args.prompt)

    gtk_argv = [sys.argv[0]]
    if args.toggle:
        gtk_argv.append("--toggle")
    if args.voice:
        gtk_argv.append("--voice")
    if args.kill:
        gtk_argv.append("--kill")
    gtk_argv.extend(unknown)
    return run_gtk_app(engine, gtk_argv)


if __name__ == "__main__":
    raise SystemExit(main())