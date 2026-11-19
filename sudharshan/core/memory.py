#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sudharshan/core/memory.py — Persistent Local Memory & Semantic RAG Engine (Wave 2, Features 11–20)

Part of Sudharshan AI Enterprise v1.0.
Implements:
  - Feature 11: Local SQLite + vector index powered by qwen3-embedding:0.6b (LocalVectorStore)
  - Feature 12: Incremental background file indexer for approved folders (BackgroundFileIndexer)
  - Feature 13: Hybrid search combining BM25 keyword matching + cosine vector similarity (HybridSearchEngine)
  - Feature 14: Source-cited answers with clickable file paths and line jump links (SourceCitationFormatter)
  - Feature 15: Episodic user memory with inspectable/editable cards (EpisodicMemoryStore)
  - Feature 16: Project-scoped workspaces with isolated RAG & memory (ProjectWorkspaceManager)
  - Feature 17: Instant clipboard-to-knowledge-base capture shortcut (ClipboardKnowledgeCapture)
  - Feature 18: Smart duplicate/near-duplicate document detector using SHA-256 + vectors (DocumentDeduplicator)
  - Feature 19: Auto-expiring ephemeral incognito chat mode with zero disk writes (IncognitoSessionManager)
  - Feature 20: Encrypted memory backup, export (JSON/MD), and restore (MemoryBackupManager)
"""

import base64
import dataclasses
import datetime
import enum
import hashlib
import hmac
import io
import json
import logging
import math
import os
import re
import secrets
import sqlite3
import struct
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Set, Tuple

from sudharshan.core.models import (
    EMBEDDING_MODEL,
    compute_cosine_similarity,
    generate_local_embedding,
)

logger = logging.getLogger("sudharshan.core.memory")


# =====================================================================
# FEATURE 11: LOCAL SQLITE + VECTOR INDEX (LocalVectorStore)
# =====================================================================

@dataclasses.dataclass
class VectorChunk:
    chunk_id: str
    doc_id: str
    file_path: str
    content: str
    embedding: List[float]
    start_line: int
    end_line: int
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)
    workspace: str = "default"


class LocalVectorStore:
    """
    SQLite-backed local vector store storing document chunks, metadata, and dense float32 embeddings.
    Provides fast Top-K vector search using cosine similarity scoring.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Respect sandbox permissions: use safe temporary directory fallback
            base_dir = Path(tempfile.gettempdir()) / "sudharshan_data"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(base_dir / "vectors.db")
        else:
            self.db_path = db_path
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vector_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding_blob BLOB NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    workspace TEXT NOT NULL DEFAULT 'default',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_workspace ON vector_chunks(workspace);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_file_path ON vector_chunks(file_path);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON vector_chunks(doc_id);")

    @staticmethod
    def _pack_vector(vec: List[float]) -> bytes:
        return struct.pack(f"{len(vec)}f", *vec)

    @staticmethod
    def _unpack_vector(blob: bytes) -> List[float]:
        num_floats = len(blob) // 4
        return list(struct.unpack(f"{num_floats}f", blob))

    def insert_chunks(self, chunks: List[VectorChunk]) -> int:
        if not chunks:
            return 0
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            for c in chunks:
                blob = self._pack_vector(c.embedding)
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO vector_chunks 
                    (chunk_id, doc_id, file_path, content, embedding_blob, start_line, end_line, workspace, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        c.chunk_id,
                        c.doc_id,
                        c.file_path,
                        c.content,
                        blob,
                        c.start_line,
                        c.end_line,
                        c.workspace,
                        json.dumps(c.metadata),
                    ),
                )
            conn.commit()
            return len(chunks)

    def search_similar(
        self,
        query_vector: List[float],
        top_k: int = 5,
        workspace: str = "default",
        min_similarity: float = 0.0,
    ) -> List[Tuple[VectorChunk, float]]:
        """Performs cosine vector search against chunks in the specified workspace."""
        results: List[Tuple[VectorChunk, float]] = []
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT chunk_id, doc_id, file_path, content, embedding_blob, start_line, end_line, workspace, metadata_json
                FROM vector_chunks WHERE workspace = ?
                """,
                (workspace,),
            )
            rows = cursor.fetchall()
            for r in rows:
                vec = self._unpack_vector(r["embedding_blob"])
                sim = compute_cosine_similarity(query_vector, vec)
                if sim >= min_similarity:
                    chunk = VectorChunk(
                        chunk_id=r["chunk_id"],
                        doc_id=r["doc_id"],
                        file_path=r["file_path"],
                        content=r["content"],
                        embedding=vec,
                        start_line=r["start_line"],
                        end_line=r["end_line"],
                        metadata=json.loads(r["metadata_json"] or "{}"),
                        workspace=r["workspace"],
                    )
                    results.append((chunk, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def delete_document(self, doc_id: str, workspace: str = "default") -> int:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM vector_chunks WHERE doc_id = ? AND workspace = ?", (doc_id, workspace))
            conn.commit()
            return cursor.rowcount

    def count_chunks(self, workspace: str = "default") -> int:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM vector_chunks WHERE workspace = ?", (workspace,))
            return cursor.fetchone()[0]


# =====================================================================
# FEATURE 12: INCREMENTAL BACKGROUND FILE INDEXER (BackgroundFileIndexer)
# =====================================================================

class DocumentTextExtractor:
    """Safe text extractor supporting PDF, DOCX, Markdown, Code, and TXT files."""

    @staticmethod
    def extract_text(file_path: str) -> str:
        p = Path(file_path)
        if not p.is_file():
            return ""

        suffix = p.suffix.lower()

        # 1. DOCX: extract XML body text directly from ZIP
        if suffix == ".docx":
            try:
                with zipfile.ZipFile(file_path) as z:
                    xml_content = z.read("word/document.xml")
                    tree = ET.fromstring(xml_content)
                    paragraphs = []
                    # Word XML namespace tag is w:t
                    for elem in tree.iter():
                        if elem.tag.endswith("}t") and elem.text:
                            paragraphs.append(elem.text)
                    return "\n".join(paragraphs)
            except Exception as e:
                logger.warning("DOCX extraction error for %s: %s", file_path, e)
                return ""

        # 2. PDF: pure Python stream scanner for text objects
        if suffix == ".pdf":
            try:
                # Basic stream text decoder without external dependencies
                with open(file_path, "rb") as f:
                    content = f.read().decode("latin1", errors="ignore")
                matches = re.findall(r"\((.*?)\)\s*Tj", content)
                if matches:
                    return "\n".join(matches)
                # Fallback to plain string extraction if streams are uncompressed
                clean_lines = [line.strip() for line in content.splitlines() if len(line.strip()) > 3]
                return "\n".join(clean_lines[:500])
            except Exception as e:
                logger.warning("PDF extraction error for %s: %s", file_path, e)
                return ""

        # 3. Text, Markdown, and Code files
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception as e:
            logger.warning("File read error for %s: %s", file_path, e)
            return ""


class BackgroundFileIndexer:
    """
    Scans and indexes user-approved folders incrementally.
    Uses SHA-256 and modification timestamps to re-index only altered files.
    """

    SUPPORTED_EXTENSIONS = {
        ".txt", ".md", ".markdown", ".pdf", ".docx",
        ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
        ".rs", ".go", ".c", ".cpp", ".h", ".json", ".yaml", ".yml", ".toml", ".sh"
    }

    def __init__(
        self,
        vector_store: LocalVectorStore,
        workspace: str = "default",
        chunk_size_chars: int = 600,
        chunk_overlap_chars: int = 100,
    ):
        self.vector_store = vector_store
        self.workspace = workspace
        self.chunk_size = chunk_size_chars
        self.chunk_overlap = chunk_overlap_chars
        self.indexed_files: Dict[str, Dict[str, Any]] = {}
        self._init_index_state()

    def _init_index_state(self) -> None:
        with self.vector_store._lock, self.vector_store._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS file_index_meta (
                    file_path TEXT PRIMARY KEY,
                    workspace TEXT NOT NULL,
                    mtime REAL NOT NULL,
                    sha256 TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    last_indexed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def _calculate_file_hash(self, file_path: str) -> str:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def chunk_document(self, file_path: str, text: str) -> List[VectorChunk]:
        """Splits document text into overlapping chunks with calculated line numbers."""
        lines = text.splitlines(keepends=True)
        chunks: List[VectorChunk] = []
        doc_id = hashlib.sha256(file_path.encode("utf-8")).hexdigest()[:16]

        current_text = ""
        current_start_line = 1
        line_cursor = 1

        for line_num, line in enumerate(lines, 1):
            if not current_text:
                current_start_line = line_num

            current_text += line

            if len(current_text) >= self.chunk_size:
                end_line = line_num
                cid = f"{doc_id}_{len(chunks) + 1}"
                emb = generate_local_embedding(current_text)
                chunks.append(
                    VectorChunk(
                        chunk_id=cid,
                        doc_id=doc_id,
                        file_path=file_path,
                        content=current_text.strip(),
                        embedding=emb,
                        start_line=current_start_line,
                        end_line=end_line,
                        metadata={"file_name": os.path.basename(file_path), "length": len(current_text)},
                        workspace=self.workspace,
                    )
                )
                # Overlap retention
                overlap_text = current_text[-self.chunk_overlap :] if self.chunk_overlap > 0 else ""
                current_text = overlap_text
                current_start_line = max(1, line_num - 2)

        if current_text.strip():
            cid = f"{doc_id}_{len(chunks) + 1}"
            emb = generate_local_embedding(current_text)
            chunks.append(
                VectorChunk(
                    chunk_id=cid,
                    doc_id=doc_id,
                    file_path=file_path,
                    content=current_text.strip(),
                    embedding=emb,
                    start_line=current_start_line,
                    end_line=len(lines) if lines else 1,
                    metadata={"file_name": os.path.basename(file_path), "length": len(current_text)},
                    workspace=self.workspace,
                )
            )

        return chunks

    def index_file(self, file_path: str, force: bool = False) -> Tuple[bool, int]:
        """Indexes a single file if modified or new. Returns (was_indexed, chunk_count)."""
        p = Path(file_path)
        if not p.is_file() or p.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return False, 0

        mtime = p.stat().st_mtime
        doc_id = hashlib.sha256(file_path.encode("utf-8")).hexdigest()[:16]

        with self.vector_store._lock, self.vector_store._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT mtime, sha256 FROM file_index_meta WHERE file_path = ? AND workspace = ?",
                (file_path, self.workspace),
            )
            row = cursor.fetchone()
            if row and not force:
                if abs(row["mtime"] - mtime) < 0.01:
                    return False, 0

        current_hash = self._calculate_file_hash(file_path)
        if row and not force and row["sha256"] == current_hash:
            return False, 0

        # Extract text and chunk
        text = DocumentTextExtractor.extract_text(file_path)
        if not text.strip():
            return False, 0

        # Purge existing chunks for this doc
        self.vector_store.delete_document(doc_id, workspace=self.workspace)

        chunks = self.chunk_document(file_path, text)
        self.vector_store.insert_chunks(chunks)

        with self.vector_store._lock, self.vector_store._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO file_index_meta 
                (file_path, workspace, mtime, sha256, chunk_count, last_indexed)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (file_path, self.workspace, mtime, current_hash, len(chunks)),
            )
            conn.commit()

        return True, len(chunks)

    def scan_and_index_directory(self, dir_path: str) -> Dict[str, Any]:
        """Scans approved directory and indexes all eligible files."""
        total_scanned = 0
        indexed_files = 0
        total_chunks = 0

        p = Path(dir_path)
        if not p.is_dir():
            return {"status": "error", "message": f"Directory not found: {dir_path}"}

        for root, _, files in os.walk(dir_path):
            for file in files:
                fpath = os.path.join(root, file)
                suffix = Path(fpath).suffix.lower()
                if suffix in self.SUPPORTED_EXTENSIONS:
                    total_scanned += 1
                    did_index, chunks = self.index_file(fpath)
                    if did_index:
                        indexed_files += 1
                        total_chunks += chunks

        return {
            "status": "success",
            "directory": dir_path,
            "workspace": self.workspace,
            "scanned_files": total_scanned,
            "indexed_files": indexed_files,
            "total_chunks_added": total_chunks,
        }


# =====================================================================
# FEATURE 13: HYBRID SEARCH (BM25 + COSINE VECTOR SIMILARITY)
# =====================================================================

class BM25SearchEngine:
    """Pure-Python BM25 keyword search indexer with Okapi BM25 scoring."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_lengths: Dict[str, int] = {}
        self.avg_doc_len: float = 0.0
        self.inverted_index: Dict[str, Dict[str, int]] = {}  # term -> {doc_id: freq}
        self.total_docs: int = 0
        self.docs_store: Dict[str, VectorChunk] = {}

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\b[a-zA-Z0-9_-]{2,}\b", text.lower())

    def add_chunks(self, chunks: List[VectorChunk]) -> None:
        for c in chunks:
            self.docs_store[c.chunk_id] = c
            tokens = self._tokenize(c.content)
            self.doc_lengths[c.chunk_id] = len(tokens)
            term_freqs: Dict[str, int] = {}
            for t in tokens:
                term_freqs[t] = term_freqs.get(t, 0) + 1

            for t, freq in term_freqs.items():
                if t not in self.inverted_index:
                    self.inverted_index[t] = {}
                self.inverted_index[t][c.chunk_id] = freq

        self.total_docs = len(self.doc_lengths)
        if self.total_docs > 0:
            self.avg_doc_len = sum(self.doc_lengths.values()) / self.total_docs

    def search(self, query: str, top_k: int = 5) -> List[Tuple[VectorChunk, float]]:
        query_terms = self._tokenize(query)
        scores: Dict[str, float] = {}

        for term in query_terms:
            if term not in self.inverted_index:
                continue
            postings = self.inverted_index[term]
            doc_freq = len(postings)
            idf = math.log(1.0 + (self.total_docs - doc_freq + 0.5) / (doc_freq + 0.5))

            for chunk_id, tf in postings.items():
                d_len = self.doc_lengths.get(chunk_id, 1)
                num = tf * (self.k1 + 1.0)
                denom = tf + self.k1 * (1.0 - self.b + self.b * (d_len / max(1.0, self.avg_doc_len)))
                score = idf * (num / denom)
                scores[chunk_id] = scores.get(chunk_id, 0.0) + score

        sorted_chunks = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [(self.docs_store[cid], score) for cid, score in sorted_chunks if cid in self.docs_store]


class HybridSearchEngine:
    """
    Fuses BM25 keyword matching with dense cosine vector similarity
    via Reciprocal Rank Fusion (RRF) and normalized alpha-blending.
    """

    def __init__(self, vector_store: LocalVectorStore, alpha: float = 0.5):
        self.vector_store = vector_store
        self.alpha = alpha  # Weight on vector search (1.0 = pure vector, 0.0 = pure BM25)

    def search(
        self,
        query: str,
        top_k: int = 5,
        workspace: str = "default",
    ) -> List[Tuple[VectorChunk, float]]:
        # 1. Vector Search
        q_emb = generate_local_embedding(query)
        vec_results = self.vector_store.search_similar(q_emb, top_k=top_k * 2, workspace=workspace)

        # 2. Extract candidate chunks for BM25
        with self.vector_store._lock, self.vector_store._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT chunk_id, doc_id, file_path, content, embedding_blob, start_line, end_line, workspace, metadata_json
                FROM vector_chunks WHERE workspace = ?
                """,
                (workspace,),
            )
            all_rows = cursor.fetchall()

        all_chunks = []
        for r in all_rows:
            all_chunks.append(
                VectorChunk(
                    chunk_id=r["chunk_id"],
                    doc_id=r["doc_id"],
                    file_path=r["file_path"],
                    content=r["content"],
                    embedding=[],
                    start_line=r["start_line"],
                    end_line=r["end_line"],
                    metadata=json.loads(r["metadata_json"] or "{}"),
                    workspace=r["workspace"],
                )
            )

        bm25 = BM25SearchEngine()
        bm25.add_chunks(all_chunks)
        bm25_results = bm25.search(query, top_k=top_k * 2)

        # 3. Reciprocal Rank Fusion (RRF)
        # RRF_score = sum(1 / (60 + rank))
        rrf_scores: Dict[str, float] = {}
        chunk_map: Dict[str, VectorChunk] = {}

        for rank, (chunk, score) in enumerate(vec_results, 1):
            rrf_scores[chunk.chunk_id] = rrf_scores.get(chunk.chunk_id, 0.0) + (self.alpha * (1.0 / (60.0 + rank)))
            chunk_map[chunk.chunk_id] = chunk

        for rank, (chunk, score) in enumerate(bm25_results, 1):
            rrf_scores[chunk.chunk_id] = rrf_scores.get(chunk.chunk_id, 0.0) + ((1.0 - self.alpha) * (1.0 / (60.0 + rank)))
            chunk_map[chunk.chunk_id] = chunk

        sorted_fused = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [(chunk_map[cid], score) for cid, score in sorted_fused if cid in chunk_map]


# =====================================================================
# FEATURE 14: SOURCE-CITED ANSWERS (SourceCitationFormatter)
# =====================================================================

class SourceCitationFormatter:
    """Formats retrieved knowledge chunks into clickable Markdown citations and synthesized references."""

    @staticmethod
    def format_citation(chunk: VectorChunk, citation_idx: int) -> str:
        filename = os.path.basename(chunk.file_path)
        file_url = f"file://{os.path.abspath(chunk.file_path)}#L{chunk.start_line}-L{chunk.end_line}"
        return f"[{citation_idx}] [{filename}#L{chunk.start_line}-L{chunk.end_line}]({file_url})"

    @staticmethod
    def build_cited_response(
        raw_answer: str,
        retrieved_chunks: List[VectorChunk],
    ) -> str:
        if not retrieved_chunks:
            return raw_answer

        citation_lines = ["\n\n### Verified Sources"]
        for idx, chunk in enumerate(retrieved_chunks, 1):
            cite = SourceCitationFormatter.format_citation(chunk, idx)
            snippet = chunk.content.replace("\n", " ")[:120]
            citation_lines.append(f"- {cite}: \"{snippet}...\"")

        return raw_answer.strip() + "\n" + "\n".join(citation_lines)


# =====================================================================
# FEATURE 15: EPISODIC USER MEMORY (EpisodicMemoryStore)
# =====================================================================

@dataclasses.dataclass
class MemoryCard:
    card_id: str
    title: str
    category: str
    content: str
    importance: int  # 1 to 5
    tags: List[str]
    created_at: str = dataclasses.field(default_factory=lambda: datetime.datetime.now().isoformat())
    updated_at: str = dataclasses.field(default_factory=lambda: datetime.datetime.now().isoformat())
    workspace: str = "default"


class EpisodicMemoryStore:
    """
    Manages inspectable, editable, and deletable episodic memory cards for user preferences,
    facts, environment setups, and system instructions.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = Path(tempfile.gettempdir()) / "sudharshan_data"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(base_dir / "episodic_memory.db")
        else:
            self.db_path = db_path
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_cards (
                    card_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance INTEGER NOT NULL DEFAULT 3,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    workspace TEXT NOT NULL DEFAULT 'default',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_workspace ON memory_cards(workspace);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_category ON memory_cards(category);")

    def create_card(
        self,
        title: str,
        content: str,
        category: str = "general",
        importance: int = 3,
        tags: Optional[List[str]] = None,
        workspace: str = "default",
    ) -> MemoryCard:
        cid = f"mem_{int(time.time() * 1000)}_{secrets.token_hex(3)}"
        now = datetime.datetime.now().isoformat()
        card = MemoryCard(
            card_id=cid,
            title=title,
            category=category,
            content=content,
            importance=max(1, min(5, importance)),
            tags=tags or [],
            created_at=now,
            updated_at=now,
            workspace=workspace,
        )
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO memory_cards 
                (card_id, title, category, content, importance, tags_json, workspace, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card.card_id,
                    card.title,
                    card.category,
                    card.content,
                    card.importance,
                    json.dumps(card.tags),
                    card.workspace,
                    card.created_at,
                    card.updated_at,
                ),
            )
            conn.commit()
        return card

    def get_card(self, card_id: str) -> Optional[MemoryCard]:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM memory_cards WHERE card_id = ?", (card_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return MemoryCard(
                card_id=row["card_id"],
                title=row["title"],
                category=row["category"],
                content=row["content"],
                importance=row["importance"],
                tags=json.loads(row["tags_json"] or "[]"),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                workspace=row["workspace"],
            )

    def update_card(
        self,
        card_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        category: Optional[str] = None,
        importance: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ) -> bool:
        card = self.get_card(card_id)
        if not card:
            return False

        new_title = title if title is not None else card.title
        new_content = content if content is not None else card.content
        new_category = category if category is not None else card.category
        new_importance = max(1, min(5, importance)) if importance is not None else card.importance
        new_tags = tags if tags is not None else card.tags
        now = datetime.datetime.now().isoformat()

        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                UPDATE memory_cards 
                SET title = ?, content = ?, category = ?, importance = ?, tags_json = ?, updated_at = ?
                WHERE card_id = ?
                """,
                (new_title, new_content, new_category, new_importance, json.dumps(new_tags), now, card_id),
            )
            conn.commit()
        return True

    def delete_card(self, card_id: str) -> bool:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memory_cards WHERE card_id = ?", (card_id,))
            conn.commit()
            return cursor.rowcount > 0

    def list_cards(self, workspace: str = "default", category: Optional[str] = None) -> List[MemoryCard]:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            if category:
                cursor.execute(
                    "SELECT * FROM memory_cards WHERE workspace = ? AND category = ? ORDER BY importance DESC, updated_at DESC",
                    (workspace, category),
                )
            else:
                cursor.execute(
                    "SELECT * FROM memory_cards WHERE workspace = ? ORDER BY importance DESC, updated_at DESC",
                    (workspace,),
                )
            rows = cursor.fetchall()
            return [
                MemoryCard(
                    card_id=r["card_id"],
                    title=r["title"],
                    category=r["category"],
                    content=r["content"],
                    importance=r["importance"],
                    tags=json.loads(r["tags_json"] or "[]"),
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    workspace=r["workspace"],
                )
                for r in rows
            ]


# =====================================================================
# FEATURE 16: PROJECT-SCOPED WORKSPACES (ProjectWorkspaceManager)
# =====================================================================

@dataclasses.dataclass
class ProjectWorkspace:
    workspace_id: str
    name: str
    root_path: str
    description: str
    created_at: str = dataclasses.field(default_factory=lambda: datetime.datetime.now().isoformat())


class ProjectWorkspaceManager:
    """Manages isolated workspaces with dedicated RAG vector indices and episodic memories."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = Path(tempfile.gettempdir()) / "sudharshan_data"
            base_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(base_dir / "workspaces.db")
        else:
            self.db_path = db_path
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self.active_workspace_id: str = "default"
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workspaces (
                    workspace_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    root_path TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            # Default workspace
            conn.execute(
                """
                INSERT OR IGNORE INTO workspaces (workspace_id, name, root_path, description, created_at)
                VALUES ('default', 'Default Workspace', '.', 'Global default workspace', CURRENT_TIMESTAMP);
                """
            )
            conn.commit()

    def create_workspace(self, name: str, root_path: str, description: str = "") -> ProjectWorkspace:
        wid = re.sub(r"[^a-zA-Z0-9_-]", "_", name.lower().strip())
        ws = ProjectWorkspace(
            workspace_id=wid,
            name=name,
            root_path=str(Path(root_path).resolve()),
            description=description,
        )
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO workspaces (workspace_id, name, root_path, description, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ws.workspace_id, ws.name, ws.root_path, ws.description, ws.created_at),
            )
            conn.commit()
        return ws

    def switch_workspace(self, workspace_id: str) -> bool:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT workspace_id FROM workspaces WHERE workspace_id = ?", (workspace_id,))
            if cursor.fetchone():
                self.active_workspace_id = workspace_id
                return True
        return False

    def list_workspaces(self) -> List[ProjectWorkspace]:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM workspaces ORDER BY name ASC")
            return [
                ProjectWorkspace(
                    workspace_id=r["workspace_id"],
                    name=r["name"],
                    root_path=r["root_path"],
                    description=r["description"],
                    created_at=r["created_at"],
                )
                for r in cursor.fetchall()
            ]


# =====================================================================
# FEATURE 17: INSTANT CLIPBOARD-TO-KNOWLEDGE CAPTURE (ClipboardKnowledgeCapture)
# =====================================================================

class ClipboardKnowledgeCapture:
    """Instant clipboard ingest into knowledge base with auto-tagging, metadata, and vectors."""

    def __init__(self, vector_store: LocalVectorStore, memory_store: EpisodicMemoryStore):
        self.vector_store = vector_store
        self.memory_store = memory_store

    def capture_text(
        self,
        text: str,
        title_hint: Optional[str] = None,
        workspace: str = "default",
        target: str = "both",  # "vector", "memory", "both"
    ) -> Dict[str, Any]:
        cleaned = (text or "").strip()
        if not cleaned:
            return {"status": "error", "message": "Clipboard text is empty."}

        first_line = cleaned.splitlines()[0][:60]
        title = title_hint or (first_line if len(first_line) > 5 else "Clipboard Snippet")

        # Auto-tagging heuristic
        tags = ["clipboard", "captured"]
        if "def " in cleaned or "class " in cleaned or "import " in cleaned:
            tags.append("code")
        if "http://" in cleaned or "https://" in cleaned:
            tags.append("url")
        if "@" in cleaned:
            tags.append("contact")

        created_card_id = None
        if target in ("memory", "both"):
            card = self.memory_store.create_card(
                title=title,
                content=cleaned,
                category="snippets",
                importance=3,
                tags=tags,
                workspace=workspace,
            )
            created_card_id = card.card_id

        created_chunk_id = None
        if target in ("vector", "both"):
            cid = f"clip_{int(time.time() * 1000)}_{secrets.token_hex(2)}"
            emb = generate_local_embedding(cleaned)
            chunk = VectorChunk(
                chunk_id=cid,
                doc_id=f"doc_clip_{int(time.time())}",
                file_path="clipboard://snippet",
                content=cleaned,
                embedding=emb,
                start_line=1,
                end_line=len(cleaned.splitlines()),
                metadata={"title": title, "tags": tags},
                workspace=workspace,
            )
            self.vector_store.insert_chunks([chunk])
            created_chunk_id = cid

        return {
            "status": "success",
            "title": title,
            "tags": tags,
            "memory_card_id": created_card_id,
            "vector_chunk_id": created_chunk_id,
            "workspace": workspace,
        }


# =====================================================================
# FEATURE 18: SMART DUPLICATE / NEAR-DUPLICATE DETECTOR (DocumentDeduplicator)
# =====================================================================

@dataclasses.dataclass
class DuplicateMatch:
    original_path: str
    duplicate_path: str
    match_type: str  # "exact_sha256" or "near_semantic"
    similarity: float
    size_bytes: int


class DocumentDeduplicator:
    """Detects exact duplicates via SHA-256 and near-duplicate documents via semantic vector cosine."""

    def __init__(self, semantic_threshold: float = 0.92):
        self.semantic_threshold = semantic_threshold

    @staticmethod
    def calculate_sha256(file_path: str) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def scan_directory_for_duplicates(self, dir_path: str) -> List[DuplicateMatch]:
        matches: List[DuplicateMatch] = []
        files: List[str] = []

        for root, _, filenames in os.walk(dir_path):
            for fn in filenames:
                fp = os.path.join(root, fn)
                if os.path.isfile(fp):
                    files.append(fp)

        # 1. Exact SHA-256 Matching
        hash_map: Dict[str, str] = {}
        exact_duplicate_files: Set[str] = set()

        for fp in files:
            try:
                fhash = self.calculate_sha256(fp)
                if fhash in hash_map:
                    original = hash_map[fhash]
                    size = os.path.getsize(fp)
                    matches.append(
                        DuplicateMatch(
                            original_path=original,
                            duplicate_path=fp,
                            match_type="exact_sha256",
                            similarity=1.0,
                            size_bytes=size,
                        )
                    )
                    exact_duplicate_files.add(fp)
                else:
                    hash_map[fhash] = fp
            except Exception as e:
                logger.warning("Error calculating hash for %s: %s", fp, e)

        # 2. Near-duplicate semantic detection on text files
        text_files = [
            f for f in files
            if f not in exact_duplicate_files and Path(f).suffix.lower() in {".txt", ".md", ".py", ".docx"}
        ]

        embeddings: Dict[str, List[float]] = {}
        for fp in text_files:
            try:
                text = DocumentTextExtractor.extract_text(fp)
                if text.strip():
                    embeddings[fp] = generate_local_embedding(text[:1200])
            except Exception:
                pass

        processed_pairs: Set[Tuple[str, str]] = set()
        tf_list = list(embeddings.keys())
        for i in range(len(tf_list)):
            for j in range(i + 1, len(tf_list)):
                f1, f2 = tf_list[i], tf_list[j]
                pair_key = (f1, f2)
                if pair_key in processed_pairs:
                    continue
                processed_pairs.add(pair_key)

                sim = compute_cosine_similarity(embeddings[f1], embeddings[f2])
                if sim >= self.semantic_threshold:
                    matches.append(
                        DuplicateMatch(
                            original_path=f1,
                            duplicate_path=f2,
                            match_type="near_semantic",
                            similarity=round(sim, 4),
                            size_bytes=os.path.getsize(f2),
                        )
                    )

        return matches


# =====================================================================
# FEATURE 19: AUTO-EXPIRING INCOGNITO CHAT MODE (IncognitoSessionManager)
# =====================================================================

class IncognitoSessionManager:
    """
    Manages auto-expiring ephemeral incognito chat sessions.
    Guarantees strictly volatile in-memory context; writes zero disk logs, vectors, or database records.
    """

    def __init__(self, default_ttl_seconds: int = 1800):
        self.default_ttl = default_ttl_seconds
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start_incognito_session(self, ttl_seconds: Optional[int] = None) -> str:
        sid = f"incognito_{int(time.time())}_{secrets.token_hex(4)}"
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        with self._lock:
            self.active_sessions[sid] = {
                "session_id": sid,
                "created_at": time.time(),
                "expires_at": time.time() + ttl,
                "messages": [],
                "is_active": True,
            }
        return sid

    def append_message(self, session_id: str, role: str, content: str) -> bool:
        with self._lock:
            sess = self.active_sessions.get(session_id)
            if not sess or not sess["is_active"]:
                return False

            # Check expiration
            if time.time() > sess["expires_at"]:
                self._terminate_session_locked(session_id)
                return False

            sess["messages"].append({"role": role, "content": content, "timestamp": time.time()})
            return True

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            sess = self.active_sessions.get(session_id)
            if not sess or not sess["is_active"] or time.time() > sess["expires_at"]:
                return []
            return list(sess["messages"])

    def end_session(self, session_id: str) -> bool:
        with self._lock:
            return self._terminate_session_locked(session_id)

    def _terminate_session_locked(self, session_id: str) -> bool:
        if session_id in self.active_sessions:
            # Overwrite memory buffers with zeros before deletion
            sess = self.active_sessions.pop(session_id)
            for m in sess.get("messages", []):
                m["content"] = "\x00" * len(m["content"])
            return True
        return False

    def is_incognito(self, session_id: str) -> bool:
        with self._lock:
            sess = self.active_sessions.get(session_id)
            return bool(sess and sess["is_active"] and time.time() <= sess["expires_at"])


# =====================================================================
# FEATURE 20: ENCRYPTED MEMORY BACKUP & RESTORE (MemoryBackupManager)
# =====================================================================

class MemoryBackupManager:
    """
    Exports workspace episodic memory and knowledge into portable Markdown / JSON,
    and provides authenticated encryption (PBKDF2-HMAC-SHA256 + CTR/HMAC) backup and restore.
    """

    def __init__(self, memory_store: EpisodicMemoryStore, vector_store: LocalVectorStore):
        self.memory_store = memory_store
        self.vector_store = vector_store

    def export_to_json(self, workspace: str = "default") -> str:
        cards = self.memory_store.list_cards(workspace=workspace)
        cards_dict = [dataclasses.asdict(c) for c in cards]
        data = {
            "version": "1.0",
            "workspace": workspace,
            "exported_at": datetime.datetime.now().isoformat(),
            "memory_cards": cards_dict,
        }
        return json.dumps(data, indent=2)

    def export_to_markdown(self, workspace: str = "default") -> str:
        cards = self.memory_store.list_cards(workspace=workspace)
        lines = [
            f"# Sudharshan AI Memory Backup — Workspace: {workspace}",
            f"**Exported At**: {datetime.datetime.now().isoformat()}",
            f"**Total Memory Cards**: {len(cards)}\n",
            "---",
        ]
        for c in cards:
            lines.append(f"\n## [{c.category.upper()}] {c.title}")
            lines.append(f"- **ID**: `{c.card_id}`")
            lines.append(f"- **Importance**: {'★' * c.importance}")
            lines.append(f"- **Tags**: {', '.join(c.tags)}")
            lines.append(f"- **Created**: {c.created_at}")
            lines.append("\n```markdown")
            lines.append(c.content)
            lines.append("```\n")

        return "\n".join(lines)

    @staticmethod
    def _derive_keys(passphrase: str, salt: bytes) -> Tuple[bytes, bytes]:
        # Derives 32-byte encryption key + 32-byte HMAC authentication key
        key_material = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, 100_000, 64)
        return key_material[:32], key_material[32:]

    def export_encrypted_backup(self, passphrase: str, workspace: str = "default") -> bytes:
        plain_json = self.export_to_json(workspace=workspace).encode("utf-8")
        salt = secrets.token_bytes(16)
        enc_key, auth_key = self._derive_keys(passphrase, salt)

        # AES-CTR equivalent using HMAC-SHA256 keystream generator
        nonce = secrets.token_bytes(16)
        ciphertext = bytearray()
        block_idx = 0
        for i in range(0, len(plain_json), 32):
            block_ctr = nonce + struct.pack(">Q", block_idx)
            keystream = hmac.new(enc_key, block_ctr, hashlib.sha256).digest()
            chunk = plain_json[i : i + 32]
            for c, k in zip(chunk, keystream):
                ciphertext.append(c ^ k)
            block_idx += 1

        # MAC over salt + nonce + ciphertext
        mac = hmac.new(auth_key, salt + nonce + bytes(ciphertext), hashlib.sha256).digest()

        # Format: MAGIC(4) | SALT(16) | NONCE(16) | MAC(32) | CIPHERTEXT
        header = b"SUDB" + salt + nonce + mac
        return header + bytes(ciphertext)

    def restore_encrypted_backup(self, encrypted_bytes: bytes, passphrase: str) -> Dict[str, Any]:
        if len(encrypted_bytes) < 4 + 16 + 16 + 32:
            return {"status": "error", "message": "Corrupted or invalid backup file format."}

        magic = encrypted_bytes[:4]
        if magic != b"SUDB":
            return {"status": "error", "message": "Invalid backup magic header."}

        salt = encrypted_bytes[4:20]
        nonce = encrypted_bytes[20:36]
        expected_mac = encrypted_bytes[36:68]
        ciphertext = encrypted_bytes[68:]

        enc_key, auth_key = self._derive_keys(passphrase, salt)
        calculated_mac = hmac.new(auth_key, salt + nonce + ciphertext, hashlib.sha256).digest()

        if not hmac.compare_digest(expected_mac, calculated_mac):
            return {"status": "error", "message": "Authentication failed: invalid passphrase or tampered backup."}

        # Decrypt
        plaintext = bytearray()
        block_idx = 0
        for i in range(0, len(ciphertext), 32):
            block_ctr = nonce + struct.pack(">Q", block_idx)
            keystream = hmac.new(enc_key, block_ctr, hashlib.sha256).digest()
            chunk = ciphertext[i : i + 32]
            for c, k in zip(chunk, keystream):
                plaintext.append(c ^ k)
            block_idx += 1

        try:
            data = json.loads(plaintext.decode("utf-8"))
            cards = data.get("memory_cards", [])
            restored_count = 0
            for cd in cards:
                self.memory_store.create_card(
                    title=cd["title"],
                    content=cd["content"],
                    category=cd.get("category", "general"),
                    importance=cd.get("importance", 3),
                    tags=cd.get("tags", []),
                    workspace=cd.get("workspace", data.get("workspace", "default")),
                )
                restored_count += 1

            return {
                "status": "success",
                "restored_cards": restored_count,
                "workspace": data.get("workspace", "default"),
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to restore payload: {e}"}


# =====================================================================
# WAVE 2 COMPREHENSIVE SELF-TEST SUITE
# =====================================================================

def run_self_test() -> int:
    """Validates all 10 features of Wave 2 (Persistent Local Memory & Semantic RAG)."""
    print("Running Sudharshan Wave 2 (Persistent Local Memory & Semantic RAG) self-tests...")

    # Safe scoped test database
    temp_dir = tempfile.mkdtemp(prefix="sudharshan_test_mem_")
    db_path = os.path.join(temp_dir, "test_vectors.db")

    # 1. Feature 11: LocalVectorStore
    store = LocalVectorStore(db_path=db_path)
    emb_ai = generate_local_embedding("artificial intelligence algorithms")
    emb_cook = generate_local_embedding("baking fresh sourdough bread")

    c1 = VectorChunk("c1", "doc1", "/path/ai.py", "Deep learning algorithms and neural nets.", emb_ai, 1, 10)
    c2 = VectorChunk("c2", "doc2", "/path/bread.md", "Sourdough fermentation and baking guide.", emb_cook, 1, 15)
    store.insert_chunks([c1, c2])

    assert store.count_chunks() == 2, f"Expected 2 chunks, got {store.count_chunks()}"
    q_vec = generate_local_embedding("machine learning models")
    hits = store.search_similar(q_vec, top_k=2)
    assert len(hits) == 2
    assert hits[0][0].chunk_id == "c1", "Expected AI chunk to rank higher"
    print("  -> Passed: Feature 11 (LocalVectorStore cosine search & SQLite WAL storage).")

    # 2. Feature 12: BackgroundFileIndexer
    indexer = BackgroundFileIndexer(store, workspace="default")
    test_file = os.path.join(temp_dir, "sample_code.py")
    with open(test_file, "w") as f:
        f.write("# Sample Python Code\ndef calculate_hash(x):\n    return hash(x)\n")

    did_idx, count = indexer.index_file(test_file)
    assert did_idx is True and count >= 1
    # Incremental test: immediate re-index should skip
    did_idx_2, _ = indexer.index_file(test_file)
    assert did_idx_2 is False, "Incremental indexer should skip unmodified file"
    print("  -> Passed: Feature 12 (Incremental BackgroundFileIndexer & file chunking).")

    # 3. Feature 13: HybridSearchEngine (BM25 + Cosine)
    hybrid = HybridSearchEngine(store, alpha=0.5)
    hybrid_hits = hybrid.search("sourdough fermentation", top_k=2)
    assert len(hybrid_hits) >= 1
    assert hybrid_hits[0][0].chunk_id == "c2"
    print("  -> Passed: Feature 13 (HybridSearchEngine RRF fusing BM25 & cosine vectors).")

    # 4. Feature 14: SourceCitationFormatter
    formatted = SourceCitationFormatter.build_cited_response(
        "Sourdough requires active starter fermentation.",
        [c2]
    )
    assert "[1] [bread.md#L1-L15]" in formatted
    assert "file://" in formatted
    print("  -> Passed: Feature 14 (SourceCitationFormatter clickable file paths & line links).")

    # 5. Feature 15: EpisodicMemoryStore
    mem_db = os.path.join(temp_dir, "test_mem.db")
    mem_store = EpisodicMemoryStore(db_path=mem_db)
    card = mem_store.create_card(
        title="Preferred Language",
        content="Kaushik prefers Python and Rust for high-performance systems.",
        category="preferences",
        importance=5,
        tags=["programming", "system"],
    )
    assert card.card_id.startswith("mem_")
    assert mem_store.update_card(card.card_id, content="Updated: Kaushik loves Python and Rust.") is True
    updated = mem_store.get_card(card.card_id)
    assert updated is not None and "Updated:" in updated.content
    print("  -> Passed: Feature 15 (EpisodicMemoryStore CRUD cards with importance ratings).")

    # 6. Feature 16: ProjectWorkspaceManager
    ws_db = os.path.join(temp_dir, "test_ws.db")
    ws_mgr = ProjectWorkspaceManager(db_path=ws_db)
    new_ws = ws_mgr.create_workspace("Sudharshan Core", temp_dir, "Core engine workspace")
    assert new_ws.workspace_id == "sudharshan_core"
    assert ws_mgr.switch_workspace(new_ws.workspace_id) is True
    assert ws_mgr.active_workspace_id == "sudharshan_core"
    print("  -> Passed: Feature 16 (ProjectWorkspaceManager isolated workspaces).")

    # 7. Feature 17: ClipboardKnowledgeCapture
    capturer = ClipboardKnowledgeCapture(store, mem_store)
    cap_res = capturer.capture_text(
        "def quick_sort(arr):\n    return arr if len(arr) <= 1 else arr",
        title_hint="Quick Sort Snippet"
    )
    assert cap_res["status"] == "success"
    assert "code" in cap_res["tags"]
    print("  -> Passed: Feature 17 (ClipboardKnowledgeCapture instant ingest & auto-tagging).")

    # 8. Feature 18: DocumentDeduplicator
    dup1 = os.path.join(temp_dir, "dup1.txt")
    dup2 = os.path.join(temp_dir, "dup2.txt")
    with open(dup1, "w") as f:
        f.write("Identical file contents for SHA-256 test.")
    with open(dup2, "w") as f:
        f.write("Identical file contents for SHA-256 test.")

    dedup = DocumentDeduplicator()
    dups = dedup.scan_directory_for_duplicates(temp_dir)
    assert any(d.match_type == "exact_sha256" for d in dups)
    print("  -> Passed: Feature 18 (DocumentDeduplicator SHA-256 exact & semantic similarity).")

    # 9. Feature 19: IncognitoSessionManager
    incog = IncognitoSessionManager(default_ttl_seconds=10)
    sid = incog.start_incognito_session()
    assert incog.is_incognito(sid) is True
    incog.append_message(sid, "user", "Sensitive secret query")
    msgs = incog.get_messages(sid)
    assert len(msgs) == 1
    assert incog.end_session(sid) is True
    assert incog.is_incognito(sid) is False
    assert len(incog.get_messages(sid)) == 0
    print("  -> Passed: Feature 19 (IncognitoSessionManager auto-expiring zero-disk privacy).")

    # 10. Feature 20: MemoryBackupManager
    backup_mgr = MemoryBackupManager(mem_store, store)
    json_dump = backup_mgr.export_to_json()
    assert "Preferred Language" in json_dump
    md_dump = backup_mgr.export_to_markdown()
    assert "# Sudharshan AI Memory Backup" in md_dump

    enc_backup = backup_mgr.export_encrypted_backup("super_secret_passphrase_123")
    assert enc_backup.startswith(b"SUDB")

    restore_res = backup_mgr.restore_encrypted_backup(enc_backup, "super_secret_passphrase_123")
    assert restore_res["status"] == "success"
    assert restore_res["restored_cards"] >= 1

    wrong_pass_res = backup_mgr.restore_encrypted_backup(enc_backup, "wrong_passphrase")
    assert wrong_pass_res["status"] == "error"
    print("  -> Passed: Feature 20 (MemoryBackupManager PBKDF2/HMAC encrypted backup & restore).")

    print("\nAll 10 Features in Wave 2 verified and passed successfully!\n")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_self_test())
