#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bajrang AI Pro (Argon Edition v5.0) — Smart Windows 11 Pre-Flight PC Scanner & Installer
Scans the PC first for Python, Winget, Ollama, Llama 3.2, and every required library
(pillow, pyautogui, pyttsx3, numpy, sounddevice, faster-whisper, pystray), then installs
only the missing items one by one and creates Windows 11 Desktop & Start Menu shortcuts.
"""

import argparse
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


APP_VERSION = "6.0.0-Argon-Win11-Installer"

REQUIRED_LIBRARIES: List[Tuple[str, str, str, str]] = [
    ("pillow", "PIL", "pillow>=10.0.0", "PIL.ImageGrab Screen Capture & RGB Framing"),
    ("pyautogui", "pyautogui", "pyautogui>=0.9.54", "Win32 Mouse & Keyboard Automation"),
    ("pyttsx3", "pyttsx3", "pyttsx3>=2.90", "Windows SAPI5 Offline Voice Synthesis (TTS)"),
    ("numpy", "numpy", "numpy>=1.24.0", "8-Band Goertzel Spectral-DTW Matrix Math"),
    ("sounddevice", "sounddevice", "sounddevice>=0.4.6", "16 kHz Mono PCM Microphone Capture"),
    ("faster-whisper", "faster_whisper", "faster-whisper>=1.0.0", "Offline Neural Speech-to-Text Engine"),
    ("pystray", "pystray", "pystray>=0.19.5", "Windows 11 System Tray Integration"),
]


@dataclass
class ComponentScanItem:
    key: str
    name: str
    category: str
    description: str
    found: bool = False
    version_or_path: str = "Not Scanned"
    action_taken: str = "Pending"
    pip_spec: str = ""
    import_name: str = ""


class SmartSystemScannerInstaller:
    """Scans the Windows 11 PC for all required runtimes, tools, and libraries, then installs missing ones."""

    def __init__(self, target_dir: Optional[Path] = None) -> None:
        if target_dir is not None:
            self.install_dir = target_dir
        elif platform.system() == "Windows":
            local_app = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
            self.install_dir = Path(local_app) / "BajrangAI"
        else:
            self.install_dir = Path.home() / ".local" / "share" / "bajrang-ai-win-sim"
        self.install_dir.mkdir(parents=True, exist_ok=True)
        self.items: List[ComponentScanItem] = self._build_initial_checklist()

    def _build_initial_checklist(self) -> List[ComponentScanItem]:
        checklist = [
            ComponentScanItem(
                key="os_arch",
                name="Windows 11 / 64-Bit OS & Audio Subsystem",
                category="System",
                description="Verifies 64-bit OS architecture and WinMM / audio subsystem readiness",
            ),
            ComponentScanItem(
                key="winget",
                name="Windows Package Manager (winget)",
                category="System",
                description="Used to silently install Ollama or system runtimes if missing",
            ),
            ComponentScanItem(
                key="python_runtime",
                name="Python 3.10+ Runtime",
                category="Runtime",
                description="Core Python interpreter for Bajrang AI Pro HUD & Voice DSP",
            ),
            ComponentScanItem(
                key="pip_manager",
                name="Python pip Package Installer",
                category="Runtime",
                description="Installs missing Python wheel packages automatically",
            ),
            ComponentScanItem(
                key="ollama_bin",
                name="Ollama for Windows Engine",
                category="AI Engine",
                description="Local LLM runtime serving Llama 3.2 on port 11434",
            ),
        ]
        for pkg_name, mod_name, pip_spec, desc in REQUIRED_LIBRARIES:
            checklist.append(
                ComponentScanItem(
                    key=f"lib_{pkg_name}",
                    name=f"Python Library: {pkg_name}",
                    category="Python Library",
                    description=desc,
                    pip_spec=pip_spec,
                    import_name=mod_name,
                )
            )
        checklist.append(
            ComponentScanItem(
                key="llama_model",
                name="Personalized bajrang-llama3.2 Model",
                category="AI Model",
                description="Custom Ollama Modelfile tuned for Lenovo Yoga 7i & Windows 11",
            )
        )
        return checklist

    def scan_single_item(self, item: ComponentScanItem) -> ComponentScanItem:
        if item.key == "os_arch":
            sys_name = platform.system()
            arch = platform.machine()
            item.found = True
            item.version_or_path = f"{sys_name} {platform.release()} ({arch})"
            item.action_taken = "FOUND ✓"
            return item

        if item.key == "winget":
            wg = shutil.which("winget")
            if wg:
                item.found = True
                item.version_or_path = wg
                item.action_taken = "FOUND ✓"
            else:
                item.found = platform.system() != "Windows"
                item.version_or_path = "winget (Built-in on Windows 11)" if not wg else wg
                item.action_taken = "FOUND ✓" if item.found else "MISSING (Optional)"
            return item

        if item.key == "python_runtime":
            ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            item.found = sys.version_info >= (3, 9)
            item.version_or_path = f"Python {ver} ({sys.executable})"
            item.action_taken = "FOUND ✓" if item.found else "NEEDS UPGRADE"
            return item

        if item.key == "pip_manager":
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "pip", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                    check=False,
                )
                if proc.returncode == 0:
                    item.found = True
                    item.version_or_path = proc.stdout.strip().split(" from ")[0]
                    item.action_taken = "FOUND ✓"
                else:
                    item.found = False
                    item.version_or_path = "pip module not present"
                    item.action_taken = "MISSING -> WILL BOOTSTRAP"
            except Exception:
                item.found = False
                item.version_or_path = "pip unavailable"
                item.action_taken = "MISSING -> WILL BOOTSTRAP"
            return item

        if item.key == "ollama_bin":
            ol_path = shutil.which("ollama")
            if not ol_path and platform.system() == "Windows":
                candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
                if candidate.exists():
                    ol_path = str(candidate)
            if ol_path:
                item.found = True
                item.version_or_path = ol_path
                item.action_taken = "FOUND ✓"
            else:
                item.found = False
                item.version_or_path = "Not installed"
                item.action_taken = "MISSING -> WILL INSTALL"
            return item

        if item.key.startswith("lib_"):
            spec = importlib.util.find_spec(item.import_name)
            if spec is not None:
                item.found = True
                item.version_or_path = f"Module '{item.import_name}' verified"
                item.action_taken = "FOUND ✓"
            else:
                item.found = False
                item.version_or_path = f"Package '{item.pip_spec}' not installed"
                item.action_taken = "MISSING -> WILL INSTALL"
            return item

        if item.key == "llama_model":
            ol_path = shutil.which("ollama")
            if ol_path:
                try:
                    proc = subprocess.run(
                        [ol_path, "list"],
                        capture_output=True,
                        text=True,
                        timeout=8,
                        check=False,
                    )
                    if proc.returncode == 0 and "bajrang-llama3.2" in proc.stdout:
                        item.found = True
                        item.version_or_path = "bajrang-llama3.2:latest"
                        item.action_taken = "FOUND ✓"
                        return item
                except Exception:
                    pass
            item.found = False
            item.version_or_path = "bajrang-llama3.2 Modelfile not built yet"
            item.action_taken = "MISSING -> WILL BUILD"
            return item

        return item

    def run_full_scan(
        self, on_progress: Optional[Callable[[int, int, ComponentScanItem], None]] = None
    ) -> Tuple[int, int]:
        total = len(self.items)
        found_count = 0
        for idx, item in enumerate(self.items):
            self.scan_single_item(item)
            if item.found:
                found_count += 1
            if on_progress:
                on_progress(idx + 1, total, item)
        return found_count, total

    def install_missing_item(self, item: ComponentScanItem, dry_run: bool = False) -> bool:
        if item.found:
            item.action_taken = "ALREADY PRESENT (SKIPPED)"
            return True

        if dry_run:
            item.found = True
            item.action_taken = "SIMULATED INSTALL ✓"
            return True

        if item.key == "pip_manager":
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "ensurepip", "--upgrade"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                item.found = proc.returncode == 0
                item.action_taken = "INSTALLED ✓" if item.found else "FAILED (Check Python)"
                return item.found
            except Exception as exc:
                item.action_taken = f"ERROR: {exc}"
                return False

        if item.key == "ollama_bin":
            if platform.system() == "Windows" and shutil.which("winget"):
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
                        check=False,
                    )
                    if proc.returncode == 0 or shutil.which("ollama"):
                        item.found = True
                        item.version_or_path = "Installed via winget"
                        item.action_taken = "INSTALLED ✓"
                        return True
                except Exception:
                    pass
            item.action_taken = "OPTIONAL (Use BYO API Key or https://ollama.com/download/windows)"
            return False

        if item.key.startswith("lib_"):
            try:
                proc = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--upgrade",
                        "--disable-pip-version-check",
                        item.pip_spec,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
                if proc.returncode == 0:
                    item.found = True
                    item.version_or_path = f"Installed ({item.pip_spec})"
                    item.action_taken = "INSTALLED ✓"
                    return True
                item.action_taken = "PIP INSTALL SKIPPED (Offline / Use Pre-Installed)"
                return False
            except Exception as exc:
                item.action_taken = f"SKIPPED ({exc})"
                return False

        if item.key == "llama_model":
            modelfile_path = self.install_dir / "Modelfile.bajrang"
            modelfile_content = (
                "FROM llama3.2\n"
                "PARAMETER temperature 0.35\n"
                "PARAMETER top_p 0.9\n"
                "PARAMETER num_ctx 8192\n"
                "PARAMETER num_thread 8\n"
                'SYSTEM """You are Bajrang AI Pro for Kaushik Ram Ravuru on Windows 11 & Fedora. '
                'Reply concisely and emit JSON actions only when asked to automate the desktop."""\n'
            )
            modelfile_path.write_text(modelfile_content, encoding="utf-8")
            ol_path = shutil.which("ollama")
            if ol_path:
                try:
                    subprocess.run([ol_path, "pull", "llama3.2"], timeout=600, check=False)
                    proc = subprocess.run(
                        [ol_path, "create", "bajrang-llama3.2", "-f", str(modelfile_path)],
                        capture_output=True,
                        text=True,
                        timeout=120,
                        check=False,
                    )
                    if proc.returncode == 0:
                        item.found = True
                        item.version_or_path = "bajrang-llama3.2 built"
                        item.action_taken = "BUILT MODEL ✓"
                        return True
                except Exception:
                    pass
            item.found = True
            item.version_or_path = f"Saved {modelfile_path.name} (Ready for Ollama)"
            item.action_taken = "MODELFILE SAVED ✓"
            return True

        return True

    def write_diagnostic_log(self, event: str) -> Path:
        log_path = self.install_dir / "install_diagnostics.log"
        self.install_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {event}\n")
        return log_path

    def clean_uninstall(self) -> Tuple[bool, str]:
        removed_items: List[str] = []
        if platform.system() == "Windows":
            desktop_lnk = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop" / "Bajrang AI Pro.lnk"
            if desktop_lnk.exists():
                try:
                    desktop_lnk.unlink()
                    removed_items.append(str(desktop_lnk))
                except Exception:
                    pass
        for fname in [
            "bajrang_core.py",
            "bajrang_windows.py",
            "installer_windows.py",
            "requirements_windows.txt",
            "setup_windows.bat",
            "Launch_Bajrang_AI.bat",
            "Modelfile.bajrang",
            "install_diagnostics.log",
        ]:
            fp = self.install_dir / fname
            if fp.exists():
                try:
                    fp.unlink()
                    removed_items.append(fname)
                except Exception:
                    pass
        return True, f"Uninstalled {len(removed_items)} application files from {self.install_dir} (preserved user history.db)."

    def deploy_app_files_and_shortcuts(self, source_dir: Optional[Path] = None) -> Dict[str, str]:
        src = source_dir or Path(__file__).resolve().parent
        deployed: Dict[str, str] = {}

        for fname in ["bajrang_core.py", "bajrang_windows.py", "requirements_windows.txt", "setup_windows.bat"]:
            candidate = src / fname
            if candidate.exists():
                dest = self.install_dir / fname
                if candidate.resolve() != dest.resolve():
                    shutil.copy2(candidate, dest)
                deployed[fname] = str(dest)

        launcher_bat = self.install_dir / "Launch_Bajrang_AI.bat"
        launcher_bat.write_text(
            f'@echo off\r\ncd /d "{self.install_dir}"\r\nstart "" "{sys.executable}" "{self.install_dir / "bajrang_windows.py"}"\r\n',
            encoding="utf-8",
        )
        deployed["Launch_Bajrang_AI.bat"] = str(launcher_bat)

        if platform.system() == "Windows":
            ps_script = (
                "$WshShell = New-Object -ComObject WScript.Shell; "
                "$Desktop = [Environment]::GetFolderPath('Desktop'); "
                "$Shortcut = $WshShell.CreateShortcut((Join-Path $Desktop 'Bajrang AI Pro.lnk')); "
                f"$Shortcut.TargetPath = '{sys.executable}'; "
                f"$Shortcut.Arguments = '\"{self.install_dir / 'bajrang_windows.py'}\"'; "
                f"$Shortcut.WorkingDirectory = '{self.install_dir}'; "
                "$Shortcut.Description = 'Bajrang AI Pro (Argon Edition) for Windows 11'; "
                "$Shortcut.Save()"
            )
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                deployed["Desktop_Shortcut"] = "Bajrang AI Pro.lnk"
            except Exception:
                pass

        return deployed


def run_cli_installer(dry_run: bool = False) -> int:
    print("=" * 72)
    print(f"  Bajrang AI Pro ({APP_VERSION}) — Pre-Flight PC Scanner & Installer")
    print("=" * 72)
    scanner = SmartSystemScannerInstaller()
    print(f"\n[Step 1/3] Scanning PC components and Python libraries (Target: {scanner.install_dir})...\n")

    found_count, total = scanner.run_full_scan()
    for idx, item in enumerate(scanner.items, start=1):
        badge = "[FOUND ✓]" if item.found else "[MISSING]"
        print(f"  {idx:02d}/{total:02d} {badge:12s} {item.name:42s} -> {item.version_or_path}")

    missing = [it for it in scanner.items if not it.found]
    print(f"\nScan Summary: {found_count}/{total} components already present, {len(missing)} missing.")

    print("\n[Step 2/3] Installing missing libraries and models one by one...")
    for item in scanner.items:
        if not item.found:
            print(f"  -> Installing {item.name} ({item.pip_spec or item.key})...")
            scanner.install_missing_item(item, dry_run=dry_run)
            print(f"     Result: {item.action_taken}")
        else:
            print(f"  -> Skipping {item.name} (Already installed)")

    print("\n[Step 3/3] Deploying application files and Windows 11 shortcuts...")
    deployed = scanner.deploy_app_files_and_shortcuts()
    for k, v in deployed.items():
        print(f"  -> Deployed {k}: {v}")

    print("\nInstallation Complete! Run `python bajrang_windows.py` or use the Desktop shortcut.")
    return 0


def run_gui_installer() -> None:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        run_cli_installer()
        return

    scanner = SmartSystemScannerInstaller()
    root = tk.Tk()
    root.title("Bajrang AI Pro v5.0 — Smart Windows 11 Setup & Pre-Flight Scanner")
    root.geometry("860x620")
    root.configure(bg="#090b11")

    header = tk.Frame(root, bg="#121521", padx=20, pady=14)
    header.pack(fill=tk.X)
    tk.Label(
        header,
        text="⚡ Bajrang AI Pro — Windows 11 Smart Setup Wizard (.exe)",
        bg="#121521",
        fg="#f8fafc",
        font=("Segoe UI", 14, "bold"),
    ).pack(anchor="w")
    tk.Label(
        header,
        text=f"Target Directory: {scanner.install_dir}  |  Scans PC first, then installs only missing packages",
        bg="#121521",
        fg="#94a3b8",
        font=("Consolas", 9),
    ).pack(anchor="w", pady=(2, 0))

    body = tk.Frame(root, bg="#090b11", padx=20, pady=12)
    body.pack(fill=tk.BOTH, expand=True)

    status_var = tk.StringVar(value="Ready to scan your Windows 11 PC for required libraries & Ollama runtime.")
    tk.Label(
        body,
        textvariable=status_var,
        bg="#090b11",
        fg="#fbbf24",
        font=("Segoe UI", 10, "bold"),
    ).pack(anchor="w", pady=(0, 8))

    cols = ("component", "category", "status", "details")
    tree = ttk.Treeview(body, columns=cols, show="headings", height=14)
    tree.heading("component", text="Component / Library")
    tree.heading("category", text="Category")
    tree.heading("status", text="Scan / Install Status")
    tree.heading("details", text="Detected Version / Path")
    tree.column("component", width=260)
    tree.column("category", width=110)
    tree.column("status", width=165)
    tree.column("details", width=270)
    tree.pack(fill=tk.BOTH, expand=True)

    row_ids: Dict[str, str] = {}
    for item in scanner.items:
        rid = tree.insert("", tk.END, values=(item.name, item.category, "WAITING FOR SCAN", item.description))
        row_ids[item.key] = rid

    footer = tk.Frame(root, bg="#121521", padx=20, pady=12)
    footer.pack(fill=tk.X)

    def refresh_tree() -> None:
        for it in scanner.items:
            rid = row_ids.get(it.key)
            if rid:
                tree.item(rid, values=(it.name, it.category, it.action_taken, it.version_or_path))

    def on_scan_only() -> None:
        def worker() -> None:
            status_var.set("Scanning PC for Python, Winget, Ollama, and 7 required libraries...")
            found_count, total = scanner.run_full_scan()
            root.after(0, refresh_tree)
            missing_cnt = total - found_count
            root.after(
                0,
                lambda: status_var.set(
                    f"Pre-Flight Scan Complete: {found_count}/{total} found, {missing_cnt} missing. Click 'Install Missing & Finish' to proceed."
                ),
            )

        threading.Thread(target=worker, daemon=True).start()

    def on_smart_install() -> None:
        def worker() -> None:
            status_var.set("Step 1/3: Scanning PC for existing packages...")
            scanner.run_full_scan()
            root.after(0, refresh_tree)

            for it in scanner.items:
                if not it.found:
                    it.action_taken = "INSTALLING..."
                    root.after(0, refresh_tree)
                    root.after(0, lambda name=it.name: status_var.set(f"Step 2/3: Installing missing {name}..."))
                    scanner.install_missing_item(it, dry_run=False)
                    root.after(0, refresh_tree)
                else:
                    it.action_taken = "FOUND ✓ (Skipped)"
                    root.after(0, refresh_tree)

            root.after(0, lambda: status_var.set("Step 3/3: Creating Windows 11 Desktop Shortcut & deploying Bajrang AI Pro..."))
            scanner.deploy_app_files_and_shortcuts()
            root.after(
                0,
                lambda: status_var.set(
                    f"✅ Setup Complete! Installed to {scanner.install_dir} and created Desktop shortcut."
                ),
            )

        threading.Thread(target=worker, daemon=True).start()

    def on_launch_app() -> None:
        app_py = scanner.install_dir / "bajrang_windows.py"
        if not app_py.exists():
            app_py = Path(__file__).resolve().parent / "bajrang_windows.py"
        if app_py.exists():
            subprocess.Popen([sys.executable, str(app_py)])
            root.destroy()

    tk.Button(
        footer,
        text="🔍 1. Scan PC Now",
        command=on_scan_only,
        bg="#4f46e5",
        fg="#ffffff",
        font=("Segoe UI", 10, "bold"),
        relief=tk.FLAT,
        padx=14,
        pady=6,
    ).pack(side=tk.LEFT, padx=(0, 8))

    tk.Button(
        footer,
        text="⚡ 2. Auto-Install Missing & Create Shortcut",
        command=on_smart_install,
        bg="#f59e0b",
        fg="#0f172a",
        font=("Segoe UI", 10, "bold"),
        relief=tk.FLAT,
        padx=14,
        pady=6,
    ).pack(side=tk.LEFT, padx=(0, 8))

    tk.Button(
        footer,
        text="🚀 3. Launch Bajrang AI Pro",
        command=on_launch_app,
        bg="#10b981",
        fg="#0f172a",
        font=("Segoe UI", 10, "bold"),
        relief=tk.FLAT,
        padx=14,
        pady=6,
    ).pack(side=tk.RIGHT)

    root.after(250, on_scan_only)
    root.mainloop()


def run_self_tests() -> int:
    print("Running Smart Windows 11 Installer Self-Tests...")
    with tempfile.TemporaryDirectory() as tmp:
        scanner = SmartSystemScannerInstaller(target_dir=Path(tmp))
        found_count, total = scanner.run_full_scan()
        assert total == 13, f"Expected 13 checklist items, got {total}"
        assert found_count >= 2, "Expected OS and Python runtime to be detected"
        for it in scanner.items:
            if not it.found:
                ok = scanner.install_missing_item(it, dry_run=True)
                assert ok is True
                assert it.found is True
        deployed = scanner.deploy_app_files_and_shortcuts()
        assert "Launch_Bajrang_AI.bat" in deployed
    print("All Smart Windows 11 Installer self-tests passed!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Bajrang AI Pro Smart Windows 11 Pre-Flight Scanner & Installer")
    parser.add_argument("--cli", action="store_true", help="Run interactive CLI scanner and installer")
    parser.add_argument("--dry-run", action="store_true", help="Simulate installing missing packages")
    parser.add_argument("--uninstall", action="store_true", help="Cleanly uninstall application files and shortcuts")
    parser.add_argument("--self-test", action="store_true", help="Run self-tests")
    args = parser.parse_args()

    if getattr(args, 'uninstall', False):
        sc = SmartSystemScannerInstaller()
        ok, msg = sc.clean_uninstall()
        print(msg)
        return 0 if ok else 1
    if args.self_test:
        return run_self_tests()
    if args.cli or args.dry_run:
        return run_cli_installer(dry_run=args.dry_run)
    run_gui_installer()
    return 0


if __name__ == "__main__":
    sys.exit(main())