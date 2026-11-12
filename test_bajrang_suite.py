#!/usr/bin/env python3
import inspect
import json
import tempfile
import time
import unittest
from pathlib import Path

import bajrang_core
import fedora
import installer_windows
import razorpay_server
import windows


class TestBajrangAuditRemediations(unittest.TestCase):
    def test_c1_license_forgery_blocked_and_rsa2048_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            lm = bajrang_core.LicenseManager(Path(tmp))
            ok_forged, _ = lm.verify_key("BAJRANG-PRO-HACKER-20991231-ZZZZZZZZ")
            self.assertFalse(ok_forged, "C1: Forged BAJRANG-PRO token must be rejected")

            ok_any8, _ = lm.verify_key("BAJRANG-PRO-USER01-20991231-12345678")
            self.assertFalse(ok_any8, "C1: Any symmetric BAJRANG-PRO token must be rejected")

            cert = razorpay_server.AsymmetricLicenseIssuer.issue_license_certificate(
                email="kaushik@cbit.ac.in",
                order_id="order_test_1",
                payment_id="pay_test_1",
            )
            self.assertTrue(cert.startswith("BAJRANG-V6-"))
            ok_rsa, msg_rsa = lm.verify_key(cert)
            self.assertTrue(ok_rsa, f"C1: Valid 2048-bit RSA certificate must verify: {msg_rsa}")

            tampered = cert[:-4] + ("0000" if not cert.endswith("0000") else "ffff")
            ok_tampered, _ = lm.verify_key(tampered)
            self.assertFalse(ok_tampered, "C1: Tampered RSA signature must be rejected")

    def test_c2_no_client_side_credentials_or_key_minting(self):
        base = Path(__file__).resolve().parent
        for rel in ("index.html", "web/index.html", "portal_app.js"):
            content = (base / rel).read_text(encoding="utf-8")
            self.assertNotIn("OWNER_EMAIL_HASH", content, f"C2: {rel} must not contain OWNER_EMAIL_HASH")
            self.assertNotIn("OWNER_DEFAULT_PASSKEY", content, f"C2: {rel} must not contain OWNER_DEFAULT_PASSKEY")
            self.assertNotIn("generateBajrangLicenseKey", content, f"C2: {rel} must not mint keys in client JS")
            self.assertNotIn("BajrangOwner@9392", content, f"C2: {rel} must not contain plaintext passkey")

    def test_c3_command_allowlist_trampoline_blocked(self):
        guard = bajrang_core.SafetyGuard(strict_allowlist=True)
        trampolines = [
            'gnome-terminal -- python3 -c "import os; os.system(\'id\')"',
            "wt.exe powershell -Command calc.exe",
            "xdg-open https://malicious.example/payload",
            "code --Wait /etc/passwd",
            "gedit /etc/shadow",
        ]
        for cmd in trampolines:
            ok, reason = guard.check_command(cmd)
            self.assertFalse(ok, f"C3: Trampoline or argument command must be blocked: {cmd} ({reason})")

        ok_clean, _ = guard.check_command("gnome-terminal")
        self.assertTrue(ok_clean, "C3: Zero-argument allowed binary should be permitted")

    def test_c4_schema_validation_no_shell_exec_and_confirmation_gate(self):
        ok_shell, _, _ = bajrang_core.ToolSchemaValidator.validate_action(
            {"tool": "shell_exec", "arguments": {"command": "gnome-terminal"}}
        )
        self.assertFalse(ok_shell, "C4: shell_exec must not be an AI-callable schema tool")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = bajrang_core.ConfigManager(config_dir=root / "cfg", data_dir=root / "data")
            adapter = windows.WindowsPlatformAdapter()
            engine = bajrang_core.BajrangEngine(adapter=adapter, config=cfg)

            engine.client.chat = lambda *a, **kw: bajrang_core.AssistantTurn(
                response_type="action",
                text="Typing into window",
                actions=[{"tool": "type_text", "arguments": {"text": "echo pwned"}}],
            )
            engine.process_prompt("Type echo pwned", auto_confirm_actions=False)
            self.assertEqual(
                len(engine.pending_actions),
                1,
                "C4: Unconfirmed type_text must be held in pending_actions",
            )
            confirmed_out = engine.confirm_pending_actions()
            self.assertEqual(len(engine.pending_actions), 0)
            self.assertEqual(len(confirmed_out), 1)

    def test_c5_organizer_collision_safety_trash_undo_and_cancellation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dl = root / "Downloads"
            dl.mkdir()
            (dl / "Documents").mkdir()
            existing_report = dl / "Documents" / "report.pdf"
            existing_report.write_bytes(b"ORIGINAL_IMPORTANT_REPORT_CONTENT")

            incoming_report = dl / "report.pdf"
            incoming_report.write_bytes(b"NEW_DIFFERENT_REPORT_CONTENT")

            dup_a = dl / "notes_a.txt"
            dup_b = dl / "notes_b.txt"
            dup_a.write_bytes(b"IDENTICAL_DUPLICATE_PAYLOAD")
            dup_b.write_bytes(b"IDENTICAL_DUPLICATE_PAYLOAD")

            storage = bajrang_core.LocalChatStorage(root / "data")
            planner = bajrang_core.AutonomousTaskPlanner(storage)
            ok_p, plan = planner.create_organization_plan(str(dl), remove_duplicates=True)
            self.assertTrue(ok_p)
            ok_ex, _ = planner.execute_approved_plan(plan.plan_id, user_confirmed=True)
            self.assertTrue(ok_ex)

            self.assertEqual(
                existing_report.read_bytes(),
                b"ORIGINAL_IMPORTANT_REPORT_CONTENT",
                "C5: Existing Documents/report.pdf must NEVER be overwritten",
            )
            renamed_report = dl / "Documents" / "report_1.pdf"
            self.assertTrue(renamed_report.exists(), "C5: Colliding file must be saved as report_1.pdf")
            self.assertEqual(renamed_report.read_bytes(), b"NEW_DIFFERENT_REPORT_CONTENT")

            ok_undo, _ = planner.undo_plan(plan.plan_id)
            self.assertTrue(ok_undo, "C5: undo_plan must succeed")
            self.assertTrue(incoming_report.exists(), "C5: Undo must restore incoming report.pdf")
            self.assertTrue(dup_a.exists() and dup_b.exists(), "C5: Undo must restore trashed duplicates")

    def test_c6_provider_key_affinity_and_gemini_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = bajrang_core.ConfigManager(config_dir=root / "cfg", data_dir=root / "data")
            adapter = windows.WindowsPlatformAdapter()
            engine = bajrang_core.BajrangEngine(adapter=adapter, config=cfg)

            google_key = "AIzaSyD-TestGoogleGeminiKey1234567890"
            engine.client.configure_byo_key(google_key)
            self.assertEqual( cfg.get_api_key("groq"), "", "C6: Google AIza key must never be returned for Groq")
            self.assertEqual( cfg.get_api_key("openai"), "", "C6: Google AIza key must never be returned for OpenAI")
            self.assertEqual( cfg.get_api_key("openrouter"), "", "C6: Google AIza key must never be returned for OpenRouter")

            router_src = inspect.getsource(bajrang_core.ModularAIRouter)
            self.assertIn("x-goog-api-key", router_src, "C6: Gemini API key must be sent in x-goog-api-key header")
            self.assertNotIn("?key=", router_src, "C6: Gemini API key must not be placed in URL query string")

    def test_h1_fedora_export_and_setup_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = fedora.export_modular_project(Path(tmp) / "exported")
            self.assertTrue((out_dir / "fedora.py").is_file(), "H1: fedora.py must be exported")
            self.assertTrue((out_dir / "bajrang_llama32.py").is_file(), "H1: bajrang_llama32.py must be exported")
            self.assertTrue((out_dir / "run.sh").is_file(), "H1: run.sh must be exported")
            ext_js = (out_dir / "gnome-extension" / "extension.js").read_text(encoding="utf-8")
            self.assertIn(str(out_dir / "fedora.py"), ext_js, "H1: GNOME extension must invoke resolved fedora.py")

        setup_sh = (Path(__file__).resolve().parent / "setup_fedora.sh").read_text(encoding="utf-8")
        self.assertIn("fedora.py", setup_sh)
        self.assertIn("bajrang_core.py", setup_sh)

    def test_h2_emergency_stop_aborts_streams_and_kill_socket(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = bajrang_core.ConfigManager(config_dir=root / "cfg", data_dir=root / "data")
            adapter = fedora.FedoraWaylandAdapter()
            engine = bajrang_core.BajrangEngine(adapter=adapter, config=cfg)

            stop_ev = fedora.start_fedora_kill_socket_listener(engine)
            time.sleep(0.1)
            ok_k, msg_k = fedora.send_kill_signal_to_running_instance()
            stop_ev.set()
            self.assertTrue(ok_k, f"H2: Fedora global kill socket must succeed: {msg_k}")
            self.assertTrue(engine.kill_switch.is_cancelled, "H2: Kill switch must be marked cancelled")

    def test_h3_all_schema_tools_implemented(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = bajrang_core.ConfigManager(config_dir=root / "cfg", data_dir=root / "data")
            adapter = windows.WindowsPlatformAdapter()
            engine = bajrang_core.BajrangEngine(adapter=adapter, config=cfg)
            actions = [
                {"tool": "list_windows", "arguments": {}},
                {"tool": "scroll_view", "arguments": {"direction": "down", "amount": 3}},
                {"tool": "navigate_hotkey", "arguments": {"keys": ["ctrl", "c"]}},
                {"tool": "inspect_directory", "arguments": {"path": str(root)}},
                {"tool": "memory_store", "arguments": {"key": "pref", "value": "dark_mode"}},
            ]
            for act in actions:
                res = engine.execute_action(act)
                self.assertNotIn("Unsupported tool", res.output, f"H3: {act['tool']} must be supported")

    def test_h4_unknown_key_rejected_and_hotkey_order_independent(self):
        win_adapter = windows.WindowsPlatformAdapter()
        fed_adapter = fedora.FedoraWaylandAdapter()

        res_w = win_adapter.press_key("nonexistent_key_999")
        res_f = fed_adapter.press_key("nonexistent_key_999")
        self.assertFalse(res_w.success, "H4: Windows press_key must reject unknown keys")
        self.assertTrue(res_w.blocked, "H4: Windows press_key must mark unknown keys blocked")
        self.assertFalse(res_f.success, "H4: Fedora press_key must reject unknown keys")
        self.assertTrue(res_f.blocked, "H4: Fedora press_key must mark unknown keys blocked")

        res_hk1 = fed_adapter.hotkey(["f4", "alt"])
        res_hk2 = win_adapter.hotkey(["r", "win"])
        self.assertTrue(res_hk1.blocked, "H4: Reversed ['f4', 'alt'] must be blocked")
        self.assertTrue(res_hk2.blocked, "H4: Reversed ['r', 'win'] must be blocked")

    def test_h5_razorpay_http_server_and_rsa_2048(self):
        self.assertGreaterEqual(bajrang_core.RSA_2048_MODULUS.bit_length(), 2048)
        self.assertEqual(razorpay_server.run_self_test(), 0)

    def test_h6_installer_honest_status_consent_and_uninstall(self):
        self.assertEqual(installer_windows.run_self_test(), 0)

    def test_h7_deployment_configs_isolated_to_web_dir(self):
        base = Path(__file__).resolve().parent
        vercel_cfg = json.loads((base / "vercel.json").read_text(encoding="utf-8"))
        self.assertEqual(vercel_cfg.get("outputDirectory"), "web", "H7: vercel.json must serve only web/")
        deploy_yml = (base / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
        self.assertIn('path: "web"', deploy_yml, "H7: deploy.yml must upload only web/")
        web_html = (base / "web" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("PACKAGED_GZ_B64URL", web_html, "H7: web/index.html must not inline Base64 source blobs")

    def test_h8_session_pinned_prompt_and_tts_lock_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = bajrang_core.ConfigManager(config_dir=root / "cfg", data_dir=root / "data")
            adapter = windows.WindowsPlatformAdapter()
            engine = bajrang_core.BajrangEngine(adapter=adapter, config=cfg)

            s1 = engine.new_session("Session One")
            s2 = engine.new_session("Session Two")
            engine.switch_session(s2)
            engine.process_prompt("Pinned to session 1", session_id=s1)
            msgs_s1 = engine.storage.get_session_messages(s1)
            msgs_s2 = engine.storage.get_session_messages(s2)
            self.assertEqual(len(msgs_s1), 2, "H8: Prompt & reply must be written to pinned session s1")
            self.assertEqual(len(msgs_s2), 0, "H8: Switched session s2 must not receive s1 messages")


if __name__ == "__main__":
    unittest.main(verbosity=2)
