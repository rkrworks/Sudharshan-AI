import base64
import hashlib
import hmac
import json
import math
import os
import re
import sqlite3
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9_]+", (text or "").lower())


class LocalVectorIndex:
    def __init__(self, db_path: Path, dim: int = 128) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.dim = dim
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    line_start INTEGER DEFAULT 1,
                    content TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )"""
            )
            conn.commit()

    def embed_text(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        tokens = _tokenize(text)
        if not tokens:
            return vec
        for tok in tokens:
            h = int(hashlib.blake2b(tok.encode("utf-8"), digest_size=8).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [round(v / norm, 6) for v in vec]

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (na * nb)

    def upsert_chunk(self, chunk_id: str, source_path: str, content: str, line_start: int = 1) -> None:
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        vec = self.embed_text(content)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO chunks (chunk_id, source_path, line_start, content, sha256, vector_json, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(chunk_id) DO UPDATE SET
                     content=excluded.content, sha256=excluded.sha256,
                     vector_json=excluded.vector_json, updated_at=excluded.updated_at""",
                (chunk_id, source_path, line_start, content, sha, json.dumps(vec), time.time()),
            )
            conn.commit()

    def all_chunks(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT chunk_id, source_path, line_start, content, sha256, vector_json FROM chunks").fetchall()
        return [
            {
                "chunk_id": r[0],
                "source_path": r[1],
                "line_start": r[2],
                "content": r[3],
                "sha256": r[4],
                "vector": json.loads(r[5]),
            }
            for r in rows
        ]


class IncrementalFileIndexer:
    SUPPORTED_EXTS = {".md", ".txt", ".py", ".js", ".ts", ".json", ".csv", ".docx", ".pdf"}

    def __init__(self, index: LocalVectorIndex) -> None:
        self.index = index
        self._file_hashes: Dict[str, str] = {}

    @staticmethod
    def _extract_text(path: Path) -> str:
        ext = path.suffix.lower()
        if ext == ".docx":
            with zipfile.ZipFile(path, "r") as zf:
                xml_bytes = zf.read("word/document.xml")
            root = ET.fromstring(xml_bytes)
            return "\n".join(el.text for el in root.iter() if el.text)
        if ext == ".pdf":
            raw = path.read_bytes()
            text_parts = re.findall(rb"\(([^()]{3,200})\)", raw)
            return "\n".join(p.decode("latin-1", errors="ignore") for p in text_parts)
        return path.read_text(encoding="utf-8", errors="ignore")

    def index_folder(self, folder: Path, chunk_lines: int = 30) -> Dict[str, int]:
        folder = Path(folder)
        indexed = 0
        skipped = 0
        for p in sorted(folder.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in self.SUPPORTED_EXTS:
                continue
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            key = str(p.resolve())
            if self._file_hashes.get(key) == sha:
                skipped += 1
                continue
            text = self._extract_text(p)
            lines = text.splitlines() or [text]
            for start in range(0, len(lines), chunk_lines):
                snippet = "\n".join(lines[start:start + chunk_lines]).strip()
                if not snippet:
                    continue
                cid = f"{key}:{start + 1}"
                self.index.upsert_chunk(cid, key, snippet, line_start=start + 1)
            self._file_hashes[key] = sha
            indexed += 1
        return {"indexed_files": indexed, "skipped_unchanged": skipped}


class HybridSearchEngine:
    def __init__(self, index: LocalVectorIndex) -> None:
        self.index = index

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        chunks = self.index.all_chunks()
        if not chunks:
            return []
        q_tokens = _tokenize(query)
        q_vec = self.index.embed_text(query)
        n_docs = len(chunks)
        doc_tokens = [_tokenize(c["content"]) for c in chunks]
        avg_dl = sum(len(t) for t in doc_tokens) / max(1, n_docs)
        df: Dict[str, int] = {}
        for toks in doc_tokens:
            for t in set(toks):
                df[t] = df.get(t, 0) + 1

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for chunk, toks in zip(chunks, doc_tokens):
            bm25 = 0.0
            dl = len(toks) or 1
            for qt in q_tokens:
                tf = toks.count(qt)
                if tf == 0:
                    continue
                idf = math.log(1.0 + (n_docs - df.get(qt, 0) + 0.5) / (df.get(qt, 0) + 0.5))
                bm25 += idf * ((tf * 2.2) / (tf + 1.2 * (1.0 - 0.75 + 0.75 * dl / max(1.0, avg_dl))))
            cos = self.index.cosine_similarity(q_vec, chunk["vector"])
            combined = 0.55 * bm25 + 0.45 * max(0.0, cos)
            scored.append((combined, {
                "chunk_id": chunk["chunk_id"],
                "source_path": chunk["source_path"],
                "line_start": chunk["line_start"],
                "content": chunk["content"],
                "score": round(combined, 4),
            }))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]


class CitationFormatter:
    @staticmethod
    def format_cited_answer(answer: str, sources: List[Dict[str, Any]]) -> str:
        if not sources:
            return answer
        cites = []
        for idx, s in enumerate(sources, 1):
            p = Path(s["source_path"])
            line = int(s.get("line_start", 1))
            cites.append(f"[{idx}] [{p.name}:L{line}](file://{p.as_posix()}#L{line})")
        return f"{answer}\n\nSources: " + " | ".join(cites)


class EpisodicMemoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS episodic_memories (
                    memory_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )"""
            )
            conn.commit()

    def add(self, memory_id: str, category: str, content: str, tags: str = "") -> Dict[str, Any]:
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO episodic_memories VALUES (?, ?, ?, ?, ?, ?)",
                (memory_id, category, content, tags, now, now),
            )
            conn.commit()
        return {"memory_id": memory_id, "category": category, "content": content, "tags": tags}

    def edit(self, memory_id: str, new_content: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE episodic_memories SET content=?, updated_at=? WHERE memory_id=?",
                (new_content, time.time(), memory_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete(self, memory_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("DELETE FROM episodic_memories WHERE memory_id=?", (memory_id,))
            conn.commit()
            return cur.rowcount > 0

    def list_cards(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT memory_id, category, content, tags, updated_at FROM episodic_memories ORDER BY updated_at DESC").fetchall()
        return [{"memory_id": r[0], "category": r[1], "content": r[2], "tags": r[3], "updated_at": r[4]} for r in rows]


class ProjectWorkspaceManager:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def get_workspace(self, project_name: str) -> Dict[str, Any]:
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", project_name).strip("_") or "default"
        ws_dir = self.root_dir / safe
        ws_dir.mkdir(parents=True, exist_ok=True)
        vec = LocalVectorIndex(ws_dir / "rag.db")
        mem = EpisodicMemoryStore(ws_dir / "memory.db")
        return {"name": safe, "dir": ws_dir, "vector_index": vec, "memory_store": mem, "search": HybridSearchEngine(vec)}


class ClipboardKnowledgeCapture:
    def __init__(self, index: LocalVectorIndex) -> None:
        self.index = index

    def capture(self, text: str, source_label: str = "clipboard") -> Dict[str, Any]:
        clean = (text or "").strip()
        if not clean:
            return {"captured": False, "reason": "empty_clipboard"}
        sha = hashlib.sha256(clean.encode("utf-8")).hexdigest()[:16]
        cid = f"clip:{sha}"
        self.index.upsert_chunk(cid, source_label, clean, line_start=1)
        return {"captured": True, "chunk_id": cid, "chars": len(clean)}


class SmartDocumentDeduplicator:
    @staticmethod
    def find_duplicates(index: LocalVectorIndex, similarity_threshold: float = 0.92) -> Dict[str, List[Tuple[str, str, float]]]:
        chunks = index.all_chunks()
        exact: List[Tuple[str, str, float]] = []
        near: List[Tuple[str, str, float]] = []
        for i in range(len(chunks)):
            for j in range(i + 1, len(chunks)):
                a, b = chunks[i], chunks[j]
                if a["sha256"] == b["sha256"]:
                    exact.append((a["chunk_id"], b["chunk_id"], 1.0))
                else:
                    sim = index.cosine_similarity(a["vector"], b["vector"])
                    if sim >= similarity_threshold:
                        near.append((a["chunk_id"], b["chunk_id"], round(sim, 4)))
        return {"exact": exact, "near": near}


class IncognitoSessionManager:
    def __init__(self, ttl_seconds: float = 1800.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def start_session(self, session_id: str) -> None:
        self._sessions[session_id] = {"expires_at": time.time() + self.ttl_seconds, "messages": []}

    def add_message(self, session_id: str, role: str, content: str) -> bool:
        self.purge_expired()
        if session_id not in self._sessions:
            return False
        self._sessions[session_id]["messages"].append({"role": role, "content": content})
        return True

    def get_messages(self, session_id: str) -> List[Dict[str, str]]:
        self.purge_expired()
        sess = self._sessions.get(session_id)
        return list(sess["messages"]) if sess else []

    def purge_expired(self) -> int:
        now = time.time()
        expired = [sid for sid, d in self._sessions.items() if d["expires_at"] <= now]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)


class EncryptedMemoryVault:
    @staticmethod
    def _derive_keys(passphrase: str, salt: bytes) -> Tuple[bytes, bytes]:
        dk = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, 120000, dklen=64)
        return dk[:32], dk[32:]

    @staticmethod
    def _keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
        out = bytearray()
        counter = 0
        while len(out) < length:
            block = hashlib.sha256(enc_key + nonce + counter.to_bytes(4, "big")).digest()
            out.extend(block)
            counter += 1
        return bytes(out[:length])

    @classmethod
    def export_encrypted(cls, store: EpisodicMemoryStore, passphrase: str) -> str:
        plaintext = json.dumps(store.list_cards()).encode("utf-8")
        salt = os.urandom(16)
        nonce = os.urandom(16)
        enc_key, mac_key = cls._derive_keys(passphrase, salt)
        stream = cls._keystream(enc_key, nonce, len(plaintext))
        ct = bytes(a ^ b for a, b in zip(plaintext, stream))
        tag = hmac.new(mac_key, salt + nonce + ct, hashlib.sha256).digest()
        return base64.b64encode(salt + nonce + tag + ct).decode("ascii")

    @classmethod
    def restore_encrypted(cls, store: EpisodicMemoryStore, blob_b64: str, passphrase: str) -> int:
        raw = base64.b64decode(blob_b64.encode("ascii"))
        salt, nonce, tag, ct = raw[:16], raw[16:32], raw[32:64], raw[64:]
        enc_key, mac_key = cls._derive_keys(passphrase, salt)
        expected = hmac.new(mac_key, salt + nonce + ct, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("Invalid passphrase or corrupted encrypted memory backup")
        stream = cls._keystream(enc_key, nonce, len(ct))
        pt = bytes(a ^ b for a, b in zip(ct, stream))
        cards = json.loads(pt.decode("utf-8"))
        for c in cards:
            store.add(c["memory_id"], c["category"], c["content"], c.get("tags", ""))
        return len(cards)

    @staticmethod
    def export_markdown(store: EpisodicMemoryStore) -> str:
        lines = ["# Sudharshan AI — Episodic Memory Export", ""]
        for c in store.list_cards():
            lines.append(f"- **[{c['category']}] {c['memory_id']}**: {c['content']}")
        return "\n".join(lines) + "\n"
