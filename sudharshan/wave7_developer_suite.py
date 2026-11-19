import ast
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class LocalGitAssistant:
    @staticmethod
    def generate_conventional_commit(diff_text: str) -> str:
        low = (diff_text or "").lower()
        prefix = "feat"
        if any(k in low for k in ("fix", "bug", "error", "patch")):
            prefix = "fix"
        elif any(k in low for k in ("refactor", "rename", "cleanup")):
            prefix = "refactor"
        elif any(k in low for k in ("test_", "assert")):
            prefix = "test"
        files = re.findall(r"\+\+\+ b/([^\s]+)", diff_text or "")
        scope = Path(files[0]).stem if files else "core"
        return f"{prefix}({scope}): update {len(files) or 1} file(s) with verified changes"

    @staticmethod
    def parse_conflicts(text: str) -> List[Dict[str, str]]:
        blocks = re.findall(r"<<<<<<<[^\n]*\n(.*?)=======\n(.*?)>>>>>>>[^\n]*", text or "", re.DOTALL)
        return [{"ours": a.strip(), "theirs": b.strip()} for a, b in blocks]


class TerminalErrorExplainer:
    RULES: List[Tuple[str, str, str]] = [
        (r"ModuleNotFoundError: No module named '([^']+)'", "Missing Python package", "Install the dependency inside your active virtualenv."),
        (r"PermissionError|Permission denied", "Insufficient filesystem permissions", "Check file ownership or avoid writing to protected system paths."),
        (r"Address already in use|EADDRINUSE", "TCP port already bound", "Inspect the listening process with LocalPortRadar before restarting."),
        (r"command not found", "Executable missing from PATH", "Verify toolchain installation and PATH via EnvironmentPathDoctor."),
    ]

    @classmethod
    def explain(cls, command: str, stderr: str) -> Dict[str, str]:
        for pat, cause, fix in cls.RULES:
            m = re.search(pat, stderr or "", re.I)
            if m:
                return {"command": command, "root_cause": cause, "detail": m.group(0), "proposed_fix": fix}
        return {"command": command, "root_cause": "General command failure", "detail": (stderr or "")[:200], "proposed_fix": "Inspect stderr output and run with verbose flags."}


class ASTCodebaseIndexer:
    REGEX_LANGS: Dict[str, str] = {
        ".js": r"(?:function|class)\s+([A-Za-z_][A-Za-z0-9_]*)",
        ".ts": r"(?:function|class|interface|type)\s+([A-Za-z_][A-Za-z0-9_]*)",
        ".rs": r"(?:fn|struct|enum|trait)\s+([A-Za-z_][A-Za-z0-9_]*)",
        ".go": r"(?:func|type)\s+(?:\([^)]+\)\s+)?([A-Za-z_][A-Za-z0-9_]*)",
        ".c": r"(?:struct|enum)\s+([A-Za-z_][A-Za-z0-9_]*)",
    }

    @classmethod
    def index_directory(cls, root: Path) -> List[Dict[str, Any]]:
        symbols: List[Dict[str, Any]] = []
        for p in sorted(Path(root).rglob("*")):
            if not p.is_file():
                continue
            ext = p.suffix.lower()
            if ext == ".py":
                try:
                    tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            symbols.append({"name": node.name, "kind": type(node).__name__, "file": str(p), "line": node.lineno})
                except SyntaxError:
                    pass
            elif ext in cls.REGEX_LANGS:
                txt = p.read_text(encoding="utf-8", errors="ignore")
                for i, ln in enumerate(txt.splitlines(), 1):
                    m = re.search(cls.REGEX_LANGS[ext], ln)
                    if m:
                        symbols.append({"name": m.group(1), "kind": ext.lstrip("."), "file": str(p), "line": i})
        return symbols


class ContainerInspector:
    @staticmethod
    def validate_compose_text(yaml_text: str) -> Tuple[bool, List[str]]:
        issues: List[str] = []
        if "services:" not in (yaml_text or ""):
            issues.append("Missing top-level 'services:' section")
        if re.search(r"privileged:\s*true", yaml_text or "", re.I):
            issues.append("Security warning: privileged: true container detected")
        if re.search(r"/var/run/docker\.sock", yaml_text or ""):
            issues.append("Security warning: Docker socket mount exposes host root")
        return len(issues) == 0, issues

    @staticmethod
    def detect_runtime() -> Optional[str]:
        for rt in ("podman", "docker"):
            if shutil.which(rt):
                return rt
        return None


class OfflineAPITesterAndConverter:
    @staticmethod
    def parse_curl(curl_cmd: str) -> Dict[str, Any]:
        tokens = shlex.split(curl_cmd)
        method = "GET"
        url = ""
        headers: Dict[str, str] = {}
        body = ""
        i = 0
        while i < len(tokens):
            t = tokens[i]
            if t in ("-X", "--request") and i + 1 < len(tokens):
                method = tokens[i + 1].upper()
                i += 2
            elif t in ("-H", "--header") and i + 1 < len(tokens):
                k, _, v = tokens[i + 1].partition(":")
                headers[k.strip()] = v.strip()
                i += 2
            elif t in ("-d", "--data", "--data-raw") and i + 1 < len(tokens):
                body = tokens[i + 1]
                if method == "GET":
                    method = "POST"
                i += 2
            elif t.startswith(("http://", "https://")):
                url = t
                i += 1
            else:
                i += 1
        return {"method": method, "url": url, "headers": headers, "body": body}

    @staticmethod
    def json_to_yaml(obj: Any, indent: int = 0) -> str:
        pad = "  " * indent
        if isinstance(obj, dict):
            lines = []
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    lines.append(f"{pad}{k}:\n{OfflineAPITesterAndConverter.json_to_yaml(v, indent + 1)}")
                else:
                    lines.append(f"{pad}{k}: {json.dumps(v)}")
            return "\n".join(lines)
        if isinstance(obj, list):
            return "\n".join(f"{pad}- {json.dumps(x)}" for x in obj)
        return f"{pad}{json.dumps(obj)}"


class RegexWorkbench:
    @staticmethod
    def test_pattern(pattern: str, sample_text: str) -> Dict[str, Any]:
        compiled = re.compile(pattern)
        matches = [
            {"match": m.group(0), "span": m.span(), "groups": list(m.groups())}
            for m in compiled.finditer(sample_text or "")
        ]
        explanations = []
        if r"\d" in pattern:
            explanations.append("Matches digits (0-9)")
        if r"\w" in pattern:
            explanations.append("Matches word characters")
        if "^" in pattern:
            explanations.append("Anchored at start")
        if "$" in pattern:
            explanations.append("Anchored at end")
        return {"pattern": pattern, "match_count": len(matches), "matches": matches, "notes": explanations}


class UnitTestGenerator:
    @staticmethod
    def generate_for_python_file(file_path: Path) -> str:
        fp = Path(file_path)
        tree = ast.parse(fp.read_text(encoding="utf-8"))
        funcs = [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]
        lines = [
            "import unittest",
            f"import {fp.stem}",
            "",
            f"class Test{fp.stem.title().replace('_', '')}(unittest.TestCase):",
        ]
        if not funcs:
            lines.append("    def test_module_loads(self):")
            lines.append(f"        self.assertIsNotNone({fp.stem})")
        else:
            for fn in funcs:
                lines.append(f"    def test_{fn}_callable(self):")
                lines.append(f"        self.assertTrue(callable({fp.stem}.{fn}))")
        lines.append("")
        lines.append('if __name__ == "__main__":')
        lines.append("    unittest.main()")
        return "\n".join(lines) + "\n"


class LocalPortRadar:
    @staticmethod
    def listening_ports() -> List[Dict[str, Any]]:
        ports: List[Dict[str, Any]] = []
        tcp_file = Path("/proc/net/tcp")
        if tcp_file.is_file():
            for ln in tcp_file.read_text(encoding="utf-8", errors="ignore").splitlines()[1:]:
                parts = ln.split()
                if len(parts) >= 4 and parts[3] == "0A":
                    local_hex = parts[1]
                    ip_hex, port_hex = local_hex.split(":")
                    port = int(port_hex, 16)
                    ports.append({"port": port, "state": "LISTEN", "source": "/proc/net/tcp"})
        return ports


class CLIFlagTranslator:
    TEMPLATES: List[Tuple[str, str, List[str]]] = [
        ("disk usage", "du -sh *", ["-s: summarize each argument", "-h: human-readable sizes"]),
        ("find large files", "find . -type f -size +100M", ["-type f: regular files only", "-size +100M: larger than 100 MiB"]),
        ("compress folder", "tar -czvf archive.tar.gz folder/", ["-c: create", "-z: gzip", "-v: verbose", "-f: archive filename"]),
        ("listening ports", "ss -tulnp", ["-t: TCP", "-u: UDP", "-l: listening", "-n: numeric", "-p: process"]),
    ]

    @classmethod
    def translate(cls, request: str) -> Dict[str, Any]:
        low = (request or "").lower()
        for key, cmd, flags in cls.TEMPLATES:
            if all(w in low for w in key.split()):
                return {"command": cmd, "flags": flags, "matched": key}
        return {"command": "man <command>", "flags": ["Provide a specific CLI intent such as 'disk usage' or 'find large files'"], "matched": "fallback"}


class EnvironmentPathDoctor:
    @staticmethod
    def diagnose() -> Dict[str, Any]:
        tools = ("python3", "git", "node", "npm", "gcc", "ollama")
        found = {t: shutil.which(t) for t in tools}
        path_entries = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
        missing_dirs = [p for p in path_entries if not Path(p).exists()]
        return {
            "toolchains": found,
            "venv_active": bool(os.environ.get("VIRTUAL_ENV")),
            "path_entries": len(path_entries),
            "missing_path_dirs": missing_dirs,
        }
