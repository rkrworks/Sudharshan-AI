"""
SUDHARSHAN AI — Unified Nebula Model Adapter.

Provides a single provider-agnostic interface for:
1. sudharshan_native (local Sudharshan Native checkpoint)
2. ollama (existing local Ollama multi-model engine — 100% backwards-compatible)
3. gemini (Google Gemini via x-goog-api-key header)
4. groq (Groq OpenAI-compatible API)
5. openai (OpenAI API)
6. openai_compatible (any custom OpenAI-style local or remote endpoint)

Includes provider switching, model selection, streaming callbacks, token accounting,
latency monitoring, fallback routing, offline detection, and capability discovery.
"""
import time
from typing import Any, Callable, Dict, List, Optional

import bajrang_core

from .model_numpy import GenerationConfig, SudharshanNativeNumPyModel
from .tokenizer import SudharshanBPETokenizer


class NebulaModelAdapter:
    SUPPORTED_PROVIDERS = (
        "sudharshan_native",
        "ollama",
        "gemini",
        "groq",
        "openai",
        "openai_compatible",
    )

    def __init__(
        self,
        config: bajrang_core.ConfigManager,
        native_model: Optional[SudharshanNativeNumPyModel] = None,
        native_tokenizer: Optional[SudharshanBPETokenizer] = None,
    ) -> None:
        self.config = config
        self.unified_client = bajrang_core.UnifiedModelClient(config)
        self.native_model = native_model
        self.native_tokenizer = native_tokenizer
        self.active_provider = "ollama"
        self.active_model_name = str(config.settings.get("model", "qwen3.5:4b"))
        self.custom_endpoint = ""
        self.token_accounting: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0}
        self.latency_history_ms: List[float] = []

    def switch_provider(self, provider: str, model_name: Optional[str] = None, endpoint: str = "") -> Dict[str, Any]:
        if provider not in self.SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported provider '{provider}'. Supported: {self.SUPPORTED_PROVIDERS}")
        self.active_provider = provider
        if model_name:
            self.active_model_name = model_name
        if endpoint:
            self.custom_endpoint = endpoint.rstrip("/")
        return {
            "provider": self.active_provider,
            "model": self.active_model_name,
            "endpoint": self.custom_endpoint,
        }

    def discover_capabilities(self) -> Dict[str, Dict[str, Any]]:
        ollama_ok, ollama_models, _ = self.unified_client.check_health()
        online = bajrang_core.NetworkConnectivityDetector.is_online(timeout_sec=0.3)
        return {
            "sudharshan_native": {
                "available": self.native_model is not None and self.native_tokenizer is not None,
                "local": True,
                "streaming": True,
                "tools": True,
            },
            "ollama": {
                "available": ollama_ok,
                "local": True,
                "streaming": True,
                "tools": True,
                "models": ollama_models,
            },
            "gemini": {"available": online and bool(self.config.get_api_key("gemini_argon")), "local": False, "streaming": True},
            "groq": {"available": online and bool(self.config.get_api_key("groq")), "local": False, "streaming": True},
            "openai": {"available": online and bool(self.config.get_api_key("openai")), "local": False, "streaming": True},
            "openai_compatible": {"available": bool(self.custom_endpoint), "local": "127.0.0.1" in self.custom_endpoint, "streaming": True},
        }

    def generate(
        self,
        prompt: str,
        on_token: Optional[Callable[[str], None]] = None,
        max_new_tokens: int = 24,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        if self.active_provider == "sudharshan_native":
            if self.native_model is None or self.native_tokenizer is None:
                return {"ok": False, "provider": "sudharshan_native", "error": "Native model/tokenizer not loaded"}
            p_ids = self.native_tokenizer.encode(prompt, add_bos=True)
            gen_ids: List[int] = []

            def _emit(tid: int) -> None:
                gen_ids.append(tid)
                if on_token:
                    on_token(self.native_tokenizer.decode([tid], skip_special_tokens=True))

            out_ids = self.native_model.generate(
                p_ids,
                gen_cfg=GenerationConfig(max_new_tokens=max_new_tokens, temperature=0.7),
                on_token=_emit,
            )
            reply = self.native_tokenizer.decode(out_ids[len(p_ids):], skip_special_tokens=True)
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            self.token_accounting["prompt_tokens"] += len(p_ids)
            self.token_accounting["completion_tokens"] += len(gen_ids)
            self.token_accounting["requests"] += 1
            self.latency_history_ms.append(latency_ms)
            return {
                "ok": True,
                "provider": "sudharshan_native",
                "model": self.native_model.config.name,
                "reply": reply,
                "prompt_tokens": len(p_ids),
                "completion_tokens": len(gen_ids),
                "latency_ms": latency_ms,
            }

        # Delegate Ollama & Cloud BYO providers cleanly through existing hardened UnifiedModelClient
        turn, tel = self.unified_client.chat_stream(prompt, on_token=on_token)
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        self.token_accounting["requests"] += 1
        self.token_accounting["completion_tokens"] += int(tel.get("tokens", 0))
        self.latency_history_ms.append(latency_ms)
        return {
            "ok": True,
            "provider": self.active_provider,
            "model": tel.get("model", self.active_model_name),
            "reply": turn.text,
            "latency_ms": latency_ms,
            "telemetry": tel,
        }
