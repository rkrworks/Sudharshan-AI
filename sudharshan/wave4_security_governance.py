import difflib
import enum
import hashlib
import hmac
import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import bajrang_core


class HashChainedAuditLog:
    GENESIS = "0" * 64

    def __init__(self, db_path: Path, signing_key: Optional[bytes] = None) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.signing_key = signing_key or hashlib.sha256(b"sudharshan-local-audit-key").digest()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS audit_chain (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    entry_hash TEXT NOT NULL,
                    signature TEXT NOT NULL
                )"""
            )
            conn.commit()

    def _compute(self, prev_hash: str, ts: float, action: str, actor: str, payload_json: str) -> Tuple[str, str]:
        body = f"{prev_hash}|{ts:.6f}|{action}|{actor}|{payload_json}".encode("utf-8")
        entry_hash = hashlib.sha256(body).hexdigest()
        sig = hmac.new(self.signing_key, entry_hash.encode("ascii"), hashlib.sha256).hexdigest()
        return entry_hash, sig

    def append(self, action: str, actor: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        ts = time.time()
        payload_json = json.dumps(payload, sort_keys=True)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT entry_hash FROM audit_chain ORDER BY seq DESC LIMIT 1").fetchone()
            prev_hash = row[0] if row else self.GENESIS
            entry_hash, sig = self._compute(prev_hash, ts, action, actor, payload_json)
            conn.execute(
                "INSERT INTO audit_chain (ts, action, actor, payload_json, prev_hash, entry_hash, signature) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts, action, actor, payload_json, prev_hash, entry_hash, sig),
            )
            conn.commit()
        return {"prev_hash": prev_hash, "entry_hash": entry_hash, "signature": sig}

    def verify_chain(self) -> Tuple[bool, str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT seq, ts, action, actor, payload_json, prev_hash, entry_hash, signature FROM audit_chain ORDER BY seq ASC").fetchall()
        expected_prev = self.GENESIS
        for seq, ts, action, actor, payload_json, prev_hash, entry_hash, sig in rows:
            if prev_hash != expected_prev:
                return False, f"Broken chain link at seq {seq}"
            calc_hash, calc_sig = self._compute(prev_hash, ts, action, actor, payload_json)
            if not hmac.compare_digest(calc_hash, entry_hash) or not hmac.compare_digest(calc_sig, sig):
                return False, f"Tampered audit record at seq {seq}"
            expected_prev = entry_hash
        return True, f"Verified {len(rows)} chained entries"


class PermissionTier(enum.Enum):
    READ_ONLY = "read_only"
    SAFE_WRITE = "safe_write"
    ELEVATED_CONFIRM = "elevated_confirm"
    HARD_BLOCKED = "hard_blocked"


class FourTierPermissionEngine:
    TOOL_TIERS: Dict[str, PermissionTier] = {
        "list_windows": PermissionTier.READ_ONLY,
        "inspect_directory": PermissionTier.READ_ONLY,
        "search_kb": PermissionTier.READ_ONLY,
        "memory_store": PermissionTier.SAFE_WRITE,
        "export_markdown": PermissionTier.SAFE_WRITE,
        "organize_directory": PermissionTier.ELEVATED_CONFIRM,
        "close_app": PermissionTier.ELEVATED_CONFIRM,
        "kill_process": PermissionTier.ELEVATED_CONFIRM,
        "shell_exec": PermissionTier.HARD_BLOCKED,
        "format_disk": PermissionTier.HARD_BLOCKED,
    }

    @classmethod
    def evaluate(cls, tool_name: str, user_confirmed: bool = False) -> Dict[str, Any]:
        tier = cls.TOOL_TIERS.get(tool_name, PermissionTier.ELEVATED_CONFIRM)
        if tier == PermissionTier.HARD_BLOCKED:
            return {"allowed": False, "tier": tier.value, "requires_confirmation": False, "reason": "Hard-blocked tool"}
        if tier == PermissionTier.ELEVATED_CONFIRM and not user_confirmed:
            return {"allowed": False, "tier": tier.value, "requires_confirmation": True, "reason": "Explicit user confirmation required"}
        return {"allowed": True, "tier": tier.value, "requires_confirmation": False, "reason": "Permitted"}


class CommandPreviewDiffBuilder:
    @staticmethod
    def build_file_diff(path: str, before: str, after: str) -> str:
        diff_lines = difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
        return "".join(diff_lines)

    @staticmethod
    def build_mutation_modal_payload(operation: str, targets: List[str], diff_preview: str = "") -> Dict[str, Any]:
        return {
            "operation": operation,
            "target_count": len(targets),
            "targets": list(targets),
            "diff_preview": diff_preview,
            "requires_confirm": True,
        }


class PreActionRollbackManager:
    def __init__(self, snapshot_root: Path) -> None:
        self.snapshot_root = Path(snapshot_root)
        self.snapshot_root.mkdir(parents=True, exist_ok=True)

    def create_snapshot(self, action_id: str, files: List[Path]) -> Path:
        snap_dir = self.snapshot_root / action_id
        snap_dir.mkdir(parents=True, exist_ok=True)
        manifest = []
        for idx, fp in enumerate(files):
            fp = Path(fp).resolve()
            if fp.is_file():
                backup = snap_dir / f"{idx}_{fp.name}"
                shutil.copy2(fp, backup)
                manifest.append({"original": str(fp), "backup": str(backup), "existed": True})
            else:
                manifest.append({"original": str(fp), "backup": "", "existed": False})
        (snap_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return snap_dir

    def rollback(self, action_id: str) -> int:
        snap_dir = self.snapshot_root / action_id
        manifest_path = snap_dir / "manifest.json"
        if not manifest_path.is_file():
            return 0
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        restored = 0
        for item in manifest:
            orig = Path(item["original"])
            if item["existed"]:
                orig.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(Path(item["backup"]), orig)
                restored += 1
            elif orig.exists():
                orig.unlink()
                restored += 1
        return restored


class ShellCommandSanitizer:
    BLOCKED_PATTERNS: List[Tuple[str, str]] = [
        ("fork_bomb", r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),
        ("pipe_to_shell", r"\b(?:curl|wget)\b[^|]*\|\s*(?:sh|bash|zsh|python|python3)\b"),
        ("destructive_glob", r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+(?:/\s*$|/\*|~|\$HOME)"),
        ("mkfs_dd", r"\b(?:mkfs\.[a-z0-9]+|dd\s+if=/dev/(?:zero|random)\s+of=/dev/[sh]d)"),
        ("subshell_eval", r"(?:\$\(|`|;\s*rm\b)"),
    ]

    @classmethod
    def inspect(cls, command: str) -> Tuple[bool, str]:
        cmd = (command or "").strip()
        if not cmd:
            return False, "Empty command rejected"
        for label, pat in cls.BLOCKED_PATTERNS:
            if re.search(pat, cmd, re.I):
                return False, f"Blocked by sanitizer rule: {label}"
        try:
            tokens = shlex.split(cmd)
        except ValueError as exc:
            return False, f"Malformed shell quoting: {exc}"
        if not tokens:
            return False, "Empty token stream"
        return True, "Sanitized"


class SecretPIIRedactor:
    PATTERNS: List[Tuple[str, str]] = [
        ("PRIVATE_KEY", r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        ("GEMINI_KEY", r"\bAIza[0-9A-Za-z\-_]{20,}\b"),
        ("OPENAI_KEY", r"\bsk-(?:proj-)?[0-9A-Za-z\-_]{20,}\b"),
        ("GROQ_KEY", r"\bgsk_[0-9A-Za-z]{20,}\b"),
        ("AWS_KEY", r"\bAKIA[0-9A-Z]{16}\b"),
        ("JWT", r"\beyJ[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}\b"),
        ("EMAIL", r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        ("CREDIT_CARD", r"\b(?:\d[ -]*?){13,16}\b"),
    ]

    @classmethod
    def redact(cls, text: str) -> str:
        out = text or ""
        for label, pat in cls.PATTERNS:
            out = re.sub(pat, f"[REDACTED_{label}]", out)
        return out


class OSKeyringAdapter:
    def __init__(self, vault_dir: Path) -> None:
        self.vault = bajrang_core.SecurityVault(Path(vault_dir))

    def store(self, key_name: str, secret_value: str) -> str:
        return self.vault.store_secret(key_name, secret_value)

    def retrieve(self, key_name: str) -> str:
        return self.vault.get_secret(key_name)


class NetworkEgressController:
    def __init__(self, airplane_mode: bool = True, allowed_hosts: Optional[List[str]] = None) -> None:
        self.airplane_mode = airplane_mode
        self.allowed_hosts = set(allowed_hosts or ["127.0.0.1", "localhost"])
        self.external_bytes_sent = 0
        self.blocked_hosts: List[str] = []

    def check_egress(self, host: str, payload_bytes: int = 0) -> Tuple[bool, str]:
        h = (host or "").strip().lower()
        if h in ("127.0.0.1", "localhost", "::1"):
            return True, "Loopback traffic permitted"
        if self.airplane_mode:
            self.blocked_hosts.append(h)
            return False, f"Airplane mode kill-switch active: blocked egress to {h}"
        if h not in self.allowed_hosts:
            self.blocked_hosts.append(h)
            return False, f"Host '{h}' not in egress allowlist"
        self.external_bytes_sent += max(0, int(payload_bytes))
        return True, f"Egress permitted to allowlisted host {h}"


class IntegrityVerifier:
    @staticmethod
    def sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @classmethod
    def generate_manifest(cls, root: Path, files: List[Path]) -> str:
        lines = []
        for f in sorted(files):
            rel = Path(f).resolve().relative_to(Path(root).resolve()).as_posix()
            lines.append(f"{cls.sha256_file(f)}  {rel}")
        return "\n".join(lines) + "\n"

    @classmethod
    def verify_manifest(cls, root: Path, manifest_text: str) -> Tuple[bool, List[str]]:
        failures: List[str] = []
        root = Path(root).resolve()
        for line in (manifest_text or "").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = re.split(r"\s+", line, maxsplit=1)
            if len(parts) != 2:
                continue
            expected_hash, rel_path = parts[0].lower(), parts[1].lstrip("*")
            target = root / rel_path
            if not target.is_file():
                failures.append(f"MISSING: {rel_path}")
                continue
            actual = cls.sha256_file(target)
            if not hmac.compare_digest(actual, expected_hash):
                failures.append(f"MISMATCH: {rel_path}")
        return len(failures) == 0, failures


class PanicKillSwitch:
    def __init__(self) -> None:
        self._procs: List[subprocess.Popen] = []
        self.triggered_count = 0

    def register_process(self, proc: subprocess.Popen) -> None:
        self._procs.append(proc)

    def trigger_panic(self) -> Dict[str, int]:
        terminated = 0
        for p in list(self._procs):
            if p.poll() is None:
                try:
                    p.terminate()
                    p.wait(timeout=1.5)
                except Exception:
                    try:
                        p.kill()
                    except Exception:
                        pass
                terminated += 1
        self._procs.clear()
        self.triggered_count += 1
        return {"terminated_processes": terminated, "triggered_count": self.triggered_count}
