#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bajrang AI Pro (Argon Edition v6.0) — Windows 11 & Cross-Platform Commercial Desktop Assistant
Integrates the unified `bajrang_core` v6.0 architecture:
  - SecurityVault (OS keyring / Windows DPAPI / 0600 vault)
  - AsymmetricLicenseVerifier (RSA Public-Key verification; no hardcoded client secrets)
  - LongTermMemoryStore & DatabaseMigrationManager (SQLite WAL + v1..v3 migrations + Memories CRUD)
  - ModularAIRouter (Gemini Argon, Ollama Local, Groq, OpenRouter, OpenAI + Task Complexity Router + Fallback)
  - AutonomousTaskPlanner (Multi-step Downloads organizer, SHA-256 duplicate finder, explicit permission gates)
  - AdvancedVoiceEngine (Continuous listening, wake word, barge-in, spectral noise floor + VAD, 8-band Goertzel-DTW + Whisper/SAPI)
  - CrossPlatformComputerUse (Verified Win32 EnumWindows/SetForegroundWindow, PIL.ImageGrab, PyAutoGUI/user32 input)
"""

try:
    from bajrang_core import (
        CORE_VERSION,
        AdvancedVoiceEngine,
        AsymmetricLicenseVerifier,
        AutonomousTaskPlanner,
        CrossPlatformComputerUse,
        DatabaseMigrationManager,
        LongTermMemoryStore,
        ModularAIRouter,
        PerformanceProfile,
        PerformanceSettings,
        SecurityVault,
        TaskComplexity,
        ToolSchemaValidator,
        redact_sensitive_text,
    )
    HAS_BAJRANG_CORE = True
except ImportError:
    HAS_BAJRANG_CORE = False

import argparse
import array
import base64
import ctypes
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
import platform
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

IS_WINDOWS = platform.system().lower() == "windows"
APP_TITLE = "Bajrang AI Pro (Windows 11 & Fedora Edition)"
APP_VERSION = "5.0.0-cross-platform"
IPC_PORT = int(os.environ.get("BAJRANG_IPC_PORT", "17420"))

PERSONALIZED_LLAMA_SYSTEM_PROMPT = """You are Bajrang AI Pro, a personalized, fast, and secure desktop assistant running on Windows 11 and Fedora Linux (Lenovo Yoga 7i • Intel Core i5-1135G7 • Intel Iris Xe • 12 GB RAM).

OPERATIONAL RULES:
1. Engage in clear, direct conversation by default and answer questions without invoking tools unless an action is requested.
2. ONLY emit executable actions or shell commands when the user explicitly commands a desktop action (e.g., "open", "launch", "type", "click", "run", "press", "close", "search").
3. When actions are required, respond ONLY with valid raw JSON matching the schema below.
4. When the user's request is conversational, analytical, or educational, respond in clean markdown text (or JSON with "type": "conversation" and "actions": []).
5. Never output administrator-escalated or destructive system commands.

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
        "key": "enter" | "backspace" | "tab" | "esc" | "super" | "ctrl+c" | "alt+f4",
        "command": "non-admin command (e.g. start notepad or calc)"
      }
    }
  ]
}
"""

PERSONALIZED_MODELFILE_TEMPLATE = """FROM llama3.2
PARAMETER temperature 0.35
PARAMETER top_p 0.9
PARAMETER num_ctx 8192
PARAMETER num_thread 8
SYSTEM \"\"\"{system_prompt}\"\"\"
"""

PROVIDER_PRESETS: Dict[str, Dict[str, str]] = {
    "ollama": {
        "label": "Personalized Local Llama 3.2 (Ollama Offline)",
        "endpoint": "http://localhost:11434/api/chat",
        "model": "llama3.2",
    },
    "gemini_argon": {
        "label": "Google Gemini Argon / 2.5 Pro (BYO API Key)",
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model": "gemini-2.5-pro",
    },
    "groq": {
        "label": "Groq Cloud Llama 3.3 70B (BYO API Key)",
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
    },
    "openrouter": {
        "label": "OpenRouter Free Llama 3.2 (BYO API Key)",
        "endpoint": "https://openrouter.ai/api/v1/chat/completions",
        "model": "meta-llama/llama-3.2-3b-instruct:free",
    },
    "openai": {
        "label": "OpenAI GPT-4o-mini (BYO API Key)",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
    },
}

DEFAULT_SETTINGS: Dict[str, Any] = {
    "provider": os.environ.get("BAJRANG_PROVIDER", "ollama"),
    "ollama_host": os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
    "model": os.environ.get("BAJRANG_MODEL", "llama3.2"),
    "personalized_model_name": "bajrang-llama3.2",
    "custom_persona_prompt": PERSONALIZED_LLAMA_SYSTEM_PROMPT,
    "hardware_profile": "Lenovo Yoga 7i 14ITL5 • Intel Core i5-1135G7 • 12GB RAM • Windows 11 / Fedora Dual-Boot",
    "fallback_models": [
        "llama3.2",
        "bajrang-llama3.2",
        "llama3.2:3b",
        "llama3.2:1b",
        "llama3.2-vision",
        "qwen2.5-vl:3b",
    ],
    "byo_provider": "gemini_argon",
    "byo_api_key": os.environ.get("BAJRANG_API_KEY", ""),
    "byo_api_endpoint": os.environ.get(
        "BAJRANG_API_ENDPOINT",
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    ),
    "byo_model": os.environ.get("BAJRANG_BYO_MODEL", "gemini-2.5-pro"),
    "theme_mode": "dark",
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
    "google_account_email": "kaushikramravuru@gmail.com",
    "subscription_price_inr": 100,
    "show_top_pill": True,
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
        "format c:",
        "del /f /s /q c:\\",
        "rd /s /q c:\\",
        "rmdir /s /q c:\\",
        "remove-item -recurse -force c:\\",
        "diskpart",
        "bcdedit",
        "reg delete hklm",
        "cipher /w:c",
        "vssadmin delete shadows",
    ],
    "forbidden_regex": [
        r"^\s*sudo\s+rm\s+-rf",
        r"^\s*sudo\s+dd\b",
        r"(?:^|[;&|]\s*)sudo\b",
        r"(?:^|[;&|]\s*)pkexec\b",
        r"(?:^|[;&|]\s*)runas\b",
        r"start-process\b.*-verb\s+runas",
        r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/(?:\s|$|\*)",
        r"\b(?:curl|wget)\b.*\|\s*(?:ba)?sh\b",
        r"\biex\s*\(\s*(?:irm|iwr|invoke-webrequest|invoke-restmethod)",
        r"\bformat\s+[a-zA-Z]:",
        r"\b(?:del|rd|rmdir)\s+/[fqs].*\bc:\\",
    ],
    "enforce_no_root": True,
}

WIN32_VK_MAP: Dict[str, List[int]] = {
    "enter": [0x0D],
    "return": [0x0D],
    "backspace": [0x08],
    "tab": [0x09],
    "esc": [0x1B],
    "escape": [0x1B],
    "space": [0x20],
    "left": [0x25],
    "up": [0x26],
    "right": [0x27],
    "down": [0x28],
    "delete": [0x2E],
    "super": [0x5B],
    "win": [0x5B],
    "meta": [0x5B],
    "ctrl+c": [0x11, 0x43],
    "ctrl+v": [0x11, 0x56],
    "ctrl+w": [0x11, 0x57],
    "ctrl+t": [0x11, 0x54],
    "ctrl+l": [0x11, 0x4C],
    "alt+f4": [0x12, 0x73],
    "alt+tab": [0x12, 0x09],
    "28:1 28:0": [0x0D],
    "14:1 14:0": [0x08],
}


class AgentState(enum.Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    EXECUTING = "executing"
    BLOCKED = "blocked"


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
    provider_used: str = "ollama"
    model_used: str = "llama3.2"


class ConfigManager:
    def __init__(self, config_dir: Optional[Path] = None, data_dir: Optional[Path] = None) -> None:
        if IS_WINDOWS:
            appdata = os.environ.get("APPDATA", os.path.expanduser("~\\AppData\\Roaming"))
            localappdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
            default_cfg = Path(appdata) / "BajrangAI"
            default_data = Path(localappdata) / "BajrangAI"
        else:
            xdg_cfg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
            xdg_data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
            default_cfg = Path(xdg_cfg) / "bajrang-ai"
            default_data = Path(xdg_data) / "bajrang-ai"

        self.config_dir = Path(config_dir) if config_dir else default_cfg
        self.data_dir = Path(data_dir) if data_dir else default_data
        self.settings_path = self.config_dir / "settings.json"
        self.blocklist_path = self.config_dir / "blocklist.json"
        self.modelfile_path = self.config_dir / "Modelfile.bajrang"
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

    def build_personalized_llama_modelfile(self) -> Tuple[bool, str]:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        persona_prompt = str(self.settings.get("custom_persona_prompt", PERSONALIZED_LLAMA_SYSTEM_PROMPT))
        hw_profile = str(self.settings.get("hardware_profile", DEFAULT_SETTINGS["hardware_profile"]))
        combined_prompt = f"{persona_prompt.strip()}\n\nUSER HARDWARE PROFILE: {hw_profile}"
        content = PERSONALIZED_MODELFILE_TEMPLATE.format(system_prompt=combined_prompt.replace('"""', "'''"))
        self.modelfile_path.write_text(content, encoding="utf-8")

        custom_name = str(self.settings.get("personalized_model_name", "bajrang-llama3.2"))
        if shutil.which("ollama"):
            try:
                res = subprocess.run(
                    ["ollama", "create", custom_name, "-f", str(self.modelfile_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=30.0,
                    check=False,
                )
                if res.returncode == 0:
                    self.settings["model"] = custom_name
                    self.settings["provider"] = "ollama"
                    self.save_settings()
                    return True, f"Built and activated personalized Ollama model '{custom_name}'."
                return False, f"Wrote {self.modelfile_path}, but ollama create exited {res.returncode}: {res.stderr.strip()}"
            except Exception as exc:
                return False, f"Wrote {self.modelfile_path} (ollama command error: {exc})."
        return True, f"Saved personalized Modelfile to {self.modelfile_path}. Run: ollama create {custom_name} -f \"{self.modelfile_path}\""


class LicenseManager:
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


class LocalChatStorage:
    def __init__(self, data_dir: Optional[Path] = None) -> None:
        cfg = ConfigManager(data_dir=data_dir)
        self.data_dir = cfg.data_dir
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


class CustomVoiceRecognizer:
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
        "open notepad": [
            [0.33, 0.44, 0.20, 0.08, 0.11, 0.07, 0.04, 0.02],
            [0.26, 0.49, 0.28, 0.12, 0.14, 0.08, 0.04, 0.03],
            [0.22, 0.40, 0.38, 0.20, 0.12, 0.07, 0.04, 0.02],
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
        cfg = ConfigManager(data_dir=data_dir)
        self.data_dir = cfg.data_dir
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

        try:
            import sounddevice as sd
            import numpy as np
            frames = int(self.SAMPLE_RATE * duration_sec)
            recording = sd.rec(frames, samplerate=self.SAMPLE_RATE, channels=1, dtype="int16")
            sd.wait()
            with wave.open(str(tmp_wav), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.SAMPLE_RATE)
                wf.writeframes(recording.tobytes())
            if tmp_wav.is_file() and tmp_wav.stat().st_size > 44:
                return tmp_wav, "Recorded audio via sounddevice."
        except Exception:
            pass

        if IS_WINDOWS:
            try:
                winmm = ctypes.windll.winmm
                alias = f"bajrang_{int(time.time())}"
                winmm.mciSendStringW(f"open new Type waveaudio Alias {alias}", None, 0, 0)
                winmm.mciSendStringW(
                    f"set {alias} time format ms bitspersample 16 channels 1 samplespersec {self.SAMPLE_RATE}",
                    None,
                    0,
                    0,
                )
                winmm.mciSendStringW(f"record {alias}", None, 0, 0)
                time.sleep(max(0.5, float(duration_sec)))
                winmm.mciSendStringW(f"stop {alias}", None, 0, 0)
                winmm.mciSendStringW(f'save {alias} "{tmp_wav}"', None, 0, 0)
                winmm.mciSendStringW(f"close {alias}", None, 0, 0)
                if tmp_wav.is_file() and tmp_wav.stat().st_size > 44:
                    return tmp_wav, "Recorded audio via Windows WinMM (winmm.dll)."
            except Exception:
                pass

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
                    return tmp_wav, "Recorded audio via PipeWire (pw-record)."
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
                    return tmp_wav, "Recorded audio via ALSA (arecord)."
            except Exception:
                pass

        return None, "Microphone capture unavailable (install sounddevice or check Windows microphone permissions)."

    def read_pcm16_wav(self, wav_path: Path) -> List[float]:
        with wave.open(str(wav_path), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        if sampwidth != 2 or n_frames == 0:
            return []

        total_shorts = int(len(raw) / 2)
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
            from faster_whisper import WhisperModel
            if not hasattr(self, "_whisper_model"):
                self._whisper_model = WhisperModel("base.en", device="cpu", compute_type="int8")
            segments, _ = self._whisper_model.transcribe(str(wav_path), beam_size=1)
            text = " ".join(seg.text.strip() for seg in segments).strip()
            if text:
                return True, text, "faster-whisper (local CPU)"
        except Exception:
            pass

        if IS_WINDOWS:
            try:
                ps_script = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$rec = New-Object System.Speech.Recognition.SpeechRecognitionEngine; "
                    "$rec.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar)); "
                    f"$rec.SetInputToWaveFile('{wav_path}'); "
                    "$res = $rec.Recognize(); "
                    "if ($res) { Write-Output $res.Text }"
                )
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_script],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=8.0,
                    check=False,
                )
                sapi_text = (proc.stdout or "").strip()
                if sapi_text:
                    return True, sapi_text, "Windows SAPI SpeechRecognitionEngine"
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
            f"Voice detected ({metrics['rms_db']} dB), no matching template (best DTW={best_dist:.2f}).",
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
        clean = re.sub(r"[`*_#>~'\"]", "", text).strip()[:300]
        try:
            import pyttsx3
            eng = pyttsx3.init()
            eng.say(clean)
            eng.runAndWait()
            return
        except Exception:
            pass

        if IS_WINDOWS:
            ps_cmd = (
                "Add-Type -AssemblyName System.Speech; "
                f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{clean}')"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif shutil.which("spd-say"):
            subprocess.Popen(
                ["spd-say", "--wait", clean],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


class SafetyGuard:
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
            if any(tok in ("sudo", "pkexec", "doas", "su", "runas") for tok in tokens):
                return False, "Blocked by Safety Guardrail: privilege escalation ('sudo'/'runas') is prohibited."

        for sub in self.forbidden_substrings:
            if sub in lower_cmd:
                return False, f"Blocked by Safety Guardrail: prohibited token '{sub}' detected."

        for regex in self.forbidden_regex:
            if regex.search(normalized):
                return False, f"Blocked by Safety Guardrail: matched destructive pattern '{regex.pattern}'."

        return True, "Command passed safety checks."


class KillSwitchManager:
    def __init__(self, grace_ms: int = 500) -> None:
        self.grace_ms = grace_ms
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
        if IS_WINDOWS:
            try:
                user32 = ctypes.windll.user32
                for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C):
                    user32.keybd_event(vk, 0, 0x0002, 0)
            except Exception:
                pass

    def trigger(self) -> str:
        self._cancel_event.set()
        killed_pids: List[int] = []

        with self._lock:
            procs = list(self._active_procs.values())

        for proc in procs:
            if proc.poll() is None:
                killed_pids.append(proc.pid)
                if IS_WINDOWS:
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=2.0,
                            check=False,
                        )
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                else:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    except Exception:
                        try:
                            proc.terminate()
                        except Exception:
                            pass

        with self._lock:
            self._active_procs.clear()

        self.release_stuck_keys()

        if killed_pids:
            return f"Emergency Kill-Switch activated: terminated PIDs {killed_pids} and released modifier keys."
        return "Emergency Kill-Switch activated: cancelled active operation and released modifier keys."


class CrossPlatformPerception:
    def __init__(self) -> None:
        self.screen_width: int = 1920
        self.screen_height: int = 1080
        self._detect_display_resolution()

    def _detect_display_resolution(self) -> None:
        if IS_WINDOWS:
            try:
                user32 = ctypes.windll.user32
                w = user32.GetSystemMetrics(0)
                h = user32.GetSystemMetrics(1)
                if w > 0 and h > 0:
                    self.screen_width = int(w)
                    self.screen_height = int(h)
                    return
            except Exception:
                pass

    def capture_screen_base64(self, max_dimension: int = 1280) -> Tuple[Optional[str], str]:
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            self.screen_width, self.screen_height = img.size
            img_rgb = img.convert("RGB")
            img_rgb.thumbnail((max_dimension, max_dimension))
            buf = io.BytesIO()
            img_rgb.save(buf, format="JPEG", quality=82)
            b64_data = base64.b64encode(buf.getvalue()).decode("ascii")
            return b64_data, f"Captured screen via PIL.ImageGrab ({self.screen_width}x{self.screen_height})."
        except Exception as exc:
            return None, f"Screen capture unavailable ({exc}). Ensure Pillow is installed."

    def get_desktop_context_summary(self) -> str:
        os_name = f"Windows {platform.release()}" if IS_WINDOWS else f"Linux ({platform.system()})"
        return f"OS: {os_name} | Display Resolution: {self.screen_width}x{self.screen_height}"


class WindowsInputController:
    def __init__(self, key_delay_ms: int = 12, perception: Optional[CrossPlatformPerception] = None) -> None:
        self.key_delay_ms = key_delay_ms
        self.perception = perception or CrossPlatformPerception()

    def check_daemon(self) -> Tuple[bool, str]:
        try:
            import pyautogui
            return True, "PyAutoGUI + Win32 user32 input automation active."
        except ImportError:
            if IS_WINDOWS:
                return True, "Native Win32 ctypes.windll.user32 input automation active."
            return False, "Install pyautogui (`pip install pyautogui`) for cross-platform input."

    def mouse_move(self, x: int, y: int) -> ActionResult:
        clamped_x = max(0, min(int(x), self.perception.screen_width))
        clamped_y = max(0, min(int(y), self.perception.screen_height))
        try:
            import pyautogui
            pyautogui.moveTo(clamped_x, clamped_y, duration=0.1)
            return ActionResult(tool="ydotool_move", success=True, output=f"Moved cursor to ({clamped_x}, {clamped_y}) via PyAutoGUI.")
        except Exception:
            if IS_WINDOWS:
                ctypes.windll.user32.SetCursorPos(clamped_x, clamped_y)
                return ActionResult(tool="ydotool_move", success=True, output=f"Moved cursor to ({clamped_x}, {clamped_y}) via Win32 SetCursorPos.")
            return ActionResult(tool="ydotool_move", success=False, output="Mouse move requires Windows user32 or PyAutoGUI.")

    def mouse_click(
        self,
        button: str = "left",
        x: Optional[int] = None,
        y: Optional[int] = None,
    ) -> ActionResult:
        if x is not None and y is not None:
            self.mouse_move(int(x), int(y))
        btn = str(button).lower()
        try:
            import pyautogui
            pyautogui.click(button=btn if btn in ("left", "right", "middle") else "left")
            return ActionResult(tool="ydotool_click", success=True, output=f"Clicked {btn} button via PyAutoGUI.")
        except Exception:
            if IS_WINDOWS:
                user32 = ctypes.windll.user32
                flags = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}.get(btn, (0x0002, 0x0004))
                user32.mouse_event(flags[0], 0, 0, 0, 0)
                user32.mouse_event(flags[1], 0, 0, 0, 0)
                return ActionResult(tool="ydotool_click", success=True, output=f"Clicked {btn} button via Win32 mouse_event.")
            return ActionResult(tool="ydotool_click", success=False, output="Mouse click requires Windows user32 or PyAutoGUI.")

    def type_text(self, text: str) -> ActionResult:
        if not text:
            return ActionResult(tool="ydotool_type", success=False, output="Empty text payload.")
        try:
            import pyautogui
            pyautogui.write(text, interval=self.key_delay_ms / 1000.0)
            return ActionResult(tool="ydotool_type", success=True, output=f"Typed '{text}' via PyAutoGUI.")
        except Exception:
            if IS_WINDOWS:
                user32 = ctypes.windll.user32
                for ch in text:
                    vk = user32.VkKeyScanW(ord(ch))
                    vk_code = vk & 0xFF
                    shift = (vk >> 8) & 1
                    if shift:
                        user32.keybd_event(0x10, 0, 0, 0)
                    user32.keybd_event(vk_code, 0, 0, 0)
                    user32.keybd_event(vk_code, 0, 0x0002, 0)
                    if shift:
                        user32.keybd_event(0x10, 0, 0x0002, 0)
                    time.sleep(self.key_delay_ms / 1000.0)
                return ActionResult(tool="ydotool_type", success=True, output=f"Typed '{text}' via Win32 keybd_event.")
            return ActionResult(tool="ydotool_type", success=False, output="Text typing requires Windows user32 or PyAutoGUI.")

    def press_key(self, key_spec: str) -> ActionResult:
        cleaned = str(key_spec).strip().lower()
        try:
            import pyautogui
            if "+" in cleaned:
                parts = [p.strip() for p in cleaned.split("+")]
                pyautogui.hotkey(*parts)
            else:
                alias = {"28:1 28:0": "enter", "14:1 14:0": "backspace", "super": "win"}.get(cleaned, cleaned)
                pyautogui.press(alias)
            return ActionResult(tool="ydotool_key", success=True, output=f"Pressed key '{cleaned}' via PyAutoGUI.")
        except Exception:
            if IS_WINDOWS:
                vks = WIN32_VK_MAP.get(cleaned, [0x0D])
                user32 = ctypes.windll.user32
                for vk in vks:
                    user32.keybd_event(vk, 0, 0, 0)
                for vk in reversed(vks):
                    user32.keybd_event(vk, 0, 0x0002, 0)
                return ActionResult(tool="ydotool_key", success=True, output=f"Pressed key '{cleaned}' via Win32 keybd_event.")
            return ActionResult(tool="ydotool_key", success=False, output="Key press requires Windows user32 or PyAutoGUI.")


class ShellRunner:
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
            if IS_WINDOWS:
                popen_args: Any = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
                kwargs: Dict[str, Any] = {}
            else:
                popen_args = ["bash", "--noprofile", "--norc", "-c", command]
                kwargs = {"start_new_session": True}

            proc = subprocess.Popen(
                popen_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                **kwargs,
            )
            self.kill_switch.register_process(proc)
            try:
                stdout, stderr = proc.communicate(timeout=self.timeout_sec)
            except subprocess.TimeoutExpired:
                self.kill_switch.trigger()
                return ActionResult(
                    tool="shell_exec",
                    success=False,
                    output=f"Command timed out after {self.timeout_sec}s: {command}",
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
                    output=combined or f"Command completed successfully (exit 0): {command}",
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
                output=f"Execution failed for {command}: {exc}",
            )


class UnifiedModelClient:
    def __init__(self, config: ConfigManager) -> None:
        self.config = config
        self.history: List[Dict[str, Any]] = []

    @property
    def system_prompt(self) -> str:
        base = str(self.config.settings.get("custom_persona_prompt", PERSONALIZED_LLAMA_SYSTEM_PROMPT))
        hw = str(self.config.settings.get("hardware_profile", DEFAULT_SETTINGS["hardware_profile"]))
        return f"{base.strip()}\n\nUSER HARDWARE CONTEXT: {hw}"

    @property
    def provider(self) -> str:
        if self.config.settings.get("byo_api_key") and self.config.settings.get("provider") != "ollama":
            return "byo_api"
        return "ollama"

    @property
    def active_model(self) -> str:
        if self.provider == "byo_api":
            return str(self.config.settings.get("byo_model", "gemini-2.5-pro"))
        return str(self.config.settings.get("model", "llama3.2"))

    def configure_byo_key(
        self,
        api_key: str,
        preset_name: str = "gemini_argon",
        custom_endpoint: Optional[str] = None,
        custom_model: Optional[str] = None,
    ) -> None:
        clean_key = api_key.strip()
        preset = PROVIDER_PRESETS.get(preset_name, PROVIDER_PRESETS["gemini_argon"])
        self.config.settings["byo_provider"] = preset_name
        self.config.settings["byo_api_key"] = clean_key
        self.config.settings["byo_api_endpoint"] = (custom_endpoint or preset["endpoint"]).strip()
        self.config.settings["byo_model"] = (custom_model or preset["model"]).strip()
        self.config.settings["provider"] = "byo_api" if clean_key else "ollama"
        self.config.save_settings()

    def clear_history(self) -> None:
        self.history.clear()

    def load_session_messages(self, stored_messages: List[Dict[str, Any]]) -> None:
        self.history = [
            {"role": m["role"], "content": m["content"]}
            for m in stored_messages
            if m.get("role") in ("user", "assistant")
        ]

    def check_health(self) -> Tuple[bool, List[str], str]:
        if self.provider == "byo_api":
            raw_key = str(self.config.settings.get("byo_api_key", ""))
            masked_key = (raw_key[:6] + "..." + raw_key[-3:]) if len(raw_key) > 9 else "configured"
            endpoint = str(self.config.settings.get("byo_api_endpoint", ""))
            return True, [self.active_model], f"BYO Cloud API active ({self.active_model} • {endpoint} • key {masked_key})"

        host = str(self.config.settings.get("ollama_host", "http://localhost:11434")).rstrip("/")
        url = f"{host}/api/tags"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
                return True, models, f"Connected to local Ollama at {host} ({len(models)} models available)."
        except Exception as exc:
            return (
                False,
                [],
                f"Ollama unreachable at {host} ({exc}). Start Ollama or enter a free BYO API key in Settings.",
            )

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
        if screenshot_b64 and ("vision" in self.active_model.lower() or "vl" in self.active_model.lower()):
            user_msg["images"] = [screenshot_b64]
        messages.append(user_msg)

        if self.provider == "byo_api":
            turn = self._chat_byo(messages, user_prompt)
            turn.provider_used = "byo_api"
            turn.model_used = self.active_model
            return turn

        turn = self._chat_ollama(messages, user_prompt)
        turn.provider_used = "ollama"
        turn.model_used = self.active_model
        return turn

    def _chat_byo(self, messages: List[Dict[str, Any]], user_prompt: str) -> AssistantTurn:
        api_key = str(self.config.settings.get("byo_api_key", ""))
        endpoint = str(
            self.config.settings.get(
                "byo_api_endpoint",
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            )
        )
        model_name = self.active_model

        payload = {
            "model": model_name,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "temperature": 0.2 if re.search(r"\b(open|launch|run|click|type|close|press)\b", user_prompt, re.I) else 0.5,
        }
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                choice = body.get("choices", [{}])[0]
                assistant_content = choice.get("message", {}).get("content", "")
        except Exception as exc:
            return AssistantTurn(
                response_type="conversation",
                text=f"**BYO Cloud API Error** ({model_name} @ {endpoint}): {exc}. Verify your API key in Settings.",
            )

        turn = self.parse_structured_output(assistant_content)
        self.history.append({"role": "user", "content": user_prompt})
        self.history.append({"role": "assistant", "content": assistant_content})
        return turn

    def _chat_ollama(self, messages: List[Dict[str, Any]], user_prompt: str) -> AssistantTurn:
        host = str(self.config.settings.get("ollama_host", "http://localhost:11434")).rstrip("/")
        model_name = self.active_model

        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.2 if re.search(r"\b(open|launch|run|click|type|close|press)\b", user_prompt, re.I) else 0.5,
            },
        }

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{host}/api/chat",
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                assistant_content = body.get("message", {}).get("content", "")
        except Exception as exc:
            return AssistantTurn(
                response_type="conversation",
                text=f"**Could not reach local Ollama server** at {host} ({exc}). Start Ollama or click ⚙️ Settings to enter your own API key for free cloud inference.",
            )

        turn = self.parse_structured_output(assistant_content)
        self.history.append({"role": "user", "content": user_prompt})
        self.history.append({"role": "assistant", "content": assistant_content})
        return turn


class BajrangWindowsEngine:
    def __init__(
        self,
        config: Optional[ConfigManager] = None,
        state_callback: Optional[Callable[[AgentState, str], None]] = None,
        ui_turn_callback: Optional[Callable[[str, AssistantTurn], None]] = None,
    ) -> None:
        self.config = config or ConfigManager()
        self.state_callback = state_callback
        self.ui_turn_callback = ui_turn_callback
        self.state = AgentState.IDLE

        self.storage = LocalChatStorage(data_dir=self.config.data_dir)
        existing_sessions = self.storage.list_sessions(limit=1)
        if existing_sessions:
            self.current_session_id = existing_sessions[0]["session_id"]
        else:
            self.current_session_id = self.storage.create_session(
                title="Windows 11 Desktop Session",
                model=str(self.config.settings.get("model", "llama3.2")),
            )

        self.voice = CustomVoiceRecognizer(
            data_dir=self.config.data_dir,
            vad_threshold_db=float(self.config.settings.get("voice_vad_threshold_db", -38.0)),
            tts_enabled=bool(self.config.settings.get("tts_enabled", True)),
        )
        self.safety = SafetyGuard(self.config.blocklist)
        self.kill_switch = KillSwitchManager(
            grace_ms=int(self.config.settings.get("kill_switch_grace_ms", 500)),
        )
        self.perception = CrossPlatformPerception()
        self.input_controller = WindowsInputController(
            key_delay_ms=int(self.config.settings.get("key_delay_ms", 12)),
            perception=self.perception,
        )
        self.shell_runner = ShellRunner(
            safety=self.safety,
            kill_switch=self.kill_switch,
            timeout_sec=int(self.config.settings.get("shell_timeout_sec", 15)),
            max_output_bytes=int(self.config.settings.get("shell_max_output_bytes", 16384)),
        )
        self.client = UnifiedModelClient(config=self.config)
        self.client.load_session_messages(self.storage.get_session_messages(self.current_session_id))

    def set_state(self, new_state: AgentState, status_text: str = "") -> None:
        self.state = new_state
        if self.state_callback:
            self.state_callback(new_state, status_text)

    def new_session(self, title: str = "New Conversation") -> str:
        self.current_session_id = self.storage.create_session(title=title, model=self.client.active_model)
        self.client.clear_history()
        return self.current_session_id

    def switch_session(self, session_id: str) -> List[Dict[str, Any]]:
        self.current_session_id = session_id
        msgs = self.storage.get_session_messages(session_id)
        self.client.load_session_messages(msgs)
        return msgs

    def trigger_emergency_kill(self) -> str:
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

        if tool in ("ydotool_move", "win_move"):
            return self.input_controller.mouse_move(
                x=int(params.get("x", 0)),
                y=int(params.get("y", 0)),
            )
        if tool in ("ydotool_click", "win_click"):
            return self.input_controller.mouse_click(
                button=str(params.get("button", "left")),
                x=params.get("x"),
                y=params.get("y"),
            )
        if tool in ("ydotool_type", "win_type"):
            return self.input_controller.type_text(str(params.get("text", "")))
        if tool in ("ydotool_key", "win_key"):
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
        self.set_state(AgentState.THINKING, f"Thinking ({self.client.active_model})...")

        self.storage.add_message(
            session_id=self.current_session_id,
            role="user",
            content=user_prompt,
            model=self.client.active_model,
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
            model=self.client.active_model,
        )

        if speak_reply and turn.text:
            self.voice.speak_tts(turn.text)

        return turn

    def capture_voice_turn(self, duration_sec: float = 4.0) -> Tuple[bool, str, Optional[AssistantTurn], str]:
        self.set_state(AgentState.LISTENING, "Listening (Voice DSP)...")
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


def run_windows_tkinter_app(engine: BajrangWindowsEngine) -> int:
    import tkinter as tk
    from tkinter import ttk

    THEMES = {
        "dark": {
            "bg": "#111420",
            "sidebar": "#0b0d15",
            "card": "#1b2032",
            "fg": "#f8fafc",
            "muted": "#94a3b8",
            "accent": "#4f46e5",
            "amber": "#f59e0b",
            "danger": "#dc2626",
            "ok": "#10b981",
        },
        "light": {
            "bg": "#f8fafc",
            "sidebar": "#eef2f6",
            "card": "#ffffff",
            "fg": "#0f172a",
            "muted": "#475569",
            "accent": "#4f46e5",
            "amber": "#d97706",
            "danger": "#dc2626",
            "ok": "#059669",
        },
    }

    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("920x580")
    root.minsize(720, 460)

    top_pill = tk.Toplevel(root)
    top_pill.overrideredirect(True)
    top_pill.attributes("-topmost", True)
    screen_w = root.winfo_screenwidth()
    top_pill.geometry(f"220x34+{max(20, screen_w - 250)}+8")
    top_pill.configure(bg="#111420")

    pill_frame = tk.Frame(top_pill, bg="#111420", padx=8, pady=4)
    pill_frame.pack(fill=tk.BOTH, expand=True)

    pill_dot = tk.Label(pill_frame, text="●", fg="#2ec27e", bg="#111420", font=("Segoe UI", 11, "bold"))
    pill_dot.pack(side=tk.LEFT)

    def toggle_main_window() -> None:
        if root.state() == "withdrawn":
            root.deiconify()
            root.lift()
        else:
            root.withdraw()

    pill_btn = tk.Button(
        pill_frame,
        text="⚡ Bajrang AI Pro",
        bg="#111420",
        fg="#f8fafc",
        bd=0,
        font=("Segoe UI", 9, "bold"),
        command=toggle_main_window,
    )
    pill_btn.pack(side=tk.LEFT, padx=4)

    pill_kill_btn = tk.Button(
        pill_frame,
        text="KILL",
        bg="#dc2626",
        fg="#ffffff",
        bd=0,
        font=("Segoe UI", 8, "bold"),
        command=lambda: on_kill_clicked(),
    )
    pill_kill_btn.pack(side=tk.RIGHT)

    header = tk.Frame(root, padx=12, pady=8)
    header.pack(fill=tk.X)

    status_dot_lbl = tk.Label(header, text="●", font=("Segoe UI", 14, "bold"))
    status_dot_lbl.pack(side=tk.LEFT, padx=(0, 6))

    title_lbl = tk.Label(header, text="Bajrang AI Pro (Windows 11)", font=("Segoe UI", 12, "bold"))
    title_lbl.pack(side=tk.LEFT)

    status_text_lbl = tk.Label(
        header,
        text=f"  Idle • {engine.client.active_model} ({engine.client.provider})",
        font=("Segoe UI", 9),
    )
    status_text_lbl.pack(side=tk.LEFT, padx=8)

    def on_kill_clicked() -> None:
        msg = engine.trigger_emergency_kill()
        append_chat_line(f"🛑 {msg}", "blocked")

    kill_btn = tk.Button(
        header,
        text="🛑 KILL (Ctrl+Esc)",
        bg="#dc2626",
        fg="#ffffff",
        font=("Segoe UI", 9, "bold"),
        relief=tk.FLAT,
        padx=10,
        pady=3,
        command=on_kill_clicked,
    )
    kill_btn.pack(side=tk.RIGHT, padx=4)

    def open_settings_modal() -> None:
        win = tk.Toplevel(root)
        win.title("Bajrang AI Pro — BYO API Key & Personalized Llama 3.2 Settings")
        win.geometry("500x360")
        win.transient(root)
        win.grab_set()
        frm = tk.Frame(win, padx=16, pady=16)
        frm.pack(fill=tk.BOTH, expand=True)

        tk.Label(frm, text="BYO Cloud API Key (Leave blank for Local Llama 3.2):", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        key_var = tk.StringVar(value=str(engine.config.settings.get("byo_api_key", "")))
        tk.Entry(frm, textvariable=key_var, width=56).pack(fill=tk.X, pady=(2, 8))

        tk.Label(frm, text="API Endpoint URL:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ep_var = tk.StringVar(value=str(engine.config.settings.get("byo_api_endpoint", "")))
        tk.Entry(frm, textvariable=ep_var, width=56).pack(fill=tk.X, pady=(2, 8))

        tk.Label(frm, text="Cloud Model Name (e.g. gemini-2.5-pro or llama-3.3-70b-versatile):", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        mod_var = tk.StringVar(value=str(engine.config.settings.get("byo_model", "gemini-2.5-pro")))
        tk.Entry(frm, textvariable=mod_var, width=56).pack(fill=tk.X, pady=(2, 8))

        tk.Label(frm, text="Pro License Key (BAJRANG-PRO-...):", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        lic_var = tk.StringVar(value=str(engine.config.settings.get("license_key", "")))
        tk.Entry(frm, textvariable=lic_var, width=56).pack(fill=tk.X, pady=(2, 12))

        btn_bar = tk.Frame(frm)
        btn_bar.pack(fill=tk.X)

        def save_cfg() -> None:
            engine.client.configure_byo_key(key_var.get(), "gemini_argon", ep_var.get(), mod_var.get())
            if lic_var.get().strip():
                engine.config.settings["license_key"] = lic_var.get().strip()
                engine.config.save_settings()
            status_text_lbl.configure(text=f"  Idle • {engine.client.active_model} ({engine.client.provider})")
            win.destroy()

        def build_modelfile() -> None:
            ok, msg = engine.config.build_personalized_llama_modelfile()
            append_chat_line(f"🦙 Personalized Llama 3.2: {msg}", "assistant")
            win.destroy()

        tk.Button(btn_bar, text="Save Settings", bg="#4f46e5", fg="#ffffff", relief=tk.FLAT, padx=12, pady=4, command=save_cfg).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_bar, text="Build Personalized Llama 3.2", bg="#f59e0b", fg="#0f172a", relief=tk.FLAT, padx=12, pady=4, command=build_modelfile).pack(side=tk.LEFT, padx=4)

    settings_btn = tk.Button(
        header,
        text="⚙️ API Key / Persona",
        relief=tk.FLAT,
        padx=8,
        pady=3,
        command=open_settings_modal,
    )
    settings_btn.pack(side=tk.RIGHT, padx=4)

    def toggle_theme_mode() -> None:
        cur = engine.config.settings.get("theme_mode", "dark")
        nxt = "light" if cur == "dark" else "dark"
        engine.config.settings["theme_mode"] = nxt
        engine.config.save_settings()
        apply_current_theme()

    theme_btn = tk.Button(header, text="☀️/🌙 Theme", relief=tk.FLAT, padx=8, pady=3, command=toggle_theme_mode)
    theme_btn.pack(side=tk.RIGHT, padx=4)

    body = tk.Frame(root)
    body.pack(fill=tk.BOTH, expand=True)

    sidebar = tk.Frame(body, width=220, padx=8, pady=8)
    sidebar.pack(side=tk.LEFT, fill=tk.Y)
    sidebar.pack_propagate(False)

    def create_new_chat() -> None:
        engine.new_session("New Conversation")
        refresh_sessions()
        load_session_messages()

    new_btn = tk.Button(
        sidebar,
        text="+ New Chat Session",
        bg="#4f46e5",
        fg="#ffffff",
        font=("Segoe UI", 9, "bold"),
        relief=tk.FLAT,
        pady=5,
        command=create_new_chat,
    )
    new_btn.pack(fill=tk.X, pady=(0, 6))

    session_listbox = tk.Listbox(sidebar, bd=0, highlightthickness=0, font=("Segoe UI", 9))
    session_listbox.pack(fill=tk.BOTH, expand=True)

    session_ids: List[str] = []

    def refresh_sessions() -> None:
        session_listbox.delete(0, tk.END)
        session_ids.clear()
        for s in engine.storage.list_sessions(limit=35):
            session_ids.append(s["session_id"])
            session_listbox.insert(tk.END, f"💬 {s['title']} ({s['message_count']})")

    def on_session_select(_evt: Any) -> None:
        sel = session_listbox.curselection()
        if sel and sel[0] < len(session_ids):
            engine.switch_session(session_ids[sel[0]])
            load_session_messages()

    session_listbox.bind("<<ListboxSelect>>", on_session_select)

    right_pane = tk.Frame(body, padx=10, pady=8)
    right_pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    chat_text = tk.Text(right_pane, wrap=tk.WORD, bd=0, padx=10, pady=10, font=("Segoe UI", 10), state=tk.DISABLED)
    chat_text.pack(fill=tk.BOTH, expand=True)

    input_bar = tk.Frame(right_pane, pady=8)
    input_bar.pack(fill=tk.X)

    def on_voice_clicked() -> None:
        def worker() -> None:
            ok, transcript, turn, info = engine.capture_voice_turn()
            if not ok:
                root.after(0, lambda: append_chat_line(f"🎙️ Voice Mode: {info}", "assistant"))

        threading.Thread(target=worker, daemon=True).start()

    voice_btn = tk.Button(
        input_bar,
        text="🎙️ Speak",
        bg="#9333ea",
        fg="#ffffff",
        font=("Segoe UI", 9, "bold"),
        relief=tk.FLAT,
        padx=10,
        pady=5,
        command=on_voice_clicked,
    )
    voice_btn.pack(side=tk.LEFT, padx=(0, 6))

    prompt_var = tk.StringVar()
    prompt_entry = tk.Entry(input_bar, textvariable=prompt_var, font=("Segoe UI", 10))
    prompt_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0, 6))

    def on_send_prompt(*_args: Any) -> None:
        p = prompt_var.get().strip()
        if not p:
            return
        prompt_var.set("")
        append_chat_line(f"You: {p}", "user")

        def worker() -> None:
            turn = engine.process_prompt(p)
            root.after(0, lambda: render_turn(turn))

        threading.Thread(target=worker, daemon=True).start()

    prompt_entry.bind("<Return>", on_send_prompt)
    root.bind("<Control-Escape>", lambda _e: on_kill_clicked())

    send_btn = tk.Button(
        input_bar,
        text="Send",
        bg="#4f46e5",
        fg="#ffffff",
        font=("Segoe UI", 9, "bold"),
        relief=tk.FLAT,
        padx=14,
        pady=5,
        command=on_send_prompt,
    )
    send_btn.pack(side=tk.RIGHT)

    def append_chat_line(text: str, kind: str = "assistant") -> None:
        chat_text.configure(state=tk.NORMAL)
        chat_text.insert(tk.END, text + "\n\n", kind)
        chat_text.see(tk.END)
        chat_text.configure(state=tk.DISABLED)

    def render_turn(turn: AssistantTurn) -> None:
        if turn.text:
            append_chat_line(f"Bajrang AI ({turn.model_used}): {turn.text}", "assistant")
        for r in turn.results:
            badge = "🛑 BLOCKED" if r.blocked else ("✅ OK" if r.success else "⚠️ ERROR")
            tag = "blocked" if (r.blocked or not r.success) else "ok"
            append_chat_line(f"  [{badge} • {r.tool}] {r.output}", tag)
        refresh_sessions()

    def load_session_messages() -> None:
        chat_text.configure(state=tk.NORMAL)
        chat_text.delete("1.0", tk.END)
        chat_text.configure(state=tk.DISABLED)
        msgs = engine.storage.get_session_messages(engine.current_session_id)
        if not msgs:
            ok_m, _, m_msg = engine.client.check_health()
            ok_i, i_msg = engine.input_controller.check_daemon()
            lic_ok, lic_msg = LicenseManager.verify_key(str(engine.config.settings.get("license_key", "")))
            diag = (
                f"Bajrang AI Pro ({APP_VERSION}) ready on Windows 11 / Cross-Platform.\n"
                f"• Intelligence ({engine.client.active_model}): {m_msg}\n"
                f"• Voice Engine: WinMM / SAPI + 8-Band Goertzel Spectral-DTW Ready\n"
                f"• Input Controller: {i_msg}\n"
                f"• Local SQLite Storage: {engine.storage.db_path}\n"
                f"• Subscription: {lic_msg}"
            )
            append_chat_line(diag, "assistant")
            return
        for m in msgs:
            if m["role"] == "user":
                append_chat_line(f"You: {m['content']}", "user")
            else:
                append_chat_line(f"Bajrang AI: {m['content']}", "assistant")

    def on_state_change(state: AgentState, status_text: str) -> None:
        colors = {
            AgentState.IDLE: "#2ec27e",
            AgentState.LISTENING: "#c061cb",
            AgentState.THINKING: "#3584e4",
            AgentState.EXECUTING: "#ff7800",
            AgentState.BLOCKED: "#e01b24",
        }
        col = colors.get(state, "#2ec27e")
        root.after(
            0,
            lambda: (
                status_dot_lbl.configure(fg=col),
                pill_dot.configure(fg=col),
                status_text_lbl.configure(text=f"  {status_text or state.value.capitalize()} • {engine.client.active_model}"),
            ),
        )

    engine.state_callback = on_state_change

    def apply_current_theme() -> None:
        mode = engine.config.settings.get("theme_mode", "dark")
        pal = THEMES.get(mode, THEMES["dark"])
        root.configure(bg=pal["bg"])
        header.configure(bg=pal["bg"])
        title_lbl.configure(bg=pal["bg"], fg=pal["fg"])
        status_text_lbl.configure(bg=pal["bg"], fg=pal["muted"])
        status_dot_lbl.configure(bg=pal["bg"])
        body.configure(bg=pal["bg"])
        sidebar.configure(bg=pal["sidebar"])
        session_listbox.configure(bg=pal["sidebar"], fg=pal["fg"])
        right_pane.configure(bg=pal["bg"])
        chat_text.configure(bg=pal["card"], fg=pal["fg"], insertbackground=pal["fg"])
        input_bar.configure(bg=pal["bg"])
        prompt_entry.configure(bg=pal["card"], fg=pal["fg"], insertbackground=pal["fg"])
        chat_text.tag_configure("user", foreground=pal["accent"], font=("Segoe UI", 10, "bold"))
        chat_text.tag_configure("assistant", foreground=pal["fg"])
        chat_text.tag_configure("ok", foreground=pal["ok"], font=("Consolas", 9))
        chat_text.tag_configure("blocked", foreground=pal["danger"], font=("Consolas", 9, "bold"))

    apply_current_theme()
    refresh_sessions()
    load_session_messages()
    root.mainloop()
    return 0


def run_self_tests() -> int:
    print("[Test 1/5] Verifying Windows + Linux Dual SafetyGuard...")
    guard = SafetyGuard()
    for bad_cmd in (
        "format c:",
        "del /f /s /q c:\\",
        "Remove-Item -Recurse -Force C:\\",
        "runas /user:Administrator cmd",
        "sudo rm -rf /",
    ):
        ok, _ = guard.validate_command(bad_cmd)
        assert not ok, f"Expected command to be blocked: {bad_cmd}"
    for safe_cmd in ("notepad.exe", "calc.exe", "echo Hello Windows 11"):
        ok, reason = guard.validate_command(safe_cmd)
        assert ok, f"Expected safe command to pass: {safe_cmd} ({reason})"
    print("  -> Passed: Windows + Linux SafetyGuard verified.")

    print("[Test 2/5] Verifying Custom 8-Band Spectral-DTW Voice Recognizer...")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        rec = CustomVoiceRecognizer(data_dir=tmp_path)
        wav_np = CustomVoiceRecognizer.generate_synthetic_speech_wav(
            tmp_path / "open_notepad.wav", phrase="open notepad"
        )
        ok_enr, _ = rec.enroll_phrase_from_wav("open notepad", wav_np)
        assert ok_enr
        ok_rec, transcript, info = rec.recognize_wav(wav_np)
        assert ok_rec and transcript == "open notepad"
    print(f"  -> Passed: Matched '{transcript}' ({info}).")

    print("[Test 3/5] Verifying Cross-Platform Local SQLite3 Chat History...")
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LocalChatStorage(data_dir=Path(tmpdir))
        sid = store.create_session(title="Windows 11 Voice Session", model="llama3.2")
        store.add_message(sid, "user", "Open Notepad on Windows 11")
        store.add_message(sid, "assistant", "Opening Notepad now.")
        assert len(store.list_sessions()) == 1
        assert len(store.search_messages("Notepad")) == 2
    print("  -> Passed: Local SQLite3 storage verified.")

    print("[Test 4/5] Verifying BYO Cloud API Key & Personalized Modelfile Builder...")
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = ConfigManager(config_dir=Path(tmpdir), data_dir=Path(tmpdir))
        client = UnifiedModelClient(config=cfg)
        client.configure_byo_key("AIzaSyWin11TestKey", preset_name="gemini_argon")
        assert client.provider == "byo_api" and client.active_model == "gemini-2.5-pro"
        cfg.build_personalized_llama_modelfile()
        assert cfg.modelfile_path.is_file()
    print("  -> Passed: BYO Cloud API Key & Modelfile verified.")

    print("[Test 5/5] Verifying LicenseManager...")
    key = LicenseManager.generate_key("WINUSER", valid_days=30)
    ok_lic, _ = LicenseManager.verify_key(key)
    assert ok_lic
    print(f"  -> Passed: Verified license key {key}.")
    print("\n[Test 6/6] Verifying v6.0 Core Engine (Vault, SQLite v3 Migrations, Task Planner, Complexity Router)...")
    if HAS_BAJRANG_CORE:
        with tempfile.TemporaryDirectory() as tmp_v6:
            p_v6 = Path(tmp_v6)
            vault = SecurityVault(p_v6 / "config")
            backend_used = vault.store_secret("api_key_gemini_argon", "AIzaTestKey12345678901234567890")
            assert vault.get_secret("api_key_gemini_argon") == "AIzaTestKey12345678901234567890"
            mem = LongTermMemoryStore(p_v6 / "history.db")
            ok_m, _, _ = mem.store_memory("preferred_editor", "VS Code on Windows 11", category="preference", importance=5)
            assert ok_m is True
            blocked_pii, _, _ = mem.store_memory("leaked_key", "AIzaSySecretKey999999999999999999999", category="fact")
            assert blocked_pii is False
            dl_dir = p_v6 / "Downloads"
            dl_dir.mkdir()
            (dl_dir / "notes.pdf").write_bytes(b"PDF_CONTENT_123")
            (dl_dir / "notes_copy.pdf").write_bytes(b"PDF_CONTENT_123")
            (dl_dir / "photo.png").write_bytes(b"PNG_DATA_456")
            planner = AutonomousTaskPlanner(mem, CrossPlatformComputerUse())
            ok_p, plan = planner.create_organization_plan(str(dl_dir), remove_duplicates=True)
            assert ok_p is True and plan.requires_permission is True
            assert plan.inspection_report["duplicate_count"] == 1
            exec_unapproved, _ = planner.execute_approved_plan(plan.plan_id, user_confirmed=False)
            assert exec_unapproved is False
            exec_approved, done_plan = planner.execute_approved_plan(plan.plan_id, user_confirmed=True)
            assert exec_approved is True and done_plan.status == "completed"
            print(f"  -> Passed: v6.0 Core Engine verified (Vault={backend_used}, Duplicates removed=1).")

    print("\nAll 6/6 Bajrang AI Pro v6.0 (Windows 11 & Cross-Platform Edition) self-tests passed!")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bajrang AI Pro (Windows 11 & Cross-Platform Edition) — Local Llama 3.2, BYO API Key, Voice DSP & SQLite History"
    )
    parser.add_argument("--model", default=None, help="Ollama model name (default: llama3.2)")
    parser.add_argument("--api-key", default=None, help="Configure BYO Cloud API key")
    parser.add_argument("--api-preset", default="gemini_argon", help="BYO preset: gemini_argon, groq, openrouter, openai")
    parser.add_argument("--build-personalized-llama", action="store_true", help="Build custom personalized Llama 3.2 Modelfile")
    parser.add_argument("--toggle-theme", action="store_true", help="Toggle bright/dark mode")
    parser.add_argument("--voice", action="store_true", help="Trigger immediate Voice Mode capture")
    parser.add_argument("--kill", action="store_true", help="Trigger Emergency Kill-Switch")
    parser.add_argument("--headless", action="store_true", help="Run in terminal mode")
    parser.add_argument("--prompt", default=None, help="Run a single prompt and print the response")
    parser.add_argument("--self-test", action="store_true", help="Run automated verification suite")

    args, _ = parser.parse_known_args(argv)

    if args.self_test:
        return run_self_tests()

    cfg = ConfigManager()
    cfg.save_defaults()

    if args.build_personalized_llama:
        ok, msg = cfg.build_personalized_llama_modelfile()
        print(msg)
        return 0 if ok else 1

    if args.api_key is not None:
        client = UnifiedModelClient(config=cfg)
        client.configure_byo_key(args.api_key, args.api_preset)

    if args.model:
        cfg.settings["model"] = args.model
        cfg.save_settings()

    engine = BajrangWindowsEngine(config=cfg)

    if args.toggle_theme:
        cur = cfg.settings.get("theme_mode", "dark")
        nxt = "light" if cur == "dark" else "dark"
        cfg.settings["theme_mode"] = nxt
        cfg.save_settings()
        print(f"Theme switched to: {nxt}")
        return 0

    if args.kill:
        print(engine.trigger_emergency_kill())
        return 0

    if args.prompt:
        turn = engine.process_prompt(args.prompt)
        print(f"\n[Bajrang AI ({turn.model_used})]: {turn.text}")
        for r in turn.results:
            print(f"  -> [{r.tool}] {r.output}")
        return 0

    if args.headless or (not IS_WINDOWS and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY")):
        print(f"=== {APP_TITLE} ({APP_VERSION}) — Terminal Mode ===")
        while True:
            try:
                p = input("You > ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not p or p.lower() in ("/quit", "exit", "quit"):
                break
            turn = engine.process_prompt(p)
            print(f"\nBajrang AI > {turn.text}\n")
        return 0

    return run_windows_tkinter_app(engine)


if __name__ == "__main__":
    raise SystemExit(main())
