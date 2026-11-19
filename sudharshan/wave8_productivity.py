import ast
import csv
import datetime
import io
import math
import operator
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class MarkdownKnowledgeVault:
    def __init__(self, vault_dir: Path) -> None:
        self.vault_dir = Path(vault_dir)

    def build_graph(self) -> Dict[str, Any]:
        nodes: List[str] = []
        edges: List[Tuple[str, str]] = []
        backlinks: Dict[str, List[str]] = {}
        for p in sorted(self.vault_dir.rglob("*.md")):
            name = p.stem
            nodes.append(name)
            txt = p.read_text(encoding="utf-8", errors="ignore")
            for target in re.findall(r"\[\[([^\]]+)\]\]", txt):
                tgt = target.strip()
                edges.append((name, tgt))
                backlinks.setdefault(tgt, []).append(name)
        return {"nodes": nodes, "edges": edges, "backlinks": backlinks}


class PaperReaderEngine:
    @staticmethod
    def summarize_document(text: str, max_bullets: int = 4) -> Dict[str, Any]:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if len(s.strip()) > 20]
        return {
            "word_count": len((text or "").split()),
            "executive_summary": sentences[:max_bullets],
            "total_sentences": len(sentences),
        }


class LocalTaskReminderManager:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    due_iso TEXT NOT NULL,
                    done INTEGER DEFAULT 0
                )"""
            )
            conn.commit()

    def add_task(self, title: str, due_iso: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("INSERT INTO tasks (title, due_iso, done) VALUES (?, ?, 0)", (title, due_iso))
            conn.commit()
            return int(cur.lastrowid)

    def list_tasks(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT id, title, due_iso, done FROM tasks ORDER BY due_iso ASC").fetchall()
        return [{"id": r[0], "title": r[1], "due_iso": r[2], "done": bool(r[3])} for r in rows]

    def export_ics(self) -> str:
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Sudharshan AI//Local Tasks//EN"]
        for t in self.list_tasks():
            dt = re.sub(r"[^0-9T]", "", t["due_iso"])[:15] or "20261119T090000"
            lines.extend(["BEGIN:VTODO", f"UID:sudharshan-task-{t['id']}", f"SUMMARY:{t['title']}", f"DUE:{dt}Z", "END:VTODO"])
        lines.append("END:VCALENDAR")
        return "\n".join(lines) + "\n"


class MorningBriefingGenerator:
    @staticmethod
    def generate(tasks: List[Dict[str, Any]], thermal_hud: Dict[str, Any], pending_git_files: int = 0) -> str:
        open_tasks = [t for t in tasks if not t.get("done")]
        lines = [
            "# Sudharshan AI — Morning Briefing",
            f"- Open Tasks: {len(open_tasks)}",
            f"- Free RAM: {thermal_hud.get('free_ram_gb')} GB | Disk Free: {thermal_hud.get('disk_free_gb')} GB",
            f"- Pending Git Changes: {pending_git_files}",
        ]
        for t in open_tasks[:5]:
            lines.append(f"  - [ ] {t['title']} (Due: {t['due_iso']})")
        return "\n".join(lines)


class SpacedRepetitionEngine:
    @staticmethod
    def sm2_review(repetitions: int, interval_days: int, ease_factor: float, quality: int) -> Dict[str, Any]:
        q = max(0, min(5, int(quality)))
        if q < 3:
            reps = 0
            interval = 1
        else:
            if repetitions == 0:
                interval = 1
            elif repetitions == 1:
                interval = 6
            else:
                interval = round(interval_days * ease_factor)
            reps = repetitions + 1
        ef = max(1.3, ease_factor + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))
        return {"repetitions": reps, "interval_days": interval, "ease_factor": round(ef, 3)}

    @staticmethod
    def generate_flashcards_from_markdown(md_text: str) -> List[Dict[str, str]]:
        cards = []
        for m in re.finditer(r"^\s*[-*]\s+\*\*([^*]+)\*\*:\s*(.+)$", md_text or "", re.M):
            cards.append({"front": f"Define {m.group(1).strip()}", "back": m.group(2).strip()})
        return cards


class SmartCalculatorScratchpad:
    _OPS = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.USub: operator.neg,
    }

    @classmethod
    def eval_math(cls, expr: str) -> float:
        node = ast.parse(expr, mode="eval").body

        def _eval(n: ast.AST) -> float:
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
                return float(n.value)
            if isinstance(n, ast.BinOp) and type(n.op) in cls._OPS:
                return float(cls._OPS[type(n.op)](_eval(n.left), _eval(n.right)))
            if isinstance(n, ast.UnaryOp) and type(n.op) in cls._OPS:
                return float(cls._OPS[type(n.op)](_eval(n.operand)))
            raise ValueError("Unsupported expression node")

        return _eval(node)

    @staticmethod
    def convert_unit(value: float, from_unit: str, to_unit: str) -> float:
        table = {
            ("km", "m"): 1000.0, ("m", "km"): 0.001,
            ("gb", "mb"): 1024.0, ("mb", "gb"): 1.0 / 1024.0,
            ("kg", "lb"): 2.20462262, ("lb", "kg"): 0.45359237,
        }
        key = (from_unit.lower(), to_unit.lower())
        if key not in table:
            raise ValueError(f"Unsupported unit conversion: {from_unit} -> {to_unit}")
        return round(value * table[key], 4)

    @staticmethod
    def convert_timezone(iso_dt: str, from_offset_hours: float, to_offset_hours: float) -> str:
        dt = datetime.datetime.fromisoformat(iso_dt)
        shifted = dt + datetime.timedelta(hours=(to_offset_hours - from_offset_hours))
        return shifted.isoformat()


class WritingAssistant:
    FILLERS = ("basically", "actually", "just", "very", "really", "in order to")

    @classmethod
    def concise_rewrite(cls, text: str) -> str:
        out = text or ""
        out = re.sub(r"\bin order to\b", "to", out, flags=re.I)
        for f in cls.FILLERS[:-1]:
            out = re.sub(rf"\b{f}\b\s*", "", out, flags=re.I)
        return re.sub(r"\s{2,}", " ", out).strip()


class LocalCalendarICSParser:
    @staticmethod
    def parse_events(ics_text: str) -> List[Dict[str, str]]:
        events = []
        for blk in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", ics_text or "", re.DOTALL):
            summary = re.search(r"SUMMARY:([^\r\n]+)", blk)
            dtstart = re.search(r"DTSTART[^:]*:([^\r\n]+)", blk)
            dtend = re.search(r"DTEND[^:]*:([^\r\n]+)", blk)
            if summary and dtstart and dtend:
                events.append({"summary": summary.group(1).strip(), "start": dtstart.group(1).strip(), "end": dtend.group(1).strip()})
        return events

    @classmethod
    def detect_conflicts(cls, ics_text: str) -> List[Tuple[str, str]]:
        evts = sorted(cls.parse_events(ics_text), key=lambda e: e["start"])
        conflicts = []
        for i in range(len(evts) - 1):
            if evts[i]["end"] > evts[i + 1]["start"]:
                conflicts.append((evts[i]["summary"], evts[i + 1]["summary"]))
        return conflicts


class StructuredTableExtractor:
    @staticmethod
    def extract_to_markdown_and_csv(raw_text: str) -> Dict[str, str]:
        rows = []
        for ln in (raw_text or "").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            if "|" in ln:
                cells = [c.strip() for c in ln.strip("|").split("|")]
            elif "\t" in ln:
                cells = [c.strip() for c in ln.split("\t")]
            else:
                cells = [c.strip() for c in re.split(r"\s{2,}", ln)]
            rows.append(cells)
        if not rows:
            return {"markdown": "", "csv": ""}
        buf = io.StringIO()
        csv.writer(buf).writerows(rows)
        md = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * len(rows[0])) + " |"]
        for r in rows[1:]:
            md.append("| " + " | ".join(r) + " |")
        return {"markdown": "\n".join(md), "csv": buf.getvalue()}


class PrivacyActivityDigest:
    def __init__(self) -> None:
        self._events: List[Dict[str, Any]] = []

    def record(self, workspace: str, duration_sec: float) -> None:
        self._events.append({"workspace": workspace, "duration_sec": float(duration_sec), "ts": time.time()})

    def summarize(self) -> Dict[str, float]:
        totals: Dict[str, float] = {}
        for e in self._events:
            totals[e["workspace"]] = round(totals.get(e["workspace"], 0.0) + e["duration_sec"], 2)
        return totals
