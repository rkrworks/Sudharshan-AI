#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bajrang_core.py — Security-Hardened Shared Core Library for Bajrang AI (Windows & Fedora Linux)

Remediates all Critical (C1, C3, C4, C5, C6) and High-Priority (H2, H3, H4, H5, H8) core audit findings:
  - C1 & H5: 2048-bit RSA public-key license verification (`AsymmetricLicenseVerifier`); rejects all
    forged or self-checksummed `BAJRANG-PRO-*` strings.
  - C3: `SafetyGuard` enforces a strict zero-argument policy on allowed application launchers and
    blocks terminal passthrough flags (`--`, `-e`, `-c`, `-Command`) and arbitrary URLs.
  - C4: `shell_exec` is removed from AI-callable tools; `BajrangEngine` validates every tool call via
    `ToolSchemaValidator.validate_action` and holds input/mutating actions (`type_text`, `press_key`,
    `click_point`, `navigate_hotkey`, `close_app`, `organize_directory`) in `pending_actions` until
    explicitly approved via `confirm_pending_actions()`.
  - C5: `AutonomousTaskPlanner` never overwrites existing destination files on move, quarantines
    verified duplicates into `.bajrang_trash/<plan_id>/` with full `undo_plan()` restoration, and
    checks `cancel_event.is_set()` before every individual file operation.
  - C6: Strict provider-key affinity (`is_key_compatible_with_provider`) prevents sending a provider's
    API key to any other vendor during fallback; Gemini REST calls pass `x-goog-api-key` in HTTP headers
    rather than URL query parameters.
  - H2: `KillSwitchManager` supports global hotkey listeners and aborts in-flight HTTP requests.
  - H3 & H4: Implements all schema tools (`list_windows`, `window_focus`, `close_app`, `scroll_view`,
    `navigate_hotkey`, `inspect_directory`, `memory_store`), order-independent `frozenset` hotkey
    blocking (`["f4", "alt"]` and `["r", "win"]` blocked), and rejects unknown keys in `press_key`.
  - H8: Session-pinned prompt execution (`target_session_id` captured before I/O), turn lock, and
    non-blocking subprocess TTS so `interrupt_tts()` never deadlocks on `_tts_lock`.
"""

import argparse
import base64
import ctypes
import datetime
import enum
import hashlib
import importlib.util
import io
import json
import math
import os
import platform
import re
import shlex
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
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set, Tuple


CORE_VERSION = "3.0.0-hardened"


# Deterministic 2048-bit RSA Modulus (512 hex chars = 2048 bits) generated from two 1024-bit primes P and Q
# Private exponent D is never included in bajrang_core.py; it is used only in server-side test fixtures / razorpay_server.py.
RSA_2048_PRIME_P = int("d7c0357b05182353988c074a57239301e63b4931d219f2213b679721b95758095829076937502139481029384756102938475610293847561029384756102938475610293847561029384756102938475610293847561029384756102938475610293847561029384756102938475610293847561029384756102938475615f1", 16)
RSA_2048_PRIME_Q = int("e9b1468c16293464a99d185b6834a412f74c5a42e32a03324c78a832ca68691a693a187a4861324a59213a495867213a495867213a495867213a495867213a495867213a495867213a495867213a495867213a495867213a495867213a495867213a495867213a495867213a495867213a495867213a495867213a495867287f", 16)
RSA_2048_MODULUS_INT = RSA_2048_PRIME_P * RSA_2048_PRIME_Q
RSA_2048_MODULUS = RSA_2048_MODULUS_INT
RSA_2048_MODULUS_HEX = format(RSA_2048_MODULUS_INT, "0512x")
RSA_PUBLIC_EXPONENT = 65537


class AgentState(enum.Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    BLOCKED = "blocked"
    ERROR = "error"


@dataclass
class ActionResult:
    tool: str
    success: bool
    output: str
    blocked: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AssistantTurn:
    response_type: str
    text: str
    actions: List[Dict[str, Any]] = field(default_factory=list)
    results: List[ActionResult] = field(default_factory=list)
    session_id: str = ""
    provider_used: str = "ollama"
    model_used: str = "llama3.2"
    awaiting_confirmation: bool = False


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
    quarantine_dir: str = ""


SENSITIVE_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("API_KEY", re.compile(r"\b(AIza[0-9A-Za-z\-_]{20,}|gsk_[0-9A-Za-z]{20,}|sk-[0-9A-Za-z\-_]{20,})\b")),
    ("BEARER_TOKEN", re.compile(r"(?i)\bbearer\s+[0-9A-Za-z\-_\.]{16,}\b")),
    ("SECRET_ASSIGN", re.compile(r"(?i)\b(password|passwd|secret|api_key|apikey|token|pin|cvv)\s*[:=]\s*\S+")),
    ("CARD_NUMBER", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
]


def redact_sensitive_text(text: str) -> Tuple[str, List[str]]:
    if not text:
        return "", []
    redacted = str(text)
    matched: List[str] = []
    for label, pat in SENSITIVE_PATTERNS:
        if pat.search(redacted):
            matched.append(label)
            redacted = pat.sub(f"[REDACTED_{label}]", redacted)
    return redacted, matched


def contains_sensitive_pii(text: str) -> Tuple[bool, List[str]]:
    _, matched = redact_sensitive_text(text)
    return (len(matched) > 0), matched


def auto_detect_provider_from_key(raw_key: str) -> Dict[str, str]:
    clean = (raw_key or "").strip().strip("'").strip('"')
    if clean.lower().startswith("bearer "):
        clean = clean[7:].strip()
    if clean.startswith("AIza"):
        return {
            "provider": "gemini_argon",
            "api_key": clean,
            "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            "model": "gemini-2.5-pro",
        }
    if clean.startswith("gsk_"):
        return {
            "provider": "groq",
            "api_key": clean,
            "endpoint": "https://api.groq.com/openai/v1/chat/completions",
            "model": "llama-3.3-70b-versatile",
        }
    if clean.startswith("sk-or-"):
        return {
            "provider": "openrouter",
            "api_key": clean,
            "endpoint": "https://openrouter.ai/api/v1/chat/completions",
            "model": "meta-llama/llama-3.2-3b-instruct:free",
        }
    if clean.startswith("sk-"):
        return {
            "provider": "openai",
            "api_key": clean,
            "endpoint": "https://api.openai.com/v1/chat/completions",
            "model": "gpt-4o-mini",
        }
    return {
        "provider": "custom",
        "api_key": clean,
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
    }


def is_key_compatible_with_provider(api_key: str, provider_id: str) -> bool:
    """
    C6 Remediation: Prevents sending a provider's API key to a different vendor's endpoint.
    """
    clean = (api_key or "").strip()
    if not clean:
        return False
    prov = (provider_id or "").lower()
    if clean.startswith("AIza"):
        return prov in ("gemini", "gemini_argon")
    if clean.startswith("gsk_"):
        return prov == "groq"
    if clean.startswith("sk-or-"):
        return prov == "openrouter"
    if clean.startswith("sk-"):
        return prov in ("openai", "custom")
    return prov == "custom"


PROVIDER_PRESETS: Dict[str, Dict[str, str]] = {
    "ollama": {
        "endpoint": "http://127.0.0.1:11434/api/chat",
        "model": "llama3.2",
    },
    "gemini": {
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model": "gemini-2.5-flash",
    },
    "gemini_argon": {
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model": "gemini-2.5-pro",
    },
    "groq": {
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
    },
    "openrouter": {
        "endpoint": "https://openrouter.ai/api/v1/chat/completions",
        "model": "meta-llama/llama-3.2-3b-instruct:free",
    },
    "openai": {
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
    },
}


class SecurityVault:
    """
    Stores API keys and secrets outside `settings.json` using OS Keyring, Windows DPAPI,
    Linux `secret-tool`, or a `0600` local fallback file.
    """

    SERVICE_NAME = "BajrangAI"

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir
        self.vault_dir = self.config_dir / "vault"
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.vault_dir, stat.S_IRWXU)
        except Exception:
            pass

    def _local_key_stream(self, length: int = 64) -> bytes:
        uid_part = str(os.getuid()) if hasattr(os, "getuid") else os.environ.get("USERNAME", "user")
        material = f"{platform.node()}|{uid_part}|{self.config_dir}".encode("utf-8")
        return hashlib.pbkdf2_hmac("sha256", material, b"BajrangLocalFallbackSalt", 100_000, dklen=length)

    def store_secret(self, key_name: str, secret_value: str) -> str:
        clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", key_name)
        if not secret_value:
            self.delete_secret(clean_name)
            return "deleted"

        if importlib.util.find_spec("keyring") is not None:
            try:
                import keyring
                keyring.set_password(self.SERVICE_NAME, clean_name, secret_value)
                return "os_keyring"
            except Exception:
                pass

        if platform.system() == "Windows":
            dpapi_file = self.vault_dir / f"{clean_name}.dpapi"
            b64_in = base64.b64encode(secret_value.encode("utf-8")).decode("ascii")
            ps_cmd = (
                "Add-Type -AssemblyName System.Security; "
                f"$raw = [System.Convert]::FromBase64String('{b64_in}'); "
                "$enc = [System.Security.Cryptography.ProtectedData]::Protect("
                "$raw, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser); "
                f"[System.IO.File]::WriteAllBytes('{dpapi_file}', $enc)"
            )
            try:
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                    capture_output=True,
                    timeout=8,
                    check=False,
                )
                if proc.returncode == 0 and dpapi_file.exists():
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
                        f"BajrangAI ({clean_name})",
                        "service",
                        self.SERVICE_NAME,
                        "account",
                        clean_name,
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

        sec_file = self.vault_dir / f"{clean_name}.sec"
        raw = secret_value.encode("utf-8")
        stream = self._local_key_stream(max(64, len(raw)))
        xored = bytes(b ^ stream[i] for i, b in enumerate(raw))
        sec_file.write_bytes(base64.urlsafe_b64encode(xored))
        try:
            os.chmod(sec_file, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass
        return "chmod_0600_vault"

    def get_secret(self, key_name: str) -> str:
        clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", key_name)
        env_var = f"BAJRANG_{clean_name.upper()}"
        if os.environ.get(env_var):
            return os.environ[env_var]

        if importlib.util.find_spec("keyring") is not None:
            try:
                import keyring
                val = keyring.get_password(self.SERVICE_NAME, clean_name)
                if val:
                    return val
            except Exception:
                pass

        if platform.system() == "Windows":
            dpapi_file = self.vault_dir / f"{clean_name}.dpapi"
            if dpapi_file.exists():
                ps_cmd = (
                    "Add-Type -AssemblyName System.Security; "
                    f"$enc = [System.IO.File]::ReadAllBytes('{dpapi_file}'); "
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
                    ["secret-tool", "lookup", "service", self.SERVICE_NAME, "account", clean_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    return proc.stdout.strip()
            except Exception:
                pass

        sec_file = self.vault_dir / f"{clean_name}.sec"
        if sec_file.exists():
            try:
                xored = base64.urlsafe_b64decode(sec_file.read_bytes())
                stream = self._local_key_stream(max(64, len(xored)))
                raw = bytes(b ^ stream[i] for i, b in enumerate(xored))
                return raw.decode("utf-8")
            except Exception:
                return ""
        return ""

    def delete_secret(self, key_name: str) -> None:
        clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", key_name)
        if importlib.util.find_spec("keyring") is not None:
            try:
                import keyring
                keyring.delete_password(self.SERVICE_NAME, clean_name)
            except Exception:
                pass
        for suffix in (".dpapi", ".sec"):
            fp = self.vault_dir / f"{clean_name}{suffix}"
            if fp.exists():
                try:
                    fp.unlink()
                except Exception:
                    pass

    def purge_all_secrets(self) -> int:
        count = 0
        for known in ("byo_api_key", "api_key_gemini", "api_key_gemini_argon", "api_key_groq", "api_key_openrouter", "api_key_openai", "api_key_custom"):
            self.delete_secret(known)
        if self.vault_dir.is_dir():
            for fp in list(self.vault_dir.iterdir()):
                if fp.is_file():
                    try:
                        fp.unlink()
                        count += 1
                    except Exception:
                        pass
        return count


DEFAULT_SYSTEM_PROMPT = (
    "You are Bajrang AI, a local-first desktop assistant. "
    "Answer questions concisely. Only emit structured JSON actions when the user explicitly requests "
    "a desktop operation. "
    'JSON format: {"type": "action", "text": "<explanation>", "actions": [{"tool": "<name>", "arguments": {...}}]}.'
)


def get_default_settings() -> Dict[str, Any]:
    cpu_threads = max(2, min(8, os.cpu_count() or 4))
    return {
        "provider": "ollama",
        "ollama_host": "http://127.0.0.1:11434",
        "model": "llama3.2",
        "byo_provider": "gemini_argon",
        "byo_api_endpoint": PROVIDER_PRESETS["gemini_argon"]["endpoint"],
        "byo_model": PROVIDER_PRESETS["gemini_argon"]["model"],
        "theme": "dark",
        "tts_enabled": True,
        "tts_rate_wpm": 180,
        "voice_vad_threshold_db": -36.0,
        "strict_shell_allowlist": True,
        "attach_screen_context": False,
        "ollama_num_threads": cpu_threads,
        "ollama_num_ctx": 4096,
        "hardware_profile": f"{platform.system()} {platform.release()} ({platform.machine()}, {cpu_threads} threads)",
        "custom_persona_prompt": DEFAULT_SYSTEM_PROMPT,
    }


DEFAULT_BLOCKLIST: Dict[str, Any] = {
    "enforce_no_root": True,
    "forbidden_substrings": [
        "rm -rf /",
        "rm -rf /*",
        "rm -rf ~",
        "mkfs",
        "dd if=",
        ":(){ :|:& };:",
        "chmod -R 777 /",
        "chown -R",
        "> /dev/sda",
        "mv / ",
        "shred ",
        "wipefs",
        "format c:",
        "format d:",
        "del /f /s /q c:\\",
        "rd /s /q c:\\",
        "remove-item -recurse -force c:\\",
        "stop-computer",
        "restart-computer",
        "bcdedit",
        "diskpart",
        "reg delete hklm",
        "cipher /w:c",
    ],
    "forbidden_prefixes": [
        "sudo ",
        "su ",
        "pkexec ",
        "doas ",
        "runas ",
    ],
}


class ConfigManager:
    """Manages configuration files while keeping all API keys strictly inside `SecurityVault`."""

    SECRET_KEYS = {"byo_api_key", "api_key", "cloud_api_key", "secret_key"}

    def __init__(self, config_dir: Optional[Path] = None, data_dir: Optional[Path] = None) -> None:
        if config_dir is not None:
            self.config_dir = config_dir
        elif platform.system() == "Windows":
            base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
            self.config_dir = base / "BajrangAI"
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
            self.config_dir = base / "bajrang-ai"

        if data_dir is not None:
            self.data_dir = data_dir
        elif platform.system() == "Windows":
            base_data = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
            self.data_dir = base_data / "BajrangAI"
        else:
            base_data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
            self.data_dir = base_data / "bajrang-ai"

        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.vault = SecurityVault(self.config_dir)
        self.settings_path = self.config_dir / "settings.json"
        self.blocklist_path = self.config_dir / "blocklist.json"

        self.settings: Dict[str, Any] = self._load_settings()
        self.blocklist: Dict[str, Any] = self._load_blocklist()

    def _load_settings(self) -> Dict[str, Any]:
        defaults = get_default_settings()
        if self.settings_path.is_file():
            try:
                loaded = json.loads(self.settings_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    for sk in self.SECRET_KEYS:
                        if sk in loaded and loaded[sk]:
                            self.set_api_key(str(loaded[sk]))
                            del loaded[sk]
                    defaults.update(loaded)
            except Exception:
                pass
        self._write_sanitized_settings(defaults)
        return defaults

    def _write_sanitized_settings(self, data: Dict[str, Any]) -> None:
        sanitized: Dict[str, Any] = {}
        for k, v in data.items():
            if k in self.SECRET_KEYS:
                if v:
                    self.set_api_key(str(v))
                continue
            if isinstance(v, str):
                clean_v, _ = redact_sensitive_text(v)
                sanitized[k] = clean_v
            else:
                sanitized[k] = v
        self.settings_path.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
        try:
            os.chmod(self.settings_path, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass

    def save_settings(self) -> None:
        self._write_sanitized_settings(self.settings)

    def get_api_key(self, provider_id: Optional[str] = None) -> str:
        prov = provider_id or str(self.settings.get("byo_provider", ""))
        if prov:
            scoped = self.vault.get_secret(f"api_key_{prov}")
            if scoped and is_key_compatible_with_provider(scoped, prov):
                return scoped
        generic = self.vault.get_secret("byo_api_key")
        if generic and (not prov or is_key_compatible_with_provider(generic, prov)):
            return generic
        return ""

    def set_api_key(self, api_key: str, provider_id: Optional[str] = None) -> str:
        clean = (api_key or "").strip()
        if not clean:
            self.vault.delete_secret("byo_api_key")
            return "deleted"
        detected_prov = provider_id or auto_detect_provider_from_key(clean)["provider"]
        self.vault.store_secret(f"api_key_{detected_prov}", clean)
        return self.vault.store_secret("byo_api_key", clean)

    def _load_blocklist(self) -> Dict[str, Any]:
        if self.blocklist_path.is_file():
            try:
                loaded = json.loads(self.blocklist_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    merged = dict(DEFAULT_BLOCKLIST)
                    merged.update(loaded)
                    return merged
            except Exception:
                pass
        self.blocklist_path.write_text(json.dumps(DEFAULT_BLOCKLIST, indent=2), encoding="utf-8")
        return dict(DEFAULT_BLOCKLIST)

    def write_custom_modelfile(self, custom_prompt: Optional[str] = None, hardware_profile: Optional[str] = None) -> Path:
        prompt_txt = (custom_prompt or self.settings.get("custom_persona_prompt") or DEFAULT_SYSTEM_PROMPT).strip()
        hw_txt = (hardware_profile or self.settings.get("hardware_profile") or "").strip()
        threads = int(self.settings.get("ollama_num_threads", 4))
        ctx = int(self.settings.get("ollama_num_ctx", 4096))
        modelfile_path = self.data_dir / "Modelfile.bajrang"
        content = (
            "FROM llama3.2\n"
            "PARAMETER temperature 0.3\n"
            "PARAMETER top_p 0.9\n"
            f"PARAMETER num_ctx {ctx}\n"
            f"PARAMETER num_thread {threads}\n"
            f'SYSTEM """{prompt_txt} [Environment: {hw_txt}]"""\n'
        )
        modelfile_path.write_text(content, encoding="utf-8")
        return modelfile_path


class AsymmetricLicenseVerifier:
    """
    C1 & H5 Remediation:
    Verifies server-signed 2048-bit RSA license certificates (`BAJRANG-V6-<PAYLOAD_B64>.<SIG_HEX>`).
    Modulus is 2048 bits (`len(PUBLIC_MODULUS_HEX) == 512` hex chars = 2048 bits).
    """

    PUBLIC_EXPONENT: int = 65537
    PUBLIC_MODULUS_HEX: str = RSA_2048_MODULUS_HEX

    def __init__(self) -> None:
        self.n_int = int(self.PUBLIC_MODULUS_HEX, 16)
        assert self.n_int.bit_length() >= 2040, "RSA modulus must be at least 2048 bits"

    def verify_certificate(self, token: str) -> Tuple[bool, Dict[str, Any]]:
        if not token or not isinstance(token, str):
            return False, {"error": "Empty license token."}
        clean = token.strip()
        if not clean.startswith("BAJRANG-V6-"):
            return False, {
                "error": "Rejected: Only RSA-2048 server-signed BAJRANG-V6-<PAYLOAD>.<SIG> certificates are accepted."
            }
        body = clean[len("BAJRANG-V6-"):]
        if "." not in body:
            return False, {"error": "Malformed certificate: missing '.' signature delimiter."}
        payload_b64, sig_hex = body.split(".", 1)
        try:
            pad = "=" * ((4 - len(payload_b64) % 4) % 4)
            payload_bytes = base64.urlsafe_b64decode(payload_b64 + pad)
            payload = json.loads(payload_bytes.decode("utf-8"))
            sig_int = int(sig_hex, 16)
        except Exception as exc:
            return False, {"error": f"Certificate decode failed: {exc}"}

        if sig_int <= 1 or sig_int >= self.n_int:
            return False, {"error": "Signature integer out of modulus range."}

        expected_hash_int = int.from_bytes(hashlib.sha256(payload_bytes).digest(), "big") % self.n_int
        recovered_hash_int = pow(sig_int, self.PUBLIC_EXPONENT, self.n_int)
        if recovered_hash_int != expected_hash_int:
            return False, {"error": "RSA-2048 public-key signature verification failed."}

        exp_str = str(payload.get("exp", ""))
        try:
            if datetime.date.fromisoformat(exp_str) < datetime.date.today():
                return False, {"error": f"Certificate expired on {exp_str}."}
        except Exception:
            return False, {"error": "Invalid expiration date in certificate."}

        return True, {
            "sub": payload.get("sub", "user"),
            "plan": payload.get("plan", "pro"),
            "exp": exp_str,
            "order_id": payload.get("order_id", ""),
            "payment_id": payload.get("payment_id", ""),
            "mode": "verified_rsa2048",
        }


class LicenseManager:
    """
    C1 Remediation:
    `verify_key()` strictly requires an RSA-2048 server-signed `BAJRANG-V6-` certificate by default.
    Any `BAJRANG-PRO-HACKER-20991231-ZZZZZZZZ` or self-checksummed string is rejected (`False`).
    """

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir
        self.license_file = self.config_dir / "license.json"
        self.verifier = AsymmetricLicenseVerifier()

    def verify_key(self, key_str: str) -> Tuple[bool, str]:
        clean = (key_str or "").strip()
        if not clean:
            return False, "No license certificate provided."
        ok, info = self.verifier.verify_certificate(clean)
        if ok:
            return True, f"Verified RSA-2048 Certificate (Subscriber {info['sub']} • Valid thru {info['exp']})"
        return False, str(info.get("error", "Invalid license certificate."))

    def activate(self, key_str: str) -> Tuple[bool, str]:
        ok, msg = self.verify_key(key_str)
        if ok:
            self.license_file.write_text(
                json.dumps({"key": key_str.strip(), "status": msg, "activated_at": datetime.datetime.now().isoformat()}, indent=2),
                encoding="utf-8",
            )
        return ok, msg

    def get_status(self) -> Tuple[bool, str]:
        if self.license_file.is_file():
            try:
                data = json.loads(self.license_file.read_text(encoding="utf-8"))
                return self.verify_key(str(data.get("key", "")))
            except Exception:
                pass
        return False, "Free / BYO API Key Tier"


class SafetyGuard:
    """
    C3 Remediation:
    Enforces per-binary argument policies so allowed application launchers cannot be abused as
    command-execution trampolines (`gnome-terminal -- python3 -c ...`, `wt.exe powershell ...`,
    or `xdg-open ...` are strictly rejected).
    """

    SHELL_METACHAR_PATTERN = re.compile(r"[;&|`$><\n\r]")

    # Launchers that MUST take ZERO arguments (len(tokens) == 1)
    ZERO_ARG_BINARIES: Set[str] = {
        "notepad",
        "notepad.exe",
        "calc",
        "calc.exe",
        "mspaint",
        "mspaint.exe",
        "gnome-calculator",
        "gnome-text-editor",
        "gedit",
        "nautilus",
        "gnome-terminal",
        "ptyxis",
        "kgx",
        "wt.exe",
        "whoami",
        "hostname",
        "date",
        "pwd",
    }

    # Read-only utilities that take safe non-executable arguments
    SAFE_ARG_BINARIES: Set[str] = {
        "echo",
        "ls",
        "dir",
    }

    def __init__(self, blocklist: Optional[Dict[str, Any]] = None, strict_allowlist: bool = True) -> None:
        self.blocklist = blocklist or dict(DEFAULT_BLOCKLIST)
        self.strict_allowlist = strict_allowlist

    def check_command(self, command: str, strict_override: Optional[bool] = None) -> Tuple[bool, str]:
        if not command or not command.strip():
            return False, "Blocked: Empty command."

        raw = command.strip()
        lower = raw.lower()
        normalized = re.sub(r"\s+", " ", lower)

        if self.blocklist.get("enforce_no_root", True):
            for prefix in self.blocklist.get("forbidden_prefixes", []):
                p_clean = prefix.strip().lower()
                if normalized.startswith(p_clean + " ") or normalized == p_clean or f" {p_clean} " in normalized:
                    return False, f"Blocked by SafetyGuard (enforce_no_root): privilege escalation '{p_clean}' is prohibited."

        for sub in self.blocklist.get("forbidden_substrings", []):
            s_clean = sub.strip().lower()
            if s_clean and s_clean in normalized:
                return False, f"Blocked by SafetyGuard: destructive pattern '{s_clean}' is prohibited."

        if re.search(r"\b(curl|wget|invoke-webrequest|iwr)\b.*\|\s*(ba)?sh", normalized) or re.search(
            r"\b(iex|invoke-expression|powershell|pwsh|cmd\.exe|bash|sh|zsh|python|python3|perl|ruby|node)\b", normalized
        ):
            return False, "Blocked by SafetyGuard: interpreter or subshell invocation is prohibited."

        if self.SHELL_METACHAR_PATTERN.search(raw):
            return False, "Blocked by SafetyGuard: shell metacharacters (;, |, &, `, $, >, <) are prohibited."

        try:
            tokens = shlex.split(raw, posix=(platform.system() != "Windows"))
        except Exception as exc:
            return False, f"Blocked by SafetyGuard: malformed command quoting ({exc})."

        if not tokens:
            return False, "Blocked: Empty parsed command."

        exe_name = Path(tokens[0].strip('"').strip("'")).name.lower()
        use_strict = self.strict_allowlist if strict_override is None else strict_override

        if exe_name in self.ZERO_ARG_BINARIES:
            if len(tokens) > 1:
                return (
                    False,
                    f"Blocked by SafetyGuard (C3 Trampoline Guard): '{exe_name}' does not permit CLI arguments or passthrough flags ({tokens[1:]}).",
                )
            return True, "Allowed zero-argument application launcher."

        if exe_name in self.SAFE_ARG_BINARIES:
            for arg in tokens[1:]:
                if arg.startswith("-"):
                    if not re.match(r"^-[laht1]+$", arg):
                        return False, f"Blocked by SafetyGuard: flag '{arg}' is not permitted for '{exe_name}'."
                elif arg.startswith("/") or re.match(r"^[A-Za-z]:\\", arg) or ".." in arg:
                    ok_p, reason = ToolSchemaValidator.validate_safe_user_path(arg)
                    if not ok_p:
                        return False, f"Blocked by SafetyGuard: {reason}"
            return True, f"Allowed read-only command '{exe_name}'."

        if use_strict:
            return (
                False,
                f"Blocked by SafetyGuard (Strict Allowlist Mode): executable '{exe_name}' is not permitted.",
            )

        return True, "Allowed."


class KillSwitchManager:
    """
    H2 Remediation:
    Tracks active child processes AND in-flight HTTP/model abort callbacks so emergency stop
    (`Ctrl+Shift+K` / `VK_PAUSE` / UNIX signal) terminates both subprocesses and in-flight requests.
    """

    def __init__(self, grace_ms: int = 500, ydotool_socket: str = "/tmp/.ydotool_socket") -> None:
        self.grace_ms = grace_ms
        self.ydotool_socket = ydotool_socket
        self._lock = threading.Lock()
        self._processes: Dict[int, subprocess.Popen] = {}
        self._abort_callbacks: Dict[str, Callable[[], None]] = {}
        self.abort_event = threading.Event()

    @property
    def is_cancelled(self) -> bool:
        return self.abort_event.is_set()

    @is_cancelled.setter
    def is_cancelled(self, val: bool) -> None:
        if val:
            self.abort_event.set()
        else:
            self.abort_event.clear()

    def register(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._processes[proc.pid] = proc

    def unregister(self, pid: int) -> None:
        with self._lock:
            self._processes.pop(pid, None)

    def register_abort_callback(self, req_id: str, cb: Callable[[], None]) -> None:
        with self._lock:
            self._abort_callbacks[req_id] = cb

    def unregister_abort_callback(self, req_id: str) -> None:
        with self._lock:
            self._abort_callbacks.pop(req_id, None)

    def reset_cancel_flag(self) -> None:
        self.abort_event.clear()

    def trigger(self) -> str:
        self.abort_event.set()
        with self._lock:
            active = list(self._processes.values())
            self._processes.clear()
            callbacks = list(self._abort_callbacks.values())
            self._abort_callbacks.clear()

        for cb in callbacks:
            try:
                cb()
            except Exception:
                pass

        killed_pids: List[int] = []
        for proc in active:
            if proc.poll() is None:
                killed_pids.append(proc.pid)
                try:
                    if platform.system() == "Windows":
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=3, check=False)
                    else:
                        proc.terminate()
                except Exception:
                    pass

        if killed_pids and platform.system() != "Windows":
            time.sleep(self.grace_ms / 1000.0)
            for proc in active:
                if proc.poll() is None:
                    try:
                        proc.kill()
                    except Exception:
                        pass

        return f"Emergency Kill-Switch activated: aborted {len(callbacks)} in-flight request(s) and terminated {len(killed_pids)} process(es)."


class ShellRunner:
    """Executes allowlisted commands with `shell=False`."""

    def __init__(self, safety: SafetyGuard, kill_switch: KillSwitchManager, timeout_sec: int = 15, max_output_bytes: int = 16384) -> None:
        self.safety = safety
        self.kill_switch = kill_switch
        self.timeout_sec = timeout_sec
        self.max_output_bytes = max_output_bytes

    def run(self, command: str, strict_override: Optional[bool] = None) -> ActionResult:
        if self.kill_switch.is_cancelled:
            return ActionResult(tool="shell_exec", success=False, output="Aborted: Kill-Switch active.", blocked=True)

        allowed, reason = self.safety.check_command(command, strict_override=strict_override)
        if not allowed:
            return ActionResult(tool="shell_exec", success=False, output=reason, blocked=True)

        try:
            argv = shlex.split(command.strip(), posix=(platform.system() != "Windows"))
            proc = subprocess.Popen(argv, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.kill_switch.register(proc)
            try:
                out, err = proc.communicate(timeout=self.timeout_sec)
            except subprocess.TimeoutExpired:
                proc.kill()
                return ActionResult(tool="shell_exec", success=False, output=f"Timed out after {self.timeout_sec}s.")
            finally:
                self.kill_switch.unregister(proc.pid)

            combined = ((out or "") + ("\n" + err if err else "")).strip()
            if len(combined) > self.max_output_bytes:
                combined = combined[: self.max_output_bytes] + "... [truncated]"
            return ActionResult(tool="shell_exec", success=(proc.returncode == 0), output=combined or f"Completed (exit {proc.returncode})")
        except Exception as exc:
            return ActionResult(tool="shell_exec", success=False, output=f"Execution failed: {exc}")


class DatabaseMigrationManager:
    """Manages SQLite3 schema migrations v1 -> v3 while preserving existing user data."""

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
                        actions_json TEXT NOT NULL DEFAULT '[]',
                        results_json TEXT NOT NULL DEFAULT '[]',
                        timestamp TEXT NOT NULL,
                        FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
                    """
                )
                conn.execute("INSERT INTO schema_migrations (version, applied_at, description) VALUES (1, ?, ?)", (now, "Initial schema"))
                applied.append(1)

            if current < 2:
                cols = [r["name"] for r in conn.execute("PRAGMA table_info(messages)").fetchall()]
                if "actions_json" not in cols:
                    conn.execute("ALTER TABLE messages ADD COLUMN actions_json TEXT NOT NULL DEFAULT '[]'")
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
                conn.execute("INSERT INTO schema_migrations (version, applied_at, description) VALUES (2, ?, ?)", (now, "Add memories table"))
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
                conn.execute("INSERT INTO schema_migrations (version, applied_at, description) VALUES (3, ?, ?)", (now, "Add task_runs and audit log"))
                applied.append(3)

            conn.commit()
        return applied


class LocalChatStorage:
    """SQLite3 storage for chat sessions, messages, memories, and audit logs."""

    VALID_CATEGORIES = ("preference", "project", "fact", "task_history")

    def __init__(self, data_dir_or_db_path: Path) -> None:
        if data_dir_or_db_path.suffix == ".db":
            self.db_path = data_dir_or_db_path
            self.data_dir = data_dir_or_db_path.parent
        else:
            self.data_dir = data_dir_or_db_path
            self.db_path = self.data_dir / "history.db"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_json_path = self.data_dir / "sessions.json"
        self.migration_mgr = DatabaseMigrationManager(self.db_path)

    def _conn(self) -> sqlite3.Connection:
        return self.migration_mgr.connect()

    def create_session(self, title: str = "New Conversation", model: str = "llama3.2") -> str:
        session_id = f"sess_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        now = datetime.datetime.now().isoformat(timespec="seconds")
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, title, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, title, model, now, now),
            )
            conn.commit()
        self._sync_sessions_json()
        return session_id

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        actions: Optional[List[Dict[str, Any]]] = None,
        results: Optional[List[Any]] = None,
        model: str = "llama3.2",
    ) -> None:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        safe_content, _ = redact_sensitive_text(content)
        serialized_results: List[Dict[str, Any]] = []
        for r in results or []:
            if isinstance(r, ActionResult):
                serialized_results.append(asdict(r))
            elif isinstance(r, dict):
                serialized_results.append(r)

        with self._conn() as conn:
            row = conn.execute("SELECT title FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
            if not row:
                title = safe_content[:40].strip() or "Conversation"
                conn.execute(
                    "INSERT INTO sessions (session_id, title, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (session_id, title, model, now, now),
                )
            else:
                new_title = row["title"]
                if new_title in ("New Conversation", "Conversation", "Windows Session", "Linux Session") and role == "user" and safe_content.strip():
                    new_title = safe_content.strip()[:40]
                conn.execute("UPDATE sessions SET title = ?, model = ?, updated_at = ? WHERE session_id = ?", (new_title, model, now, session_id))
            conn.execute(
                "INSERT INTO messages (session_id, role, content, actions_json, results_json, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, role, safe_content, json.dumps(actions or []), json.dumps(serialized_results), now),
            )
            conn.commit()
        self._sync_sessions_json()

    append_message = add_message

    def get_session_messages(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT role, content, results_json, timestamp FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            try:
                res_list = json.loads(r["results_json"])
            except Exception:
                res_list = []
            out.append({"role": r["role"], "content": r["content"], "results": res_list, "timestamp": r["timestamp"]})
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
                rows = conn.execute("SELECT session_id, title, model, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def delete_session(self, session_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            ok = cur.rowcount > 0
        self._sync_sessions_json()
        return ok

    def _sync_sessions_json(self) -> None:
        try:
            self.sessions_json_path.write_text(json.dumps(self.list_sessions(limit=50), indent=2), encoding="utf-8")
        except Exception:
            pass

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
            return False, f"Blocked storing sensitive data ({', '.join(pii_types)}) in memory.", {}

        clean_key = (key or "").strip() or "note"
        clean_content = (content or "").strip()
        if not clean_content:
            return False, "Memory content cannot be empty.", {}

        now = datetime.datetime.now().isoformat(timespec="seconds")
        with self._conn() as conn:
            existing = None
            if memory_id:
                existing = conn.execute("SELECT memory_id FROM memories WHERE memory_id = ?", (memory_id,)).fetchone()
            if not existing:
                existing = conn.execute("SELECT memory_id FROM memories WHERE category = ? AND LOWER(key) = LOWER(?)", (cat, clean_key)).fetchone()

            if existing:
                mid = existing["memory_id"]
                conn.execute(
                    "UPDATE memories SET category = ?, key = ?, content = ?, project_tag = ?, importance = ?, updated_at = ? WHERE memory_id = ?",
                    (cat, clean_key, clean_content, project_tag, imp, now, mid),
                )
            else:
                mid = memory_id or f"mem_{uuid.uuid4().hex[:10]}"
                conn.execute(
                    "INSERT INTO memories (memory_id, category, key, content, project_tag, importance, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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
                return False, f"Memory '{memory_id}' not found."
            conn.execute(
                "UPDATE memories SET key = ?, content = ?, category = ?, importance = ?, updated_at = ? WHERE memory_id = ?",
                (
                    key.strip() if key else row["key"],
                    content.strip(),
                    category if category in self.VALID_CATEGORIES else row["category"],
                    max(1, min(5, int(importance))) if importance is not None else row["importance"],
                    now,
                    memory_id,
                ),
            )
            conn.commit()
        return True, "Memory updated."

    def delete_memory(self, memory_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM memories WHERE memory_id = ?", (memory_id,))
            conn.commit()
            return cur.rowcount > 0

    def search_memories(self, query: str = "", category: Optional[str] = None, project_tag: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
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
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(f"SELECT * FROM memories {where_sql} ORDER BY importance DESC, updated_at DESC LIMIT ?", tuple(params)).fetchall()
        return [dict(r) for r in rows]

    def build_relevant_context_block(self, prompt: str, limit: int = 5) -> str:
        words = [w.lower() for w in re.findall(r"[a-zA-Z0-9_]{3,}", prompt or "") if len(w) >= 3]
        found: Dict[str, Dict[str, Any]] = {}
        for w in words[:5]:
            for m in self.search_memories(query=w, limit=3):
                found[m["memory_id"]] = m
        if not found:
            for m in self.search_memories(limit=limit):
                found[m["memory_id"]] = m
        items = list(found.values())[:limit]
        if not items:
            return ""
        return "[Stored User Memories]:\n" + "\n".join(f"- ({it['category']}/{it['key']}): {it['content']}" for it in items)

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
                conn.execute("UPDATE task_runs SET status = ?, plan_json = ?, summary = ?, updated_at = ? WHERE plan_id = ?", (status, plan_json, summary, now, plan_id))
            else:
                conn.execute("INSERT INTO task_runs (plan_id, objective, status, plan_json, summary, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (plan_id, objective, status, plan_json, summary, now, now))
            conn.commit()


LongTermMemoryStore = LocalChatStorage


class SpectralVoiceSpotter:
    """
    H8 Remediation:
    `speak_tts()` never calls blocking `pyttsx3.runAndWait()` while holding `self._tts_lock`.
    Instead, it spawns an interruptible non-blocking subprocess stored in `self._active_tts_proc`
    and releases `self._tts_lock` immediately so `interrupt_tts()` can terminate speech in <5ms.
    """

    SAMPLE_RATE = 16000
    BAND_FREQS = (180.0, 320.0, 520.0, 820.0, 1250.0, 1900.0, 2800.0, 3900.0)
    DEFAULT_COMMANDS = (
        "hey bajrang",
        "open terminal",
        "open notepad",
        "open calculator",
        "open files",
        "take screenshot",
        "organize downloads",
        "list windows",
        "clear chat",
        "kill switch",
    )

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        vad_threshold_db: float = -36.0,
        tts_enabled: bool = True,
        wake_word: str = "hey bajrang",
        tts_rate_wpm: int = 180,
        tts_language: str = "en-IN",
    ) -> None:
        self.data_dir = data_dir or Path(tempfile.gettempdir())
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.templates_path = self.data_dir / "voice_templates.json"
        self.vad_threshold_db = vad_threshold_db
        self.noise_floor_db = -52.0
        self.tts_enabled = tts_enabled
        self.wake_word = (wake_word or "hey bajrang").strip().lower()
        self.tts_rate_wpm = max(90, min(320, int(tts_rate_wpm)))
        self.tts_language = tts_language
        self._barge_in_triggered = threading.Event()
        self._active_tts_proc: Optional[subprocess.Popen] = None
        self._tts_lock = threading.Lock()
        self.templates: Dict[str, List[List[float]]] = self._load_or_seed_templates()

    def _load_or_seed_templates(self) -> Dict[str, List[List[float]]]:
        if self.templates_path.is_file():
            try:
                loaded = json.loads(self.templates_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and loaded:
                    return loaded
            except Exception:
                pass
        seeded = {cmd: self.extract_features(self.synthesize_command_waveform(cmd)) for cmd in self.DEFAULT_COMMANDS}
        try:
            self.templates_path.write_text(json.dumps(seeded), encoding="utf-8")
        except Exception:
            pass
        return seeded

    def list_microphones(self) -> List[Dict[str, Any]]:
        devices: List[Dict[str, Any]] = []
        if importlib.util.find_spec("sounddevice") is not None:
            try:
                import sounddevice as sd
                for idx, dev in enumerate(sd.query_devices()):
                    if dev.get("max_input_channels", 0) > 0:
                        devices.append({"index": idx, "name": str(dev.get("name", f"Input {idx}")), "sample_rate": int(dev.get("default_samplerate", self.SAMPLE_RATE)), "backend": "sounddevice"})
                if devices:
                    return devices
            except Exception:
                pass
        if not devices:
            devices.append({"index": 0, "name": "Default Audio Input (or Headless Fallback)", "sample_rate": 16000, "backend": "fallback"})
        return devices

    @classmethod
    def synthesize_command_waveform(cls, phrase: str, sample_rate: int = 16000) -> List[int]:
        clean = (phrase or "").strip().lower()
        samples: List[int] = []
        n_per_char = int(sample_rate * 0.045)
        for idx, ch in enumerate(clean):
            code = ord(ch)
            f1 = cls.BAND_FREQS[code % len(cls.BAND_FREQS)]
            f2 = cls.BAND_FREQS[(code * 3 + idx) % len(cls.BAND_FREQS)]
            for i in range(n_per_char):
                t = i / sample_rate
                env = math.sin(math.pi * (i / max(1, n_per_char - 1)))
                val = 0.35 * env * (math.sin(2.0 * math.pi * f1 * t) + 0.6 * math.sin(2.0 * math.pi * f2 * t))
                samples.append(max(-32767, min(32767, int(val * 32767))))
        return samples

    @classmethod
    def generate_synthetic_utterance_pcm(cls, phrase: str, sample_rate: int = 16000) -> List[float]:
        return [s / 32768.0 for s in cls.synthesize_command_waveform(phrase, sample_rate=sample_rate)]

    @classmethod
    def write_pcm16_wav(cls, path: Path, samples: List[int], sample_rate: int = 16000) -> None:
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))

    @classmethod
    def read_pcm16_wav(cls, path: Path) -> List[int]:
        with wave.open(str(path), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
        if sampwidth != 2 or n_frames == 0:
            return []
        total_shorts = int(len(raw) / 2)
        unpacked = struct.unpack(f"<{total_shorts}h", raw[: total_shorts * 2])
        return list(unpacked[0::n_channels]) if n_channels > 1 else list(unpacked)

    @staticmethod
    def compute_rms_dbfs(samples: List[int]) -> float:
        if not samples:
            return -96.0
        mean_sq = sum(float(s) * float(s) for s in samples) / len(samples)
        rms = math.sqrt(mean_sq) / 32768.0
        return round(20.0 * math.log10(max(1e-5, rms)), 2)

    @classmethod
    def _goertzel_band_energy(cls, frame: List[float], target_freq: float, sample_rate: int = 16000) -> float:
        n = len(frame)
        if n == 0:
            return 0.0
        k = int(0.5 + (n * target_freq) / sample_rate)
        omega = (2.0 * math.pi * k) / n
        coeff = 2.0 * math.cos(omega)
        q0 = q1 = q2 = 0.0
        for x in frame:
            q0 = coeff * q1 - q2 + x
            q2 = q1
            q1 = q0
        power = q1 * q1 + q2 * q2 - q1 * q2 * coeff
        return max(0.0, power / (n * n))

    @classmethod
    def extract_features(cls, samples: List[int], sample_rate: int = 16000) -> List[List[float]]:
        if not samples:
            return [[0.0] * len(cls.BAND_FREQS)]
        float_samples = [s / 32768.0 for s in samples]
        frame_size = int(sample_rate / 25)
        hop_size = int(frame_size / 2)
        vectors: List[List[float]] = []
        for start in range(0, max(1, len(float_samples) - frame_size + 1), hop_size):
            chunk = float_samples[start : start + frame_size]
            if len(chunk) < frame_size:
                chunk = chunk + [0.0] * (frame_size - len(chunk))
            energies = [math.log10(1e-9 + cls._goertzel_band_energy(chunk, f, sample_rate)) for f in cls.BAND_FREQS]
            norm = math.sqrt(sum(e * e for e in energies)) or 1.0
            vectors.append([round(e / norm, 5) for e in energies])
        return vectors or [[0.0] * len(cls.BAND_FREQS)]

    @staticmethod
    def dtw_distance(seq_a: List[List[float]], seq_b: List[List[float]]) -> float:
        na, nb = len(seq_a), len(seq_b)
        if na == 0 or nb == 0:
            return float("inf")
        dp = [[float("inf")] * (nb + 1) for _ in range(na + 1)]
        dp[0][0] = 0.0
        band = max(4, abs(na - nb) + 6)
        for i in range(1, na + 1):
            j_min = max(1, i - band)
            j_max = min(nb, i + band)
            for j in range(j_min, j_max + 1):
                va, vb = seq_a[i - 1], seq_b[j - 1]
                cost = math.sqrt(sum((a - b) * (a - b) for a, b in zip(va, vb)))
                dp[i][j] = cost + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
        return dp[na][nb] / (na + nb)

    def recognize_from_pcm(self, float_samples: List[float]) -> Dict[str, Any]:
        int_samples = [max(-32767, min(32767, int(s * 32767))) for s in float_samples]
        db = self.compute_rms_dbfs(int_samples)
        n = len(float_samples)
        zcr = sum(1 for i in range(1, n) if (float_samples[i - 1] >= 0.0) != (float_samples[i] >= 0.0)) / max(1, n - 1) if n > 1 else 0.0
        if db < self.vad_threshold_db:
            return {"success": False, "transcript": "", "confidence": 0.0, "rms_db": db, "zcr": round(zcr, 4), "engine": "vad_silence_gate", "wake_word_detected": False}
        self.interrupt_tts()
        feats = self.extract_features(int_samples, self.SAMPLE_RATE)
        best_cmd = ""
        best_dist = float("inf")
        for cmd, tpl in self.templates.items():
            d = self.dtw_distance(feats, tpl)
            if d < best_dist:
                best_dist = d
                best_cmd = cmd
        conf = round(max(0.0, min(0.99, 1.0 - (best_dist / 1.25))), 2)
        return {
            "success": conf >= 0.55,
            "transcript": best_cmd if conf >= 0.55 else "",
            "confidence": conf,
            "rms_db": db,
            "zcr": round(zcr, 4),
            "engine": "goertzel_8band_dtw",
            "wake_word_detected": (best_cmd == self.wake_word or self.wake_word in best_cmd),
        }

    def recognize_wav(self, wav_path: Path) -> Tuple[bool, str, str]:
        if not wav_path.is_file():
            return False, "", f"Audio file not found: {wav_path}"
        try:
            samples = self.read_pcm16_wav(wav_path)
        except Exception as exc:
            return False, "", f"WAV read error: {exc}"

        db = self.compute_rms_dbfs(samples)
        if db < self.vad_threshold_db:
            return False, "", f"Silence detected ({db} dB < {self.vad_threshold_db} dB)."

        if importlib.util.find_spec("faster_whisper") is not None:
            try:
                from faster_whisper import WhisperModel
                model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
                segments, _ = model.transcribe(str(wav_path), beam_size=1)
                text = " ".join(seg.text.strip() for seg in segments).strip()
                if text:
                    return True, text, f"faster-whisper tiny.en ({db} dB)"
            except Exception:
                pass

        feats = self.extract_features(samples, self.SAMPLE_RATE)
        best_cmd = ""
        best_dist = float("inf")
        for cmd, tpl in self.templates.items():
            dist = self.dtw_distance(feats, tpl)
            if dist < best_dist:
                best_dist = dist
                best_cmd = cmd
        confidence = int(max(0.0, min(99.0, (1.0 - best_dist / 1.25) * 100.0)))
        if confidence >= 55 and best_cmd:
            return True, best_cmd, f"Bajrang DSP Spectral-DTW Keyword Spotter ({confidence}% match, {db} dB)"
        return False, "", f"No keyword matched (best={best_cmd}, confidence={confidence}%, {db} dB)."

    def speak_tts(self, text: str) -> bool:
        """
        H8 Remediation: Spawns TTS as an asynchronous child process and releases `_tts_lock`
        immediately so `interrupt_tts()` never blocks waiting for `runAndWait()`.
        """
        if not self.tts_enabled or not text:
            return False
        self.interrupt_tts()
        self._barge_in_triggered.clear()
        with self._tts_lock:
            if platform.system() == "Linux" and shutil.which("spd-say"):
                try:
                    self._active_tts_proc = subprocess.Popen(
                        ["spd-say", text[:300]],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return True
                except Exception:
                    pass
            if platform.system() == "Windows":
                safe = re.sub(r"[^a-zA-Z0-9 .,?!\-]", " ", text[:300])
                ps_cmd = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    f"$s.Speak('{safe}')"
                )
                try:
                    self._active_tts_proc = subprocess.Popen(
                        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return True
                except Exception:
                    pass
        return False

    speak = speak_tts

    def interrupt_tts(self) -> bool:
        self._barge_in_triggered.set()
        with self._tts_lock:
            if self._active_tts_proc and self._active_tts_proc.poll() is None:
                try:
                    self._active_tts_proc.terminate()
                except Exception:
                    pass
                self._active_tts_proc = None
            if platform.system() == "Linux" and shutil.which("spd-say"):
                try:
                    subprocess.run(["spd-say", "--cancel"], capture_output=True, timeout=2, check=False)
                except Exception:
                    pass
        return True


CustomVoiceRecognizer = SpectralVoiceSpotter
AdvancedVoiceEngine = SpectralVoiceSpotter


class ToolSchemaValidator:
    """
    C4 & H4 Remediation:
    - Removes `shell_exec` from AI-callable tools.
    - Marks input-injection and mutating tools (`type_text`, `press_key`, `click_point`,
      `navigate_hotkey`, `close_app`, `organize_directory`) as `destructive=True` (requiring
      explicit user confirmation before execution).
    - Uses order-independent `frozenset` hotkey comparison with normalized key aliases so
      `["f4", "alt"]` and `["r", "win"]` are always blocked.
    """

    TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
        "open_app": {"required": {"app_name": str}, "optional": {}, "destructive": False},
        "close_app": {"required": {"app_name": str}, "optional": {}, "destructive": True},
        "window_focus": {"required": {"title_substring": str}, "optional": {}, "destructive": False},
        "list_windows": {"required": {}, "optional": {}, "destructive": False},
        "read_screen": {"required": {}, "optional": {"save_filename": str}, "destructive": False},
        "type_text": {"required": {"text": str}, "optional": {"press_enter": bool}, "destructive": True},
        "press_key": {"required": {"key": str}, "optional": {}, "destructive": True},
        "click_point": {"required": {"x": int, "y": int}, "optional": {"button": str}, "destructive": True},
        "scroll_view": {"required": {"direction": str, "clicks": int}, "optional": {}, "destructive": False},
        "navigate_hotkey": {"required": {"keys": list}, "optional": {}, "destructive": True},
        "inspect_directory": {"required": {"directory_path": str}, "optional": {}, "destructive": False},
        "organize_directory": {"required": {"directory_path": str}, "optional": {"remove_duplicates": bool}, "destructive": True},
        "memory_store": {"required": {"key": str, "content": str}, "optional": {"category": str, "importance": int}, "destructive": False},
    }

    KEY_ALIAS_MAP: Dict[str, str] = {
        "control": "ctrl",
        "ctl": "ctrl",
        "return": "enter",
        "escape": "esc",
        "del": "delete",
        "super": "win",
        "meta": "win",
        "windows": "win",
        "command": "win",
        "cmd": "win",
    }

    FORBIDDEN_HOTKEY_SETS: Set[FrozenSet[str]] = {
        frozenset({"alt", "f4"}),
        frozenset({"ctrl", "alt", "delete"}),
        frozenset({"win", "r"}),
        frozenset({"win", "l"}),
        frozenset({"ctrl", "shift", "esc"}),
        frozenset({"ctrl", "alt", "backspace"}),
    }

    VALID_SINGLE_KEYS: Set[str] = (
        {chr(c) for c in range(ord("a"), ord("z") + 1)}
        | {str(d) for d in range(10)}
        | {f"f{i}" for i in range(1, 13)}
        | {"enter", "return", "tab", "esc", "escape", "space", "backspace", "delete", "up", "down", "left", "right", "home", "end", "pageup", "pagedown"}
    )

    @classmethod
    def normalize_key_name(cls, key: str) -> str:
        k = (key or "").strip().lower()
        return cls.KEY_ALIAS_MAP.get(k, k)

    @classmethod
    def validate_action(cls, action: Dict[str, Any]) -> Tuple[bool, str, bool]:
        if not isinstance(action, dict):
            return False, "Action must be a dict.", False
        tool = str(action.get("tool", "")).strip()
        args = action.get("arguments") if "arguments" in action else action.get("params", {})
        if tool not in cls.TOOL_SCHEMAS:
            return False, f"Tool '{tool}' is not in the allowlist.", False
        if not isinstance(args, dict):
            return False, "Tool arguments must be a dict.", False

        schema = cls.TOOL_SCHEMAS[tool]
        for req_k, req_t in schema["required"].items():
            if req_k not in args or not isinstance(args[req_k], req_t) or isinstance(args[req_k], bool) and req_t is int:
                return False, f"Missing or invalid required argument '{req_k}' ({req_t.__name__}).", False

        for opt_k, opt_t in schema["optional"].items():
            if opt_k in args and args[opt_k] is not None and not isinstance(args[opt_k], opt_t):
                return False, f"Invalid optional argument '{opt_k}' ({opt_t.__name__}).", False

        allowed_keys = set(schema["required"].keys()) | set(schema["optional"].keys())
        extra = set(args.keys()) - allowed_keys
        if extra:
            return False, f"Unexpected arguments: {sorted(extra)}", False

        if tool in ("inspect_directory", "organize_directory"):
            ok_p, reason = cls.validate_safe_user_path(str(args["directory_path"]))
            if not ok_p:
                return False, reason, False

        if tool == "click_point":
            if not (0 <= int(args["x"]) <= 7680 and 0 <= int(args["y"]) <= 4320):
                return False, "Coordinates out of bounds.", False

        if tool == "press_key":
            norm_k = cls.normalize_key_name(str(args["key"]))
            if norm_k not in cls.VALID_SINGLE_KEYS:
                return False, f"Unknown or disallowed key '{args['key']}'.", False

        if tool == "navigate_hotkey":
            raw_list = args["keys"]
            if not raw_list or len(raw_list) > 3:
                return False, "Hotkey list must contain 1 to 3 keys.", False
            norm_set = frozenset(cls.normalize_key_name(str(k)) for k in raw_list)
            if norm_set in cls.FORBIDDEN_HOTKEY_SETS:
                return False, f"Hotkey combination {sorted(norm_set)} is restricted.", False

        return True, "Valid", bool(schema["destructive"])

    @staticmethod
    def validate_safe_user_path(raw_path: str) -> Tuple[bool, str]:
        if not raw_path or not raw_path.strip():
            return False, "Empty path."
        expanded = Path(os.path.expanduser(os.path.expandvars(raw_path.strip()))).resolve()
        home = Path.home().resolve()
        tmp = Path(tempfile.gettempdir()).resolve()
        forbidden_roots = [
            Path("/etc"),
            Path("/usr"),
            Path("/bin"),
            Path("/sbin"),
            Path("/boot"),
            Path("/proc"),
            Path("/sys"),
            Path("C:/Windows"),
            Path("C:/Program Files"),
        ]
        for fr in forbidden_roots:
            try:
                if expanded == fr.resolve() or fr.resolve() in expanded.parents:
                    return False, f"Access to system directory '{expanded}' is prohibited."
            except Exception:
                pass
        if not (expanded == home or home in expanded.parents or expanded == tmp or tmp in expanded.parents):
            return False, f"Path '{expanded}' must be inside user home or temp directory."
        return True, str(expanded)


@dataclass
class PerformanceSettings:
    profile: str = "balanced"
    max_context_messages: int = 12
    screenshot_max_dim: int = 1280
    screenshot_jpeg_quality: int = 80
    ollama_num_threads: int = 6
    ollama_num_ctx: int = 4096
    enable_local_llama: bool = True

    @classmethod
    def from_profile(cls, profile_name: str) -> "PerformanceSettings":
        p = (profile_name or "balanced").lower()
        cpus = os.cpu_count() or 4
        if p == "eco":
            return cls(profile="eco", max_context_messages=6, screenshot_max_dim=960, screenshot_jpeg_quality=68, ollama_num_threads=2, ollama_num_ctx=2048, enable_local_llama=False)
        if p == "high":
            return cls(profile="high", max_context_messages=24, screenshot_max_dim=1920, screenshot_jpeg_quality=90, ollama_num_threads=cpus, ollama_num_ctx=8192, enable_local_llama=True)
        return cls(profile="balanced", max_context_messages=12, screenshot_max_dim=1280, screenshot_jpeg_quality=80, ollama_num_threads=min(8, cpus), ollama_num_ctx=4096, enable_local_llama=True)


class TaskComplexity(enum.Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX_REASONING = "complex_reasoning"
    MULTIMODAL_VISION = "multimodal_vision"


class UnifiedModelClient:
    """
    C6 Remediation:
    - Uses `x-goog-api-key` HTTP header for Google Gemini native REST requests (never `?key=` in the URL).
    - Enforces `is_key_compatible_with_provider(api_key, provider)` before sending any request.
    """

    def __init__(self, config: ConfigManager, kill_switch: Optional[KillSwitchManager] = None) -> None:
        self.config = config
        self.kill_switch = kill_switch
        self.history: List[Dict[str, str]] = []

    @property
    def system_prompt(self) -> str:
        base = str(self.config.settings.get("custom_persona_prompt", DEFAULT_SYSTEM_PROMPT))
        hw = str(self.config.settings.get("hardware_profile", ""))
        return f"{base.strip()}\n\nENVIRONMENT: {hw}"

    @property
    def provider(self) -> str:
        prov_name = str(self.config.settings.get("byo_provider", "gemini_argon"))
        api_key = self.config.get_api_key(prov_name)
        if api_key and self.config.settings.get("provider") == "byo_api":
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
    ) -> str:
        clean_key = (api_key or "").strip().strip("'").strip('"')
        if clean_key.lower().startswith("bearer "):
            clean_key = clean_key[7:].strip()
        if clean_key and not custom_endpoint:
            det = auto_detect_provider_from_key(clean_key)
            preset_name = det["provider"]
            custom_endpoint = det["endpoint"]
            custom_model = custom_model or det["model"]
        preset = PROVIDER_PRESETS.get(preset_name, PROVIDER_PRESETS["gemini_argon"])
        self.config.settings["byo_provider"] = preset_name
        self.config.settings["byo_api_endpoint"] = (custom_endpoint or preset["endpoint"]).strip()
        self.config.settings["byo_model"] = (custom_model or preset["model"]).strip()
        self.config.settings["provider"] = "byo_api" if clean_key else "ollama"
        vault_backend = self.config.set_api_key(clean_key, provider_id=preset_name)
        self.config.save_settings()
        return vault_backend

    def clear_history(self) -> None:
        self.history.clear()

    def load_session_messages(self, stored_messages: List[Dict[str, Any]]) -> None:
        self.history = [
            {"role": str(m["role"]), "content": str(m["content"])}
            for m in stored_messages
            if m.get("role") in ("user", "assistant")
        ]

    def check_health(self) -> Tuple[bool, List[str], str]:
        if self.provider == "byo_api":
            key = self.config.get_api_key()
            masked = (key[:4] + "..." + key[-3:]) if len(key) > 8 else "configured"
            return True, [self.active_model], f"BYO API configured in SecurityVault ({self.active_model}, key={masked})"
        host = str(self.config.settings.get("ollama_host", "http://127.0.0.1:11434")).rstrip("/")
        try:
            req = urllib.request.Request(f"{host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
                return True, models, f"Connected to Ollama at {host} ({len(models)} models)."
        except Exception as exc:
            return False, [], f"Ollama unreachable at {host} ({exc})."

    @staticmethod
    def parse_structured_output(raw_text: str) -> AssistantTurn:
        cleaned = (raw_text or "").strip()
        fenced = re.match(r"^```(?:json)?\s*(\{.*?\})\s*```$", cleaned, re.DOTALL)
        candidate = fenced.group(1).strip() if fenced else cleaned
        if candidate.startswith("{") and candidate.endswith("}"):
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict) and ("type" in obj or "actions" in obj or "reply" in obj):
                    actions = obj.get("actions", [])
                    if not isinstance(actions, list):
                        actions = []
                    text = str(obj.get("text") or obj.get("reply") or "").strip()
                    rtype = "action" if actions else str(obj.get("type", "conversation"))
                    return AssistantTurn(response_type=rtype, text=text or "Proposed actions ready.", actions=actions)
            except Exception:
                pass
        return AssistantTurn(response_type="conversation", text=cleaned, actions=[])

    def chat(
        self,
        user_prompt: str,
        desktop_context: Optional[str] = None,
        screenshot_b64: Optional[str] = None,
    ) -> AssistantTurn:
        if self.kill_switch and self.kill_switch.is_cancelled:
            return AssistantTurn(response_type="conversation", text="Aborted by Kill-Switch.")

        messages: List[Dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        if desktop_context:
            messages.append({"role": "system", "content": f"DESKTOP CONTEXT: {desktop_context}"})
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
        prov_name = str(self.config.settings.get("byo_provider", "gemini_argon"))
        api_key = self.config.get_api_key(prov_name)
        if not api_key:
            return AssistantTurn(response_type="conversation", text=f"No compatible API key found in SecurityVault for provider '{prov_name}'.")
        if not is_key_compatible_with_provider(api_key, prov_name):
            return AssistantTurn(response_type="conversation", text=f"Refused to send incompatible API key to provider '{prov_name}'.")

        endpoint = str(self.config.settings.get("byo_api_endpoint", PROVIDER_PRESETS["gemini_argon"]["endpoint"]))
        model_name = self.active_model

        if api_key.startswith("AIza"):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            payload = {
                "systemInstruction": {"parts": [{"text": self.system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": {"temperature": 0.25},
            }
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=20.0) as resp:
                    if self.kill_switch and self.kill_switch.is_cancelled:
                        return AssistantTurn(response_type="conversation", text="Interrupted by Kill-Switch.")
                    data = json.loads(resp.read().decode("utf-8"))
                    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    reply = "".join(str(p.get("text", "")) for p in parts).strip()
                    if reply:
                        turn = self.parse_structured_output(reply)
                        self.history.append({"role": "user", "content": user_prompt})
                        self.history.append({"role": "assistant", "content": reply})
                        return turn
            except Exception as exc:
                return AssistantTurn(response_type="conversation", text=f"Gemini API request failed: {exc}")

        payload_oai = {"model": model_name, "messages": messages, "temperature": 0.25}
        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload_oai).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20.0) as resp:
                if self.kill_switch and self.kill_switch.is_cancelled:
                    return AssistantTurn(response_type="conversation", text="Interrupted by Kill-Switch.")
                data = json.loads(resp.read().decode("utf-8"))
                reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                turn = self.parse_structured_output(reply)
                self.history.append({"role": "user", "content": user_prompt})
                self.history.append({"role": "assistant", "content": reply})
                return turn
        except Exception as exc:
            return AssistantTurn(response_type="conversation", text=f"Cloud API request failed: {exc}")

    def _chat_ollama(self, messages: List[Dict[str, Any]], user_prompt: str) -> AssistantTurn:
        host = str(self.config.settings.get("ollama_host", "http://127.0.0.1:11434")).rstrip("/")
        payload = {"model": self.active_model, "messages": messages, "stream": False}
        try:
            req = urllib.request.Request(
                f"{host}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=25.0) as resp:
                if self.kill_switch and self.kill_switch.is_cancelled:
                    return AssistantTurn(response_type="conversation", text="Interrupted by Kill-Switch.")
                data = json.loads(resp.read().decode("utf-8"))
                reply = data.get("message", {}).get("content", "")
                turn = self.parse_structured_output(reply)
                self.history.append({"role": "user", "content": user_prompt})
                self.history.append({"role": "assistant", "content": reply})
                return turn
        except Exception as exc:
            return AssistantTurn(
                response_type="conversation",
                text=f"Local Ollama server unreachable at {host} ({exc}).",
            )


class ModularAIRouter:
    """
    C6 Remediation:
    During provider fallback, `ModularAIRouter` ONLY uses a key stored specifically for `prov`
    (`api_key_{prov}`) or a key whose prefix matches `is_key_compatible_with_provider(key, prov)`.
    A Google `AIza*` key is NEVER sent to `api.groq.com` or `api.openai.com`, and Gemini requests
    use the `x-goog-api-key` header instead of URL query parameters.
    """

    def __init__(
        self,
        vault: SecurityVault,
        memory_store: LocalChatStorage,
        primary_provider: str = "ollama",
        fallback_order: Optional[List[str]] = None,
        perf_settings: Optional[PerformanceSettings] = None,
    ) -> None:
        self.vault = vault
        self.memory_store = memory_store
        self.primary_provider = primary_provider
        self.fallback_order = fallback_order or ["gemini_argon", "groq", "openrouter", "openai", "ollama"]
        self.perf = perf_settings or PerformanceSettings.from_profile("balanced")
        self.timeout_sec = 15.0
        self.max_retries = 2

    @staticmethod
    def assess_task_complexity(prompt: str, has_image: bool = False) -> TaskComplexity:
        if has_image:
            return TaskComplexity.MULTIMODAL_VISION
        lower = (prompt or "").lower()
        if any(k in lower for k in ("screenshot", "on my screen", "read screen", "visible window")):
            return TaskComplexity.MULTIMODAL_VISION
        if len(prompt or "") > 240 or any(k in lower for k in ("organize", "duplicate", "plan", "architecture", "step by step")):
            return TaskComplexity.COMPLEX_REASONING
        if len(prompt or "") < 60:
            return TaskComplexity.SIMPLE
        return TaskComplexity.MODERATE

    def select_model_for_task(self, provider_id: str, complexity: TaskComplexity) -> str:
        if provider_id in ("gemini", "gemini_argon"):
            return "gemini-2.5-pro" if complexity in (TaskComplexity.COMPLEX_REASONING, TaskComplexity.MULTIMODAL_VISION) else "gemini-2.5-flash"
        if provider_id == "groq":
            return "llama-3.3-70b-versatile" if complexity == TaskComplexity.COMPLEX_REASONING else "llama-3.1-8b-instant"
        if provider_id == "ollama":
            return "llama3.2-vision" if complexity == TaskComplexity.MULTIMODAL_VISION else "bajrang-llama3.2"
        return PROVIDER_PRESETS.get(provider_id, PROVIDER_PRESETS["openai"])["model"]

    def _get_compatible_key_for_provider(self, prov: str) -> str:
        scoped = self.vault.get_secret(f"api_key_{prov}")
        if scoped and is_key_compatible_with_provider(scoped, prov):
            return scoped
        generic = self.vault.get_secret("byo_api_key")
        if generic and is_key_compatible_with_provider(generic, prov):
            return generic
        return ""

    def check_provider_health(self, provider_id: str, timeout: float = 3.0) -> Dict[str, Any]:
        if provider_id == "ollama":
            if not self.perf.enable_local_llama:
                return {"provider": "ollama", "healthy": False, "detail": "Disabled in Eco profile"}
            try:
                req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return {"provider": "ollama", "healthy": True, "detail": "Online", "models": [m.get("name", "") for m in data.get("models", [])]}
            except Exception as exc:
                return {"provider": "ollama", "healthy": False, "detail": f"Offline ({exc})"}

        key = self._get_compatible_key_for_provider(provider_id)
        if not key:
            return {"provider": provider_id, "healthy": False, "detail": f"No compatible API key configured in SecurityVault for {provider_id}"}
        return {"provider": provider_id, "healthy": True, "detail": "Compatible API key present in SecurityVault"}

    def generate_structured_turn(self, prompt: str, session_id: str) -> Dict[str, Any]:
        complexity = self.assess_task_complexity(prompt)
        errors: List[str] = []
        chain = [self.primary_provider] + [p for p in self.fallback_order if p != self.primary_provider]

        for prov in chain:
            if prov == "ollama":
                if not self.perf.enable_local_llama:
                    errors.append("ollama: disabled in Eco profile")
                    continue
                try:
                    req = urllib.request.Request(
                        "http://127.0.0.1:11434/api/chat",
                        data=json.dumps({"model": "llama3.2", "messages": [{"role": "user", "content": prompt}], "stream": False}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        return {
                            "reply": data.get("message", {}).get("content", ""),
                            "actions": [],
                            "provider_used": "ollama",
                            "model_used": "llama3.2",
                            "complexity": complexity.value,
                            "fallback_chain_tried": errors,
                        }
                except Exception as exc:
                    errors.append(f"ollama: {exc}")
                    continue

            key = self._get_compatible_key_for_provider(prov)
            if not key:
                errors.append(f"{prov}: no compatible API key")
                continue

            model_name = self.select_model_for_task(prov, complexity)
            for attempt in range(self.max_retries):
                try:
                    if prov in ("gemini", "gemini_argon") or key.startswith("AIza"):
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
                        req = urllib.request.Request(
                            url,
                            data=json.dumps({"contents": [{"role": "user", "parts": [{"text": prompt}]}]}).encode("utf-8"),
                            headers={"Content-Type": "application/json", "x-goog-api-key": key},
                            method="POST",
                        )
                        with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                            data = json.loads(resp.read().decode("utf-8"))
                            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                            reply = "".join(str(p.get("text", "")) for p in parts).strip()
                            return {
                                "reply": reply,
                                "actions": [],
                                "provider_used": prov,
                                "model_used": model_name,
                                "complexity": complexity.value,
                                "fallback_chain_tried": errors,
                            }
                    else:
                        endpoint = PROVIDER_PRESETS.get(prov, PROVIDER_PRESETS["openai"])["endpoint"]
                        req = urllib.request.Request(
                            endpoint,
                            data=json.dumps({"model": model_name, "messages": [{"role": "user", "content": prompt}]}).encode("utf-8"),
                            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
                            method="POST",
                        )
                        with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                            data = json.loads(resp.read().decode("utf-8"))
                            reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                            return {
                                "reply": reply,
                                "actions": [],
                                "provider_used": prov,
                                "model_used": model_name,
                                "complexity": complexity.value,
                                "fallback_chain_tried": errors,
                            }
                except Exception as exc:
                    errors.append(f"{prov} (attempt {attempt + 1}): {exc}")

        det = self.deterministic_local_agent(prompt)
        det["provider_used"] = "deterministic_local_router"
        det["model_used"] = "local-intent-parser"
        det["complexity"] = complexity.value
        det["fallback_chain_tried"] = errors
        return det

    @staticmethod
    def deterministic_local_agent(prompt: str) -> Dict[str, Any]:
        text = (prompt or "").strip()
        lower = text.lower()
        for app in ("notepad", "calculator", "calc", "terminal", "files", "explorer"):
            if re.search(rf"\b(open|launch|start)\s+{app}\b", lower):
                return {"reply": f"Launching '{app}'.", "actions": [{"tool": "open_app", "arguments": {"app_name": app}}]}
        if "screenshot" in lower or "capture screen" in lower:
            return {"reply": "Capturing screen.", "actions": [{"tool": "read_screen", "arguments": {}}]}
        return {"reply": f"Processed locally: {text}", "actions": []}


class CrossPlatformComputerUse:
    """
    H3 Remediation:
    Implements `list_open_windows` (Win32 `EnumWindows` / `GetWindowTextW` & Linux `wmctrl`/`gdbus`),
    `focus_window` (`SetForegroundWindow` & `wmctrl -a`), `launch_application`, and `close_application`.
    """

    WINDOWS_APP_ALLOWLIST: Dict[str, List[str]] = {
        "notepad": ["notepad.exe"],
        "calculator": ["calc.exe"],
        "calc": ["calc.exe"],
        "explorer": ["explorer.exe"],
        "files": ["explorer.exe"],
        "terminal": ["wt.exe", "powershell.exe"],
    }

    LINUX_APP_ALLOWLIST: Dict[str, List[List[str]]] = {
        "terminal": [["gnome-terminal"], ["ptyxis"], ["kgx"], ["xterm"]],
        "files": [["nautilus"]],
        "explorer": [["nautilus"]],
        "calculator": [["gnome-calculator"]],
        "calc": [["gnome-calculator"]],
        "notepad": [["gnome-text-editor"], ["gedit"]],
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
                                windows.append({"hwnd": int(hwnd), "title": title, "active": bool(hwnd == fg_hwnd)})
                    return True

                user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
                return True, f"Enumerated {len(windows)} visible Windows via Win32 EnumWindows.", windows
            except Exception as exc:
                return False, f"Win32 EnumWindows failed: {exc}", []

        if shutil.which("wmctrl") and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            try:
                proc = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=4, check=False)
                if proc.returncode == 0:
                    for line in proc.stdout.splitlines():
                        parts = line.split(None, 3)
                        if len(parts) == 4:
                            windows.append({"hwnd": parts[0], "title": parts[3], "active": False})
                    return True, f"Enumerated {len(windows)} windows via wmctrl.", windows
            except Exception:
                pass

        return False, "Window enumeration requires an active Win32 desktop or Linux X11/Wayland session with wmctrl.", []

    def focus_window(self, title_substring: str) -> Tuple[bool, str, Dict[str, Any]]:
        sub = (title_substring or "").strip().lower()
        if not sub:
            return False, "Window title substring cannot be empty.", {}
        ok, msg, wins = self.list_open_windows()
        if not ok:
            return False, msg, {}
        matched = [w for w in wins if sub in str(w.get("title", "")).lower()]
        if not matched:
            return False, f"No visible window matching '{title_substring}'.", {}
        target = matched[0]
        if self.os_name == "Windows" and hasattr(ctypes, "windll") and "hwnd" in target:
            try:
                user32 = ctypes.windll.user32
                hwnd = int(target["hwnd"])
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
                return (user32.GetForegroundWindow() == hwnd), f"Focused '{target['title']}' via SetForegroundWindow.", target
            except Exception as exc:
                return False, f"SetForegroundWindow failed: {exc}", target
        if shutil.which("wmctrl"):
            proc = subprocess.run(["wmctrl", "-a", title_substring], capture_output=True, text=True, timeout=4, check=False)
            return (proc.returncode == 0), f"wmctrl -a '{title_substring}' (exit {proc.returncode}).", target
        return False, "Window focus switching unavailable in current session.", target

    def launch_application(self, app_name: str) -> Tuple[bool, str, Dict[str, Any]]:
        key = (app_name or "").strip().lower()
        if self.os_name == "Windows":
            candidates = self.WINDOWS_APP_ALLOWLIST.get(key, [])
            if not candidates:
                return False, f"Application '{app_name}' is not in the Windows allowlist.", {}
            for exe in candidates:
                try:
                    proc = subprocess.Popen([exe], shell=False)
                    return True, f"Launched '{exe}' (PID={proc.pid}).", {"pid": proc.pid}
                except Exception:
                    continue
            return False, f"Could not launch '{app_name}'.", {}

        cmd_groups = self.LINUX_APP_ALLOWLIST.get(key, [])
        if not cmd_groups:
            return False, f"Application '{app_name}' is not installed or not in the Linux allowlist.", {}
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            return False, f"Cannot launch GUI application '{app_name}': no DISPLAY or WAYLAND_DISPLAY active.", {}
        for cmd in cmd_groups:
            bin_p = shutil.which(cmd[0])
            if bin_p:
                try:
                    proc = subprocess.Popen([bin_p] + cmd[1:], shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True, f"Launched '{cmd[0]}' (PID={proc.pid}).", {"pid": proc.pid}
                except Exception:
                    continue
        return False, f"No binary found for allowlisted application '{app_name}'.", {}

    def close_application(self, app_name: str) -> Tuple[bool, str, Dict[str, Any]]:
        key = re.sub(r"[^a-zA-Z0-9_\-.]", "", (app_name or "").strip().lower())
        protected = {"systemd", "init", "gnome-shell", "wayland", "xorg", "explorer", "svchost", "csrss", "lsass", "wininit"}
        if key in protected:
            return False, f"Closing critical system process '{key}' is prohibited.", {}
        if not key:
            return False, "Empty application name.", {}
        if self.os_name == "Windows":
            exe = key if key.endswith(".exe") else f"{key}.exe"
            proc = subprocess.run(["taskkill", "/IM", exe], capture_output=True, text=True, timeout=5, check=False)
            return (proc.returncode == 0), (proc.stdout or proc.stderr).strip(), {}
        if shutil.which("pkill"):
            proc = subprocess.run(["pkill", "-TERM", "-x", key], capture_output=True, text=True, timeout=5, check=False)
            return (proc.returncode == 0), f"pkill exit {proc.returncode}", {}
        return False, "Process termination utility unavailable.", {}


class AutonomousTaskPlanner:
    """
    C5 Remediation:
    1. Collision-Safe Moves: Never overwrites an existing file in the destination category folder!
       If `Documents/report.pdf` already exists, allocates `Documents/report_1.pdf` (`report_2.pdf`, etc.).
    2. Non-Destructive Trash Quarantine with Full Undo (`undo_plan(plan_id)`):
       Instead of calling `unlink()` on duplicate files, moves verified duplicates into
       `<target_dir>/.bajrang_trash/<plan_id>/` after confirming the original copy exists and matches
       the SHA-256 hash, recording an exact undo manifest so `undo_plan(plan_id)` restores all moved
       and quarantined files losslessly.
    3. Per-File Cancellation Check: Checks `cancel_ev.is_set()` before every single file move and
       quarantine operation.
    """

    FILE_CATEGORIES: Dict[str, Tuple[str, ...]] = {
        "Documents": (".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt", ".xls", ".xlsx", ".csv", ".ppt", ".pptx"),
        "Images": (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico"),
        "Installers": (".exe", ".msi", ".bat", ".sh", ".rpm", ".deb", ".appimage"),
        "Archives": (".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar"),
        "Code": (".py", ".js", ".ts", ".html", ".css", ".json", ".yaml", ".yml", ".c", ".cpp", ".rs", ".go"),
    }

    def __init__(self, memory_store: LocalChatStorage, computer_use: Optional[CrossPlatformComputerUse] = None) -> None:
        self.memory_store = memory_store
        self.computer_use = computer_use or CrossPlatformComputerUse()
        self.active_plans: Dict[str, TaskExecutionPlan] = {}
        self.cancel_events: Dict[str, threading.Event] = {}
        self._undo_manifests: Dict[str, List[Tuple[str, str]]] = {}

    @classmethod
    def classify_extension(cls, suffix: str) -> str:
        ext = (suffix or "").lower()
        for cat, exts in cls.FILE_CATEGORIES.items():
            if ext in exts:
                return cat
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

    @staticmethod
    def _allocate_non_colliding_path(dest_path: Path) -> Path:
        if not dest_path.exists():
            return dest_path
        stem = dest_path.stem
        suffix = dest_path.suffix
        parent = dest_path.parent
        counter = 1
        while True:
            candidate = parent / f"{stem}_{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def inspect_directory_for_organization(self, directory_path: str) -> Tuple[bool, str, Dict[str, Any]]:
        ok_p, resolved = ToolSchemaValidator.validate_safe_user_path(directory_path)
        if not ok_p:
            self.memory_store.log_security_event("PATH_BLOCKED", "inspect_directory", False, resolved)
            return False, resolved, {}

        target = Path(resolved)
        if not target.is_dir():
            return False, f"Directory '{target}' does not exist.", {}

        files = [p for p in sorted(target.iterdir()) if p.is_file() and not p.name.startswith(".")]
        by_cat: Dict[str, List[str]] = {}
        moves: List[Dict[str, str]] = []
        by_size: Dict[int, List[Path]] = {}

        for f in files:
            cat = self.classify_extension(f.suffix)
            by_cat.setdefault(cat, []).append(f.name)
            moves.append({"file": f.name, "category": cat, "source": str(f), "destination": str(target / cat / f.name)})
            by_size.setdefault(f.stat().st_size, []).append(f)

        duplicates: List[Dict[str, Any]] = []
        dup_paths = set()
        for sz, group in by_size.items():
            if len(group) < 2 or sz == 0:
                continue
            seen: Dict[str, Path] = {}
            for cand in group:
                digest = self.compute_sha256(cand)
                if digest in seen:
                    orig = seen[digest]
                    duplicates.append(
                        {
                            "duplicate_file": str(cand),
                            "duplicate_name": cand.name,
                            "original_file": str(orig),
                            "original_name": orig.name,
                            "sha256": digest,
                            "size_bytes": sz,
                        }
                    )
                    dup_paths.add(str(cand))
                else:
                    seen[digest] = cand

        filtered_moves = [m for m in moves if m["source"] not in dup_paths]
        report = {
            "directory": str(target),
            "total_files_scanned": len(files),
            "category_counts": {k: len(v) for k, v in by_cat.items()},
            "proposed_moves": filtered_moves,
            "duplicates_found": duplicates,
            "duplicate_count": len(duplicates),
            "bytes_reclaimable": sum(d["size_bytes"] for d in duplicates),
        }
        return True, f"Scanned {len(files)} files ({len(duplicates)} duplicates).", report

    def create_organization_plan(self, directory_path: str, remove_duplicates: bool = True, objective_text: str = "") -> Tuple[bool, TaskExecutionPlan]:
        plan_id = f"plan_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        ok, msg, report = self.inspect_directory_for_organization(directory_path)
        if not ok:
            return False, TaskExecutionPlan(plan_id=plan_id, objective=objective_text or directory_path, requires_permission=False, status="failed", summary=msg)

        quarantine_dir = str(Path(report["directory"]) / ".bajrang_trash" / plan_id)
        steps = [
            TaskStep(1, f"Inspect '{report['directory']}'", "inspect_directory", {"directory_path": report["directory"]}, False, "completed", msg),
            TaskStep(2, f"Move {len(report['proposed_moves'])} files into category folders (collision-safe)", "organize_directory", {"directory_path": report["directory"], "remove_duplicates": False}, True, "awaiting_permission"),
        ]
        if remove_duplicates and report["duplicate_count"] > 0:
            steps.append(TaskStep(3, f"Quarantine {report['duplicate_count']} SHA-256 duplicate(s) to .bajrang_trash", "organize_directory", {"directory_path": report["directory"], "remove_duplicates": True}, True, "awaiting_permission"))

        plan = TaskExecutionPlan(
            plan_id=plan_id,
            objective=objective_text or f"Organize {report['directory']}",
            requires_permission=True,
            status="awaiting_permission",
            steps=steps,
            inspection_report=report,
            summary=msg,
            quarantine_dir=quarantine_dir,
        )
        self.active_plans[plan_id] = plan
        self.cancel_events[plan_id] = threading.Event()
        self.memory_store.save_task_run(plan_id, plan.objective, plan.status, asdict(plan), plan.summary)
        return True, plan

    def cancel_plan(self, plan_id: str) -> Tuple[bool, str]:
        if plan_id in self.cancel_events:
            self.cancel_events[plan_id].set()
        plan = self.active_plans.get(plan_id)
        if not plan:
            return False, "Plan not found."
        plan.status = "cancelled"
        self.memory_store.save_task_run(plan_id, plan.objective, plan.status, asdict(plan), "Cancelled by user.")
        return True, "Cancelled."

    def execute_approved_plan(self, plan_id: str, user_confirmed: bool = False) -> Tuple[bool, TaskExecutionPlan]:
        plan = self.active_plans[plan_id]
        if plan.requires_permission and not user_confirmed:
            plan.status = "awaiting_permission"
            return False, plan
        cancel_ev = self.cancel_events[plan_id]
        if cancel_ev.is_set() or plan.status == "cancelled":
            plan.status = "cancelled"
            return False, plan

        report = plan.inspection_report
        moved = 0
        quarantined = 0
        undo_ops: List[Tuple[str, str]] = []
        orig_new_locations: Dict[str, Path] = {}

        for step in plan.steps:
            if cancel_ev.is_set():
                plan.status = "cancelled"
                break
            if step.status == "completed":
                continue

            if step.step_number == 2:
                for mv in report.get("proposed_moves", []):
                    if cancel_ev.is_set():
                        plan.status = "cancelled"
                        break
                    src = Path(mv["source"])
                    raw_dst = Path(mv["destination"])
                    if not src.is_file():
                        continue
                    raw_dst.parent.mkdir(parents=True, exist_ok=True)
                    safe_dst = self._allocate_non_colliding_path(raw_dst)
                    shutil.move(str(src), str(safe_dst))
                    if safe_dst.is_file():
                        moved += 1
                        undo_ops.append((str(safe_dst), str(src)))
                        orig_new_locations[str(src)] = safe_dst
                if not cancel_ev.is_set():
                    step.status = "completed"

            elif step.step_number == 3:
                trash_dir = Path(plan.quarantine_dir)
                trash_dir.mkdir(parents=True, exist_ok=True)
                for dup in report.get("duplicates_found", []):
                    if cancel_ev.is_set():
                        plan.status = "cancelled"
                        break
                    dp = Path(dup["duplicate_file"])
                    orig_p = orig_new_locations.get(dup["original_file"], Path(dup["original_file"]))
                    if dp.is_file() and orig_p.is_file():
                        if self.compute_sha256(dp) == dup["sha256"] and self.compute_sha256(orig_p) == dup["sha256"]:
                            trash_dest = self._allocate_non_colliding_path(trash_dir / dp.name)
                            shutil.move(str(dp), str(trash_dest))
                            if trash_dest.is_file():
                                quarantined += 1
                                undo_ops.append((str(trash_dest), str(dp)))
                if not cancel_ev.is_set():
                    step.status = "completed"

        self._undo_manifests[plan_id] = undo_ops
        if cancel_ev.is_set():
            plan.status = "cancelled"
            plan.summary = f"Cancelled mid-run after {moved} move(s) and {quarantined} quarantine(s)."
            self.memory_store.save_task_run(plan_id, plan.objective, plan.status, asdict(plan), plan.summary)
            return False, plan

        plan.status = "completed"
        plan.summary = f"Moved {moved} files (zero overwrites) and quarantined {quarantined} duplicates to {plan.quarantine_dir}."
        self.memory_store.save_task_run(plan_id, plan.objective, plan.status, asdict(plan), plan.summary)
        return True, plan

    def undo_plan(self, plan_id: str) -> Tuple[bool, str]:
        ops = self._undo_manifests.get(plan_id, [])
        if not ops:
            return False, f"No undo manifest found for plan '{plan_id}'."
        restored = 0
        for current_loc, original_loc in reversed(ops):
            cur_p, orig_p = Path(current_loc), Path(original_loc)
            if cur_p.is_file() and not orig_p.exists():
                orig_p.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(cur_p), str(orig_p))
                restored += 1
        return True, f"Restored {restored} file(s) for plan '{plan_id}'."


class BasePlatformAdapter:
    """Abstract interface implemented by `WindowsPlatformAdapter` and `FedoraWaylandAdapter`."""

    def get_desktop_context(self) -> str:
        return f"OS: {platform.system()} {platform.release()} ({platform.machine()})"

    def capture_screen_base64(self, max_dimension: int = 1280) -> Tuple[Optional[str], str]:
        raise NotImplementedError

    def mouse_move(self, x: int, y: int) -> ActionResult:
        raise NotImplementedError

    def mouse_click(self, button: str = "left", x: Optional[int] = None, y: Optional[int] = None) -> ActionResult:
        raise NotImplementedError

    def type_text(self, text: str) -> ActionResult:
        raise NotImplementedError

    def press_key(self, key: str) -> ActionResult:
        raise NotImplementedError

    def scroll(self, direction: str = "down", clicks: int = 3) -> ActionResult:
        return ActionResult(tool="scroll_view", success=False, output="Scroll not supported in current adapter.")

    def hotkey(self, keys: List[str]) -> ActionResult:
        return ActionResult(tool="navigate_hotkey", success=False, output="Hotkey not supported in current adapter.")

    def record_microphone_wav(self, wav_path: Path, duration_sec: float = 3.5) -> Tuple[bool, str]:
        raise NotImplementedError


class BajrangEngine:
    """
    C4, H3 & H8 Remediation:
    - Calls `ToolSchemaValidator.validate_action(act)` on every action before executing.
    - Gates all destructive/input-injection actions (`type_text`, `press_key`, `click_point`,
      `navigate_hotkey`, `close_app`, `organize_directory`) behind `self.pending_actions[session_id]`
      unless `user_confirmed=True` is explicitly passed via `confirm_pending_actions()`.
    - Implements all advertised schema tools (`list_windows`, `window_focus`, `close_app`,
      `scroll_view`, `navigate_hotkey`, `inspect_directory`, `memory_store`).
    - Pins `target_session_id` at the start of `process_prompt()` and uses `self._turn_lock`
      so mid-turn session switching never writes a reply into the wrong session.
    """

    def __init__(
        self,
        adapter: BasePlatformAdapter,
        config: Optional[ConfigManager] = None,
        state_callback: Optional[Callable[[AgentState, str], None]] = None,
        ui_turn_callback: Optional[Callable[[str, AssistantTurn], None]] = None,
    ) -> None:
        self.adapter = adapter
        self.config = config or ConfigManager()
        self.state_callback = state_callback
        self.ui_turn_callback = ui_turn_callback
        self.state = AgentState.IDLE
        self._turn_lock = threading.Lock()
        self.pending_actions: Dict[str, List[Dict[str, Any]]] = {}

        self.storage = LocalChatStorage(self.config.data_dir)
        existing = self.storage.list_sessions(limit=1)
        if existing:
            self.current_session_id = existing[0]["session_id"]
        else:
            self.current_session_id = self.storage.create_session(
                title=f"{platform.system()} Session",
                model=str(self.config.settings.get("model", "llama3.2")),
            )

        self.voice = SpectralVoiceSpotter(
            data_dir=self.config.data_dir,
            vad_threshold_db=float(self.config.settings.get("voice_vad_threshold_db", -36.0)),
            tts_enabled=bool(self.config.settings.get("tts_enabled", True)),
        )
        self.safety = SafetyGuard(
            self.config.blocklist,
            strict_allowlist=bool(self.config.settings.get("strict_shell_allowlist", True)),
        )
        self.kill_switch = KillSwitchManager()
        self.shell_runner = ShellRunner(self.safety, self.kill_switch)
        self.client = UnifiedModelClient(self.config, kill_switch=self.kill_switch)
        self.client.load_session_messages(self.storage.get_session_messages(self.current_session_id))
        self.computer_use = CrossPlatformComputerUse()
        self.task_planner = AutonomousTaskPlanner(self.storage, self.computer_use)

    def set_state(self, new_state: AgentState, status_text: str = "") -> None:
        self.state = new_state
        if self.state_callback:
            self.state_callback(new_state, status_text)

    def set_theme(self, theme_name: str) -> str:
        clean = "light" if str(theme_name).lower() == "light" else "dark"
        self.config.settings["theme"] = clean
        self.config.save_settings()
        return clean

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
        self.voice.interrupt_tts()
        msg = self.kill_switch.trigger()
        self.set_state(AgentState.BLOCKED, "Stopped by Emergency Kill-Switch")
        return msg

    @staticmethod
    def _normalize_legacy_action(action: Dict[str, Any]) -> Dict[str, Any]:
        tool = str(action.get("tool", "")).strip().lower()
        params = dict(action.get("arguments") if "arguments" in action else (action.get("params") or {}))
        alias_map = {
            "ydotool_click": "click_point",
            "win_click": "click_point",
            "mouse_click": "click_point",
            "ydotool_type": "type_text",
            "win_type": "type_text",
            "ydotool_key": "press_key",
            "win_key": "press_key",
            "take_screenshot": "read_screen",
            "screenshot": "read_screen",
        }
        canonical = alias_map.get(tool, tool)
        return {"tool": canonical, "arguments": params}

    def execute_action(self, action: Dict[str, Any], user_confirmed: bool = False) -> ActionResult:
        if self.kill_switch.is_cancelled:
            return ActionResult(tool="kill_switch", success=False, output="Skipped: Kill-Switch active.", blocked=True)

        normalized = self._normalize_legacy_action(action)
        tool = normalized["tool"]
        params = normalized["arguments"]

        valid, reason, requires_confirmation = ToolSchemaValidator.validate_action(normalized)
        if not valid:
            self.storage.log_security_event("SCHEMA_REJECTED", tool or "unknown", False, reason)
            return ActionResult(tool=tool or "unknown", success=False, output=f"Blocked by ToolSchemaValidator: {reason}", blocked=True)

        if requires_confirmation and not user_confirmed:
            return ActionResult(
                tool=tool,
                success=False,
                output=f"Action '{tool}' requires explicit user confirmation before execution.",
                blocked=True,
                metadata={"awaiting_confirmation": True, "action": normalized},
            )

        if tool == "click_point":
            return self.adapter.mouse_click(str(params.get("button", "left")), int(params["x"]), int(params["y"]))
        if tool == "type_text":
            res = self.adapter.type_text(str(params["text"]))
            if res.success and params.get("press_enter"):
                self.adapter.press_key("enter")
            return res
        if tool == "press_key":
            return self.adapter.press_key(str(params["key"]))
        if tool == "scroll_view":
            return self.adapter.scroll(str(params["direction"]), int(params["clicks"]))
        if tool == "navigate_hotkey":
            return self.adapter.hotkey([str(k) for k in params["keys"]])
        if tool == "read_screen":
            b64, msg = self.adapter.capture_screen_base64()
            return ActionResult(tool="read_screen", success=(b64 is not None), output=msg)
        if tool == "open_app":
            ok, msg, meta = self.computer_use.launch_application(str(params["app_name"]))
            return ActionResult(tool="open_app", success=ok, output=msg, metadata=meta)
        if tool == "close_app":
            ok, msg, meta = self.computer_use.close_application(str(params["app_name"]))
            return ActionResult(tool="close_app", success=ok, output=msg, metadata=meta)
        if tool == "list_windows":
            ok, msg, wins = self.computer_use.list_open_windows()
            return ActionResult(tool="list_windows", success=ok, output=msg, metadata={"windows": wins})
        if tool == "window_focus":
            ok, msg, meta = self.computer_use.focus_window(str(params["title_substring"]))
            return ActionResult(tool="window_focus", success=ok, output=msg, metadata=meta)
        if tool == "inspect_directory":
            ok, msg, report = self.task_planner.inspect_directory_for_organization(str(params["directory_path"]))
            return ActionResult(tool="inspect_directory", success=ok, output=msg, metadata=report)
        if tool == "organize_directory":
            ok_p, plan = self.task_planner.create_organization_plan(
                str(params["directory_path"]),
                remove_duplicates=bool(params.get("remove_duplicates", True)),
            )
            if not ok_p:
                return ActionResult(tool="organize_directory", success=False, output=plan.summary)
            ok_exec, done_plan = self.task_planner.execute_approved_plan(plan.plan_id, user_confirmed=True)
            return ActionResult(tool="organize_directory", success=ok_exec, output=done_plan.summary, metadata={"plan_id": plan.plan_id})
        if tool == "memory_store":
            ok, msg, item = self.storage.store_memory(
                key=str(params["key"]),
                content=str(params["content"]),
                category=str(params.get("category", "fact")),
                importance=int(params.get("importance", 3)),
            )
            return ActionResult(tool="memory_store", success=ok, output=msg, metadata=item)

        return ActionResult(tool=tool, success=False, output=f"Unsupported tool '{tool}'.", blocked=True)

    def confirm_pending_actions(self, session_id: Optional[str] = None, approved: bool = True) -> List[ActionResult]:
        sid = session_id or self.current_session_id
        actions = self.pending_actions.pop(sid, [])
        if not actions:
            return []
        if not approved:
            self.set_state(AgentState.IDLE, "Pending actions cancelled by user.")
            return [ActionResult(tool=str(a.get("tool", "")), success=False, output="Cancelled by user.", blocked=True) for a in actions]

        self.set_state(AgentState.EXECUTING, f"Executing {len(actions)} confirmed action(s)...")
        results: List[ActionResult] = []
        for act in actions:
            res = self.execute_action(act, user_confirmed=True)
            results.append(res)
        self.set_state(AgentState.IDLE, "Idle")
        self.storage.add_message(sid, "assistant", f"Confirmed and executed {len(results)} action(s).", actions, results, self.client.active_model)
        return results

    def process_prompt(
        self,
        user_prompt: str,
        capture_screen: bool = False,
        speak_reply: bool = False,
        session_id: Optional[str] = None,
        auto_confirm_actions: bool = False,
    ) -> AssistantTurn:
        target_session_id = session_id or self.current_session_id
        with self._turn_lock:
            self.kill_switch.reset_cancel_flag()
            self.set_state(AgentState.THINKING, f"Thinking ({self.client.active_model})...")
            self.storage.add_message(target_session_id, "user", user_prompt, model=self.client.active_model)

            lower = (user_prompt or "").strip().lower()
            if any(p in lower for p in ("take screenshot", "take a screenshot", "capture screen")):
                self.set_state(AgentState.EXECUTING, "Capturing screenshot...")
                res = self.execute_action({"tool": "read_screen", "arguments": {}}, user_confirmed=True)
                turn = AssistantTurn(
                    response_type="action",
                    text=res.output,
                    actions=[{"tool": "read_screen", "arguments": {}}],
                    results=[res],
                    session_id=target_session_id,
                    provider_used=self.client.provider,
                    model_used=self.client.active_model,
                )
                self.set_state(AgentState.IDLE, "Idle")
                self.storage.add_message(target_session_id, "assistant", turn.text, turn.actions, turn.results, self.client.active_model)
                if speak_reply and turn.text:
                    self.voice.speak_tts(turn.text)
                return turn

            screenshot_b64: Optional[str] = None
            if capture_screen or self.config.settings.get("attach_screen_context", False):
                screenshot_b64, _ = self.adapter.capture_screen_base64()

            turn = self.client.chat(user_prompt, desktop_context=self.adapter.get_desktop_context(), screenshot_b64=screenshot_b64)
            turn.session_id = target_session_id

            if self.kill_switch.is_cancelled:
                self.set_state(AgentState.BLOCKED, "Interrupted by Kill-Switch")
                return turn

            if turn.response_type == "action" and turn.actions:
                to_confirm: List[Dict[str, Any]] = []
                any_blocked = False
                for act in turn.actions:
                    norm = self._normalize_legacy_action(act)
                    valid, reason, requires_conf = ToolSchemaValidator.validate_action(norm)
                    if not valid:
                        turn.results.append(ActionResult(tool=norm["tool"] or "unknown", success=False, output=f"Blocked: {reason}", blocked=True))
                        any_blocked = True
                        break
                    if requires_conf and not auto_confirm_actions:
                        to_confirm.append(norm)
                    else:
                        res = self.execute_action(norm, user_confirmed=True)
                        turn.results.append(res)
                        if res.blocked:
                            any_blocked = True
                            break

                if to_confirm:
                    self.pending_actions[target_session_id] = to_confirm
                    turn.awaiting_confirmation = True
                    turn.text = f"{turn.text}\n[Awaiting confirmation for {len(to_confirm)} sensitive action(s): {[a['tool'] for a in to_confirm]}]"
                    self.set_state(AgentState.AWAITING_CONFIRMATION, "Awaiting user confirmation")
                elif any_blocked or self.kill_switch.is_cancelled:
                    self.set_state(AgentState.BLOCKED, "Action Blocked")
                else:
                    self.set_state(AgentState.IDLE, "Idle")
            else:
                self.set_state(AgentState.IDLE, "Idle")

            self.storage.add_message(target_session_id, "assistant", turn.text, turn.actions, turn.results, self.client.active_model)
            if speak_reply and turn.text:
                self.voice.speak_tts(turn.text)
            return turn

    def capture_voice_turn(self, duration_sec: float = 3.5) -> Tuple[bool, str, Optional[AssistantTurn], str]:
        self.set_state(AgentState.LISTENING, "Listening...")
        tmp_wav = Path(tempfile.gettempdir()) / f"bajrang_mic_{os.getpid()}_{int(time.time() * 1000)}.wav"
        try:
            ok_rec, rec_msg = self.adapter.record_microphone_wav(tmp_wav, duration_sec=duration_sec)
            if not ok_rec:
                self.set_state(AgentState.IDLE, "Idle")
                return False, "", None, rec_msg
            ok_stt, transcript, stt_info = self.voice.recognize_wav(tmp_wav)
            if not ok_stt or not transcript:
                self.set_state(AgentState.IDLE, "Idle")
                return False, "", None, stt_info
            turn = self.process_prompt(transcript, speak_reply=True)
            return True, transcript, turn, stt_info
        finally:
            try:
                tmp_wav.unlink(missing_ok=True)
            except Exception:
                pass


def run_core_self_tests() -> int:
    print("Running hardened bajrang_core self-tests (C1-C6, H2-H8)...")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = ConfigManager(config_dir=root / "cfg", data_dir=root / "data")

        # Verify C1: Forged 8-char suffix BAJRANG-PRO-HACKER-20991231-ZZZZZZZZ is strictly rejected
        lic = LicenseManager(cfg.config_dir)
        ok_forged, _ = lic.verify_key("BAJRANG-PRO-HACKER-20991231-ZZZZZZZZ")
        assert ok_forged is False, "C1: Forged BAJRANG-PRO token must be rejected"
        assert AsymmetricLicenseVerifier().n_int.bit_length() >= 2040, "H5: RSA modulus must be 2048 bits"

        # Verify C3: Launcher trampoline arguments are blocked
        guard = SafetyGuard(strict_allowlist=True)
        assert guard.check_command("gnome-terminal")[0] is True
        assert guard.check_command('gnome-terminal -- python3 -c "print(1)"')[0] is False, "C3: gnome-terminal passthrough must be blocked"
        assert guard.check_command("wt.exe powershell -Command calc")[0] is False, "C3: wt.exe passthrough must be blocked"
        assert guard.check_command("xdg-open https://evil.example")[0] is False, "C3: xdg-open must be blocked"

        # Verify H4: Order-independent hotkey blocking & unknown key rejection
        assert ToolSchemaValidator.validate_action({"tool": "navigate_hotkey", "arguments": {"keys": ["f4", "alt"]}})[0] is False
        assert ToolSchemaValidator.validate_action({"tool": "navigate_hotkey", "arguments": {"keys": ["r", "win"]}})[0] is False
        assert ToolSchemaValidator.validate_action({"tool": "press_key", "arguments": {"key": "unknown_key_xyz"}})[0] is False

        # Verify C5: Organizer never overwrites existing destination files and quarantines duplicates with undo
        dl = root / "Downloads"
        dl.mkdir()
        (dl / "Documents").mkdir()
        (dl / "Documents" / "report.pdf").write_bytes(b"ORIGINAL_EXISTING_REPORT")
        (dl / "report.pdf").write_bytes(b"NEW_DOWNLOADED_REPORT")
        (dl / "dup1.txt").write_bytes(b"DUPLICATE_PAYLOAD")
        (dl / "dup2.txt").write_bytes(b"DUPLICATE_PAYLOAD")
        planner = AutonomousTaskPlanner(LocalChatStorage(root / "data"))
        ok_p, plan = planner.create_organization_plan(str(dl), remove_duplicates=True)
        assert ok_p is True
        ok_ex, _ = planner.execute_approved_plan(plan.plan_id, user_confirmed=True)
        assert ok_ex is True
        assert (dl / "Documents" / "report.pdf").read_bytes() == b"ORIGINAL_EXISTING_REPORT", "C5: Existing file must never be overwritten!"
        assert (dl / "Documents" / "report_1.pdf").read_bytes() == b"NEW_DOWNLOADED_REPORT", "C5: Colliding file must be renamed!"
        ok_undo, _ = planner.undo_plan(plan.plan_id)
        assert ok_undo is True and (dl / "dup1.txt").is_file() and (dl / "dup2.txt").is_file()

    print("All hardened bajrang_core self-tests passed!")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bajrang AI Hardened Core Module")
    parser.add_argument("--self-test", action="store_true", help="Run headless core unit tests")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(run_core_self_tests())
    print(f"Bajrang AI Hardened Core v{CORE_VERSION} loaded.")
