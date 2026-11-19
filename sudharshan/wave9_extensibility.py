import ast
import http.server
import json
import re
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


class MCPClient:
    def __init__(self, transport: str = "stdio") -> None:
        if transport not in ("stdio", "sse"):
            raise ValueError("MCP transport must be 'stdio' or 'sse'")
        self.transport = transport
        self._req_id = 0

    def build_rpc_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._req_id += 1
        return {"jsonrpc": "2.0", "id": self._req_id, "method": method, "params": params or {}}

    def invoke_stdio_handler(self, handler: Callable[[Dict[str, Any]], Dict[str, Any]], method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        req = self.build_rpc_request(method, params)
        resp = handler(req)
        if resp.get("jsonrpc") != "2.0" or resp.get("id") != req["id"]:
            raise ValueError("Invalid MCP JSON-RPC 2.0 response")
        return resp


class SandboxedPluginSDK:
    ALLOWED_CAPABILITIES = {"read_files", "write_workspace", "clipboard", "local_model", "notifications"}

    @classmethod
    def validate_manifest(cls, manifest: Dict[str, Any]) -> Tuple[bool, str]:
        for key in ("name", "version", "entrypoint", "capabilities"):
            if key not in manifest:
                return False, f"Missing manifest field: {key}"
        caps = set(manifest.get("capabilities", []))
        unknown = caps - cls.ALLOWED_CAPABILITIES
        if unknown:
            return False, f"Unauthorized plugin capabilities: {sorted(unknown)}"
        return True, "Manifest valid"


class VisualPipelineEngine:
    def __init__(self) -> None:
        self._registry: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}

    def register_step(self, step_type: str, fn: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        self._registry[step_type] = fn

    def run_pipeline(self, steps: List[Dict[str, Any]], initial_ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = dict(initial_ctx)
        trace = []
        for s in steps:
            stype = s["type"]
            if stype not in self._registry:
                raise KeyError(f"Unregistered pipeline step type: {stype}")
            out = self._registry[stype]({**ctx, **s.get("params", {})})
            ctx.update(out)
            trace.append({"step": s.get("name", stype), "type": stype, "ok": True})
        return {"context": ctx, "trace": trace}


class PluginSecurityScanner:
    FORBIDDEN_CALLS = {"eval", "exec", "__import__", "compile"}
    FORBIDDEN_ATTRS = {("os", "system"), ("os", "popen"), ("subprocess", "Popen"), ("subprocess", "run")}

    @classmethod
    def scan_python_source(cls, source: str) -> Tuple[bool, List[str]]:
        findings: List[str] = []
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            return False, [f"SyntaxError: {exc}"]
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in cls.FORBIDDEN_CALLS:
                    findings.append(f"Blocked call: {node.func.id}() at line {node.lineno}")
                elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    pair = (node.func.value.id, node.func.attr)
                    if pair in cls.FORBIDDEN_ATTRS:
                        findings.append(f"Blocked call: {pair[0]}.{pair[1]}() at line {node.lineno}")
        return len(findings) == 0, findings


class LocalAPIServer:
    def __init__(self, port: int = 0) -> None:
        self.bearer_token = secrets.token_urlsafe(24)
        self._server: Optional[http.server.ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.port = port

    def start(self) -> int:
        token = self.bearer_token

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                auth = self.headers.get("Authorization", "")
                if auth != f"Bearer {token}":
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b'{"error":"unauthorized"}')
                    return
                if self.path == "/api/v1/health":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok", "bind": "127.0.0.1"}).encode("utf-8"))
                    return
                self.send_response(404)
                self.end_headers()

            def log_message(self, format, *args):
                pass

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), _Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()


class HotReloadToolRegistry:
    def __init__(self, tools_dir: Path) -> None:
        self.tools_dir = Path(tools_dir)
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        self.tools: Dict[str, Dict[str, Any]] = {}

    def reload(self) -> int:
        loaded: Dict[str, Dict[str, Any]] = {}
        for p in sorted(self.tools_dir.glob("*.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            if "name" in data and "parameters" in data:
                loaded[data["name"]] = data
        self.tools = loaded
        return len(self.tools)


class LocalWebhookMQTTBridge:
    def __init__(self) -> None:
        self._subscriptions: List[Tuple[str, Callable[[str, Dict[str, Any]], Any]]] = []

    def subscribe(self, topic_pattern: str, callback: Callable[[str, Dict[str, Any]], Any]) -> None:
        self._subscriptions.append((topic_pattern, callback))

    @staticmethod
    def _topic_matches(pattern: str, topic: str) -> bool:
        regex = "^" + re.escape(pattern).replace(r"\+", "[^/]+").replace(r"\#", ".*") + "$"
        return bool(re.match(regex, topic))

    def dispatch(self, topic: str, payload: Dict[str, Any]) -> int:
        matched = 0
        for pat, cb in self._subscriptions:
            if self._topic_matches(pat, topic):
                cb(topic, payload)
                matched += 1
        return matched


class PluginProcessSupervisor:
    @staticmethod
    def run_isolated_worker(script_code: str, max_restarts: int = 1, timeout_sec: float = 3.0) -> Dict[str, Any]:
        attempts = 0
        last_rc = -1
        last_out = ""
        while attempts <= max_restarts:
            attempts += 1
            proc = subprocess.run([sys.executable, "-c", script_code], capture_output=True, text=True, timeout=timeout_sec, check=False)
            last_rc = proc.returncode
            last_out = (proc.stdout or proc.stderr).strip()
            if last_rc == 0:
                return {"ok": True, "attempts": attempts, "output": last_out}
        return {"ok": False, "attempts": attempts, "returncode": last_rc, "output": last_out}


class ToolDeveloperSandbox:
    @staticmethod
    def test_tool(tool_fn: Callable[[Dict[str, Any]], Dict[str, Any]], mock_input: Dict[str, Any], expected_keys: List[str]) -> Dict[str, Any]:
        t0 = time.perf_counter()
        out = tool_fn(mock_input)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        missing = [k for k in expected_keys if k not in out]
        return {"passed": len(missing) == 0, "missing_keys": missing, "latency_ms": elapsed_ms, "output": out}
