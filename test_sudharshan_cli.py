import contextlib
import io
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from sudharshan_cli import main


class TestSudharshanCLIWorkflows(unittest.TestCase):
    def invoke(self, args, stdin=""):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch("sys.stdin", io.StringIO(stdin)):
            result = main(args)
        return result, output.getvalue()

    def test_tasks_and_markdown_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "tasks.db"
            code, output = self.invoke(["tasks", "--db", str(db), "add", "Review", "urgent", "today"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)["priority"], "high")

            _, output = self.invoke(["tasks", "--db", str(db), "list", "--status", "pending"])
            self.assertEqual(len(json.loads(output)), 1)

            calendar_path = root / "tasks.ics"
            self.invoke(["tasks", "--db", str(db), "export", "--output", str(calendar_path)])
            self.assertIn("BEGIN:VCALENDAR", calendar_path.read_text(encoding="utf-8"))

            vault = root / "vault"
            vault.mkdir()
            (vault / "one.md").write_text("See [[Two]].", encoding="utf-8")
            (vault / "two.md").write_text("A linked note.", encoding="utf-8")
            _, output = self.invoke(["vault", str(vault)])
            graph = json.loads(output)
            self.assertEqual((graph["node_count"], graph["edge_count"]), (2, 1))

    def test_git_status_and_symbol_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            _, output = self.invoke(["git", "--repo", str(root), "--suggest-commit"])
            self.assertIn("commit_suggestion", json.loads(output))

            (root / "module.py").write_text("class LocalIndex:\n    pass\n", encoding="utf-8")
            _, output = self.invoke(["symbols", "LocalIndex", "--root", str(root)])
            matches = json.loads(output)["matches"]
            self.assertEqual(matches[0]["name"], "LocalIndex")

    def test_redaction_archive_and_duplicate_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, redacted = self.invoke(["redact"], "token sk-" + "a" * 24)
            self.assertNotIn("sk-" + "a" * 24, redacted)
            self.assertIn("[REDACTED_API_KEY]", redacted)

            archive = root / "files.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("note.txt", "local")
            _, output = self.invoke(["archive-inspect", str(archive)])
            self.assertEqual(json.loads(output)[0]["name"], "note.txt")

            duplicate_dir = root / "duplicates"
            duplicate_dir.mkdir()
            (duplicate_dir / "a.txt").write_text("same", encoding="utf-8")
            (duplicate_dir / "b.txt").write_text("same", encoding="utf-8")
            _, output = self.invoke(["dedupe-report", str(duplicate_dir)])
            self.assertEqual(json.loads(output)["duplicates_found"], 1)

    def test_disk_schedule_and_organize_previews(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "__pycache__"
            cache.mkdir()
            (cache / "cache.pyc").write_bytes(b"cache")
            _, output = self.invoke(["disk-report", str(root)])
            self.assertEqual(json.loads(output)[0]["target_type"], "pycache")

            _, output = self.invoke([
                "schedule-preview", "every 15 minutes", "--command", "python backup.py"
            ])
            schedule = json.loads(output)
            self.assertEqual(schedule["cron"], "*/15 * * * *")
            self.assertFalse(schedule["executed"])

            (root / "report.pdf").write_text("document", encoding="utf-8")
            _, output = self.invoke(["organize-preview", str(root)])
            preview = json.loads(output)
            self.assertEqual(preview["moves"], 1)
            self.assertFalse(preview["changed_files"])
            self.assertTrue((root / "report.pdf").is_file())

    def test_schedule_rejects_unsupported_description(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            main(["schedule-preview", "sometime next week", "--command", "echo ready"])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
