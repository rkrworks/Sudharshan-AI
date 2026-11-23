# Sudharshan AI — Project Nebula Performance & Footprint Report

## Sudharshan Native 1.5B Architectural Profile
- **Exact Trainable Parameters:** `1,526,827,008` (1.5268B), programmatically verified via `calculate_parameter_breakdown()`
- **Layers / Heads:** 24 Transformer blocks, `hidden_size=2048`, 16 Query heads / 4 KV heads (`head_dim=128`, 4:1 GQA compression)
- **SwiGLU MLP:** `intermediate_size=8192` (`1,207,959,552` params — 79.1%)
- **Vocabulary & Context:** `vocab_size=32,768` (tied input/output embeddings: `67,108,864` params — 4.4%), `max_position_embeddings=4096`, RoPE `theta=10000.0`
- **Memory Footprint:** FP32 `5.69 GB` | FP16/BF16 `2.84 GB` | Q8_0 `1.51 GB` | Q4_K_M `0.80 GB`
- **KV Cache Savings:** 4:1 GQA reduces per-token KV cache footprint by 75% compared to standard MHA.

## Automated Execution Latency (CPU Sandbox)
- Full 40-test verification sweep: `3.32 seconds`
- `SudharshanNativeNumPyModel` Nano forward + KV-cache parity check + 6-step SFT smoke test + BPE training: `0.14 seconds`
- Adaptive Model Engine RAM fallback threshold: `< 2.5 GB` free RAM automatically shifts from `qwen3.5:4b` to `qwen3.5:2b-q4_K_M`.
