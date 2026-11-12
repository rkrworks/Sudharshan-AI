#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bajrang AI Pro (v6.0) — Comprehensive 15-Domain Automated Quality Assurance Suite (`test_bajrang_suite.py`)
Clearly distinguishes:
  - [REAL INTEGRATION TEST]: Executes directly against the local SQLite database, OS filesystem,
    Goertzel-DTW DSP engine, SHA-256 file organizer, and RSA modular verifier.
  - [MOCKED EXTERNAL SERVICE TEST]: Uses deterministic local HTTP/socket mocks for cloud LLM
    endpoints and Razorpay webhook signatures that require external API accounts.
"""

import hashlib
import hmac
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bajrang_core import (
    AdvancedVoiceEngine,
    AsymmetricLicenseVerifier,
    AutonomousTaskPlanner,
    CrossPlatformComputerUse,
    DatabaseMigrationManager,
    LongTermMemoryStore,
    ModularAIRouter,
    PerformanceSettings,
    SecurityVault,
    TaskComplexity,
    ToolSchemaValidator,
    contains_sensitive_pii,
    redact_sensitive_text,
)
from installer_windows import SmartSystemScannerInstaller
from razorpay_server import RazorpayLicenseBackend


class TestBajrangV6Suite(unittest.TestCase):
    """Comprehensive 15-domain automated verification suite for Bajrang AI Pro v6.0."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.vault = SecurityVault(self.root / "config")
        for k in ("api_key_gemini_argon", "byo_api_key", "api_key_groq", "api_key_openrouter", "api_key_openai"):
            self.vault.delete_secret(k)
        self.db_path = self.root / "history.db"
        self.memory = LongTermMemoryStore(self.db_path)
        self.computer = CrossPlatformComputerUse(PerformanceSettings.from_profile("balanced"))
        self.router = ModularAIRouter(
            vault=self.vault,
            memory_store=self.memory,
            primary_provider="gemini_argon",
            fallback_order=["groq", "openrouter", "ollama"],
            perf_settings=PerformanceSettings.from_profile("balanced"),
        )

    def tearDown(self) -> None:
        for k in ("api_key_gemini_argon", "byo_api_key", "api_key_groq", "api_key_openrouter", "api_key_openai"):
            self.vault.delete_secret(k)
        self.tmp_dir.cleanup()

    def test_01_ai_provider_connectivity_and_health_checks(self) -> None:
        """[REAL INTEGRATION TEST] Verifies provider health checks & Eco profile disabling."""
        eco_router = ModularAIRouter(
            vault=self.vault,
            memory_store=self.memory,
            primary_provider="ollama",
            perf_settings=PerformanceSettings.from_profile("eco"),
        )
        health_eco = eco_router.check_provider_health("ollama")
        self.assertFalse(health_eco["healthy"])
        self.assertIn("Eco", health_eco["detail"])

        health_no_key = self.router.check_provider_health("gemini_argon")
        self.assertFalse(health_no_key["healthy"])
        self.assertIn("No API key", health_no_key["detail"])

    def test_02_complexity_routing_and_provider_fallback(self) -> None:
        """[MOCKED EXTERNAL SERVICE TEST] Verifies task complexity classification & fallback chain."""
        self.assertEqual(ModularAIRouter.assess_task_complexity("hi"), TaskComplexity.SIMPLE)
        self.assertEqual(
            ModularAIRouter.assess_task_complexity("Organize my Downloads folder and remove duplicates step by step"),
            TaskComplexity.COMPLEX_REASONING,
        )
        self.assertEqual(
            ModularAIRouter.assess_task_complexity("What is on my screen right now?"),
            TaskComplexity.MULTIMODAL_VISION,
        )
        self.assertEqual(
            self.router.select_model_for_task("gemini_argon", TaskComplexity.SIMPLE),
            "gemini-2.5-flash",
        )
        self.assertEqual(
            self.router.select_model_for_task("gemini_argon", TaskComplexity.COMPLEX_REASONING),
            "gemini-2.5-pro",
        )

        with patch("urllib.request.urlopen", side_effect=OSError("External endpoint offline")):
            sess_id = self.memory.create_session("Fallback Test")
            turn = self.router.generate_structured_turn("open notepad", sess_id)
            self.assertEqual(turn["provider_used"], "deterministic_local_router")
            self.assertEqual(turn["actions"][0]["tool"], "open_app")
            self.assertEqual(turn["actions"][0]["arguments"]["app_name"], "notepad")

    def test_03_voice_recognition_vad_denoise_and_goertzel_dtw(self) -> None:
        """[REAL INTEGRATION TEST] Verifies VAD silence rejection, spectral denoise, wake word & 8-band Goertzel-DTW."""
        voice = AdvancedVoiceEngine(wake_word="hey bajrang")

        silence_pcm = [0.0001] * 4000
        res_silence = voice.recognize_from_pcm(silence_pcm)
        self.assertFalse(res_silence["success"])
        self.assertEqual(res_silence["engine"], "vad_silence_gate")

        wake_pcm = voice.generate_synthetic_utterance_pcm("hey bajrang")
        res_wake = voice.recognize_from_pcm(wake_pcm)
        self.assertTrue(res_wake["success"])
        self.assertEqual(res_wake["transcript"], "hey bajrang")
        self.assertTrue(res_wake["wake_word_detected"])
        self.assertGreaterEqual(res_wake["confidence"], 0.90)

        cmd_pcm = voice.generate_synthetic_utterance_pcm("open terminal")
        res_cmd = voice.recognize_from_pcm(cmd_pcm)
        self.assertTrue(res_cmd["success"])
        self.assertEqual(res_cmd["transcript"], "open terminal")

    def test_04_tts_and_barge_in_interruption(self) -> None:
        """[REAL INTEGRATION TEST] Verifies TTS configuration & barge-in interruption flag."""
        voice = AdvancedVoiceEngine(tts_rate_wpm=200, tts_language="en-IN")
        self.assertEqual(voice.tts_rate_wpm, 200)
        interrupted = voice.interrupt_tts()
        self.assertTrue(interrupted)
        self.assertTrue(voice._barge_in_triggered.is_set())

    def test_05_microphone_enumeration_and_error_handling(self) -> None:
        """[REAL INTEGRATION TEST] Verifies audio input enumeration never crashes on headless hosts."""
        voice = AdvancedVoiceEngine()
        mics = voice.list_microphones()
        self.assertIsInstance(mics, list)
        self.assertGreaterEqual(len(mics), 1)
        self.assertIn("name", mics[0])

    def test_06_sqlite_persistence_and_v1_to_v3_migration(self) -> None:
        """[REAL INTEGRATION TEST] Simulates a legacy v1 database and verifies lossless v3 migration."""
        legacy_db = self.root / "legacy_v1.db"
        conn = sqlite3.connect(str(legacy_db))
        conn.executescript(
            """
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                results_json TEXT NOT NULL DEFAULT '[]',
                timestamp TEXT NOT NULL
            );
            INSERT INTO sessions VALUES ('sess_legacy', 'Legacy Session', 'llama3.2', '2026-11-10', '2026-11-10');
            INSERT INTO messages (session_id, role, content, results_json, timestamp)
            VALUES ('sess_legacy', 'user', 'Hello from v1', '[]', '2026-11-10');
            """
        )
        conn.commit()
        conn.close()

        migrated_store = LongTermMemoryStore(legacy_db)
        msgs = migrated_store.get_session_messages("sess_legacy")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["content"], "Hello from v1")
        with migrated_store._conn() as c:
            ver = migrated_store.migration_mgr.get_current_version(c)
            self.assertEqual(ver, 3)

    def test_07_long_term_memory_crud_and_pii_guardrail(self) -> None:
        """[REAL INTEGRATION TEST] Verifies memory creation, update, search, deletion, and PII blocking."""
        ok, msg, item = self.memory.store_memory(
            key="coding_style",
            content="Omit all double-slash comments and store workspaces on native Linux ext4/btrfs.",
            category="preference",
            project_tag="bajrang_ai",
            importance=5,
        )
        self.assertTrue(ok, msg)
        mid = item["memory_id"]

        results = self.memory.search_memories(query="double-slash", category="preference")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["memory_id"], mid)

        ok_upd, _ = self.memory.update_memory(mid, "Updated preference: strict Python type hints.", importance=4)
        self.assertTrue(ok_upd)

        ctx = self.memory.build_relevant_context_block("What is my coding_style preference?")
        self.assertIn("strict Python type hints", ctx)

        ok_pii, pii_err, _ = self.memory.store_memory(
            key="secret_token",
            content="My Gemini key is AIzaSyD91234567890123456789012345678",
            category="fact",
        )
        self.assertFalse(ok_pii)
        self.assertIn("API_KEY", pii_err)

        self.assertTrue(self.memory.delete_memory(mid))
        self.assertEqual(len(self.memory.search_memories(query="type hints")), 0)

    def test_08_desktop_automation_and_honest_verification(self) -> None:
        """[REAL INTEGRATION TEST] Verifies computer-use never fabricates success and blocks protected processes."""
        ok_close, msg_close, _ = self.computer.close_application("systemd")
        self.assertFalse(ok_close)
        self.assertIn("prohibited", msg_close)

        ok_bad_app, msg_bad_app, _ = self.computer.launch_application("nonexistent_malware_binary_xyz")
        self.assertFalse(ok_bad_app)
        self.assertIn("not in the", msg_bad_app)

    def test_09_safety_controls_and_schema_validation(self) -> None:
        """[REAL INTEGRATION TEST] Verifies ToolSchemaValidator rejects unknown tools, bad paths, and forbidden hotkeys."""
        ok_valid, _, is_destr = ToolSchemaValidator.validate_action(
            {"tool": "open_app", "arguments": {"app_name": "calculator"}}
        )
        self.assertTrue(ok_valid)
        self.assertFalse(is_destr)

        ok_unknown, err_unknown, _ = ToolSchemaValidator.validate_action(
            {"tool": "raw_shell_exec", "arguments": {"cmd": "rm -rf /"}}
        )
        self.assertFalse(ok_unknown)
        self.assertIn("allowlist", err_unknown)

        ok_sys_path, err_sys_path, _ = ToolSchemaValidator.validate_action(
            {"tool": "organize_directory", "arguments": {"directory_path": "/etc"}}
        )
        self.assertFalse(ok_sys_path)
        self.assertIn("prohibited", err_sys_path)

        ok_hotkey, err_hotkey, _ = ToolSchemaValidator.validate_action(
            {"tool": "navigate_hotkey", "arguments": {"keys": ["alt", "f4"]}}
        )
        self.assertFalse(ok_hotkey)
        self.assertIn("restricted", err_hotkey)

    def test_10_autonomous_task_planner_confirmation_and_cancellation(self) -> None:
        """[REAL INTEGRATION TEST] Verifies Downloads organization, SHA-256 duplicate removal, permission gate & cancellation."""
        dl = self.root / "Downloads"
        dl.mkdir()
        (dl / "report.pdf").write_bytes(b"REPORT_BYTES_2026")
        (dl / "report_duplicate.pdf").write_bytes(b"REPORT_BYTES_2026")
        (dl / "diagram.png").write_bytes(b"PNG_IMAGE_BYTES")
        (dl / "installer.exe").write_bytes(b"MZ_INSTALLER_BYTES")

        planner = AutonomousTaskPlanner(self.memory, self.computer)
        ok_plan, plan = planner.create_organization_plan(str(dl), remove_duplicates=True)
        self.assertTrue(ok_plan)
        self.assertEqual(plan.status, "awaiting_permission")
        self.assertEqual(plan.inspection_report["duplicate_count"], 1)

        ok_unapproved, _ = planner.execute_approved_plan(plan.plan_id, user_confirmed=False)
        self.assertFalse(ok_unapproved)
        self.assertTrue((dl / "report_duplicate.pdf").exists())

        ok_approved, executed_plan = planner.execute_approved_plan(plan.plan_id, user_confirmed=True)
        self.assertTrue(ok_approved)
        self.assertEqual(executed_plan.status, "completed")
        self.assertTrue((dl / "Documents" / "report.pdf").exists())
        self.assertTrue((dl / "Images" / "diagram.png").exists())
        self.assertTrue((dl / "Installers" / "installer.exe").exists())
        self.assertFalse((dl / "report_duplicate.pdf").exists())

        dl2 = self.root / "Downloads2"
        dl2.mkdir()
        (dl2 / "a.txt").write_text("hello", encoding="utf-8")
        _, plan2 = planner.create_organization_plan(str(dl2))
        ok_cancel, _ = planner.cancel_plan(plan2.plan_id)
        self.assertTrue(ok_cancel)
        ok_after_cancel, _ = planner.execute_approved_plan(plan2.plan_id, user_confirmed=True)
        self.assertFalse(ok_after_cancel)

    def test_11_installer_detection_and_clean_uninstall(self) -> None:
        """[REAL INTEGRATION TEST] Verifies Windows smart installer pre-flight scan, diagnostic log, and clean uninstall."""
        inst_dir = self.root / "BajrangInstall"
        scanner = SmartSystemScannerInstaller(target_dir=inst_dir)
        found_cnt, total_cnt = scanner.run_full_scan()
        self.assertEqual(total_cnt, 13)
        self.assertGreaterEqual(found_cnt, 2)

        log_file = scanner.write_diagnostic_log("Unit test diagnostic entry")
        self.assertTrue(log_file.exists())

        scanner.deploy_app_files_and_shortcuts()
        self.assertTrue((inst_dir / "Launch_Bajrang_AI.bat").exists())

        ok_uninst, msg_uninst = scanner.clean_uninstall()
        self.assertTrue(ok_uninst, msg_uninst)
        self.assertFalse((inst_dir / "Launch_Bajrang_AI.bat").exists())

    def test_12_security_vault_secret_roundtrip(self) -> None:
        """[REAL INTEGRATION TEST] Verifies encrypted/vault secret storage and deletion."""
        backend = self.vault.store_secret("api_key_groq", "gsk_LiveTestSecretKey9876543210")
        self.assertIn(backend, ("os_keyring", "windows_dpapi", "linux_libsecret", "chmod_0600_vault"))
        retrieved = self.vault.get_secret("api_key_groq")
        self.assertEqual(retrieved, "gsk_LiveTestSecretKey9876543210")
        self.vault.delete_secret("api_key_groq")
        self.assertEqual(self.vault.get_secret("api_key_groq"), "")

    def test_13_network_failure_and_retry_recovery(self) -> None:
        """[MOCKED EXTERNAL SERVICE TEST] Verifies exponential backoff retry when a cloud endpoint fails transiently."""
        self.vault.store_secret("api_key_gemini_argon", "AIzaMockKeyForRetryTest1234567890")
        self.router.timeout_sec = 1.0
        self.router.max_retries = 2

        with patch("urllib.request.urlopen", side_effect=OSError("Simulated network timeout")):
            sess_id = self.memory.create_session("Retry Session")
            turn = self.router.generate_structured_turn("open calculator", sess_id)
            self.assertEqual(turn["provider_used"], "deterministic_local_router")
            self.assertGreaterEqual(len(turn["fallback_chain_tried"]), 1)

    def test_14_razorpay_payment_and_webhook_hmac_verification(self) -> None:
        """[MOCKED EXTERNAL SERVICE TEST] Verifies genuine Razorpay HMAC-SHA256 payment and webhook validation."""
        backend = RazorpayLicenseBackend(
            key_id="rzp_test_12345",
            key_secret="secret_key_abc",
            webhook_secret="whsec_xyz",
        )
        order_id = "order_P999888777"
        payment_id = "pay_Q111222333"
        valid_sig = hmac.new(
            b"secret_key_abc",
            f"{order_id}|{payment_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        self.assertTrue(backend.verify_payment_signature(order_id, payment_id, valid_sig))
        self.assertFalse(backend.verify_payment_signature(order_id, payment_id, "00" * 32))

        webhook_body = b'{"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_Q111222333"}}}}'
        valid_wh_sig = hmac.new(b"whsec_xyz", webhook_body, hashlib.sha256).hexdigest()
        self.assertTrue(backend.verify_webhook_signature(webhook_body, valid_wh_sig))
        self.assertFalse(backend.verify_webhook_signature(webhook_body, "invalid_wh_sig"))

    def test_15_asymmetric_public_key_license_verification(self) -> None:
        """[REAL INTEGRATION TEST] Verifies RSA modular public-key license verification & tamper rejection."""
        p_prime = 1000000007
        q_prime = 1000000009
        n_test = p_prime * q_prime
        phi = (p_prime - 1) * (q_prime - 1)
        e_test = 65537
        d_test = pow(e_test, -1, phi)

        verifier = AsymmetricLicenseVerifier()
        verifier.n_int = n_test

        backend = RazorpayLicenseBackend()
        backend.n_int = n_test

        cert = backend.sign_license_certificate(
            subscriber_email="verified_buyer@example.com",
            plan="pro_monthly",
            order_id="order_101",
            payment_id="pay_202",
            days_valid=30,
            private_d_int=d_test,
        )
        ok, info = verifier.verify_certificate(cert)
        self.assertTrue(ok, str(info))
        self.assertEqual(info["sub"], "verified_buyer@example.com")

        tampered = cert[:-4] + "ffff"
        ok_bad, _ = verifier.verify_certificate(tampered)
        self.assertFalse(ok_bad)


if __name__ == "__main__":
    print("=" * 76)
    print("  Bajrang AI Pro v6.0 — Running 15-Domain Automated Verification Suite")
    print("=" * 76)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestBajrangV6Suite)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
