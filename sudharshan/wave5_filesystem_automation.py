import csv
import hashlib
import json
import os
import re
import shutil
import tarfile
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


class BatchFileOrganizer:
    CATEGORY_MAP: Dict[str, str] = {
        ".pdf": "Documents", ".docx": "Documents", ".txt": "Documents", ".md": "Documents",
        ".zip": "Archives", ".tar": "Archives", ".gz": "Archives", ".zst": "Archives", ".7z": "Archives",
        ".exe": "Installers", ".msi": "Installers", ".rpm": "Installers", ".deb": "Installers", ".AppImage": "Installers",
        ".png": "Media", ".jpg": "Media", ".jpeg": "Media", ".mp4": "Media", ".mp3": "Media", ".wav": "Media",
        ".py": "Code", ".js": "Code", ".ts": "Code", ".rs": "Code", ".go": "Code", ".c": "Code",
    }

    def preview(self, directory: Path) -> List[Dict[str, str]]:
        directory = Path(directory)
        plan = []
        for p in sorted(directory.iterdir()):
            if p.is_file():
                cat = self.CATEGORY_MAP.get(p.suffix.lower(), "Other")
                plan.append({"src": str(p), "dst": str(directory / cat / p.name), "category": cat})
        return plan

    def apply(self, directory: Path, dry_run: bool = True) -> Dict[str, Any]:
        plan = self.preview(directory)
        if dry_run:
            return {"dry_run": True, "moved": 0, "plan": plan}
        executed = []
        for item in plan:
            src, dst = Path(item["src"]), Path(item["dst"])
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                dst = dst.with_name(f"{dst.stem}_{int(time.time())}{dst.suffix}")
            shutil.move(str(src), str(dst))
            executed.append({"src": str(src), "dst": str(dst)})
        manifest = Path(directory) / ".sudharshan_organize_undo.json"
        manifest.write_text(json.dumps(executed, indent=2), encoding="utf-8")
        return {"dry_run": False, "moved": len(executed), "manifest": str(manifest)}

    @staticmethod
    def undo(manifest_path: Path) -> int:
        entries = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        restored = 0
        for item in reversed(entries):
            dst, src = Path(item["dst"]), Path(item["src"])
            if dst.exists():
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(src))
                restored += 1
        return restored


class SmartDownloadsDaemon:
    def __init__(self, downloads_dir: Path) -> None:
        self.downloads_dir = Path(downloads_dir)
        self.organizer = BatchFileOrganizer()

    def scan_once(self, dry_run: bool = False) -> Dict[str, Any]:
        return self.organizer.apply(self.downloads_dir, dry_run=dry_run)


class ContentAwareRenamer:
    @staticmethod
    def suggest_name(file_path: Path) -> str:
        file_path = Path(file_path)
        text = file_path.read_text(encoding="utf-8", errors="ignore")[:800]
        m_inv = re.search(r"invoice\s*(?:#|no\.?)?\s*([A-Z0-9\-]+)", text, re.I)
        if m_inv:
            return f"invoice_{m_inv.group(1).lower()}{file_path.suffix.lower()}"
        m_h1 = re.search(r"^#\s+(.+)$", text, re.M)
        if m_h1:
            slug = re.sub(r"[^a-z0-9]+", "_", m_h1.group(1).lower()).strip("_")[:48]
            if slug:
                return f"{slug}{file_path.suffix.lower()}"
        m_def = re.search(r"^(?:class|def)\s+([A-Za-z_][A-Za-z0-9_]*)", text, re.M)
        if m_def:
            return f"{m_def.group(1).lower()}{file_path.suffix.lower()}"
        return file_path.name


class DeduplicationSweeper:
    @staticmethod
    def find_duplicates(root: Path) -> List[List[Path]]:
        by_hash: Dict[str, List[Path]] = {}
        for p in sorted(Path(root).rglob("*")):
            if p.is_file():
                h = hashlib.sha256(p.read_bytes()).hexdigest()
                by_hash.setdefault(h, []).append(p)
        return [paths for paths in by_hash.values() if len(paths) > 1]

    @classmethod
    def sweep(cls, root: Path, mode: str = "trash", trash_bin: Optional["QuarantineTrashBin"] = None) -> Dict[str, int]:
        groups = cls.find_duplicates(root)
        acted = 0
        for grp in groups:
            keeper = grp[0]
            for dup in grp[1:]:
                if mode == "hardlink":
                    dup.unlink()
                    os.link(keeper, dup)
                    acted += 1
                elif trash_bin is not None:
                    trash_bin.quarantine(dup)
                    acted += 1
        return {"duplicate_groups": len(groups), "deduplicated_files": acted}


class ArchiveManager:
    @staticmethod
    def compress_zip(sources: List[Path], archive_path: Path) -> Path:
        archive_path = Path(archive_path)
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for src in sources:
                src = Path(src)
                if src.is_file():
                    zf.write(src, src.name)
                elif src.is_dir():
                    for p in src.rglob("*"):
                        if p.is_file():
                            zf.write(p, p.relative_to(src.parent).as_posix())
        return archive_path

    @staticmethod
    def inspect_archive(archive_path: Path) -> List[str]:
        archive_path = Path(archive_path)
        if archive_path.suffix.lower() == ".zip":
            with zipfile.ZipFile(archive_path, "r") as zf:
                return zf.namelist()
        with tarfile.open(archive_path, "r:*") as tf:
            return tf.getnames()

    @staticmethod
    def safe_extract_zip(archive_path: Path, dest_dir: Path) -> List[Path]:
        dest_dir = Path(dest_dir).resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)
        extracted: List[Path] = []
        with zipfile.ZipFile(archive_path, "r") as zf:
            for member in zf.namelist():
                target = (dest_dir / member).resolve()
                if not str(target).startswith(str(dest_dir)):
                    raise ValueError(f"ZipSlip path traversal blocked: {member}")
                if member.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zf.read(member))
                    extracted.append(target)
        return extracted


class DiskSpaceAnalyzer:
    CLEANABLE_NAMES = {"__pycache__", ".pytest_cache", "node_modules", ".cache", "dist", "build"}

    @classmethod
    def analyze(cls, root: Path) -> Dict[str, Any]:
        root = Path(root)
        total_bytes = 0
        cleanable: List[Dict[str, Any]] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dp = Path(dirpath)
            dir_sz = sum((dp / fn).stat().st_size for fn in filenames if (dp / fn).exists())
            total_bytes += dir_sz
            if dp.name in cls.CLEANABLE_NAMES:
                sub_sz = sum(p.stat().st_size for p in dp.rglob("*") if p.is_file())
                cleanable.append({"path": str(dp), "category": dp.name, "size_bytes": sub_sz})
        return {"root": str(root), "total_bytes": total_bytes, "recommendations": cleanable}


class FileConversionPipeline:
    @staticmethod
    def convert(src: Path, dst: Path) -> Path:
        src, dst = Path(src), Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        s_ext, d_ext = src.suffix.lower(), dst.suffix.lower()
        if s_ext == ".csv" and d_ext == ".json":
            with open(src, "r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            dst.write_text(json.dumps(rows, indent=2), encoding="utf-8")
            return dst
        if s_ext == ".json" and d_ext == ".csv":
            rows = json.loads(src.read_text(encoding="utf-8"))
            if rows and isinstance(rows, list) and isinstance(rows[0], dict):
                with open(dst, "w", encoding="utf-8", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                    w.writeheader()
                    w.writerows(rows)
            return dst
        if s_ext == ".md" and d_ext == ".html":
            lines = src.read_text(encoding="utf-8").splitlines()
            html_lines = ["<!doctype html><html><body>"]
            for ln in lines:
                if ln.startswith("# "):
                    html_lines.append(f"<h1>{ln[2:]}</h1>")
                elif ln.startswith("## "):
                    html_lines.append(f"<h2>{ln[3:]}</h2>")
                elif ln.strip():
                    html_lines.append(f"<p>{ln}</p>")
            html_lines.append("</body></html>")
            dst.write_text("\n".join(html_lines), encoding="utf-8")
            return dst
        raise ValueError(f"Unsupported conversion: {s_ext} -> {d_ext}")


class FolderWatcherEngine:
    def __init__(self, watch_dir: Path) -> None:
        self.watch_dir = Path(watch_dir)
        self._known: Dict[str, float] = {}
        self._rules: List[Callable[[Path], Any]] = []

    def add_rule(self, rule_fn: Callable[[Path], Any]) -> None:
        self._rules.append(rule_fn)

    def poll_once(self) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        for p in sorted(self.watch_dir.rglob("*")):
            if not p.is_file():
                continue
            key = str(p.resolve())
            mtime = p.stat().st_mtime
            if key not in self._known or self._known[key] < mtime:
                self._known[key] = mtime
                for rule in self._rules:
                    events.append({"file": key, "result": rule(p)})
        return events


class QuarantineTrashBin:
    def __init__(self, trash_root: Path, retention_days: int = 30) -> None:
        self.trash_root = Path(trash_root)
        self.trash_root.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self.meta_path = self.trash_root / "quarantine_index.json"

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if self.meta_path.is_file():
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        return {}

    def _save(self, data: Dict[str, Dict[str, Any]]) -> None:
        self.meta_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def quarantine(self, file_path: Path) -> str:
        fp = Path(file_path).resolve()
        item_id = f"{int(time.time() * 1000)}_{fp.name}"
        dst = self.trash_root / item_id
        shutil.move(str(fp), str(dst))
        idx = self._load()
        idx[item_id] = {"original_path": str(fp), "trashed_at": time.time()}
        self._save(idx)
        return item_id

    def restore(self, item_id: str) -> Path:
        idx = self._load()
        if item_id not in idx:
            raise KeyError(f"Unknown quarantine item: {item_id}")
        orig = Path(idx[item_id]["original_path"])
        orig.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.trash_root / item_id), str(orig))
        del idx[item_id]
        self._save(idx)
        return orig

    def purge_expired(self, now_ts: Optional[float] = None) -> int:
        now = now_ts if now_ts is not None else time.time()
        cutoff = now - (self.retention_days * 86400)
        idx = self._load()
        purged = 0
        for item_id in list(idx.keys()):
            if idx[item_id]["trashed_at"] <= cutoff:
                p = self.trash_root / item_id
                if p.exists():
                    p.unlink()
                del idx[item_id]
                purged += 1
        self._save(idx)
        return purged


class CrossFolderSyncAssistant:
    @staticmethod
    def diff_folders(src_dir: Path, dst_dir: Path) -> Dict[str, List[str]]:
        src_dir, dst_dir = Path(src_dir), Path(dst_dir)
        src_map = {p.relative_to(src_dir).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in src_dir.rglob("*") if p.is_file()}
        dst_map = {p.relative_to(dst_dir).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in dst_dir.rglob("*") if p.is_file()}
        only_src = sorted(set(src_map) - set(dst_map))
        only_dst = sorted(set(dst_map) - set(src_map))
        modified = sorted(k for k in (set(src_map) & set(dst_map)) if src_map[k] != dst_map[k])
        return {"only_in_source": only_src, "only_in_dest": only_dst, "modified": modified}

    @classmethod
    def sync(cls, src_dir: Path, dst_dir: Path, dry_run: bool = True) -> Dict[str, Any]:
        diff = cls.diff_folders(src_dir, dst_dir)
        to_copy = diff["only_in_source"] + diff["modified"]
        if not dry_run:
            for rel in to_copy:
                target = Path(dst_dir) / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(Path(src_dir) / rel, target)
        return {"dry_run": dry_run, "copied_count": 0 if dry_run else len(to_copy), "diff": diff}
