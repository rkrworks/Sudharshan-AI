"""
SUDHARSHAN NATIVE — Executable Pure-NumPy Decoder-Only Transformer Engine.

Implements the exact Sudharshan Native architecture:
- Token Embeddings (with weight tying option)
- Rotary Positional Embeddings (RoPE)
- RMSNorm
- Grouped Query Attention (GQA) with Causal Masking
- SwiGLU Feed-Forward Network
- Residual Connections
- Incremental KV Caching
- Batched Inference
- Autoregressive Generation (Temperature, Top-k, Top-p, Repetition Penalty, Stop Tokens)
- LoRA Low-Rank Adapter Support
- Checkpoint Save / Load (.npz + config.json)
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .config import SudharshanNativeConfig, calculate_parameter_breakdown


@dataclass
class GenerationConfig:
    max_new_tokens: int = 32
    temperature: float = 0.7
    top_k: int = 40
    top_p: float = 0.9
    repetition_penalty: float = 1.1
    stop_token_ids: Tuple[int, ...] = (2,)
    seed: int = 42


def rms_norm(x: np.ndarray, weight: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    variance = np.mean(x * x, axis=-1, keepdims=True)
    return (x * (1.0 / np.sqrt(variance + eps))) * weight


def silu(x: np.ndarray) -> np.ndarray:
    clipped = np.clip(x, -40.0, 40.0)
    return clipped / (1.0 + np.exp(-clipped))


def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    x_max = np.max(x, axis=axis, keepdims=True)
    ex = np.exp(x - x_max)
    return ex / np.sum(ex, axis=axis, keepdims=True)


def build_rope_cache(max_seq_len: int, head_dim: int, theta: float = 10000.0) -> Tuple[np.ndarray, np.ndarray]:
    inv_freq = 1.0 / (theta ** (np.arange(0, head_dim, 2, dtype=np.float32) / head_dim))
    positions = np.arange(max_seq_len, dtype=np.float32)
    freqs = np.outer(positions, inv_freq)
    return np.cos(freqs).astype(np.float32), np.sin(freqs).astype(np.float32)


def apply_rope(x: np.ndarray, cos: np.ndarray, sin: np.ndarray, start_pos: int = 0) -> np.ndarray:
    # x: [B, H, T, D]
    seq_len = x.shape[2]
    c = cos[start_pos:start_pos + seq_len][None, None, :, :]
    s = sin[start_pos:start_pos + seq_len][None, None, :, :]
    x1 = x[..., 0::2]
    x2 = x[..., 1::2]
    out = np.empty_like(x)
    out[..., 0::2] = x1 * c - x2 * s
    out[..., 1::2] = x1 * s + x2 * c
    return out


class SudharshanNativeNumPyModel:
    def __init__(self, config: SudharshanNativeConfig, seed: int = 42) -> None:
        self.config = config
        self.rng = np.random.default_rng(seed)
        self.params: Dict[str, np.ndarray] = {}
        self.lora_adapters: Dict[str, Tuple[np.ndarray, np.ndarray, float]] = {}
        self._init_weights()
        self.rope_cos, self.rope_sin = build_rope_cache(
            config.max_position_embeddings, config.head_dim, config.rope_theta
        )

    def _init_mat(self, shape: Tuple[int, ...]) -> np.ndarray:
        return self.rng.normal(0.0, self.config.initializer_range, size=shape).astype(np.float32)

    def _init_weights(self) -> None:
        c = self.config
        h = c.hidden_size
        kv_dim = c.num_key_value_heads * c.head_dim
        self.params["embed_tokens"] = self._init_mat((c.vocab_size, h))
        for i in range(c.num_hidden_layers):
            p = f"layers.{i}"
            self.params[f"{p}.input_norm"] = np.ones((h,), dtype=np.float32)
            self.params[f"{p}.q_proj"] = self._init_mat((h, h))
            self.params[f"{p}.k_proj"] = self._init_mat((h, kv_dim))
            self.params[f"{p}.v_proj"] = self._init_mat((h, kv_dim))
            self.params[f"{p}.o_proj"] = self._init_mat((h, h))
            self.params[f"{p}.post_norm"] = np.ones((h,), dtype=np.float32)
            self.params[f"{p}.gate_proj"] = self._init_mat((h, c.intermediate_size))
            self.params[f"{p}.up_proj"] = self._init_mat((h, c.intermediate_size))
            self.params[f"{p}.down_proj"] = self._init_mat((c.intermediate_size, h))
        self.params["final_norm"] = np.ones((h,), dtype=np.float32)
        if not c.tie_word_embeddings:
            self.params["lm_head"] = self._init_mat((c.vocab_size, h))

    def count_instantiated_parameters(self) -> int:
        return int(sum(arr.size for arr in self.params.values()))

    def attach_lora(self, rank: int = 4, alpha: float = 8.0, target_suffixes: Tuple[str, ...] = ("q_proj", "v_proj")) -> int:
        scale = alpha / float(rank)
        added = 0
        for name, weight in self.params.items():
            if any(name.endswith(sfx) for sfx in target_suffixes) and weight.ndim == 2:
                in_d, out_d = weight.shape
                a = self.rng.normal(0.0, 0.01, size=(in_d, rank)).astype(np.float32)
                b = np.zeros((rank, out_d), dtype=np.float32)
                self.lora_adapters[name] = (a, b, scale)
                added += a.size + b.size
        return added

    def _linear(self, x: np.ndarray, name: str) -> np.ndarray:
        out = x @ self.params[name]
        if name in self.lora_adapters:
            a, b, scale = self.lora_adapters[name]
            out = out + ((x @ a) @ b) * scale
        return out

    def forward(
        self,
        input_ids: np.ndarray,
        kv_cache: Optional[List[Optional[Tuple[np.ndarray, np.ndarray]]]] = None,
        use_cache: bool = False,
    ) -> Tuple[np.ndarray, Optional[List[Tuple[np.ndarray, np.ndarray]]]]:
        ids = np.asarray(input_ids, dtype=np.int64)
        if ids.ndim == 1:
            ids = ids[None, :]
        bsz, seq_len = ids.shape
        c = self.config
        start_pos = 0
        if kv_cache is not None and len(kv_cache) > 0 and kv_cache[0] is not None:
            start_pos = kv_cache[0][0].shape[2]

        x = self.params["embed_tokens"][ids]  # [B, T, H]
        next_cache: List[Tuple[np.ndarray, np.ndarray]] = []

        for i in range(c.num_hidden_layers):
            p = f"layers.{i}"
            h_norm = rms_norm(x, self.params[f"{p}.input_norm"], c.rms_norm_eps)

            q = self._linear(h_norm, f"{p}.q_proj").reshape(bsz, seq_len, c.num_attention_heads, c.head_dim).transpose(0, 2, 1, 3)
            k = self._linear(h_norm, f"{p}.k_proj").reshape(bsz, seq_len, c.num_key_value_heads, c.head_dim).transpose(0, 2, 1, 3)
            v = self._linear(h_norm, f"{p}.v_proj").reshape(bsz, seq_len, c.num_key_value_heads, c.head_dim).transpose(0, 2, 1, 3)

            q = apply_rope(q, self.rope_cos, self.rope_sin, start_pos=start_pos)
            k = apply_rope(k, self.rope_cos, self.rope_sin, start_pos=start_pos)

            if kv_cache is not None and i < len(kv_cache) and kv_cache[i] is not None:
                prev_k, prev_v = kv_cache[i]
                k = np.concatenate([prev_k, k], axis=2)
                v = np.concatenate([prev_v, v], axis=2)
            if use_cache:
                next_cache.append((k, v))

            # Repeat KV heads for Grouped Query Attention
            if c.kv_groups > 1:
                k_exp = np.repeat(k, c.kv_groups, axis=1)
                v_exp = np.repeat(v, c.kv_groups, axis=1)
            else:
                k_exp, v_exp = k, v

            total_len = k_exp.shape[2]
            scores = np.matmul(q, np.swapaxes(k_exp, -1, -2)) / np.sqrt(float(c.head_dim))

            # Causal mask
            q_pos = np.arange(start_pos, start_pos + seq_len)[:, None]
            k_pos = np.arange(total_len)[None, :]
            mask = np.where(k_pos <= q_pos, 0.0, -1e9).astype(np.float32)
            scores = scores + mask[None, None, :, :]

            attn = softmax(scores, axis=-1)
            ctx = np.matmul(attn, v_exp).transpose(0, 2, 1, 3).reshape(bsz, seq_len, c.hidden_size)
            x = x + self._linear(ctx, f"{p}.o_proj")

            # SwiGLU FFN + Residual
            h2 = rms_norm(x, self.params[f"{p}.post_norm"], c.rms_norm_eps)
            gate = silu(self._linear(h2, f"{p}.gate_proj"))
            up = self._linear(h2, f"{p}.up_proj")
            x = x + self._linear(gate * up, f"{p}.down_proj")

        x = rms_norm(x, self.params["final_norm"], c.rms_norm_eps)
        lm_w = self.params["embed_tokens"] if c.tie_word_embeddings else self.params["lm_head"]
        logits = x @ lm_w.T  # [B, T, V]
        return logits, (next_cache if use_cache else None)

    @staticmethod
    def sample_next_token(
        logits_1d: np.ndarray,
        generated_ids: Sequence[int],
        gen_cfg: GenerationConfig,
        rng: np.random.Generator,
    ) -> int:
        logits = logits_1d.astype(np.float64).copy()
        if gen_cfg.repetition_penalty > 1.0 and generated_ids:
            for tid in set(generated_ids):
                if 0 <= tid < logits.shape[0]:
                    if logits[tid] > 0:
                        logits[tid] /= gen_cfg.repetition_penalty
                    else:
                        logits[tid] *= gen_cfg.repetition_penalty

        if gen_cfg.temperature <= 1e-5:
            return int(np.argmax(logits))

        logits = logits / gen_cfg.temperature
        if 0 < gen_cfg.top_k < logits.shape[0]:
            top_idx = np.argpartition(logits, -gen_cfg.top_k)[-gen_cfg.top_k:]
            masked = np.full_like(logits, -1e18)
            masked[top_idx] = logits[top_idx]
            logits = masked

        probs = softmax(logits, axis=-1)
        if 0.0 < gen_cfg.top_p < 1.0:
            order = np.argsort(probs)[::-1]
            sorted_p = probs[order]
            cum = np.cumsum(sorted_p)
            cutoff = int(np.searchsorted(cum, gen_cfg.top_p)) + 1
            keep = order[:max(1, cutoff)]
            new_probs = np.zeros_like(probs)
            new_probs[keep] = probs[keep]
            probs = new_probs / np.sum(new_probs)

        return int(rng.choice(len(probs), p=probs))

    def generate(
        self,
        prompt_ids: Sequence[int],
        gen_cfg: Optional[GenerationConfig] = None,
        on_token: Optional[Callable[[int], None]] = None,
    ) -> List[int]:
        cfg = gen_cfg or GenerationConfig()
        rng = np.random.default_rng(cfg.seed)
        seq = list(prompt_ids)
        logits, cache = self.forward(np.asarray([seq], dtype=np.int64), use_cache=True)
        for _ in range(cfg.max_new_tokens):
            next_id = self.sample_next_token(logits[0, -1], seq, cfg, rng)
            seq.append(next_id)
            if on_token:
                on_token(next_id)
            if next_id in cfg.stop_token_ids or len(seq) >= self.config.max_position_embeddings:
                break
            logits, cache = self.forward(np.asarray([[next_id]], dtype=np.int64), kv_cache=cache, use_cache=True)
        return seq

    def save_checkpoint(self, ckpt_dir: Path, metadata: Optional[Dict[str, Any]] = None) -> Path:
        ckpt_dir = Path(ckpt_dir)
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        (ckpt_dir / "config.json").write_text(json.dumps(self.config.to_dict(), indent=2), encoding="utf-8")
        (ckpt_dir / "meta.json").write_text(
            json.dumps({
                **(metadata or {}),
                "parameter_breakdown": calculate_parameter_breakdown(self.config),
                "instantiated_parameters": self.count_instantiated_parameters(),
            }, indent=2),
            encoding="utf-8",
        )
        np.savez(ckpt_dir / "weights.npz", **self.params)
        return ckpt_dir

    @classmethod
    def load_checkpoint(cls, ckpt_dir: Path) -> "SudharshanNativeNumPyModel":
        ckpt_dir = Path(ckpt_dir)
        cfg = SudharshanNativeConfig.from_dict(json.loads((ckpt_dir / "config.json").read_text(encoding="utf-8")))
        model = cls(cfg)
        with np.load(ckpt_dir / "weights.npz") as npz:
            for k in npz.files:
                model.params[k] = npz[k].astype(np.float32)
        return model
