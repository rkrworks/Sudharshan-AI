import json
import re
import sqlite3
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import bajrang_core


class RAMModelSwitcher:
    def __init__(
        self,
        primary_model: str = "qwen3.5:4b",
        low_ram_model: str = "qwen3.5:2b-q4_K_M",
        threshold_gb: float = 2.5,
        hysteresis_gb: float = 0.3,
        ram_probe: Optional[Callable[[], float]] = None,
    ) -> None:
        self.primary_model = primary_model
        self.low_ram_model = low_ram_model
        self.threshold_gb = threshold_gb
        self.hysteresis_gb = hysteresis_gb
        self._ram_probe = ram_probe or bajrang_core.HardwareProfiler.get_free_ram_gb
        self.current_model = primary_model
        self.downgraded = False
        self.switch_history: List[Dict[str, Any]] = []

    def evaluate(self) -> Dict[str, Any]:
        free_gb = float(self._ram_probe())
        prev = self.current_model
        if not self.downgraded and free_gb < self.threshold_gb:
            self.current_model = self.low_ram_model
            self.downgraded = True
        elif self.downgraded and free_gb >= (self.threshold_gb + self.hysteresis_gb):
            self.current_model = self.primary_model
            self.downgraded = False
        switched = prev != self.current_model
        if switched:
            self.switch_history.append({
                "timestamp": time.time(),
                "from": prev,
                "to": self.current_model,
                "free_ram_gb": round(free_gb, 2),
            })
        return {
            "model": self.current_model,
            "free_ram_gb": round(free_gb, 2),
            "downgraded": self.downgraded,
            "switched": switched,
        }


class StreamingTokenRenderer:
    def __init__(self, on_chunk: Optional[Callable[[str, Dict[str, Any]], None]] = None) -> None:
        self.on_chunk = on_chunk
        self.reset()

    def reset(self) -> None:
        self._start = time.perf_counter()
        self._ttft_ms: Optional[float] = None
        self._tokens: List[str] = []

    def push_token(self, token: str) -> Dict[str, Any]:
        now = time.perf_counter()
        if self._ttft_ms is None and token:
            self._ttft_ms = (now - self._start) * 1000.0
        self._tokens.append(token)
        elapsed = max(0.001, now - self._start)
        telemetry = {
            "tokens": len(self._tokens),
            "ttft_ms": round(self._ttft_ms or 0.0, 2),
            "tokens_per_sec": round(len(self._tokens) / elapsed, 2),
            "free_ram_gb": bajrang_core.HardwareProfiler.get_free_ram_gb(),
        }
        if self.on_chunk:
            self.on_chunk(token, telemetry)
        return telemetry

    @property
    def full_text(self) -> str:
        return "".join(self._tokens)


class HybridIntentRouter:
    RULE_PATTERNS: List[Tuple[str, str, bajrang_core.TaskComplexity]] = [
        ("ocr", r"\b(ocr|extract text|read table|scan image)\b", bajrang_core.TaskComplexity.OCR),
        ("vision", r"\b(screenshot|on my screen|what is on screen|visible window)\b", bajrang_core.TaskComplexity.MULTIMODAL_VISION),
        ("system_action", r"\b(open|launch|close|focus|tile|brightness|volume|wifi|bluetooth|mute)\b", bajrang_core.TaskComplexity.SIMPLE),
        ("file_ops", r"\b(organize|rename|deduplicate|archive|extract|compress|quarantine|sync)\b", bajrang_core.TaskComplexity.MODERATE),
        ("reasoning", r"\b(architect|prove|optimize|debug|refactor|compare|analyze|plan)\b", bajrang_core.TaskComplexity.COMPLEX_REASONING),
    ]

    def __init__(self, router_model: str = "qwen3.5:0.8b") -> None:
        self.router_model = router_model

    def classify(self, prompt: str, free_ram_gb: Optional[float] = None) -> Dict[str, Any]:
        text = (prompt or "").strip().lower()
        for intent, pattern, complexity in self.RULE_PATTERNS:
            if re.search(pattern, text):
                decision = bajrang_core.AdaptiveModelEngine.select_local_model(
                    complexity=complexity,
                    free_ram_gb=free_ram_gb,
                )
                return {
                    "intent": intent,
                    "source": "rule_fastpath",
                    "complexity": complexity.value,
                    "selected_model": decision["model"],
                    "downgraded": decision["downgraded"],
                }
        complexity = bajrang_core.TaskComplexity.SIMPLE if len(text) < 48 else bajrang_core.TaskComplexity.MODERATE
        decision = bajrang_core.AdaptiveModelEngine.select_local_model(
            complexity=complexity,
            free_ram_gb=free_ram_gb,
        )
        return {
            "intent": "general_chat",
            "source": f"router:{self.router_model}",
            "complexity": complexity.value,
            "selected_model": decision["model"],
            "downgraded": decision["downgraded"],
        }


class StrictJSONToolCaller:
    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries

    @staticmethod
    def validate_payload(raw: str, required_keys: List[str]) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        cleaned = (raw or "").strip()
        m = re.match(r"^```(?:json)?\s*(\{.*?\})\s*```$", cleaned, re.DOTALL)
        if m:
            cleaned = m.group(1).strip()
        try:
            obj = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            return False, None, f"Invalid JSON: {exc}"
        if not isinstance(obj, dict):
            return False, None, "JSON root must be an object"
        missing = [k for k in required_keys if k not in obj]
        if missing:
            return False, None, f"Missing required keys: {missing}"
        if "actions" in obj and isinstance(obj["actions"], list):
            for act in obj["actions"]:
                ok, err = bajrang_core.ToolSchemaValidator.validate_action(act)
                if not ok:
                    return False, None, f"Tool schema error: {err}"
        return True, obj, "ok"

    def call_with_retry(
        self,
        generator_fn: Callable[[str], str],
        prompt: str,
        required_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        req_keys = required_keys or ["type", "text"]
        feedback = prompt
        last_err = ""
        for attempt in range(1, self.max_retries + 1):
            raw = generator_fn(feedback)
            ok, parsed, err = self.validate_payload(raw, req_keys)
            if ok and parsed is not None:
                return {"success": True, "attempts": attempt, "data": parsed, "error": ""}
            last_err = err
            feedback = f"{prompt}\n\n[CORRECTION REQUIRED] Previous output failed schema validation ({err}). Return ONLY valid JSON with keys {req_keys}."
        return {"success": False, "attempts": self.max_retries, "data": None, "error": last_err}


@dataclass
class PlanNode:
    step_id: str
    title: str
    action: Callable[[], Any]
    status: str = "pending"
    result: Any = None
    error: str = ""


class AutonomousStepPlanner:
    def __init__(self) -> None:
        self.nodes: List[PlanNode] = []
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._cancelled = False

    def add_step(self, step_id: str, title: str, action: Callable[[], Any]) -> None:
        self.nodes.append(PlanNode(step_id=step_id, title=title, action=action))

    def pause(self) -> None:
        self._pause_event.clear()

    def resume(self) -> None:
        self._pause_event.set()

    def cancel(self) -> None:
        self._cancelled = True
        self._pause_event.set()

    def execute(self) -> Dict[str, Any]:
        for node in self.nodes:
            self._pause_event.wait(timeout=5.0)
            if self._cancelled:
                node.status = "cancelled"
                continue
            node.status = "running"
            try:
                node.result = node.action()
                node.status = "completed"
            except Exception as exc:
                node.status = "failed"
                node.error = str(exc)
                break
        return {
            "cancelled": self._cancelled,
            "steps": [
                {"id": n.step_id, "title": n.title, "status": n.status, "error": n.error}
                for n in self.nodes
            ],
        }


class ContextWindowManager:
    def __init__(self, max_tokens: int = 4096, keep_recent: int = 6) -> None:
        self.max_tokens = max_tokens
        self.keep_recent = keep_recent
        self.rolling_summary: str = ""

    @staticmethod
    def estimate_tokens(messages: List[Dict[str, str]]) -> int:
        return sum(max(1, len(str(m.get("content", ""))) // 4) for m in messages)

    def compact(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        if self.estimate_tokens(messages) <= self.max_tokens or len(messages) <= self.keep_recent:
            return list(messages)
        older = messages[:-self.keep_recent]
        recent = messages[-self.keep_recent:]
        snippets = []
        for m in older:
            role = m.get("role", "user")
            content = str(m.get("content", "")).strip().replace("\n", " ")
            if content:
                snippets.append(f"{role}: {content[:90]}")
        merged = "; ".join(snippets[-12:])
        self.rolling_summary = f"{self.rolling_summary} | {merged}".strip(" |")[-1200:]
        return [{"role": "system", "content": f"Rolling conversation summary: {self.rolling_summary}"}] + list(recent)


class PromptTemplateLibrary:
    DEFAULT_TEMPLATES: Dict[str, Dict[str, Any]] = {
        "/review": {
            "name": "Code Review",
            "variables": ["language", "code"],
            "template": "Review this {{language}} snippet for security bugs, edge cases, and complexity:\n\n{{code}}",
        },
        "/summarize": {
            "name": "Executive Summary",
            "variables": ["topic", "text"],
            "template": "Produce a 3-bullet executive summary on {{topic}}:\n\n{{text}}",
        },
        "/commit": {
            "name": "Conventional Commit",
            "variables": ["diff"],
            "template": "Write a Conventional Commit message (feat/fix/refactor) for:\n\n{{diff}}",
        },
    }

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self.storage_path = storage_path
        self.templates: Dict[str, Dict[str, Any]] = dict(self.DEFAULT_TEMPLATES)
        if storage_path and storage_path.is_file():
            self.templates.update(json.loads(storage_path.read_text(encoding="utf-8")))

    def register(self, trigger: str, name: str, template: str) -> None:
        key = trigger if trigger.startswith("/") else f"/{trigger}"
        vars_found = sorted(set(re.findall(r"\{\{([a-zA-Z0-9_]+)\}\}", template)))
        self.templates[key] = {"name": name, "variables": vars_found, "template": template}
        if self.storage_path:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self.storage_path.write_text(json.dumps(self.templates, indent=2), encoding="utf-8")

    def render(self, trigger: str, values: Dict[str, str]) -> str:
        key = trigger if trigger.startswith("/") else f"/{trigger}"
        if key not in self.templates:
            raise KeyError(f"Unknown template trigger: {key}")
        out = str(self.templates[key]["template"])
        for var in self.templates[key]["variables"]:
            if var not in values:
                raise ValueError(f"Missing template variable: {var}")
            out = out.replace(f"{{{{{var}}}}}", str(values[var]))
        return out


class ModelBenchmarkRunner:
    def __init__(self, ollama_host: str = "http://127.0.0.1:11434") -> None:
        self.ollama_host = ollama_host.rstrip("/")

    def benchmark_models(
        self,
        models: List[str],
        inference_fn: Optional[Callable[[str, str], str]] = None,
    ) -> List[Dict[str, Any]]:
        probe_prompt = 'Return JSON: {"type":"conversation","text":"ok"}'
        results: List[Dict[str, Any]] = []
        for model in models:
            ram_before = bajrang_core.HardwareProfiler.get_free_ram_gb()
            t0 = time.perf_counter()
            raw = ""
            if inference_fn is not None:
                raw = inference_fn(model, probe_prompt)
            else:
                req = urllib.request.Request(
                    f"{self.ollama_host}/api/chat",
                    data=json.dumps({"model": model, "messages": [{"role": "user", "content": probe_prompt}], "stream": False}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=15.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    raw = data.get("message", {}).get("content", "")
            elapsed = max(0.001, time.perf_counter() - t0)
            ram_after = bajrang_core.HardwareProfiler.get_free_ram_gb()
            ok, _, _ = StrictJSONToolCaller.validate_payload(raw, ["type", "text"])
            tokens = max(1, len(raw.split()))
            results.append({
                "model": model,
                "latency_ms": round(elapsed * 1000.0, 2),
                "tokens_per_sec": round(tokens / elapsed, 2),
                "ram_delta_gb": round(ram_before - ram_after, 3),
                "tool_json_valid": ok,
            })
        return results


class CloudBurstController:
    def __init__(self, enabled: bool = False) -> None:
        self.cloud_burst_enabled = enabled
        self.blocked_attempts = 0
        self.allowed_requests = 0

    def set_enabled(self, enabled: bool) -> None:
        self.cloud_burst_enabled = bool(enabled)

    def authorize_request(self, provider: str) -> Tuple[bool, str]:
        if provider == "ollama":
            return True, "Local inference always permitted"
        if not self.cloud_burst_enabled:
            self.blocked_attempts += 1
            return False, f"Offline-first mode active: Cloud Burst disabled for provider '{provider}'."
        self.allowed_requests += 1
        return True, f"Cloud Burst explicitly enabled for '{provider}'."


class PersonaManager:
    PERSONAS: Dict[str, str] = {
        "Coder": "You are a Principal Software Engineer. Provide concise, production-ready, zero-stub code with strict error handling.",
        "SysAdmin": "You are a Linux & Windows Systems Administrator. Prioritize fail-closed safety, dry-run checks, and minimal privilege.",
        "Study Tutor": "You are a patient Engineering Tutor. Explain concepts step-by-step with clear analogies and practice checks.",
        "Writer": "You are a crisp Technical Writer. Use active voice, clear structure, and zero fluff.",
        "Minimalist": "Respond in the fewest accurate words possible. Bullet points only when strictly needed.",
    }

    def __init__(self) -> None:
        self._session_personas: Dict[str, str] = {}

    def set_persona(self, session_id: str, persona_name: str) -> str:
        if persona_name not in self.PERSONAS:
            raise ValueError(f"Unknown persona '{persona_name}'. Choose from: {list(self.PERSONAS)}")
        self._session_personas[session_id] = persona_name
        return self.PERSONAS[persona_name]

    def get_system_prompt(self, session_id: str) -> str:
        name = self._session_personas.get(session_id, "Coder")
        return self.PERSONAS[name]
