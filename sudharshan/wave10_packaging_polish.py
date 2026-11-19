import json
import os
import sqlite3
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import bajrang_core
from .wave4_security_governance import IntegrityVerifier, NetworkEgressController, SecretPIIRedactor


class OnboardingWizard:
    @staticmethod
    def run_preflight() -> Dict[str, Any]:
        free_ram = bajrang_core.HardwareProfiler.get_free_ram_gb()
        decision = bajrang_core.AdaptiveModelEngine.select_local_model(
            complexity=bajrang_core.TaskComplexity.MODERATE,
            free_ram_gb=free_ram,
        )
        mics = bajrang_core.HardwareProfiler.list_audio_input_devices()
        return {
            "cpu_count": os.cpu_count() or 1,
            "free_ram_gb": free_ram,
            "recommended_model": decision["model"],
            "downgraded_for_ram": decision["downgraded"],
            "audio_devices": mics,
            "mic_ready": len(mics) > 0,
        }


class SelfHealingDoctor:
    @staticmethod
    def run_checks(data_dir: Path) -> Dict[str, Any]:
        data_dir = Path(data_dir)
        repaired: List[str] = []
        if not data_dir.exists():
            data_dir.mkdir(parents=True, exist_ok=True)
            repaired.append(f"Created missing data directory: {data_dir}")

        db_ok = True
        db_detail = "No SQLite DB yet (clean)"
        db_file = data_dir / "chat_history.db"
        if db_file.is_file():
            try:
                with sqlite3.connect(db_file) as conn:
                    res = conn.execute("PRAGMA integrity_check").fetchone()
                    db_ok = bool(res and res[0] == "ok")
                    db_detail = str(res[0]) if res else "unknown"
            except Exception as exc:
                db_ok = False
                db_detail = str(exc)

        mics = bajrang_core.HardwareProfiler.list_audio_input_devices()
        ollama_ok = bajrang_core.LocalAIModelManager().is_service_running()
        return {
            "healthy": db_ok and len(mics) > 0,
            "ollama_online": ollama_ok,
            "sqlite_ok": db_ok,
            "sqlite_detail": db_detail,
            "audio_devices_count": len(mics),
            "repaired": repaired,
        }


class GracefulDegradationMatrix:
    @staticmethod
    def compute_capabilities(ollama_online: bool, network_online: bool, audio_available: bool) -> Dict[str, bool]:
        return {
            "ui_interactive": True,
            "local_file_automation": True,
            "local_rag_search": True,
            "local_llm_inference": bool(ollama_online),
            "voice_input": bool(audio_available),
            "cloud_burst_optional": bool(network_online),
        }


class AccessibilityComplianceAudit:
    @staticmethod
    def _relative_luminance(hex_color: str) -> float:
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        def _lin(c: float) -> float:
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)

    @classmethod
    def contrast_ratio(cls, fg_hex: str, bg_hex: str) -> float:
        l1 = cls._relative_luminance(fg_hex)
        l2 = cls._relative_luminance(bg_hex)
        hi, lo = max(l1, l2), min(l1, l2)
        return round((hi + 0.05) / (lo + 0.05), 2)

    @classmethod
    def check_wcag_aa(cls, fg_hex: str, bg_hex: str, large_text: bool = False) -> Dict[str, Any]:
        ratio = cls.contrast_ratio(fg_hex, bg_hex)
        threshold = 3.0 if large_text else 4.5
        return {"fg": fg_hex, "bg": bg_hex, "ratio": ratio, "wcag_aa_pass": ratio >= threshold}


class OfflineUpdateVerifier:
    @staticmethod
    def verify_release(root_dir: Path, sha256sums_path: Path) -> Tuple[bool, List[str]]:
        manifest = Path(sha256sums_path).read_text(encoding="utf-8")
        return IntegrityVerifier.verify_manifest(Path(root_dir), manifest)


class ZeroTelemetryDashboard:
    @staticmethod
    def report(egress: NetworkEgressController) -> Dict[str, Any]:
        return {
            "airplane_mode": egress.airplane_mode,
            "external_bytes_sent": egress.external_bytes_sent,
            "blocked_egress_attempts": len(egress.blocked_hosts),
            "zero_telemetry_verified": egress.external_bytes_sent == 0,
        }


class RedactedCrashReporter:
    @staticmethod
    def create_bundle(output_zip: Path, error_trace: str, settings: Dict[str, Any]) -> Path:
        output_zip = Path(output_zip)
        output_zip.parent.mkdir(parents=True, exist_ok=True)
        redacted_trace = SecretPIIRedactor.redact(error_trace)
        redacted_settings = SecretPIIRedactor.redact(json.dumps(settings, indent=2))
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("traceback.txt", redacted_trace)
            zf.writestr("settings_redacted.json", redacted_settings)
            zf.writestr("meta.json", json.dumps({"generated_at": time.time(), "redacted": True}, indent=2))
        return output_zip
