"""
SUDHARSHAN NATIVE — 1.5B Production PyTorch (torch.nn.Module) Architecture.

Identical mathematical specification to `model_numpy.py`:
- Decoder-Only Transformer with Token Embeddings (tied or untied LM head)
- Rotary Positional Embeddings (RoPE)
- RMSNorm
- Grouped Query Attention (GQA) with Causal Self-Attention & KV Caching
- SwiGLU Feed-Forward Network
- Residual Connections & LoRA / QLoRA-compatible Adapter Layers
- Mixed-Precision (bf16/fp16) & GPU/CPU Training Support
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import SudharshanNativeConfig

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore
    nn = None  # type: ignore
    F = None  # type: ignore
    TORCH_AVAILABLE = False


if TORCH_AVAILABLE:
    class RMSNorm(nn.Module):
        def __init__(self, hidden_size: int, eps: float = 1e-6) -> None:
            super().__init__()
            self.eps = eps
            self.weight = nn.Parameter(torch.ones(hidden_size))

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            norm = x.pow(2).mean(dim=-1, keepdim=True)
            return x * torch.rsqrt(norm + self.eps) * self.weight

    class LoRALinear(nn.Module):
        def __init__(self, base_linear: nn.Linear, rank: int = 8, alpha: float = 16.0) -> None:
            super().__init__()
            self.base = base_linear
            for p in self.base.parameters():
                p.requires_grad = False
            self.scale = alpha / float(rank)
            self.lora_a = nn.Parameter(torch.randn(base_linear.in_features, rank) * 0.01)
            self.lora_b = nn.Parameter(torch.zeros(rank, base_linear.out_features))

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.base(x) + ((x @ self.lora_a) @ self.lora_b) * self.scale

    def _build_rope_torch(max_len: int, head_dim: int, theta: float, device: torch.device) -> Tuple[torch.Tensor, torch.Tensor]:
        inv_freq = 1.0 / (theta ** (torch.arange(0, head_dim, 2, device=device, dtype=torch.float32) / head_dim))
        pos = torch.arange(max_len, device=device, dtype=torch.float32)
        freqs = torch.outer(pos, inv_freq)
        return torch.cos(freqs), torch.sin(freqs)

    def _apply_rope_torch(x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor, start_pos: int = 0) -> torch.Tensor:
        seq_len = x.shape[2]
        c = cos[start_pos:start_pos + seq_len].unsqueeze(0).unsqueeze(0)
        s = sin[start_pos:start_pos + seq_len].unsqueeze(0).unsqueeze(0)
        x1, x2 = x[..., 0::2], x[..., 1::2]
        return torch.stack((x1 * c - x2 * s, x1 * s + x2 * c), dim=-1).flatten(-2)

    class GroupedQueryAttention(nn.Module):
        def __init__(self, cfg: SudharshanNativeConfig) -> None:
            super().__init__()
            self.cfg = cfg
            h = cfg.hidden_size
            kv_dim = cfg.num_key_value_heads * cfg.head_dim
            self.q_proj = nn.Linear(h, h, bias=False)
            self.k_proj = nn.Linear(h, kv_dim, bias=False)
            self.v_proj = nn.Linear(h, kv_dim, bias=False)
            self.o_proj = nn.Linear(h, h, bias=False)

        def forward(
            self,
            x: torch.Tensor,
            cos: torch.Tensor,
            sin: torch.Tensor,
            kv_cache: Optional[Tuple[torch.Tensor, torch.Tensor]] = None,
            use_cache: bool = False,
        ) -> Tuple[torch.Tensor, Optional[Tuple[torch.Tensor, torch.Tensor]]]:
            bsz, seq_len, _ = x.shape
            c = self.cfg
            start_pos = kv_cache[0].shape[2] if kv_cache is not None else 0
            q = self.q_proj(x).view(bsz, seq_len, c.num_attention_heads, c.head_dim).transpose(1, 2)
            k = self.k_proj(x).view(bsz, seq_len, c.num_key_value_heads, c.head_dim).transpose(1, 2)
            v = self.v_proj(x).view(bsz, seq_len, c.num_key_value_heads, c.head_dim).transpose(1, 2)

            q = _apply_rope_torch(q, cos, sin, start_pos=start_pos)
            k = _apply_rope_torch(k, cos, sin, start_pos=start_pos)

            if kv_cache is not None:
                k = torch.cat([kv_cache[0], k], dim=2)
                v = torch.cat([kv_cache[1], v], dim=2)
            new_cache = (k, v) if use_cache else None

            if c.kv_groups > 1:
                k_exp = k.repeat_interleave(c.kv_groups, dim=1)
                v_exp = v.repeat_interleave(c.kv_groups, dim=1)
            else:
                k_exp, v_exp = k, v

            scores = torch.matmul(q, k_exp.transpose(-2, -1)) / (c.head_dim ** 0.5)
            total_len = k_exp.shape[2]
            q_pos = torch.arange(start_pos, start_pos + seq_len, device=x.device).unsqueeze(1)
            k_pos = torch.arange(total_len, device=x.device).unsqueeze(0)
            mask = torch.where(k_pos <= q_pos, 0.0, float("-inf")).to(scores.dtype)
            attn = F.softmax(scores + mask.unsqueeze(0).unsqueeze(0), dim=-1)
            ctx = torch.matmul(attn, v_exp).transpose(1, 2).contiguous().view(bsz, seq_len, c.hidden_size)
            return self.o_proj(ctx), new_cache

    class SwiGLUFFN(nn.Module):
        def __init__(self, cfg: SudharshanNativeConfig) -> None:
            super().__init__()
            self.gate_proj = nn.Linear(cfg.hidden_size, cfg.intermediate_size, bias=False)
            self.up_proj = nn.Linear(cfg.hidden_size, cfg.intermediate_size, bias=False)
            self.down_proj = nn.Linear(cfg.intermediate_size, cfg.hidden_size, bias=False)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.down_proj(F.silu(self.gate_proj(x)) * self.up_proj(x))

    class TransformerBlock(nn.Module):
        def __init__(self, cfg: SudharshanNativeConfig) -> None:
            super().__init__()
            self.input_norm = RMSNorm(cfg.hidden_size, cfg.rms_norm_eps)
            self.attn = GroupedQueryAttention(cfg)
            self.post_norm = RMSNorm(cfg.hidden_size, cfg.rms_norm_eps)
            self.ffn = SwiGLUFFN(cfg)

        def forward(
            self,
            x: torch.Tensor,
            cos: torch.Tensor,
            sin: torch.Tensor,
            kv_cache: Optional[Tuple[torch.Tensor, torch.Tensor]] = None,
            use_cache: bool = False,
        ) -> Tuple[torch.Tensor, Optional[Tuple[torch.Tensor, torch.Tensor]]]:
            attn_out, new_cache = self.attn(self.input_norm(x), cos, sin, kv_cache=kv_cache, use_cache=use_cache)
            x = x + attn_out
            x = x + self.ffn(self.post_norm(x))
            return x, new_cache

    class SudharshanNativeTorchModel(nn.Module):
        def __init__(self, cfg: SudharshanNativeConfig) -> None:
            super().__init__()
            self.cfg = cfg
            self.embed_tokens = nn.Embedding(cfg.vocab_size, cfg.hidden_size)
            self.layers = nn.ModuleList([TransformerBlock(cfg) for _ in range(cfg.num_hidden_layers)])
            self.final_norm = RMSNorm(cfg.hidden_size, cfg.rms_norm_eps)
            self.lm_head = None if cfg.tie_word_embeddings else nn.Linear(cfg.hidden_size, cfg.vocab_size, bias=False)
            self.apply(self._init_weights)

        def _init_weights(self, module: nn.Module) -> None:
            if isinstance(module, (nn.Linear, nn.Embedding)):
                nn.init.normal_(module.weight, mean=0.0, std=self.cfg.initializer_range)

        def count_parameters(self) -> int:
            return sum(p.numel() for p in self.parameters())

        def enable_lora(self, rank: int = 8, alpha: float = 16.0) -> int:
            for layer in self.layers:
                layer.attn.q_proj = LoRALinear(layer.attn.q_proj, rank=rank, alpha=alpha)
                layer.attn.v_proj = LoRALinear(layer.attn.v_proj, rank=rank, alpha=alpha)
            return sum(p.numel() for p in self.parameters() if p.requires_grad)

        def forward(
            self,
            input_ids: torch.Tensor,
            kv_caches: Optional[List[Optional[Tuple[torch.Tensor, torch.Tensor]]]] = None,
            use_cache: bool = False,
        ) -> Tuple[torch.Tensor, Optional[List[Tuple[torch.Tensor, torch.Tensor]]]]:
            x = self.embed_tokens(input_ids)
            cos, sin = _build_rope_torch(self.cfg.max_position_embeddings, self.cfg.head_dim, self.cfg.rope_theta, x.device)
            next_caches: List[Tuple[torch.Tensor, torch.Tensor]] = []
            for idx, layer in enumerate(self.layers):
                prev = kv_caches[idx] if kv_caches is not None else None
                x, nc = layer(x, cos, sin, kv_cache=prev, use_cache=use_cache)
                if use_cache and nc is not None:
                    next_caches.append(nc)
            x = self.final_norm(x)
            logits = F.linear(x, self.embed_tokens.weight) if self.lm_head is None else self.lm_head(x)
            return logits, (next_caches if use_cache else None)

        def save_checkpoint(self, path: Path) -> Path:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            torch.save({"config": self.cfg.to_dict(), "state_dict": self.state_dict()}, p)
            return p
else:
    class SudharshanNativeTorchModel:  # pragma: no cover
        def __init__(self, cfg: SudharshanNativeConfig) -> None:
            raise RuntimeError("PyTorch is not installed in this environment. Use SudharshanNativeNumPyModel for CPU execution or install torch>=2.2 for GPU 1.5B training.")
