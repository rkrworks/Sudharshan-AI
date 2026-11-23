"""
SUDHARSHAN NATIVE — Dedicated BPE Subword Tokenizer.

Supports:
- Byte-level / character-seeded BPE subword training on arbitrary corpora
- Dedicated special tokens for conversation roles, tool-call markers, and code blocks
- Code-aware pre-tokenization preserving indentation, operators, and JSON delimiters
- Deterministic encode / decode & JSON serialization
"""
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SPECIAL_TOKENS: List[str] = [
    "<|pad|>",
    "<|bos|>",
    "<|eos|>",
    "<|unk|>",
    "<|system|>",
    "<|user|>",
    "<|assistant|>",
    "<|tool_call|>",
    "<|/tool_call|>",
    "<|tool_result|>",
    "<|/tool_result|>",
    "<|code|>",
    "<|/code|>",
]

# Code-aware pre-tokenizer: preserves special tokens, identifiers, numbers, operators, and whitespace
_PRETOKEN_RE = re.compile(
    r"<\|/?[a-z_]+\|>"
    r"|[A-Za-z_][A-Za-z0-9_]*"
    r"|[0-9]+"
    r"|\r?\n"
    r"|[ \t]+"
    r"|[^\sA-Za-z0-9_]"
)


class SudharshanBPETokenizer:
    def __init__(
        self,
        vocab: Optional[Dict[str, int]] = None,
        merges: Optional[List[Tuple[str, str]]] = None,
    ) -> None:
        self.vocab: Dict[str, int] = dict(vocab) if vocab else {}
        self.merges: List[Tuple[str, str]] = list(merges) if merges else []
        self._merge_ranks: Dict[Tuple[str, str], int] = {
            pair: i for i, pair in enumerate(self.merges)
        }
        if not self.vocab:
            for idx, tok in enumerate(SPECIAL_TOKENS):
                self.vocab[tok] = idx
        self._id_to_tok: Dict[int, str] = {i: t for t, i in self.vocab.items()}

    @property
    def vocab_size(self) -> int:
        return len(self.vocab)

    @property
    def pad_id(self) -> int:
        return self.vocab["<|pad|>"]

    @property
    def bos_id(self) -> int:
        return self.vocab["<|bos|>"]

    @property
    def eos_id(self) -> int:
        return self.vocab["<|eos|>"]

    @property
    def unk_id(self) -> int:
        return self.vocab["<|unk|>"]

    @staticmethod
    def pretokenize(text: str) -> List[str]:
        return _PRETOKEN_RE.findall(text or "")

    def train(self, texts: Sequence[str], target_vocab_size: int = 512, min_freq: int = 2) -> Dict[str, int]:
        self.vocab = {tok: idx for idx, tok in enumerate(SPECIAL_TOKENS)}
        self.merges = []

        # Seed base ASCII + observed characters so encoding never loses characters
        chars = set(chr(c) for c in range(32, 127))
        chars.update({"\n", "\t"})
        word_freqs: Counter = Counter()
        for doc in texts:
            for piece in self.pretokenize(doc):
                if piece in self.vocab:
                    continue
                for ch in piece:
                    chars.add(ch)
                word_freqs[tuple(piece)] += 1

        for ch in sorted(chars):
            if ch not in self.vocab:
                self.vocab[ch] = len(self.vocab)

        # Iterative BPE pair merging
        while len(self.vocab) < target_vocab_size:
            pair_counts: Counter = Counter()
            for word, freq in word_freqs.items():
                if len(word) < 2:
                    continue
                for i in range(len(word) - 1):
                    pair_counts[(word[i], word[i + 1])] += freq
            if not pair_counts:
                break
            best_pair, best_freq = pair_counts.most_common(1)[0]
            if best_freq < min_freq:
                break
            merged = best_pair[0] + best_pair[1]
            self.merges.append(best_pair)
            if merged not in self.vocab:
                self.vocab[merged] = len(self.vocab)

            new_freqs: Counter = Counter()
            a, b = best_pair
            for word, freq in word_freqs.items():
                out: List[str] = []
                i = 0
                n = len(word)
                while i < n:
                    if i < n - 1 and word[i] == a and word[i + 1] == b:
                        out.append(merged)
                        i += 2
                    else:
                        out.append(word[i])
                        i += 1
                new_freqs[tuple(out)] += freq
            word_freqs = new_freqs

        self._merge_ranks = {pair: i for i, pair in enumerate(self.merges)}
        self._id_to_tok = {i: t for t, i in self.vocab.items()}
        return {"vocab_size": len(self.vocab), "merges": len(self.merges)}

    def _apply_bpe(self, piece: str) -> List[str]:
        if piece in self.vocab:
            return [piece]
        symbols = list(piece)
        while len(symbols) >= 2:
            best_rank = None
            best_idx = -1
            for i in range(len(symbols) - 1):
                rank = self._merge_ranks.get((symbols[i], symbols[i + 1]))
                if rank is not None and (best_rank is None or rank < best_rank):
                    best_rank = rank
                    best_idx = i
            if best_idx < 0:
                break
            symbols = symbols[:best_idx] + [symbols[best_idx] + symbols[best_idx + 1]] + symbols[best_idx + 2:]
        return symbols

    def encode(self, text: str, add_bos: bool = False, add_eos: bool = False) -> List[int]:
        ids: List[int] = []
        if add_bos:
            ids.append(self.bos_id)
        for piece in self.pretokenize(text):
            if piece in self.vocab:
                ids.append(self.vocab[piece])
            else:
                for sub in self._apply_bpe(piece):
                    ids.append(self.vocab.get(sub, self.unk_id))
        if add_eos:
            ids.append(self.eos_id)
        return ids

    def decode(self, token_ids: Sequence[int], skip_special_tokens: bool = False) -> str:
        special_set = set(SPECIAL_TOKENS)
        parts: List[str] = []
        for tid in token_ids:
            tok = self._id_to_tok.get(int(tid), "<|unk|>")
            if skip_special_tokens and tok in special_set:
                continue
            parts.append(tok)
        return "".join(parts)

    def format_chat(self, messages: Sequence[Dict[str, str]], add_generation_prompt: bool = True) -> str:
        chunks: List[str] = []
        for m in messages:
            role = m.get("role", "user").lower()
            tag = f"<|{role}|>" if f"<|{role}|>" in self.vocab else "<|user|>"
            chunks.append(f"{tag}{m.get('content', '')}<|eos|>")
        if add_generation_prompt:
            chunks.append("<|assistant|>")
        return "".join(chunks)

    def save(self, path: Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "type": "SudharshanBPETokenizer",
            "version": "1.0",
            "special_tokens": SPECIAL_TOKENS,
            "vocab": self.vocab,
            "merges": [list(m) for m in self.merges],
        }
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: Path) -> "SudharshanBPETokenizer":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        merges = [(m[0], m[1]) for m in data.get("merges", [])]
        return cls(vocab=data["vocab"], merges=merges)
