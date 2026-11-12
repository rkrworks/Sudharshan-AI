#!/usr/bin/env python3
import argparse
import ctypes
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

IS_WINDOWS = platform.system().lower() == "windows"

REQUIRED_PIP_PACKAGES: List[Tuple[str, str, str]] = [
    ("pillow", "PIL", "Pillow (Screen Vision Capture)"),
    ("pyautogui", "pyautogui", "PyAutoGUI (Desktop Automation)"),
    ("pyttsx3", "pyttsx3", "pyttsx3 (Offline SAPI5 Voice Synthesis)"),
    ("numpy", "numpy", "NumPy (8-Band Goertzel DSP Audio Math)"),
    ("sounddevice", "sounddevice", "sounddevice (16 kHz Microphone Stream)"),
    ("pystray", "pystray", "pystray (Windows 11 System Tray Integration)"),
]


@dataclass
class ComponentCheck:
    item_id: str
    title: str
    installed: bool
    version_or_detail: str
    action_needed: str
    requires_consent: bool = False


class WindowsSmartEnvironmentScanner:
    def __init__(self, target_dir: Optional[Path] = None, config_dir: Optional[Path] = None):
        if target_dir is not None:
            self.target_dir = target_dir
        elif IS_WINDOWS:
            local_app = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
            self.target_dir = Path(local_app) / "Programs" / "BajrangAIPro"
        else:
            self.target_dir = Path.home() / ".local" / "share" / "bajrang-ai-pro-win-sim"
        self.config_dir = config_dir or (Path.home() / ".bajrang_ai")

    @staticmethod
    def is_admin() -> bool:
        if not IS_WINDOWS:
            return False
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    @staticmethod
    def check_python_runtime() -> ComponentCheck:
        ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ok = (sys.version_info.major, sys.version_info.minor) >= (3, 9)
        return ComponentCheck(
            item_id="python_runtime",
            title="Python 3.9+ Runtime (64-bit)",
            installed=ok,
            version_or_detail=f"Python {ver} ({platform.machine()})",
            action_needed="Ready" if ok else "Manual installation of Python 3.11+ required",
            requires_consent=False,
        )

    @staticmethod
    def check_winget() -> ComponentCheck:
        path = shutil.which("winget")
        return ComponentCheck(
            item_id="winget_cli",
            title="Windows Package Manager (winget)",
            installed=bool(path),
            version_or_detail=path or "Not found in PATH",
            action_needed="Ready" if path else "Optional (used for Ollama installation)",
            requires_consent=False,
        )

    @staticmethod
    def check_ollama_daemon() -> ComponentCheck:
        bin_path = shutil.which("ollama")
        reachable = False
        try:
            req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.2) as resp:
                reachable = resp.status == 200
        except Exception:
            reachable = False
        installed = bool(bin_path) or reachable
        detail = "Daemon reachable on 127.0.0.1:11434" if reachable else (bin_path or "Not installed")
        return ComponentCheck(
            item_id="ollama_daemon",
            title="Ollama Local AI Engine",
            installed=installed,
            version_or_detail=detail,
            action_needed="Ready" if installed else "Optional: Install Ollama via winget (requires consent) or use Cloud API Key",
            requires_consent=True,
        )

    @staticmethod
    def check_llama32_model() -> ComponentCheck:
        has_model = False
        try:
            req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", [])]
                has_model = any("llama3.2" in m or "bajrang-llama32" in m for m in models)
        except Exception:
            has_model = False
        return ComponentCheck(
            item_id="llama32_model",
            title="Llama 3.2 Local Model (~2.0 GB)",
            installed=has_model,
            version_or_detail="Installed in Ollama" if has_model else "Not pulled locally",
            action_needed="Ready" if has_model else "Optional: Pull llama3.2 (~2.0 GB download, requires explicit consent)",
            requires_consent=True,
        )

    @staticmethod
    def check_pip_packages() -> List[ComponentCheck]:
        results: List[ComponentCheck] = []
        for pip_name, import_name, label in REQUIRED_PIP_PACKAGES:
            spec = importlib.util.find_spec(import_name)
            installed = spec is not None
            results.append(
                ComponentCheck(
                    item_id=f"pip:{pip_name}",
                    title=label,
                    installed=installed,
                    version_or_detail=f"Module '{import_name}' present" if installed else f"Missing '{pip_name}'",
                    action_needed="Skip (Already Installed)" if installed else f"pip install {pip_name}",
                    requires_consent=False,
                )
            )
        return results

    def scan_all(self) -> List[ComponentCheck]:
        checks = [
            self.check_python_runtime(),
            self.check_winget(),
            self.check_ollama_daemon(),
            self.check_llama32_model(),
        ]
        checks.extend(self.check_pip_packages())
        return checks

    def install_single_item(
        self,
        item_id: str,
        log_cb: Optional[Callable[[str], None]] = None,
        dry_run: bool = False,
        consent_winget: bool = False,
        consent_model_pull: bool = False,
    ) -> Tuple[bool, str]:
        def emit(msg: str) -> None:
            if log_cb:
                log_cb(msg)

        if item_id.startswith("pip:"):
            pkg = item_id.split(":", 1)[1].strip()
            allowed_pkgs = {p[0] for p in REQUIRED_PIP_PACKAGES}
            if pkg not in allowed_pkgs:
                return False, f"Rejected unlisted pip package: {pkg}"
            emit(f"Installing missing Python library '{pkg}'...")
            if dry_run:
                return True, f"[Dry-Run] Would run: {sys.executable} -m pip install --upgrade {pkg}"
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--upgrade", pkg],
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                if proc.returncode == 0:
                    return True, f"Installed {pkg} successfully."
                return False, f"pip install {pkg} failed: {proc.stderr.strip()[:200]}"
            except Exception as exc:
                return False, f"Exception installing {pkg}: {exc}"

        if item_id == "ollama_daemon":
            if not consent_winget:
                return False, "Skipped Ollama install: explicit user consent required for winget (consent_winget=False)."
            if not shutil.which("winget") and not dry_run:
                return False, "winget is not available; Ollama skipped (you can still use Free BYO Cloud API keys)."
            emit("Installing Ollama via winget (with user consent)...")
            if dry_run:
                return True, "[Dry-Run] Would run: winget install -e --id Ollama.Ollama"
            try:
                proc = subprocess.run(
                    [
                        "winget",
                        "install",
                        "-e",
                        "--id",
                        "Ollama.Ollama",
                        "--accept-package-agreements",
                        "--accept-source-agreements",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                return (proc.returncode == 0, "Ollama installed via winget." if proc.returncode == 0 else proc.stderr[:200])
            except Exception as exc:
                return False, f"Ollama winget install skipped: {exc}"

        if item_id == "llama32_model":
            if not consent_model_pull:
                return False, "Skipped Llama 3.2 pull: explicit user consent required for ~2.0 GB download (consent_model_pull=False)."
            if not shutil.which("ollama") and not dry_run:
                return False, "Ollama binary not in PATH; skipping local model pull."
            emit("Pulling llama3.2 via Ollama (with user consent)...")
            if dry_run:
                return True, "[Dry-Run] Would run: ollama pull llama3.2"
            try:
                proc = subprocess.run(["ollama", "pull", "llama3.2"], capture_output=True, text=True, timeout=600)
                return (proc.returncode == 0, "Pulled llama3.2." if proc.returncode == 0 else proc.stderr[:200])
            except Exception as exc:
                return False, f"Model pull skipped: {exc}"

        if item_id in ("python_runtime", "winget_cli"):
            return False, f"Component '{item_id}' cannot be auto-installed by this wizard; please install it manually."

        return False, f"Unsupported or unrecognized installation item: {item_id}"

    def deploy_application_files(self, source_dir: Optional[Path] = None) -> Tuple[bool, str]:
        src = source_dir or Path(__file__).resolve().parent
        try:
            self.target_dir.mkdir(parents=True, exist_ok=True)
            copied = []
            for fname in (
                "bajrang_core.py",
                "windows.py",
                "fedora.py",
                "bajrang_windows.py",
                "bajrang_llama32.py",
                "requirements_common.txt",
                "requirements_windows.txt",
                "README.md",
                "SECURITY.md",
            ):
                candidate = src / fname
                if candidate.exists():
                    shutil.copy2(candidate, self.target_dir / fname)
                    copied.append(fname)
            launcher_bat = self.target_dir / "Launch_Bajrang_AI_Pro.bat"
            launcher_bat.write_text(
                '@echo off\r\ncd /d "%~dp0"\r\nstart "" pythonw "%~dp0windows.py"\r\n',
                encoding="utf-8",
            )
            return True, f"Deployed {len(copied)} files to {self.target_dir}"
        except Exception as exc:
            return False, f"Failed to deploy files: {exc}"

    def clean_uninstall(self, purge_user_data: bool = True) -> Tuple[bool, str]:
        removed = []
        try:
            try:
                from bajrang_core import SecurityVault

                vault = SecurityVault(self.config_dir)
                for prov in ("default", "gemini", "groq", "openrouter", "openai"):
                    vault.delete_api_key(prov)
                removed.append("SecurityVault credentials")
            except Exception:
                pass

            if self.target_dir.exists():
                shutil.rmtree(self.target_dir, ignore_errors=True)
                removed.append(str(self.target_dir))

            if purge_user_data and self.config_dir.exists():
                shutil.rmtree(self.config_dir, ignore_errors=True)
                removed.append(str(self.config_dir))

            if IS_WINDOWS and purge_user_data:
                local_app = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "BajrangAI"
                if local_app.exists():
                    shutil.rmtree(local_app, ignore_errors=True)
                    removed.append(str(local_app))

            return True, f"Uninstalled cleanly: {', '.join(removed) if removed else 'Nothing to remove'}"
        except Exception as exc:
            return False, f"Uninstall error: {exc}"


def run_self_test() -> int:
    print("Running Windows Smart Pre-Flight Installer self-tests (H6)...")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        scanner = WindowsSmartEnvironmentScanner(
            target_dir=tmp_path / "app_target",
            config_dir=tmp_path / "user_config",
        )
        checks = scanner.scan_all()
        assert len(checks) >= 8, "Expected at least 8 pre-flight component checks"

        ok_py, msg_py = scanner.install_single_item("python_runtime", dry_run=True)
        assert ok_py is False, f"H6 regression: python_runtime must return False, got {ok_py} ({msg_py})"

        ok_unk, msg_unk = scanner.install_single_item("unknown_component", dry_run=True)
        assert ok_unk is False, "H6 regression: unknown component must return False"

        ok_winget_no_consent, _ = scanner.install_single_item(
            "ollama_daemon", dry_run=True, consent_winget=False
        )
        assert ok_winget_no_consent is False, "H6 regression: ollama_daemon without consent must return False"

        ok_winget_consent, _ = scanner.install_single_item(
            "ollama_daemon", dry_run=True, consent_winget=True
        )
        assert ok_winget_consent is True, "ollama_daemon with consent in dry_run should succeed"

        ok_model_no_consent, _ = scanner.install_single_item(
            "llama32_model", dry_run=True, consent_model_pull=False
        )
        assert ok_model_no_consent is False, "H6 regression: llama32_model without consent must return False"

        ok_pip, _ = scanner.install_single_item("pip:numpy", dry_run=True)
        assert ok_pip is True

        ok_bad_pip, _ = scanner.install_single_item("pip:malicious_pkg", dry_run=True)
        assert ok_bad_pip is False

        (tmp_path / "user_config").mkdir(parents=True, exist_ok=True)
        (tmp_path / "user_config" / "settings.json").write_text('{"provider":"gemini"}', encoding="utf-8")
        (tmp_path / "user_config" / "vault_gemini.dpapi").write_bytes(b"secret")

        ok_dep, _ = scanner.deploy_application_files()
        assert ok_dep is True
        assert (tmp_path / "app_target" / "Launch_Bajrang_AI_Pro.bat").exists()

        ok_un, _ = scanner.clean_uninstall(purge_user_data=True)
        assert ok_un is True
        assert not (tmp_path / "app_target").exists(), "Target dir must be removed"
        assert not (tmp_path / "user_config").exists(), "H6 regression: user config & secrets must be purged on uninstall"

    print("All Windows Smart Pre-Flight Installer self-tests (H6) passed!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bajrang AI Pro — Smart Windows 11 Installer")
    parser.add_argument("--self-test", action="store_true", help="Run installer self-tests")
    parser.add_argument("--scan-only", action="store_true", help="Print JSON scan report and exit")
    parser.add_argument("--headless-install", action="store_true", help="Install missing pip dependencies headlessly")
    parser.add_argument("--consent-winget", action="store_true", help="Explicitly consent to winget Ollama install")
    parser.add_argument("--consent-model-pull", action="store_true", help="Explicitly consent to ~2 GB Llama 3.2 pull")
    parser.add_argument("--uninstall", action="store_true", help="Uninstall Bajrang AI Pro and purge stored secrets")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    scanner = WindowsSmartEnvironmentScanner()
    if args.uninstall:
        ok, msg = scanner.clean_uninstall(purge_user_data=True)
        print(msg)
        return 0 if ok else 1

    if args.scan_only:
        report = [c.__dict__ for c in scanner.scan_all()]
        print(json.dumps(report, indent=2))
        return 0

    if args.headless_install:
        for c in scanner.scan_all():
            if not c.installed:
                if c.item_id.startswith("pip:") or (
                    c.item_id == "ollama_daemon" and args.consent_winget
                ) or (c.item_id == "llama32_model" and args.consent_model_pull):
                    ok, msg = scanner.install_single_item(
                        c.item_id,
                        consent_winget=args.consent_winget,
                        consent_model_pull=args.consent_model_pull,
                    )
                    print(f"[{c.item_id}] ok={ok}: {msg}")
        ok, msg = scanner.deploy_application_files()
        print(msg)
        return 0 if ok else 1

    report = [c.__dict__ for c in scanner.scan_all()]
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())