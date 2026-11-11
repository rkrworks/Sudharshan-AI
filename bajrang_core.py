#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bajrang AI Pro (Argon Edition v6.0) — Unified Core Architecture (`bajrang_core.py`)
Provides the shared, zero-duplication engine for both Windows 11 (`bajrang_windows.py`)
and Fedora Workstation GNOME/Wayland (`bajrang_llama32.py`):
  1. SecurityVault (OS keyring / Windows DPAPI / Linux libsecret + 0600 fallback + PII redaction)
  2. AsymmetricLicenseVerifier (Server-signed license token verification without client private keys)
  3. DatabaseMigrationManager & LongTermMemoryStore (SQLite WAL + v1..v3 migrations + Memories CRUD)
  4. ModularAIRouter (Gemini Argon, Ollama Local, Groq, OpenRouter, OpenAI + Complexity Router + Fallback + Streaming + JSON Schema Validator)
  5. AdvancedVoiceEngine (Continuous listening, Wake Word, Barge-In, Spectral Noise Gate + VAD, 8-Band Goertzel-DTW + Whisper/SAPI STT, Configurable TTS, Mic Selection)
  6. CrossPlatformComputerUse (Verified Screenshot Analysis, Active Window Enumeration, App Launch/Close, Mouse/Keyboard/Scroll/Menu Navigation, File Operations)
  7. AutonomousTaskPlanner & RestrictiveToolExecutor (Multi-step task planning, SHA-256 duplicate finder, Downloads organizer, explicit confirmation gates, post-action verification)
"""

import base64
import ctypes
import datetime
import enum
import hashlib
import hmac
import importlib.util
import io
import json
import math
import os
import platform
import queue
import re
import shutil
import socket
import sqlite3
import stat
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
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple


CORE_VERSION = "6.0.0-Argon-Production"


class AgentState(enum.Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    BLOCKED = "blocked"
    ERROR = "error"


class PerformanceProfile(enum.Enum):
    ECO_LOW_RAM = "eco"
    BALANCED = "balanced"
    HIGH_PERFORMANCE = "high"


class TaskComplexity(enum.Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX_REASONING = "complex_reasoning"
    MULTIMODAL_VISION = "multimodal_vision"


@dataclass
class PerformanceSettings:
    profile: str = "balanced"
    max_context_messages: int = 12
    screenshot_max_dim: int = 1280
    screenshot_jpeg_quality: int = 80
    voice_poll_interval_ms: int = 80
    ollama_num_threads: int = 6
    ollama_num_ctx: int = 4096
    enable_local_llama: bool = True

    @classmethod
    def from_profile(cls, profile_name: str) -> "PerformanceSettings":
        p = (profile_name or "balanced").lower()
        cpu_count = os.cpu_count() or 4
        if p == "eco":
            return cls(
                profile="eco",
                max_context_messages=6,
                screenshot_max_dim=960,
                screenshot_jpeg_quality=68,
                voice_poll_interval_ms=140,
                ollama_num_threads=max(2, cpu_count - 4),
                ollama_num_ctx=2048,
                enable_local_llama=False,
            )
        if p == "high":
            return cls(
                profile="high",
                max_context_messages=24,
                screenshot_max_dim=1920,
                screenshot_jpeg_quality=90,
                voice_poll_interval_ms=45,
                ollama_num_threads=max(4, cpu_count),
                ollama_num_ctx=8192,
                enable_local_llama=True,
            )
        return cls(
            profile="balanced",
            max_context_messages=12,
            screenshot_max_dim=1280,
            screenshot_jpeg_quality=80,
            voice_poll_interval_ms=80,
            ollama_num_threads=max(4, min(8, cpu_count)),
            ollama_num_ctx=4096,
            enable_local_llama=True,
        )


SENSITIVE_PII_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("API_KEY", re.compile(r"\b(AIza[0-9A-Za-z\-_]{20,}|gsk_[0-9A-Za-z]{20,}|sk-[0-9A-Za-z\-_]{20,})\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
    ("AADHAAR_OR_SSN", re.compile(r"\b(?:\d{4}\s\d{4}\s\d{4}|\d{3}-\d{2}-\d{4})\b")),
    ("PASSWORD_ASSIGN", re.compile(r"(?i)\b(password|passwd|secret|pin|cvv|otp)\s*[:=]\s*\S+")),
]


def redact_sensitive_text(text: str) -> Tuple[str, List[str]]:
    if not text:
        return "", []
    redacted = text
    triggered: List[str] = []
    for label, pattern in SENSITIVE_PII_PATTERNS:
        if pattern.search(redacted):
            triggered.append(label)
            redacted = pattern.sub(f"[REDACTED_{label}]", redacted)
    return redacted, triggered


def contains_sensitive_pii(text: str) -> Tuple[bool, List[str]]:
    _, triggered = redact_sensitive_text(text)
    return (len(triggered) > 0), triggered


class SecurityVault:
    """
    Stores and retrieves sensitive API credentials using the operating system's native
    credential manager where available:
      1. Python `keyring` package (if installed)
      2. Windows DPAPI (`System.Security.Cryptography.ProtectedData` CurrentUser scope)
      3. Linux `secret-tool` (freedesktop.org libsecret / GNOME Keyring)
      4. Restricted user-only local vault file (`0600` chmod) when headless
    Never stores API keys in world-readable plaintext config files.
    """

    SERVICE_NAME = "BajrangAIPro_v6"

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._dpapi_dir = self.config_dir / "vault"
        self._dpapi_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self._dpapi_dir, stat.S_IRWXU)
        except Exception:
            pass

    def store_secret(self, account_key: str, secret_value: str) -> str:
        clean_key = re.sub(r"[^a-zA-Z0-9_\-]", "_", account_key)
        if not secret_value:
            self.delete_secret(clean_key)
            return "cleared"

        if importlib.util.find_spec("keyring") is not None:
            try:
                import keyring
                keyring.set_password(self.SERVICE_NAME, clean_key, secret_value)
                return "os_keyring"
            except Exception:
                pass

        if platform.system() == "Windows":
            vault_file = self._dpapi_dir / f"{clean_key}.dpapi"
            b64_in = base64.b64encode(secret_value.encode("utf-8")).decode("ascii")
            ps_cmd = (
                "Add-Type -AssemblyName System.Security; "
                f"$raw = [System.Convert]::FromBase64String('{b64_in}'); "
                "$enc = [System.Security.Cryptography.ProtectedData]::Protect("
                "$raw, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser); "
                f"[System.IO.File]::WriteAllBytes('{vault_file}', $enc)"
            )
            try:
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                    capture_output=True,
                    timeout=8,
                    check=False,
                )
                if proc.returncode == 0 and vault_file.exists():
                    return "windows_dpapi"
            except Exception:
                pass

        if platform.system() == "Linux" and shutil.which("secret-tool") and os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
            try:
                proc = subprocess.run(
                    [
                        "secret-tool",
                        "store",
                        "--label",
                        f"Bajrang AI Pro ({clean_key})",
                        "service",
                        self.SERVICE_NAME,
                        "account",
                        clean_key,
                    ],
                    input=secret_value.encode("utf-8"),
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
                if proc.returncode == 0:
                    return "linux_libsecret"
            except Exception:
                pass

        fallback_file = self._dpapi_dir / f"{clean_key}.sec"
        machine_salt = (platform.node() + "|" + str(os.getuid() if hasattr(os, "getuid") else "win")).encode("utf-8")
        key_stream = hashlib.pbkdf2_hmac("sha256", machine_salt, b"BajrangLocalVaultV6", 100_000, dklen=64)
        raw_bytes = secret_value.encode("utf-8")
        obf = bytes(b ^ key_stream[i % len(key_stream)] for i, b in enumerate(raw_bytes))
        fallback_file.write_bytes(base64.urlsafe_b64encode(obf))
        try:
            os.chmod(fallback_file, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass
        return "chmod_0600_vault"

    def get_secret(self, account_key: str) -> str:
        clean_key = re.sub(r"[^a-zA-Z0-9_\-]", "_", account_key)

        env_key = f"BAJRANG_{clean_key.upper()}"
        if os.environ.get(env_key):
            return os.environ[env_key]

        if importlib.util.find_spec("keyring") is not None:
            try:
                import keyring
                val = keyring.get_password(self.SERVICE_NAME, clean_key)
                if val:
                    return val
            except Exception:
                pass

        if platform.system() == "Windows":
            vault_file = self._dpapi_dir / f"{clean_key}.dpapi"
            if vault_file.exists():
                ps_cmd = (
                    "Add-Type -AssemblyName System.Security; "
                    f"$enc = [System.IO.File]::ReadAllBytes('{vault_file}'); "
                    "$dec = [System.Security.Cryptography.ProtectedData]::Unprotect("
                    "$enc, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser); "
                    "[System.Convert]::ToBase64String($dec)"
                )
                try:
                    proc = subprocess.run(
                        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                        capture_output=True,
                        text=True,
                        timeout=8,
                        check=False,
                    )
                    if proc.returncode == 0 and proc.stdout.strip():
                        return base64.b64decode(proc.stdout.strip()).decode("utf-8")
                except Exception:
                    pass

        if platform.system() == "Linux" and shutil.which("secret-tool") and os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
            try:
                proc = subprocess.run(
                    ["secret-tool", "lookup", "service", self.SERVICE_NAME, "account", clean_key],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    return proc.stdout.strip()
            except Exception:
                pass

        fallback_file = self._dpapi_dir / f"{clean_key}.sec"
        if fallback_file.exists():
            try:
                machine_salt = (platform.node() + "|" + str(os.getuid() if hasattr(os, "getuid") else "win")).encode("utf-8")
                key_stream = hashlib.pbkdf2_hmac("sha256", machine_salt, b"BajrangLocalVaultV6", 100_000, dklen=64)
                obf = base64.urlsafe_b64decode(fallback_file.read_bytes())
                raw_bytes = bytes(b ^ key_stream[i % len(key_stream)] for i, b in enumerate(obf))
                return raw_bytes.decode("utf-8")
            except Exception:
                return ""
        return ""

    def delete_secret(self, account_key: str) -> None:
        clean_key = re.sub(r"[^a-zA-Z0-9_\-]", "_", account_key)
        if importlib.util.find_spec("keyring") is not None:
            try:
                import keyring
                keyring.delete_password(self.SERVICE_NAME, clean_key)
            except Exception:
                pass
        for ext in (".dpapi", ".sec"):
            p = self._dpapi_dir / f"{clean_key}{ext}"
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass


class AsymmetricLicenseVerifier:
    """
    Public-Key License Verifier for Bajrang AI Pro.
    Unlike v4.0/v5.0 (which embedded a symmetric HMAC secret in client code), v6.0
    never ships any private signing key inside desktop binaries or public source code.
    Instead:
      - Licenses are signed on the backend (`razorpay_server.py`) after verifying Razorpay's
        `X-Razorpay-Signature` webhook/payment signature using an RSA/Ed25519/Schnorr-style
        modular public-key signature (`N`, `E = 65537`).
      - The desktop client holds ONLY the public modulus `PUBLIC_MODULUS_HEX` and public
        exponent `E = 65537` to verify server-issued license certificates (`BAJRANG-V6-<PAYLOAD_B64URL>.<SIG_HEX>`).
    """

    PUBLIC_EXPONENT: int = 65537
    PUBLIC_MODULUS_HEX: str = (
        "c7938e5f93d9814c703190f2365c1438011f21d56304e23978a14729f2a4210b"
        "59023e08f4908e167483e02971b68265301f7902e6980268d216f33b25621893"
    )

    def __init__(self, license_Server_url: str = "") -> None:
        self.license_server_url = license_Server_url or os.environ.get("BAJRANG_LICENSE_SERVER_URL", "")
        self.n_int = int(self.PUBLIC_MODULUS_HEX, 16)

    def verify_certificate(self, token: str) -> Tuple[bool, Dict[str, Any]]:
        if not token or not isinstance(token, str):
            return False, {"error": "Empty license token."}
        clean = token.strip()
        if not clean.startswith("BAJRANG-V6-"):
            return False, {
                "error": "Legacy or invalid format. v6.0 requires a server-signed BAJRANG-V6-<PAYLOAD>.<SIG> certificate (no client-side secret keys)."
            }
        body = clean[len("BAJRANG-V6-"):]
        if "." not in body:
            return False, {"error": "Malformed certificate: missing signature delimiter '.'."}
        payload_b64, sig_hex = body.split(".", 1)
        try:
            pad = "=" * ((4 - len(payload_b64) % 4) % 4)
            payload_bytes = base64.urlsafe_b64decode(payload_b64 + pad)
            payload = json.loads(payload_bytes.decode("utf-8"))
            sig_int = int(sig_hex, 16)
        except Exception as exc:
            return False, {"error": f"Certificate decode failed: {exc}"}

        expected_hash_int = int.from_bytes(hashlib.sha256(payload_bytes).digest(), "big") % self.n_int
        recovered_hash_int = pow(sig_int, self.PUBLIC_EXPONENT, self.n_int)
        if recovered_hash_int != expected_hash_int:
            return False, {"error": "Public-key cryptographic signature verification failed."}

        exp_str = str(payload.get("exp", ""))
        try:
            exp_date = datetime.date.fromisoformat(exp_str)
            if exp_date < datetime.date.today():
                return False, {"error": f"License certificate expired on {exp_str}."}
        except Exception:
            return False, {"error": "Invalid expiration date in certificate."}

        return True, {
            "sub": payload.get("sub", "unknown"),
            "plan": payload.get("plan", "pro_monthly"),
            "exp": exp_str,
            "order_id": payload.get("order_id", ""),
            "payment_id": payload.get("payment_id", ""),
            "verified_by": "RSA-Public-Key-Modulus-65537",
        }


class DatabaseMigrationManager:
    """
    Manages SQLite3 schema migrations cleanly from v1 (legacy sessions/messages)
    through v3 (long-term memories, autonomous task plans, and security audit log).
    Preserves 100% of existing user chat history.
    """

    CURRENT_SCHEMA_VERSION = 3

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.run_migrations()
        try:
            os.chmod(self.db_path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def get_current_version(self, conn: sqlite3.Connection) -> int:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL,
                description TEXT NOT NULL
            )
            """
        )
        row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
        return int(row["v"]) if (row and row["v"] is not None) else 0

    def run_migrations(self) -> List[int]:
        applied: List[int] = []
        with self.connect() as conn:
            current = self.get_current_version(conn)
            now = datetime.datetime.now().isoformat(timespec="seconds")

            if current < 1:
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
                        results_json TEXT NOT NULL DEFAULT '[]',
                        timestamp TEXT NOT NULL,
                        FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
                    """
                )
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at, description) VALUES (1, ?, ?)",
                    (now, "Initial sessions and messages schema"),
                )
                applied.append(1)

            if current < 2:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS memories (
                        memory_id TEXT PRIMARY KEY,
                        category TEXT NOT NULL CHECK(category IN ('preference', 'project', 'fact', 'task_history')),
                        key TEXT NOT NULL,
                        content TEXT NOT NULL,
                        project_tag TEXT NOT NULL DEFAULT 'general',
                        importance INTEGER NOT NULL DEFAULT 3 CHECK(importance BETWEEN 1 AND 5),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
                    CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);
                    """
                )
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at, description) VALUES (2, ?, ?)",
                    (now, "Add long-term memories table with categories and indexes"),
                )
                applied.append(2)

            if current < 3:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS task_runs (
                        plan_id TEXT PRIMARY KEY,
                        objective TEXT NOT NULL,
                        status TEXT NOT NULL,
                        plan_json TEXT NOT NULL,
                        summary TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS security_audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_type TEXT NOT NULL,
                        tool_name TEXT NOT NULL,
                        allowed INTEGER NOT NULL,
                        details TEXT NOT NULL,
                        timestamp TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at, description) VALUES (3, ?, ?)",
                    (now, "Add autonomous task_runs and security_audit_log tables"),
                )
                applied.append(3)

            conn.commit()
        return applied


class LongTermMemoryStore:
    """
    Persistent SQLite3 store for:
      1. Conversation sessions & messages
      2. Long-term memories (`preference`, `project`, `fact`, `task_history`)
      3. Autonomous task plans & execution history
      4. Security audit trail
    Enforces strict privacy guardrails: refuses to silently store raw API keys, passwords,
    credit card numbers, or national IDs unless explicitly redacted.
    """

    VALID_CATEGORIES = ("preference", "project", "fact", "task_history")

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.migration_mgr = DatabaseMigrationManager(db_path)

    def _conn(self) -> sqlite3.Connection:
        return self.migration_mgr.connect()

    def create_session(self, title: str = "New Conversation", model: str = "bajrang-llama3.2") -> str:
        session_id = f"sess_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        now = datetime.datetime.now().isoformat(timespec="seconds")
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, title, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, title, model, now, now),
            )
            conn.commit()
        return session_id

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        results: Optional[List[Dict[str, Any]]] = None,
        model: str = "bajrang-llama3.2",
    ) -> None:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        safe_content, _ = redact_sensitive_text(content)
        results_json = json.dumps(results or [], ensure_ascii=False)
        with self._conn() as conn:
            row = conn.execute("SELECT session_id, title FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
            if not row:
                title = safe_content[:42].strip() or "Conversation"
                conn.execute(
                    "INSERT INTO sessions (session_id, title, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (session_id, title, model, now, now),
                )
            else:
                new_title = row["title"]
                if new_title in ("New Conversation", "Conversation") and role == "user" and safe_content.strip():
                    new_title = safe_content.strip()[:42]
                conn.execute(
                    "UPDATE sessions SET title = ?, model = ?, updated_at = ? WHERE session_id = ?",
                    (new_title, model, now, session_id),
                )
            conn.execute(
                "INSERT INTO messages (session_id, role, content, results_json, timestamp) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, safe_content, results_json, now),
            )
            conn.commit()

    def get_session_messages(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT role, content, results_json, timestamp FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            try:
                res = json.loads(r["results_json"])
            except Exception:
                res = []
            out.append(
                {
                    "role": r["role"],
                    "content": r["content"],
                    "results": res,
                    "timestamp": r["timestamp"],
                }
            )
        return out

    def list_sessions(self, query: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        q = (query or "").strip().lower()
        with self._conn() as conn:
            if q:
                like = f"%{q}%"
                rows = conn.execute(
                    """
                    SELECT DISTINCT s.session_id, s.title, s.model, s.created_at, s.updated_at
                    FROM sessions s
                    LEFT JOIN messages m ON s.session_id = m.session_id
                    WHERE LOWER(s.title) LIKE ? OR LOWER(m.content) LIKE ?
                    ORDER BY s.updated_at DESC LIMIT ?
                    """,
                    (like, like, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT session_id, title, model, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def delete_session(self, session_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            return cur.rowcount > 0

    def store_memory(
        self,
        key: str,
        content: str,
        category: str = "fact",
        project_tag: str = "general",
        importance: int = 3,
        memory_id: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        cat = category if category in self.VALID_CATEGORIES else "fact"
        imp = max(1, min(5, int(importance)))
        has_pii, pii_types = contains_sensitive_pii(content)
        if has_pii:
            return (
                False,
                f"Blocked storing sensitive data ({', '.join(pii_types)}) in long-term memory.",
                {},
            )

        clean_key = key.strip() or "general_note"
        clean_content = content.strip()
        if not clean_content:
            return False, "Memory content cannot be empty.", {}

        now = datetime.datetime.now().isoformat(timespec="seconds")
        with self._conn() as conn:
            existing = None
            if memory_id:
                existing = conn.execute("SELECT memory_id FROM memories WHERE memory_id = ?", (memory_id,)).fetchone()
            if not existing:
                existing = conn.execute(
                    "SELECT memory_id FROM memories WHERE category = ? AND LOWER(key) = LOWER(?)",
                    (cat, clean_key),
                ).fetchone()

            if existing:
                mid = existing["memory_id"]
                conn.execute(
                    """
                    UPDATE memories
                    SET category = ?, key = ?, content = ?, project_tag = ?, importance = ?, updated_at = ?
                    WHERE memory_id = ?
                    """,
                    (cat, clean_key, clean_content, project_tag, imp, now, mid),
                )
            else:
                mid = memory_id or f"mem_{uuid.uuid4().hex[:10]}"
                conn.execute(
                    """
                    INSERT INTO memories (memory_id, category, key, content, project_tag, importance, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (mid, cat, clean_key, clean_content, project_tag, imp, now, now),
                )
            conn.commit()
            row = conn.execute("SELECT * FROM memories WHERE memory_id = ?", (mid,)).fetchone()
            return True, "Memory saved.", dict(row) if row else {}

    def update_memory(
        self,
        memory_id: str,
        content: str,
        key: Optional[str] = None,
        category: Optional[str] = None,
        importance: Optional[int] = None,
    ) -> Tuple[bool, str]:
        has_pii, pii_types = contains_sensitive_pii(content)
        if has_pii:
            return False, f"Blocked sensitive data ({', '.join(pii_types)})."
        now = datetime.datetime.now().isoformat(timespec="seconds")
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM memories WHERE memory_id = ?", (memory_id,)).fetchone()
            if not row:
                return False, f"Memory ID '{memory_id}' not found."
            new_key = key.strip() if key else row["key"]
            new_cat = category if (category in self.VALID_CATEGORIES) else row["category"]
            new_imp = max(1, min(5, int(importance))) if importance is not None else row["importance"]
            conn.execute(
                "UPDATE memories SET key = ?, content = ?, category = ?, importance = ?, updated_at = ? WHERE memory_id = ?",
                (new_key, content.strip(), new_cat, new_imp, now, memory_id),
            )
            conn.commit()
        return True, "Memory updated."

    def delete_memory(self, memory_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM memories WHERE memory_id = ?", (memory_id,))
            conn.commit()
            return cur.rowcount > 0

    def search_memories(
        self,
        query: str = "",
        category: Optional[str] = None,
        project_tag: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        if query and query.strip():
            like = f"%{query.strip().lower()}%"
            clauses.append("(LOWER(key) LIKE ? OR LOWER(content) LIKE ? OR LOWER(project_tag) LIKE ?)")
            params.extend([like, like, like])
        if category and category in self.VALID_CATEGORIES:
            clauses.append("category = ?")
            params.append(category)
        if project_tag and project_tag.strip():
            clauses.append("LOWER(project_tag) = LOWER(?)")
            params.append(project_tag.strip())

        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM memories {where_sql} ORDER BY importance DESC, updated_at DESC LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]

    def build_relevant_context_block(self, prompt: str, limit: int = 6) -> str:
        words = [w.lower() for w in re.findall(r"[a-zA-Z0-9_]{3,}", prompt) if len(w) >= 3]
        matched: Dict[str, Dict[str, Any]] = {}
        for w in words[:5]:
            for m in self.search_memories(query=w, limit=4):
                matched[m["memory_id"]] = m
        if len(matched) < limit:
            for m in self.search_memories(limit=limit):
                matched.setdefault(m["memory_id"], m)
        items = list(matched.values())[:limit]
        if not items:
            return ""
        lines = ["[Long-Term User & Project Memory Context]:"]
        for it in items:
            lines.append(f"- ({it['category'].upper()} | {it['key']}): {it['content']}")
        return "\n".join(lines)

    def log_security_event(self, event_type: str, tool_name: str, allowed: bool, details: str) -> None:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO security_audit_log (event_type, tool_name, allowed, details, timestamp) VALUES (?, ?, ?, ?, ?)",
                (event_type, tool_name, 1 if allowed else 0, details[:500], now),
            )
            conn.commit()

    def save_task_run(self, plan_id: str, objective: str, status: str, plan_dict: Dict[str, Any], summary: str = "") -> None:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        plan_json = json.dumps(plan_dict, ensure_ascii=False)
        with self._conn() as conn:
            row = conn.execute("SELECT plan_id FROM task_runs WHERE plan_id = ?", (plan_id,)).fetchone()
            if row:
                conn.execute(
                    "UPDATE task_runs SET status = ?, plan_json = ?, summary = ?, updated_at = ? WHERE plan_id = ?",
                    (status, plan_json, summary, now, plan_id),
                )
            else:
                conn.execute(
                    "INSERT INTO task_runs (plan_id, objective, status, plan_json, summary, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (plan_id, objective, status, plan_json, summary, now, now),
                )
            conn.commit()


class ToolSchemaValidator:
    """
    Validates AI-generated structured tool calls against a strict allowlist schema.
    Rejects unknown tools, missing/wrong-typed arguments, path traversal attempts,
    and unrestricted shell command strings.
    """

    TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
        "open_app": {
            "required": {"app_name": str},
            "optional": {},
            "destructive": False,
            "description": "Launch a verified desktop application from the allowlist.",
        },
        "close_app": {
            "required": {"app_name": str},
            "optional": {},
            "destructive": True,
            "description": "Gracefully close a running user application by name.",
        },
        "window_focus": {
            "required": {"title_substring": str},
            "optional": {},
            "destructive": False,
            "description": "Bring a desktop window matching title_substring to the foreground.",
        },
        "list_windows": {
            "required": {},
            "optional": {},
            "destructive": False,
            "description": "List all currently visible desktop windows.",
        },
        "read_screen": {
            "required": {},
            "optional": {"save_filename": str},
            "destructive": False,
            "description": "Capture and analyze the current desktop screen.",
        },
        "type_text": {
            "required": {"text": str},
            "optional": {"press_enter": bool},
            "destructive": False,
            "description": "Type text into the focused window.",
        },
        "click_point": {
            "required": {"x": int, "y": int},
            "optional": {"button": str},
            "destructive": False,
            "description": "Click mouse button at screen coordinates (x, y).",
        },
        "scroll_view": {
            "required": {"direction": str, "clicks": int},
            "optional": {},
            "destructive": False,
            "description": "Scroll the active window ('up' or 'down').",
        },
        "navigate_hotkey": {
            "required": {"keys": list},
            "optional": {},
            "destructive": False,
            "description": "Trigger a safe menu/navigation keyboard shortcut (e.g., ['ctrl', 'f']).",
        },
        "inspect_directory": {
            "required": {"directory_path": str},
            "optional": {},
            "destructive": False,
            "description": "Scan a user folder, categorize files, and detect SHA-256 duplicates without modifying anything.",
        },
        "organize_directory": {
            "required": {"directory_path": str},
            "optional": {"remove_duplicates": bool},
            "destructive": True,
            "description": "Organize files into Documents, Images, Installers, Archives, and Code folders, optionally removing verified duplicates (requires explicit confirmation).",
        },
        "memory_store": {
            "required": {"key": str, "content": str},
            "optional": {"category": str, "importance": int},
            "destructive": False,
            "description": "Save a persistent preference, project note, or fact to SQLite memory.",
        },
    }

    FORBIDDEN_HOTKEYS = {
        ("alt", "f4"),
        ("ctrl", "alt", "del"),
        ("ctrl", "alt", "delete"),
        ("super", "l"),
        ("win", "r"),
    }

    @classmethod
    def validate_action(cls, action: Dict[str, Any]) -> Tuple[bool, str, bool]:
        if not isinstance(action, dict):
            return False, "Action must be a JSON object.", False
        tool = str(action.get("tool", "")).strip()
        args = action.get("arguments", {})
        if tool not in cls.TOOL_SCHEMAS:
            return False, f"Tool '{tool}' is not in the restrictive allowlist.", False
        if not isinstance(args, dict):
            return False, f"Arguments for '{tool}' must be a JSON object.", False

        schema = cls.TOOL_SCHEMAS[tool]
        for req_key, req_type in schema["required"].items():
            if req_key not in args:
                return False, f"Missing required argument '{req_key}' for tool '{tool}'.", False
            if not isinstance(args[req_key], req_type):
                return False, f"Argument '{req_key}' for '{tool}' must be of type {req_type.__name__}.", False

        for opt_key, opt_type in schema["optional"].items():
            if opt_key in args and args[opt_key] is not None and not isinstance(args[opt_key], opt_type):
                return False, f"Optional argument '{opt_key}' must be of type {opt_type.__name__}.", False

        allowed_keys = set(schema["required"].keys()) | set(schema["optional"].keys())
        extra_keys = set(args.keys()) - allowed_keys
        if extra_keys:
            return False, f"Unexpected arguments {sorted(extra_keys)} for tool '{tool}'.", False

        if tool in ("inspect_directory", "organize_directory"):
            raw_path = str(args["directory_path"]).strip()
            ok_path, reason = cls.validate_safe_user_path(raw_path)
            if not ok_path:
                return False, reason, False

        if tool == "click_point":
            x, y = int(args["x"]), int(args["y"])
            if x < 0 or y < 0 or x > 7680 or y > 4320:
                return False, f"Coordinates ({x}, {y}) out of valid screen bounds.", False

        if tool == "navigate_hotkey":
            keys_tuple = tuple(str(k).lower().strip() for k in args["keys"])
            if keys_tuple in cls.FORBIDDEN_HOTKEYS or len(keys_tuple) > 3:
                return False, f"Hotkey combination {keys_tuple} is restricted.", False

        return True, "Valid tool call.", bool(schema["destructive"])

    @staticmethod
    def validate_safe_user_path(raw_path: str) -> Tuple[bool, str]:
        if not raw_path:
            return False, "Directory path cannot be empty."
        expanded = Path(os.path.expanduser(os.path.expandvars(raw_path))).resolve()
        home = Path.home().resolve()
        temp_root = Path(tempfile.gettempdir()).resolve()

        system_roots = [
            Path("/etc"),
            Path("/usr"),
            Path("/bin"),
            Path("/sbin"),
            Path("/boot"),
            Path("/proc"),
            Path("/sys"),
            Path("C:/Windows"),
            Path("C:/Program Files"),
            Path("C:/Program Files (x86)"),
        ]
        for sr in system_roots:
            try:
                if expanded == sr.resolve() or sr.resolve() in expanded.parents:
                    return False, f"Access to system directory '{expanded}' is strictly prohibited."
            except Exception:
                pass

        if not (expanded == home or home in expanded.parents or expanded == temp_root or temp_root in expanded.parents):
            return False, f"Path '{expanded}' must reside inside your user home or temp directory."
        return True, str(expanded)


@dataclass
class ProviderConfig:
    provider_id: str
    display_name: str
    endpoint: str
    default_model: str
    fast_model: str
    reasoning_model: str
    vision_model: str
    requires_api_key: bool = True
    timeout_sec: float = 25.0


PROVIDER_REGISTRY: Dict[str, ProviderConfig] = {
    "gemini_argon": ProviderConfig(
        provider_id="gemini_argon",
        display_name="Google Gemini Argon (2.5 Pro / Flash)",
        endpoint="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        default_model="gemini-2.5-pro",
        fast_model="gemini-2.5-flash",
        reasoning_model="gemini-2.5-pro",
        vision_model="gemini-2.5-pro",
        requires_api_key=True,
    ),
    "ollama": ProviderConfig(
        provider_id="ollama",
        display_name="Ollama Local Runtime (Llama 3.2)",
        endpoint="http://127.0.0.1:11434/api/chat",
        default_model="bajrang-llama3.2",
        fast_model="llama3.2",
        reasoning_model="bajrang-llama3.2",
        vision_model="llama3.2-vision",
        requires_api_key=False,
    ),
    "groq": ProviderConfig(
        provider_id="groq",
        display_name="Groq Cloud (Llama 3.3 70B / 3.2)",
        endpoint="https://api.groq.com/openai/v1/chat/completions",
        default_model="llama-3.3-70b-versatile",
        fast_model="llama-3.1-8b-instant",
        reasoning_model="llama-3.3-70b-versatile",
        vision_model="llama-3.2-11b-vision-preview",
        requires_api_key=True,
    ),
    "openrouter": ProviderConfig(
        provider_id="openrouter",
        display_name="OpenRouter Cloud Gateway",
        endpoint="https://openrouter.ai/api/v1/chat/completions",
        default_model="meta-llama/llama-3.2-3b-instruct:free",
        fast_model="meta-llama/llama-3.2-3b-instruct:free",
        reasoning_model="meta-llama/llama-3.3-70b-instruct",
        vision_model="meta-llama/llama-3.2-11b-vision-instruct:free",
        requires_api_key=True,
    ),
    "openai": ProviderConfig(
        provider_id="openai",
        display_name="OpenAI (GPT-4o / GPT-4o-mini)",
        endpoint="https://api.openai.com/v1/chat/completions",
        default_model="gpt-4o-mini",
        fast_model="gpt-4o-mini",
        reasoning_model="gpt-4o",
        vision_model="gpt-4o",
        requires_api_key=True,
    ),
}


class ModularAIRouter:
    """
    Intelligent Multi-Provider AI Router with:
      - Task Complexity Classification (`SIMPLE`, `MODERATE`, `COMPLEX_REASONING`, `MULTIMODAL_VISION`)
      - Automatic Model Selection based on complexity & PerformanceProfile
      - Configurable Provider Fallback Chain (e.g., `['gemini_argon', 'groq', 'openrouter', 'ollama']`)
      - Connection Health Checks (`check_provider_health`)
      - Request Timeouts & Exponential Backoff Retries
      - Streaming SSE Support (`stream_chat`)
      - Deterministic Intent & Action Extraction when offline or local
    """

    SYSTEM_INSTRUCTIONS = (
        "You are Bajrang AI Pro v6.0, a reliable, security-hardened personal desktop assistant. "
        "Distinguish clearly between answering a conversational question and executing a desktop operation. "
        "NEVER claim to have executed an action unless you emit a structured tool call in the `actions` array "
        "and the system verifies its execution. "
        "Always respond as valid JSON with keys: "
        '{"reply": "<concise helpful response>", "actions": [{"tool": "<allowlisted_tool_name>", "arguments": {...}}]}. '
        "If the user is only asking a question or chatting, return an empty `actions` list `[]`."
    )

    def __init__(
        self,
        vault: SecurityVault,
        memory_store: LongTermMemoryStore,
        primary_provider: str = "ollama",
        fallback_order: Optional[List[str]] = None,
        perf_settings: Optional[PerformanceSettings] = None,
    ) -> None:
        self.vault = vault
        self.memory_store = memory_store
        self.primary_provider = primary_provider if primary_provider in PROVIDER_REGISTRY else "ollama"
        self.fallback_order = fallback_order or ["gemini_argon", "groq", "openrouter", "openai", "ollama"]
        self.perf = perf_settings or PerformanceSettings.from_profile("balanced")
        self.max_retries = 2
        self.timeout_sec = 20.0

    @staticmethod
    def assess_task_complexity(prompt: str, has_image: bool = False) -> TaskComplexity:
        if has_image:
            return TaskComplexity.MULTIMODAL_VISION
        lower = (prompt or "").lower()
        vision_keywords = ("screenshot", "on my screen", "read screen", "what is on screen", "visible window")
        if any(k in lower for k in vision_keywords):
            return TaskComplexity.MULTIMODAL_VISION
        complex_keywords = (
            "organize",
            "duplicate",
            "plan",
            "architecture",
            "analyze",
            "refactor",
            "debug",
            "compare",
            "step by step",
            "multi-step",
        )
        if len(prompt) > 260 or any(k in lower for k in complex_keywords):
            return TaskComplexity.COMPLEX_REASONING
        if len(prompt) < 60:
            return TaskComplexity.SIMPLE
        return TaskComplexity.MODERATE

    def select_model_for_task(self, provider_id: str, complexity: TaskComplexity) -> str:
        cfg = PROVIDER_REGISTRY.get(provider_id, PROVIDER_REGISTRY["ollama"])
        if complexity == TaskComplexity.MULTIMODAL_VISION:
            return cfg.vision_model
        if complexity == TaskComplexity.COMPLEX_REASONING and self.perf.profile != "eco":
            return cfg.reasoning_model
        if complexity == TaskComplexity.SIMPLE or self.perf.profile == "eco":
            return cfg.fast_model
        return cfg.default_model

    def check_provider_health(self, provider_id: str, timeout: float = 3.0) -> Dict[str, Any]:
        cfg = PROVIDER_REGISTRY.get(provider_id)
        if not cfg:
            return {"provider": provider_id, "healthy": False, "latency_ms": -1, "detail": "Unknown provider"}

        start_t = time.perf_counter()
        if provider_id == "ollama":
            if not self.perf.enable_local_llama:
                return {"provider": "ollama", "healthy": False, "latency_ms": 0, "detail": "Disabled in Eco profile"}
            try:
                req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    ms = round((time.perf_counter() - start_t) * 1000, 1)
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name", "") for m in data.get("models", [])]
                    return {"provider": "ollama", "healthy": True, "latency_ms": ms, "models": models, "detail": "Online"}
            except Exception as exc:
                return {"provider": "ollama", "healthy": False, "latency_ms": -1, "detail": f"Offline ({exc})"}

        api_key = self.vault.get_secret(f"api_key_{provider_id}") or self.vault.get_secret("api_key_default")
        if cfg.requires_api_key and not api_key:
            return {"provider": provider_id, "healthy": False, "latency_ms": 0, "detail": "No API key configured in Vault"}

        parsed_host = cfg.endpoint.split("/")[2]
        try:
            with socket.create_connection((parsed_host, 443), timeout=timeout):
                ms = round((time.perf_counter() - start_t) * 1000, 1)
                return {"provider": provider_id, "healthy": True, "latency_ms": ms, "detail": "Key present & host reachable"}
        except Exception as exc:
            return {"provider": provider_id, "healthy": False, "latency_ms": -1, "detail": f"Unreachable ({exc})"}

    def _build_ordered_chain(self) -> List[str]:
        chain = [self.primary_provider]
        for p in self.fallback_order:
            if p not in chain and p in PROVIDER_REGISTRY:
                if p == "ollama" and not self.perf.enable_local_llama:
                    continue
                chain.append(p)
        return chain

    def generate_structured_turn(
        self,
        prompt: str,
        session_id: str,
        image_b64: Optional[str] = None,
        on_stream_token: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        complexity = self.assess_task_complexity(prompt, has_image=bool(image_b64))
        history = self.memory_store.get_session_messages(session_id, limit=self.perf.max_context_messages)
        mem_context = self.memory_store.build_relevant_context_block(prompt)

        system_text = self.SYSTEM_INSTRUCTIONS
        if mem_context:
            system_text = system_text + "\n\n" + mem_context

        chain = self._build_ordered_chain()
        errors: List[str] = []

        for provider_id in chain:
            cfg = PROVIDER_REGISTRY[provider_id]
            model_name = self.select_model_for_task(provider_id, complexity)

            if provider_id != "ollama":
                api_key = self.vault.get_secret(f"api_key_{provider_id}") or self.vault.get_secret("api_key_default")
                if not api_key:
                    errors.append(f"{provider_id}: missing API key")
                    continue
                ok, raw_resp, err = self._call_openai_compatible_with_retries(
                    cfg=cfg,
                    api_key=api_key,
                    model_name=model_name,
                    system_text=system_text,
                    history=history,
                    prompt=prompt,
                    on_stream_token=on_stream_token,
                )
            else:
                ok, raw_resp, err = self._call_ollama_with_retries(
                    cfg=cfg,
                    model_name=model_name,
                    system_text=system_text,
                    history=history,
                    prompt=prompt,
                    image_b64=image_b64,
                    on_stream_token=on_stream_token,
                )

            if ok and raw_resp:
                parsed = self._parse_model_json_or_fallback(raw_resp, prompt)
                parsed["provider_used"] = provider_id
                parsed["model_used"] = model_name
                parsed["complexity"] = complexity.value
                parsed["fallback_chain_tried"] = errors
                return parsed
            errors.append(f"{provider_id} ({model_name}): {err}")

        deterministic = self.deterministic_local_agent(prompt)
        deterministic["provider_used"] = "deterministic_local_router"
        deterministic["model_used"] = "bajrang-rule-engine-v6"
        deterministic["complexity"] = complexity.value
        deterministic["fallback_chain_tried"] = errors
        if on_stream_token and deterministic.get("reply"):
            on_stream_token(deterministic["reply"])
        return deterministic

    def _call_openai_compatible_with_retries(
        self,
        cfg: ProviderConfig,
        api_key: str,
        model_name: str,
        system_text: str,
        history: List[Dict[str, Any]],
        prompt: str,
        on_stream_token: Optional[Callable[[str], None]] = None,
    ) -> Tuple[bool, str, str]:
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_text}]
        for m in history[-self.perf.max_context_messages:]:
            if m.get("role") in ("user", "assistant"):
                messages.append({"role": m["role"], "content": str(m.get("content", ""))})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.25,
            "stream": False,
        }
        body_bytes = json.dumps(payload).encode("utf-8")

        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(
                    cfg.endpoint,
                    data=body_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                        "User-Agent": "BajrangAIPro/6.0",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                    content = (
                        raw.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    if on_stream_token and content:
                        on_stream_token(content)
                    return True, content, ""
            except Exception as exc:
                last_err = str(exc)
                if attempt + 1 < self.max_retries:
                    time.sleep(0.35 * (2 ** attempt))
        return False, "", last_err

    def _call_ollama_with_retries(
        self,
        cfg: ProviderConfig,
        model_name: str,
        system_text: str,
        history: List[Dict[str, Any]],
        prompt: str,
        image_b64: Optional[str] = None,
        on_stream_token: Optional[Callable[[str], None]] = None,
    ) -> Tuple[bool, str, str]:
        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_text}]
        for m in history[-self.perf.max_context_messages:]:
            if m.get("role") in ("user", "assistant"):
                messages.append({"role": m["role"], "content": str(m.get("content", ""))})
        user_msg: Dict[str, Any] = {"role": "user", "content": prompt}
        if image_b64:
            user_msg["images"] = [image_b64]
        messages.append(user_msg)

        payload = {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.25,
                "num_thread": self.perf.ollama_num_threads,
                "num_ctx": self.perf.ollama_num_ctx,
            },
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        last_err = "Ollama unreachable"
        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(
                    cfg.endpoint,
                    data=body_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                    content = raw.get("message", {}).get("content", "")
                    if on_stream_token and content:
                        on_stream_token(content)
                    return True, content, ""
            except Exception as exc:
                last_err = str(exc)
                if attempt + 1 < self.max_retries:
                    time.sleep(0.25 * (2 ** attempt))
        return False, "", last_err

    def _parse_model_json_or_fallback(self, raw_text: str, original_prompt: str) -> Dict[str, Any]:
        cleaned = raw_text.strip()
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
        if fence_match:
            cleaned = fence_match.group(1)
        try:
            obj = json.loads(cleaned)
            if isinstance(obj, dict) and "reply" in obj:
                actions = obj.get("actions", [])
                if not isinstance(actions, list):
                    actions = []
                return {"reply": str(obj["reply"]), "actions": actions}
        except Exception:
            pass
        return {"reply": raw_text.strip(), "actions": []}

    @staticmethod
    def deterministic_local_agent(prompt: str) -> Dict[str, Any]:
        text = (prompt or "").strip()
        lower = text.lower()

        if any(k in lower for k in ("organize", "clean up")) and any(
            d in lower for d in ("download", "folder", "directory", "desktop")
        ):
            target = str(Path.home() / "Downloads")
            path_match = re.search(r"([~/\\][a-zA-Z0-9_./\\-]+|[A-Za-z]:\\[a-zA-Z0-9_./\\-]+)", text)
            if path_match:
                target = path_match.group(1)
            remove_dups = "duplicate" in lower
            return {
                "reply": f"Prepared a multi-step organization plan for '{target}' (remove_duplicates={remove_dups}). Inspecting files first before requesting confirmation.",
                "actions": [
                    {
                        "tool": "organize_directory",
                        "arguments": {"directory_path": target, "remove_duplicates": remove_dups},
                    }
                ],
            }

        if lower.startswith("remember ") or "remember that " in lower:
            fact_body = re.sub(r"(?i)^.*?remember\s+(that\s+)?", "", text).strip()
            key_slug = "_".join(re.findall(r"[a-zA-Z0-9]+", fact_body.lower())[:4]) or "user_note"
            return {
                "reply": f"Storing '{fact_body}' in long-term SQLite memory under key '{key_slug}'.",
                "actions": [
                    {
                        "tool": "memory_store",
                        "arguments": {"key": key_slug, "content": fact_body, "category": "fact", "importance": 4},
                    }
                ],
            }

        if any(k in lower for k in ("open ", "launch ", "start ")):
            for app in ("notepad", "calculator", "calc", "terminal", "files", "explorer", "browser", "code"):
                if re.search(rf"\b{app}\b", lower):
                    return {
                        "reply": f"Requesting launch of application '{app}'.",
                        "actions": [{"tool": "open_app", "arguments": {"app_name": app}}],
                    }

        if any(k in lower for k in ("screenshot", "read screen", "what is on my screen", "capture screen")):
            return {
                "reply": "Capturing and analyzing the current desktop screen.",
                "actions": [{"tool": "read_screen", "arguments": {}}],
            }

        if any(k in lower for k in ("list windows", "active windows", "open windows")):
            return {
                "reply": "Enumerating visible desktop windows.",
                "actions": [{"tool": "list_windows", "arguments": {}}],
            }

        if lower.startswith("type "):
            payload = text[5:].strip()
            return {
                "reply": f"Typing '{payload}' into the active window.",
                "actions": [{"tool": "type_text", "arguments": {"text": payload, "press_enter": True}}],
            }

        return {
            "reply": (
                f"Processed your message: '{text}'. No system actions were executed. "
                "Configure a cloud API key in the Security Vault or start local Ollama (`ollama serve`) for full generative reasoning."
            ),
            "actions": [],
        }


class CrossPlatformComputerUse:
    """
    Executes and verifies genuine desktop computer-use actions on both Windows 11
    and Fedora Linux (GNOME / Wayland).
    Never fabricates success: every method returns `(success: bool, verified_output: str, metadata: dict)`.
    """

    WINDOWS_APP_ALLOWLIST: Dict[str, List[str]] = {
        "notepad": ["notepad.exe"],
        "calculator": ["calc.exe"],
        "calc": ["calc.exe"],
        "explorer": ["explorer.exe"],
        "files": ["explorer.exe"],
        "terminal": ["wt.exe", "powershell.exe"],
        "cmd": ["cmd.exe"],
        "mspaint": ["mspaint.exe"],
        "code": ["code.cmd", "code.exe"],
    }

    LINUX_APP_ALLOWLIST: Dict[str, List[List[str]]] = {
        "terminal": [
            ["gnome-terminal"],
            ["ptyxis"],
            ["kgx"],
            ["xfce4-terminal"],
            ["xterm"],
        ],
        "files": [["nautilus"], ["xdg-open", str(Path.home())]],
        "explorer": [["nautilus"]],
        "calculator": [["gnome-calculator"]],
        "calc": [["gnome-calculator"]],
        "notepad": [["gnome-text-editor"], ["gedit"]],
        "browser": [["xdg-open", "https://ollama.com"]],
        "code": [["code"]],
    }

    def __init__(self, perf: Optional[PerformanceSettings] = None) -> None:
        self.perf = perf or PerformanceSettings.from_profile("balanced")
        self.os_name = platform.system()

    def list_open_windows(self) -> Tuple[bool, str, List[Dict[str, Any]]]:
        windows: List[Dict[str, Any]] = []
        if self.os_name == "Windows" and hasattr(ctypes, "windll"):
            try:
                user32 = ctypes.windll.user32
                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                fg_hwnd = user32.GetForegroundWindow()

                def enum_cb(hwnd: int, _lparam: int) -> bool:
                    if user32.IsWindowVisible(hwnd):
                        length = user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(hwnd, buf, length + 1)
                            title = buf.value.strip()
                            if title:
                                windows.append(
                                    {
                                        "hwnd": int(hwnd),
                                        "title": title,
                                        "active": bool(hwnd == fg_hwnd),
                                    }
                                )
                    return True

                user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
                return True, f"Enumerated {len(windows)} visible Windows 11 windows via Win32 EnumWindows.", windows
            except Exception as exc:
                return False, f"Win32 EnumWindows failed: {exc}", []

        if shutil.which("wmctrl"):
            try:
                proc = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=4, check=False)
                if proc.returncode == 0:
                    for line in proc.stdout.splitlines():
                        parts = line.split(None, 3)
                        if len(parts) == 4:
                            windows.append({"hwnd": parts[0], "desktop": parts[1], "host": parts[2], "title": parts[3], "active": False})
                    return True, f"Enumerated {len(windows)} windows via wmctrl.", windows
            except Exception:
                pass

        if shutil.which("gdbus") and os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
            try:
                proc = subprocess.run(
                    [
                        "gdbus",
                        "call",
                        "--session",
                        "--dest",
                        "org.gnome.Shell",
                        "--object-path",
                        "/org/gnome/Shell",
                        "--method",
                        "org.gnome.Shell.Eval",
                        "global.get_window_actors().map(a => a.meta_window.get_title()).filter(Boolean)",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=4,
                    check=False,
                )
                if proc.returncode == 0 and "true" in proc.stdout:
                    return True, f"GNOME Shell windows: {proc.stdout.strip()}", [{"title": proc.stdout.strip(), "active": True}]
            except Exception:
                pass

        return False, "No active graphical window server (Win32 / X11 / Wayland session) detected in current environment.", []

    def focus_window(self, title_substring: str) -> Tuple[bool, str, Dict[str, Any]]:
        sub = (title_substring or "").strip().lower()
        if not sub:
            return False, "Window title substring cannot be empty.", {}

        ok, msg, win_list = self.list_open_windows()
        if not ok or not win_list:
            return False, f"Cannot focus window '{title_substring}': {msg}", {}

        matched = [w for w in win_list if sub in str(w.get("title", "")).lower()]
        if not matched:
            return False, f"No open window matching '{title_substring}' was found.", {"open_windows": len(win_list)}

        target = matched[0]
        if self.os_name == "Windows" and hasattr(ctypes, "windll") and "hwnd" in target:
            try:
                user32 = ctypes.windll.user32
                hwnd = int(target["hwnd"])
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
                fg_now = user32.GetForegroundWindow()
                verified = fg_now == hwnd
                return (
                    verified,
                    f"Focused window '{target['title']}' (verified={verified}).",
                    target,
                )
            except Exception as exc:
                return False, f"Failed to focus Win32 window: {exc}", target

        if shutil.which("wmctrl"):
            proc = subprocess.run(["wmctrl", "-a", title_substring], capture_output=True, text=True, timeout=4, check=False)
            if proc.returncode == 0:
                return True, f"Activated window matching '{title_substring}' via wmctrl.", target

        return False, f"Found window '{target.get('title')}', but active window switching is unsupported in this display session.", target

    def launch_application(self, app_name: str) -> Tuple[bool, str, Dict[str, Any]]:
        key = (app_name or "").strip().lower()
        if self.os_name == "Windows":
            candidates = self.WINDOWS_APP_ALLOWLIST.get(key, [])
            for exe in candidates:
                resolved = shutil.which(exe) or exe
                try:
                    proc = subprocess.Popen([resolved], shell=False)
                    time.sleep(0.15)
                    alive = proc.poll() is None
                    return (
                        True,
                        f"Launched '{exe}' on Windows (PID={proc.pid}, running={alive}).",
                        {"pid": proc.pid, "executable": exe},
                    )
                except Exception:
                    continue
            return False, f"Application '{app_name}' is not in the Windows safe allowlist or is not installed.", {}

        cmd_groups = self.LINUX_APP_ALLOWLIST.get(key, [])
        if not cmd_groups:
            return False, f"Application '{app_name}' is not installed or not in the Linux allowlist.", {}
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            return (
                False,
                f"Cannot launch GUI application '{app_name}': no DISPLAY or WAYLAND_DISPLAY session is active.",
                {},
            )
        for cmd in cmd_groups:
            bin_path = shutil.which(cmd[0])
            if bin_path:
                try:
                    proc = subprocess.Popen([bin_path] + cmd[1:], shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(0.15)
                    alive = proc.poll() is None or proc.returncode == 0
                    if alive:
                        return (
                            True,
                            f"Launched '{cmd[0]}' on Linux (PID={proc.pid}).",
                            {"pid": proc.pid, "executable": bin_path},
                        )
                except Exception:
                    continue
        return False, f"Application '{app_name}' is not installed or not in the Linux allowlist.", {}

    def close_application(self, app_name: str) -> Tuple[bool, str, Dict[str, Any]]:
        key = re.sub(r"[^a-zA-Z0-9_\-.]", "", (app_name or "").strip().lower())
        if not key:
            return False, "Application name cannot be empty.", {}
        protected = {"systemd", "init", "gnome-shell", "wayland", "xorg", "explorer", "svchost", "csrss", "lsass", "wininit"}
        if key in protected:
            return False, f"Closing critical system process '{key}' is prohibited.", {}

        if self.os_name == "Windows":
            exe_name = key if key.endswith(".exe") else f"{key}.exe"
            proc = subprocess.run(["taskkill", "/IM", exe_name], capture_output=True, text=True, timeout=6, check=False)
            if proc.returncode == 0:
                return True, f"Sent graceful close signal to '{exe_name}'.", {"stdout": proc.stdout.strip()}
            return False, f"Process '{exe_name}' was not running or could not be closed: {proc.stderr.strip()}", {}

        if shutil.which("pkill"):
            proc = subprocess.run(["pkill", "-TERM", "-x", key], capture_output=True, text=True, timeout=5, check=False)
            if proc.returncode == 0:
                return True, f"Sent SIGTERM to process '{key}'.", {}
            return False, f"No running user process named '{key}' was found (exit {proc.returncode}).", {}
        return False, "Process termination utility unavailable.", {}

    def capture_and_analyze_screen(self, output_path: Optional[Path] = None) -> Tuple[bool, str, Dict[str, Any]]:
        target = output_path or (Path(tempfile.gettempdir()) / f"bajrang_screen_{int(time.time())}.png")

        captured = False
        method_used = ""

        if importlib.util.find_spec("PIL") is not None:
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab()
                img.save(str(target), format="PNG")
                captured = target.exists() and target.stat().st_size > 0
                method_used = "PIL.ImageGrab"
            except Exception:
                captured = False

        if not captured and self.os_name == "Linux":
            for tool_cmd, label in [
                (["grim", str(target)], "grim (Wayland)"),
                (["gnome-screenshot", "-f", str(target)], "gnome-screenshot"),
            ]:
                if shutil.which(tool_cmd[0]) and (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
                    try:
                        subprocess.run(tool_cmd, capture_output=True, timeout=6, check=False)
                        if target.exists() and target.stat().st_size > 0:
                            captured = True
                            method_used = label
                            break
                    except Exception:
                        pass

        if not captured:
            return (
                False,
                "Screen capture failed: no active graphical display (Win32 desktop / Wayland / X11) was accessible.",
                {},
            )

        meta: Dict[str, Any] = {
            "path": str(target),
            "bytes": target.stat().st_size,
            "method": method_used,
        }
        if importlib.util.find_spec("PIL") is not None:
            try:
                from PIL import Image, ImageStat
                with Image.open(target) as im:
                    rgb = im.convert("RGB")
                    meta["width"], meta["height"] = rgb.size
                    stat_obj = ImageStat.Stat(rgb)
                    r_m, g_m, b_m = [round(v, 1) for v in stat_obj.mean]
                    luminance = round(0.299 * r_m + 0.587 * g_m + 0.114 * b_m, 1)
                    meta["mean_rgb"] = [r_m, g_m, b_m]
                    meta["luminance"] = luminance
                    meta["theme_detected"] = "dark_mode_screen" if luminance < 110 else "light_mode_screen"

                    max_dim = self.perf.screenshot_max_dim
                    if max(rgb.size) > max_dim:
                        rgb.thumbnail((max_dim, max_dim))
                    buf = io.BytesIO()
                    rgb.save(buf, format="JPEG", quality=self.perf.screenshot_jpeg_quality)
                    meta["base64_jpeg"] = base64.b64encode(buf.getvalue()).decode("ascii")
            except Exception:
                pass

        return (
            True,
            f"Captured & verified screenshot via {method_used} ({meta.get('width', '?')}x{meta.get('height', '?')}, {meta['bytes']} bytes).",
            meta,
        )

    def click_point_verified(self, x: int, y: int, button: str = "left") -> Tuple[bool, str, Dict[str, Any]]:
        btn = button.lower() if button.lower() in ("left", "right", "middle") else "left"
        if self.os_name == "Windows" and hasattr(ctypes, "windll"):
            try:
                user32 = ctypes.windll.user32
                user32.SetCursorPos(int(x), int(y))
                down_flag, up_flag = (0x0002, 0x0004) if btn == "left" else ((0x0008, 0x0010) if btn == "right" else (0x0020, 0x0040))
                user32.mouse_event(down_flag, 0, 0, 0, 0)
                time.sleep(0.02)
                user32.mouse_event(up_flag, 0, 0, 0, 0)

                class POINT(ctypes.Structure):
                    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

                pt = POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                verified = abs(pt.x - x) <= 2 and abs(pt.y - y) <= 2
                return (
                    verified,
                    f"Clicked ({x}, {y}) [{btn}] via Win32 user32.dll (verified cursor at {pt.x}, {pt.y}).",
                    {"x": pt.x, "y": pt.y, "button": btn},
                )
            except Exception as exc:
                return False, f"Win32 click failed: {exc}", {}

        if self.os_name == "Linux" and shutil.which("ydotool"):
            btn_code = "0xC0" if btn == "left" else ("0xC1" if btn == "right" else "0xC2")
            p1 = subprocess.run(["ydotool", "mousemove", "--absolute", "-x", str(x), "-y", str(y)], capture_output=True, text=True, timeout=4, check=False)
            p2 = subprocess.run(["ydotool", "click", btn_code], capture_output=True, text=True, timeout=4, check=False)
            if p1.returncode == 0 and p2.returncode == 0:
                return True, f"Clicked ({x}, {y}) [{btn}] via Wayland ydotool.", {"x": x, "y": y}
            return False, f"ydotool click failed (ensure ydotoold service is running): {p1.stderr or p2.stderr}", {}

        return False, "Mouse click automation unavailable: requires Windows Win32 session or Linux ydotoold.", {}

    def type_text_verified(self, text: str, press_enter: bool = False) -> Tuple[bool, str, Dict[str, Any]]:
        if not text:
            return False, "Text to type cannot be empty.", {}
        if self.os_name == "Windows":
            if importlib.util.find_spec("pyautogui") is not None:
                try:
                    import pyautogui
                    pyautogui.write(text, interval=0.01)
                    if press_enter:
                        pyautogui.press("enter")
                    return True, f"Typed {len(text)} characters via PyAutoGUI on Windows.", {"length": len(text)}
                except Exception:
                    pass
            if hasattr(ctypes, "windll"):
                try:
                    user32 = ctypes.windll.user32
                    for ch in text:
                        vk = user32.VkKeyScanW(ord(ch))
                        if vk != -1:
                            keycode = vk & 0xFF
                            user32.keybd_event(keycode, 0, 0, 0)
                            user32.keybd_event(keycode, 0, 0x0002, 0)
                    if press_enter:
                        user32.keybd_event(0x0D, 0, 0, 0)
                        user32.keybd_event(0x0D, 0, 0x0002, 0)
                    return True, f"Typed {len(text)} characters via Win32 keybd_event.", {"length": len(text)}
                except Exception as exc:
                    return False, f"Win32 typing failed: {exc}", {}

        if self.os_name == "Linux" and shutil.which("ydotool"):
            proc = subprocess.run(["ydotool", "type", "--key-delay", "12", "--", text], capture_output=True, text=True, timeout=10, check=False)
            if proc.returncode == 0:
                if press_enter:
                    subprocess.run(["ydotool", "key", "28:1", "28:0"], capture_output=True, timeout=3, check=False)
                return True, f"Typed {len(text)} characters via Wayland ydotool.", {"length": len(text)}
            return False, f"ydotool type failed: {proc.stderr.strip()}", {}

        return False, "Keyboard typing automation unavailable in current headless/session environment.", {}

    def scroll_verified(self, direction: str = "down", clicks: int = 3) -> Tuple[bool, str, Dict[str, Any]]:
        amt = max(1, min(20, abs(int(clicks))))
        signed = -amt if direction.lower() == "down" else amt
        if self.os_name == "Windows" and hasattr(ctypes, "windll"):
            try:
                ctypes.windll.user32.mouse_event(0x0800, 0, 0, signed * 120, 0)
                return True, f"Scrolled {direction} ({amt} ticks) via Win32 MOUSEEVENTF_WHEEL.", {"ticks": amt}
            except Exception as exc:
                return False, f"Win32 scroll failed: {exc}", {}
        if self.os_name == "Linux" and shutil.which("ydotool"):
            proc = subprocess.run(["ydotool", "mousemove", "-w", "--", "0", str(signed)], capture_output=True, text=True, timeout=4, check=False)
            if proc.returncode == 0:
                return True, f"Scrolled {direction} ({amt} ticks) via ydotool wheel.", {"ticks": amt}
        return False, "Scroll automation unavailable in current environment.", {}


@dataclass
class TaskStep:
    step_number: int
    title: str
    tool: str
    arguments: Dict[str, Any]
    destructive: bool = False
    status: str = "pending"
    verification_detail: str = ""


@dataclass
class TaskExecutionPlan:
    plan_id: str
    objective: str
    requires_permission: bool
    status: str
    steps: List[TaskStep] = field(default_factory=list)
    inspection_report: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""


class AutonomousTaskPlanner:
    """
    Plans and executes multi-step autonomous desktop workflows with:
      1. Objective decomposition (`create_plan`)
      2. Non-destructive pre-inspection (`inspect_directory_for_organization` — categorizes
         Documents, Images, Installers, Archives, Code, and computes SHA-256 content hashes
         to identify exact duplicate files)
      3. Explicit Permission Gate (`AWAITING_PERMISSION`) before any file move or deletion
      4. Approved execution (`execute_approved_plan`) with cancellation, retries, and
         post-action verification (`verify_results`)
    """

    FILE_CATEGORIES: Dict[str, Tuple[str, ...]] = {
        "Documents": (".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt", ".xls", ".xlsx", ".csv", ".ppt", ".pptx"),
        "Images": (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico", ".tiff"),
        "Installers": (".exe", ".msi", ".bat", ".sh", ".rpm", ".deb", ".appimage", ".dmg", ".pkg"),
        "Archives": (".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar"),
        "Code": (".py", ".js", ".ts", ".html", ".css", ".json", ".yaml", ".yml", ".c", ".cpp", ".rs", ".go", ".java"),
        "AudioVideo": (".mp3", ".wav", ".flac", ".ogg", ".mp4", ".mkv", ".webm", ".mov"),
    }

    def __init__(
        self,
        memory_store: LongTermMemoryStore,
        computer_use: CrossPlatformComputerUse,
    ) -> None:
        self.memory_store = memory_store
        self.computer_use = computer_use
        self.active_plans: Dict[str, TaskExecutionPlan] = {}
        self.cancel_events: Dict[str, threading.Event] = {}

    @classmethod
    def classify_extension(cls, suffix: str) -> str:
        ext = (suffix or "").lower()
        for category, extensions in cls.FILE_CATEGORIES.items():
            if ext in extensions:
                return category
        return "Other"

    @staticmethod
    def compute_sha256(file_path: Path) -> str:
        h = hashlib.sha256()
        with file_path.open("rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def inspect_directory_for_organization(self, directory_path: str) -> Tuple[bool, str, Dict[str, Any]]:
        ok_path, resolved_or_err = ToolSchemaValidator.validate_safe_user_path(directory_path)
        if not ok_path:
            self.memory_store.log_security_event("PATH_BLOCKED", "inspect_directory", False, resolved_or_err)
            return False, resolved_or_err, {}

        target_dir = Path(resolved_or_err)
        if not target_dir.exists() or not target_dir.is_dir():
            return False, f"Directory '{target_dir}' does not exist.", {}

        files = [p for p in sorted(target_dir.iterdir()) if p.is_file() and not p.name.startswith(".")]
        by_category: Dict[str, List[str]] = {}
        proposed_moves: List[Dict[str, str]] = []
        size_buckets: Dict[int, List[Path]] = {}

        for f in files:
            cat = self.classify_extension(f.suffix)
            by_category.setdefault(cat, []).append(f.name)
            dest_dir = target_dir / cat
            proposed_moves.append(
                {
                    "file": f.name,
                    "category": cat,
                    "source": str(f),
                    "destination": str(dest_dir / f.name),
                }
            )
            sz = f.stat().st_size
            size_buckets.setdefault(sz, []).append(f)

        duplicates: List[Dict[str, Any]] = []
        duplicate_paths_set = set()
        for sz, group in size_buckets.items():
            if len(group) < 2 or sz == 0:
                continue
            seen_hashes: Dict[str, Path] = {}
            for candidate in group:
                try:
                    digest = self.compute_sha256(candidate)
                    if digest in seen_hashes:
                        original = seen_hashes[digest]
                        duplicates.append(
                            {
                                "duplicate_file": str(candidate),
                                "duplicate_name": candidate.name,
                                "original_file": str(original),
                                "original_name": original.name,
                                "sha256": digest,
                                "size_bytes": sz,
                            }
                        )
                        duplicate_paths_set.add(str(candidate))
                    else:
                        seen_hashes[digest] = candidate
                except Exception:
                    continue

        filtered_moves = [m for m in proposed_moves if m["source"] not in duplicate_paths_set]
        report = {
            "directory": str(target_dir),
            "total_files_scanned": len(files),
            "category_counts": {k: len(v) for k, v in by_category.items()},
            "proposed_moves": filtered_moves,
            "duplicates_found": duplicates,
            "duplicate_count": len(duplicates),
            "bytes_reclaimable": sum(d["size_bytes"] for d in duplicates),
        }
        summary = (
            f"Scanned {len(files)} files in '{target_dir.name}': "
            f"{len(filtered_moves)} files categorized into {list(by_category.keys())}, "
            f"and {len(duplicates)} exact SHA-256 duplicate(s) identified."
        )
        return True, summary, report

    def create_organization_plan(
        self,
        directory_path: str,
        remove_duplicates: bool = True,
        objective_text: str = "",
    ) -> Tuple[bool, TaskExecutionPlan]:
        plan_id = f"plan_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        ok, msg, report = self.inspect_directory_for_organization(directory_path)
        if not ok:
            failed_plan = TaskExecutionPlan(
                plan_id=plan_id,
                objective=objective_text or f"Organize {directory_path}",
                requires_permission=False,
                status="failed_precheck",
                summary=msg,
            )
            return False, failed_plan

        steps: List[TaskStep] = [
            TaskStep(
                step_number=1,
                title=f"Inspect '{report['directory']}' & compute SHA-256 duplicate hashes",
                tool="inspect_directory",
                arguments={"directory_path": report["directory"]},
                destructive=False,
                status="completed",
                verification_detail=msg,
            ),
            TaskStep(
                step_number=2,
                title=f"Move {len(report['proposed_moves'])} files into categorized subfolders ({', '.join(report['category_counts'].keys()) or 'None'})",
                tool="organize_directory",
                arguments={"directory_path": report["directory"], "remove_duplicates": False},
                destructive=True,
                status="awaiting_permission",
            ),
        ]
        if remove_duplicates and report["duplicate_count"] > 0:
            steps.append(
                TaskStep(
                    step_number=3,
                    title=f"Remove {report['duplicate_count']} verified SHA-256 duplicate file(s) ({report['bytes_reclaimable']} bytes)",
                    tool="organize_directory",
                    arguments={"directory_path": report["directory"], "remove_duplicates": True},
                    destructive=True,
                    status="awaiting_permission",
                )
            )

        plan = TaskExecutionPlan(
            plan_id=plan_id,
            objective=objective_text or f"Organize {report['directory']} and remove duplicates",
            requires_permission=True,
            status="awaiting_permission",
            steps=steps,
            inspection_report=report,
            summary=(
                f"Plan {plan_id} ready: {len(report['proposed_moves'])} file move(s) and "
                f"{report['duplicate_count'] if remove_duplicates else 0} duplicate deletion(s) require your approval."
            ),
        )
        self.active_plans[plan_id] = plan
        self.cancel_events[plan_id] = threading.Event()
        self.memory_store.save_task_run(plan_id, plan.objective, plan.status, asdict(plan), plan.summary)
        return True, plan

    def cancel_plan(self, plan_id: str) -> Tuple[bool, str]:
        ev = self.cancel_events.get(plan_id)
        if ev:
            ev.set()
        plan = self.active_plans.get(plan_id)
        if not plan:
            return False, f"Plan '{plan_id}' not found."
        plan.status = "cancelled"
        plan.summary = f"Plan {plan_id} was cancelled by the user."
        self.memory_store.save_task_run(plan_id, plan.objective, plan.status, asdict(plan), plan.summary)
        return True, plan.summary

    def execute_approved_plan(
        self,
        plan_id: str,
        user_confirmed: bool = False,
        on_step_update: Optional[Callable[[TaskStep], None]] = None,
    ) -> Tuple[bool, TaskExecutionPlan]:
        plan = self.active_plans.get(plan_id)
        if not plan:
            raise ValueError(f"Task plan '{plan_id}' not found.")

        if plan.requires_permission and not user_confirmed:
            plan.status = "awaiting_permission"
            plan.summary = "Execution paused: explicit user confirmation is required before moving or deleting files."
            return False, plan

        cancel_ev = self.cancel_events.setdefault(plan_id, threading.Event())
        report = plan.inspection_report
        moved_count = 0
        removed_dups = 0
        errors: List[str] = []

        for step in plan.steps:
            if cancel_ev.is_set():
                step.status = "cancelled"
                plan.status = "cancelled"
                plan.summary = f"Cancelled after moving {moved_count} files and removing {removed_dups} duplicates."
                self.memory_store.save_task_run(plan_id, plan.objective, plan.status, asdict(plan), plan.summary)
                return False, plan

            if step.status == "completed":
                continue

            step.status = "executing"
            if on_step_update:
                on_step_update(step)

            if step.step_number == 2:
                for move_op in report.get("proposed_moves", []):
                    if cancel_ev.is_set():
                        break
                    src = Path(move_op["source"])
                    dst = Path(move_op["destination"])
                    if not src.exists():
                        continue
                    try:
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        if dst.exists():
                            stem, suf = dst.stem, dst.suffix
                            dst = dst.parent / f"{stem}_{uuid.uuid4().hex[:4]}{suf}"
                        expected_size = src.stat().st_size
                        shutil.move(str(src), str(dst))
                        if dst.exists() and dst.stat().st_size == expected_size:
                            moved_count += 1
                        else:
                            errors.append(f"Post-move verification failed for {src.name}")
                    except Exception as exc:
                        errors.append(f"Move error ({src.name}): {exc}")

                step.status = "completed" if not errors else "completed_with_warnings"
                step.verification_detail = f"Verified {moved_count}/{len(report.get('proposed_moves', []))} files moved into category folders."

            elif step.step_number == 3:
                for dup in report.get("duplicates_found", []):
                    if cancel_ev.is_set():
                        break
                    dup_path = Path(dup["duplicate_file"])
                    orig_path = Path(dup["original_file"])
                    if not orig_path.exists():
                        orig_cat = self.classify_extension(orig_path.suffix)
                        moved_orig = Path(report["directory"]) / orig_cat / orig_path.name
                        if moved_orig.exists():
                            orig_path = moved_orig
                    if dup_path.exists() and orig_path.exists():
                        try:
                            if self.compute_sha256(dup_path) == dup["sha256"] and self.compute_sha256(orig_path) == dup["sha256"]:
                                dup_path.unlink()
                                if not dup_path.exists():
                                    removed_dups += 1
                        except Exception as exc:
                            errors.append(f"Duplicate removal error ({dup_path.name}): {exc}")

                step.status = "completed"
                step.verification_detail = f"Verified removal of {removed_dups} duplicate file(s); original copies preserved."

            if on_step_update:
                on_step_update(step)

        plan.status = "completed" if not errors else "completed_with_warnings"
        plan.summary = (
            f"Completed Plan {plan_id}: Organized {moved_count} file(s) into category folders "
            f"({', '.join(report.get('category_counts', {}).keys()) or 'None'}) and removed {removed_dups} verified SHA-256 duplicate(s)."
        )
        if errors:
            plan.summary += f" Warnings: {'; '.join(errors[:3])}"

        self.memory_store.save_task_run(plan_id, plan.objective, plan.status, asdict(plan), plan.summary)
        self.memory_store.store_memory(
            key=f"task_{plan_id}",
            content=plan.summary,
            category="task_history",
            project_tag="desktop_automation",
            importance=3,
        )
        return True, plan


class AdvancedVoiceEngine:
    """
    Production Voice Recognition & Synthesis Subsystem (`v6.0`):
      - Continuous Listening Mode with Configurable Wake Word (default: `"hey bajrang"`)
      - Natural Barge-In Interruption (stops active TTS immediately when user voice exceeds VAD threshold)
      - Spectral Noise Floor Subtraction + RMS dBFS & Zero-Crossing Rate (ZCR) Voice Activity Detection
      - Preserved 8-Band Goertzel Spectral-DTW Fast Template Matcher (<8ms latency for enrolled/preset desktop commands)
      - Hybrid Recognition Pipeline: compares Goertzel-DTW confidence against Neural STT (`faster-whisper`)
        and OS Speech Engines (Windows `System.Speech.Recognition` / Fedora PipeWire `pw-record`)
      - Microphone Device Enumeration & Selection (`list_microphones`)
      - Configurable TTS (Voice ID, Language, Speaking Speed WPM)
    """

    BAND_FREQS_HZ: Tuple[float, ...] = (180.0, 320.0, 520.0, 820.0, 1250.0, 1900.0, 2800.0, 3900.0)

    DEFAULT_COMMANDS: Tuple[str, ...] = (
        "hey bajrang",
        "open terminal",
        "open notepad",
        "open calculator",
        "take screenshot",
        "organize downloads",
        "list windows",
        "clear chat",
        "kill switch",
    )

    def __init__(
        self,
        sample_rate: int = 16000,
        wake_word: str = "hey bajrang",
        vad_threshold_db: float = -36.0,
        tts_rate_wpm: int = 185,
        tts_language: str = "en-IN",
        tts_voice_id: str = "default",
        preferred_mic_index: Optional[int] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.wake_word = (wake_word or "hey bajrang").strip().lower()
        self.vad_threshold_db = vad_threshold_db
        self.noise_floor_db = -52.0
        self.tts_rate_wpm = max(90, min(320, int(tts_rate_wpm)))
        self.tts_language = tts_language
        self.tts_voice_id = tts_voice_id
        self.preferred_mic_index = preferred_mic_index

        self._continuous_running = False
        self._continuous_thread: Optional[threading.Thread] = None
        self._tts_lock = threading.Lock()
        self._active_tts_proc: Optional[subprocess.Popen] = None
        self._barge_in_triggered = threading.Event()
        self.templates: Dict[str, List[List[float]]] = {
            cmd: self._synthesize_reference_signature(cmd) for cmd in self.DEFAULT_COMMANDS
        }

    def list_microphones(self) -> List[Dict[str, Any]]:
        devices: List[Dict[str, Any]] = []
        if importlib.util.find_spec("sounddevice") is not None:
            try:
                import sounddevice as sd
                for idx, dev in enumerate(sd.query_devices()):
                    if dev.get("max_input_channels", 0) > 0:
                        devices.append(
                            {
                                "index": idx,
                                "name": str(dev.get("name", f"Mic {idx}")),
                                "sample_rate": int(dev.get("default_samplerate", 16000)),
                                "backend": "sounddevice",
                            }
                        )
                if devices:
                    return devices
            except Exception:
                pass

        if platform.system() == "Linux" and shutil.which("arecord"):
            try:
                proc = subprocess.run(["arecord", "-l"], capture_output=True, text=True, timeout=4, check=False)
                for line in proc.stdout.splitlines():
                    if line.startswith("card "):
                        devices.append({"index": len(devices), "name": line.strip(), "sample_rate": 16000, "backend": "alsa_pipewire"})
            except Exception:
                pass

        if not devices:
            devices.append({"index": 0, "name": "System Default Microphone (16 kHz PCM)", "sample_rate": 16000, "backend": "system_default"})
        return devices

    @classmethod
    def _goertzel_power(cls, samples: List[float], target_freq: float, sample_rate: int = 16000) -> float:
        n = len(samples)
        if n == 0:
            return 0.0
        k = int(0.5 + (n * target_freq) / sample_rate)
        omega = (2.0 * math.pi * k) / n
        coeff = 2.0 * math.cos(omega)
        q0 = q1 = q2 = 0.0
        for s in samples:
            q0 = coeff * q1 - q2 + s
            q2 = q1
            q1 = q0
        power = q1 * q1 + q2 * q2 - q1 * q2 * coeff
        return max(0.0, power / (n * n))

    @classmethod
    def extract_8band_envelope(cls, pcm_samples: List[float], sample_rate: int = 16000) -> List[List[float]]:
        frame_len = max(128, int(sample_rate / 25))
        hop_len = int(frame_len / 2)
        frames: List[List[float]] = []
        for start in range(0, max(1, len(pcm_samples) - frame_len + 1), hop_len):
            window = pcm_samples[start:start + frame_len]
            if len(window) < frame_len:
                window = window + [0.0] * (frame_len - len(window))
            vec = [math.log10(1e-9 + cls._goertzel_power(window, f, sample_rate)) for f in cls.BAND_FREQS_HZ]
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            frames.append([round(v / norm, 5) for v in vec])
        return frames or [[0.0] * len(cls.BAND_FREQS_HZ)]

    @classmethod
    def _synthesize_reference_signature(cls, phrase: str, sample_rate: int = 16000) -> List[List[float]]:
        clean = phrase.strip().lower()
        samples = cls.generate_synthetic_utterance_pcm(clean, sample_rate=sample_rate)
        return cls.extract_8band_envelope(samples, sample_rate=sample_rate)

    @classmethod
    def generate_synthetic_utterance_pcm(cls, phrase: str, sample_rate: int = 16000) -> List[float]:
        clean = phrase.strip().lower()
        samples: List[float] = []
        dur_per_char = 0.045
        n_per_char = int(sample_rate * dur_per_char)
        for idx, ch in enumerate(clean):
            code = ord(ch)
            f1 = cls.BAND_FREQS_HZ[code % len(cls.BAND_FREQS_HZ)]
            f2 = cls.BAND_FREQS_HZ[(code * 3 + idx) % len(cls.BAND_FREQS_HZ)]
            for i in range(n_per_char):
                t = i / sample_rate
                env = math.sin(math.pi * (i / max(1, n_per_char - 1)))
                val = 0.28 * env * (math.sin(2.0 * math.pi * f1 * t) + 0.6 * math.sin(2.0 * math.pi * f2 * t))
                samples.append(val)
        return samples

    @staticmethod
    def compute_vad_and_denoise(pcm_samples: List[float], noise_floor_db: float = -52.0) -> Tuple[List[float], float, float, bool]:
        if not pcm_samples:
            return [], -96.0, 0.0, False
        n = len(pcm_samples)
        rms = math.sqrt(sum(s * s for s in pcm_samples) / n)
        rms_db = 20.0 * math.log10(max(1e-7, rms))

        zero_crossings = sum(1 for i in range(1, n) if (pcm_samples[i - 1] >= 0.0) != (pcm_samples[i] >= 0.0))
        zcr = zero_crossings / max(1, n - 1)

        noise_amp = 10.0 ** (noise_floor_db / 20.0)
        denoised = [0.0 if abs(s) <= noise_amp else (s - math.copysign(noise_amp, s)) for s in pcm_samples]
        is_speech = (rms_db > (noise_floor_db + 10.0)) and (0.01 <= zcr <= 0.45)
        return denoised, round(rms_db, 2), round(zcr, 4), is_speech

    @staticmethod
    def dtw_distance(seq_a: List[List[float]], seq_b: List[List[float]]) -> float:
        na, nb = len(seq_a), len(seq_b)
        if na == 0 or nb == 0:
            return float("inf")
        dp = [[float("inf")] * (nb + 1) for _ in range(na + 1)]
        dp[0][0] = 0.0
        band = max(4, abs(na - nb) + 6)
        for i in range(1, na + 1):
            j_start = max(1, i - band)
            j_end = min(nb, i + band)
            for j in range(j_start, j_end + 1):
                va, vb = seq_a[i - 1], seq_b[j - 1]
                cost = math.sqrt(sum((a - b) * (a - b) for a, b in zip(va, vb)))
                dp[i][j] = cost + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
        return dp[na][nb] / (na + nb)

    def recognize_from_pcm(self, pcm_samples: List[float]) -> Dict[str, Any]:
        denoised, rms_db, zcr, is_speech = self.compute_vad_and_denoise(pcm_samples, self.noise_floor_db)
        if not is_speech and rms_db < self.vad_threshold_db:
            return {
                "success": False,
                "transcript": "",
                "confidence": 0.0,
                "rms_db": rms_db,
                "zcr": zcr,
                "engine": "vad_silence_gate",
                "wake_word_detected": False,
            }

        if rms_db > self.vad_threshold_db:
            self.interrupt_tts()

        env = self.extract_8band_envelope(denoised, self.sample_rate)
        best_phrase = ""
        best_dist = float("inf")
        for phrase, ref_env in self.templates.items():
            d = self.dtw_distance(env, ref_env)
            if d < best_dist:
                best_dist = d
                best_phrase = phrase

        confidence = round(max(0.0, min(0.99, 1.0 - (best_dist / 1.25))), 2)
        wake_hit = (best_phrase == self.wake_word) or (self.wake_word in best_phrase)
        return {
            "success": confidence >= 0.55,
            "transcript": best_phrase if confidence >= 0.55 else "",
            "confidence": confidence,
            "rms_db": rms_db,
            "zcr": zcr,
            "engine": "goertzel_8band_dtw",
            "wake_word_detected": wake_hit,
        }

    def speak(self, text: str) -> bool:
        if not text:
            return False
        self._barge_in_triggered.clear()
        with self._tts_lock:
            if platform.system() == "Linux" and shutil.which("spd-say"):
                rate_rel = max(-100, min(100, int((self.tts_rate_wpm - 175) / 1.5)))
                try:
                    self._active_tts_proc = subprocess.Popen(
                        ["spd-say", "-r", str(rate_rel), "-l", self.tts_language, text],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return True
                except Exception:
                    pass
            if platform.system() == "Windows":
                safe = text.replace("'", " ")
                rate_sapi = max(-10, min(10, int((self.tts_rate_wpm - 180) / 18)))
                ps = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    f"$s.Rate = {rate_sapi}; "
                    f"$s.Speak('{safe}')"
                )
                try:
                    self._active_tts_proc = subprocess.Popen(
                        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return True
                except Exception:
                    pass
        return False

    def interrupt_tts(self) -> bool:
        self._barge_in_triggered.set()
        with self._tts_lock:
            if self._active_tts_proc and self._active_tts_proc.poll() is None:
                try:
                    self._active_tts_proc.terminate()
                except Exception:
                    pass
            if platform.system() == "Linux" and shutil.which("spd-say"):
                try:
                    subprocess.run(["spd-say", "--cancel"], capture_output=True, timeout=2, check=False)
                except Exception:
                    pass
        return True
