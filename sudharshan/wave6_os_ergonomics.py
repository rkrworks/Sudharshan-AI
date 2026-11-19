import os
import platform
import re
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import bajrang_core


class CommandPaletteEngine:
    def __init__(self) -> None:
        self._items: List[Dict[str, str]] = []

    def register(self, item_id: str, title: str, category: str, shortcut: str = "") -> None:
        self._items.append({"id": item_id, "title": title, "category": category, "shortcut": shortcut})

    def search(self, query: str, limit: int = 8) -> List[Dict[str, str]]:
        q = (query or "").strip().lower()
        if not q:
            return self._items[:limit]
        scored: List[Tuple[int, Dict[str, str]]] = []
        for item in self._items:
            hay = f"{item['title']} {item['category']} {item['id']}".lower()
            if q in hay:
                score = 100 - hay.find(q)
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [it for _, it in scored[:limit]]


class WindowManagementController:
    VALID_ACTIONS = ("tile_left", "tile_right", "maximize", "focus", "move_workspace", "group_by_task")

    @classmethod
    def plan_command(cls, action: str, target: str, workspace: Optional[int] = None) -> Dict[str, Any]:
        if action not in cls.VALID_ACTIONS:
            raise ValueError(f"Unsupported window action: {action}")
        return {"action": action, "target": target, "workspace": workspace, "platform": platform.system()}


class ClipboardHistoryManager:
    def __init__(self, db_path: Path, max_entries: int = 200) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS clipboard_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    pinned INTEGER DEFAULT 0,
                    created_at REAL NOT NULL
                )"""
            )
            conn.commit()

    def push(self, content: str, pinned: bool = False) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO clipboard_history (content, pinned, created_at) VALUES (?, ?, ?)",
                (content, 1 if pinned else 0, time.time()),
            )
            conn.commit()
            return int(cur.lastrowid)

    def pin(self, entry_id: int, pinned: bool = True) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE clipboard_history SET pinned=? WHERE id=?", (1 if pinned else 0, entry_id))
            conn.commit()

    def search(self, query: str) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, content, pinned, created_at FROM clipboard_history WHERE lower(content) LIKE ? ORDER BY pinned DESC, created_at DESC",
                (f"%{query.lower()}%",),
            ).fetchall()
        return [{"id": r[0], "content": r[1], "pinned": bool(r[2]), "created_at": r[3]} for r in rows]


class SystemThermalHUD:
    @staticmethod
    def snapshot() -> Dict[str, Any]:
        disk = shutil.disk_usage(Path.home())
        free_ram = bajrang_core.HardwareProfiler.get_free_ram_gb()
        temp_c: Optional[float] = None
        tz = Path("/sys/class/thermal/thermal_zone0/temp")
        if tz.is_file():
            try:
                temp_c = round(int(tz.read_text().strip()) / 1000.0, 1)
            except Exception:
                temp_c = None
        return {
            "cpu_count": os.cpu_count() or 1,
            "free_ram_gb": free_ram,
            "disk_free_gb": round(disk.free / (1024 ** 3), 2),
            "disk_total_gb": round(disk.total / (1024 ** 3), 2),
            "thermal_c": temp_c,
            "platform": platform.system(),
        }


class SystemSettingsController:
    @staticmethod
    def parse_setting_command(text: str) -> Dict[str, Any]:
        low = (text or "").lower()
        m_val = re.search(r"(\d{1,3})\s*%?", low)
        val = int(m_val.group(1)) if m_val else None
        if "brightness" in low:
            return {"setting": "brightness", "value": min(100, max(0, val if val is not None else 70))}
        if "volume" in low or "mute" in low:
            return {"setting": "volume", "value": 0 if "mute" in low else min(100, max(0, val if val is not None else 50))}
        if "wifi" in low or "wi-fi" in low:
            return {"setting": "wifi", "enabled": "off" not in low and "disable" not in low}
        if "bluetooth" in low:
            return {"setting": "bluetooth", "enabled": "off" not in low and "disable" not in low}
        if "night light" in low:
            return {"setting": "night_light", "enabled": "off" not in low}
        if "power" in low:
            profile = "performance" if "perf" in low else ("power-saver" if "saver" in low else "balanced")
            return {"setting": "power_profile", "value": profile}
        return {"setting": "unknown", "raw": text}


class FocusDNDManager:
    def __init__(self) -> None:
        self.dnd_active = False
        self.pomodoro_end_ts: Optional[float] = None

    def start_focus(self, minutes: int = 25) -> Dict[str, Any]:
        self.dnd_active = True
        self.pomodoro_end_ts = time.time() + (minutes * 60)
        return {"dnd_active": True, "duration_minutes": minutes, "ends_at": self.pomodoro_end_ts}

    def stop_focus(self) -> Dict[str, Any]:
        self.dnd_active = False
        self.pomodoro_end_ts = None
        return {"dnd_active": False}


class NotificationTriager:
    CRITICAL_KW = ("security", "failed", "battery critical", "crash", "error", "urgent")
    HIGH_KW = ("meeting", "deadline", "mention", "build", "pr ")

    @classmethod
    def triage(cls, notifications: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
        buckets: Dict[str, List[Dict[str, str]]] = {"critical": [], "high": [], "normal": [], "low": []}
        for n in notifications:
            txt = f"{n.get('app', '')} {n.get('title', '')} {n.get('body', '')}".lower()
            if any(k in txt for k in cls.CRITICAL_KW):
                buckets["critical"].append(n)
            elif any(k in txt for k in cls.HIGH_KW):
                buckets["high"].append(n)
            elif "promo" in txt or "newsletter" in txt:
                buckets["low"].append(n)
            else:
                buckets["normal"].append(n)
        return buckets


class AppContextActionEngine:
    APP_ACTIONS: Dict[str, List[str]] = {
        "vscode": ["Explain Selection", "Generate Unit Tests", "Review Git Diff"],
        "terminal": ["Explain Last Error", "Translate CLI Flags", "Check Open Ports"],
        "browser": ["Summarize Page", "Extract Table to CSV", "Save Snippet to KB"],
        "pdf": ["Executive Summary", "Generate Flashcards", "OCR Region"],
    }

    @classmethod
    def actions_for_window(cls, window_title: str) -> List[str]:
        low = (window_title or "").lower()
        for key, acts in cls.APP_ACTIONS.items():
            if key in low or (key == "vscode" and "code" in low):
                return list(acts)
        return ["Ask Sudharshan", "Capture Clipboard", "Open Command Palette"]


class PlainEnglishScheduleGenerator:
    DAYS = {"sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4, "friday": 5, "saturday": 6}
    SYSTEMD_DAYS = {"sunday": "Sun", "monday": "Mon", "tuesday": "Tue", "wednesday": "Wed", "thursday": "Thu", "friday": "Fri", "saturday": "Sat"}

    @classmethod
    def generate(cls, instruction: str) -> Dict[str, str]:
        low = (instruction or "").lower()
        dow = "*"
        sd_day = "*"
        for name, num in cls.DAYS.items():
            if name in low:
                dow = str(num)
                sd_day = cls.SYSTEMD_DAYS[name]
                break
        m_time = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", low)
        hour, minute = 9, 0
        if m_time:
            hour = int(m_time.group(1))
            minute = int(m_time.group(2) or 0)
            ampm = m_time.group(3)
            if ampm == "pm" and hour < 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
        cron_expr = f"{minute} {hour} * * {dow}"
        on_cal = f"{sd_day} *-*-* {hour:02d}:{minute:02d}:00" if sd_day != "*" else f"*-*-* {hour:02d}:{minute:02d}:00"
        timer_unit = f"[Unit]\nDescription=Sudharshan Scheduled Task\n\n[Timer]\nOnCalendar={on_cal}\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n"
        return {"cron": cron_expr, "systemd_timer": timer_unit, "instruction": instruction}


class SafeProcessManager:
    PROTECTED_NAMES = {"systemd", "init", "kernel", "sshd", "dbus-daemon", "gnome-shell", "explorer.exe"}

    @classmethod
    def top_processes(cls, limit: int = 5) -> List[Dict[str, Any]]:
        if platform.system() == "Linux" and shutil.which("ps"):
            proc = subprocess.run(["ps", "-eo", "pid,comm,%mem,%cpu", "--sort=-%mem"], capture_output=True, text=True, timeout=3.0, check=False)
            out = []
            for ln in proc.stdout.splitlines()[1:limit + 1]:
                parts = ln.split()
                if len(parts) >= 4:
                    out.append({"pid": int(parts[0]), "name": parts[1], "mem_pct": float(parts[2]), "cpu_pct": float(parts[3])})
            return out
        return []

    @classmethod
    def propose_termination(cls, pid: int, name: str, confirmed: bool = False) -> Dict[str, Any]:
        if name.lower() in cls.PROTECTED_NAMES or pid <= 1:
            return {"allowed": False, "reason": f"Protected system process '{name}' (PID {pid}) cannot be terminated"}
        if not confirmed:
            return {"allowed": False, "requires_confirmation": True, "reason": f"Confirm termination of '{name}' (PID {pid})"}
        return {"allowed": True, "requires_confirmation": False, "pid": pid, "name": name}
