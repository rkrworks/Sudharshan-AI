#!/usr/bin/env python3
import argparse
import dataclasses
import json
import re
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from sudharshan.wave1_intelligence import HybridIntentRouter
from sudharshan.wave4_security_governance import IntegrityVerifier, ShellCommandSanitizer
from sudharshan.wave10_packaging_polish import SelfHealingDoctor
from sudharshan.core.developer import CodebaseSymbolIndexer, LocalGitAssistant
from sudharshan.core.desktop import CronSystemdTimerGenerator
from sudharshan.core.fs_automation import (
    BatchFileOrganizer,
    DeduplicationSweepEngine,
    DiskSpaceAnalyzer,
    NaturalArchiveManager,
)
from sudharshan.core.productivity import MarkdownKnowledgeVault, NaturalLanguageTaskManager
from sudharshan.core.security import SecretPIIRedactor


def _print_json(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _valid_schedule_description(description: str) -> bool:
    text = description.strip().lower()
    if text in {"every hour", "every 15 minutes", "every friday at 6 pm"}:
        return True
    match = re.fullmatch(r"(?:every day at|daily at)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if not match:
        return False
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if minute > 59:
        return False
    return 1 <= hour <= 12 if match.group(3) else 0 <= hour <= 23


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sudharshan", description="Sudharshan AI CLI Companion")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ask = sub.add_parser("ask", help="Classify and route a local prompt")
    p_ask.add_argument("prompt", nargs="+")

    sub.add_parser("pipe", help="Read stdin and route through Sudharshan local intent router")

    p_run = sub.add_parser("run", help="Sanitize and preview a shell command (fail-closed)")
    p_run.add_argument("command", nargs="+")

    sub.add_parser("doctor", help="Run self-healing diagnostics")

    p_ver = sub.add_parser("verify", help="Verify SHA256SUMS manifest")
    p_ver.add_argument("--root", default=".")
    p_ver.add_argument("--manifest", default="SHA256SUMS")

    p_tasks = sub.add_parser("tasks", help="Manage local tasks and export pending tasks to iCalendar")
    p_tasks.add_argument("--db", help="SQLite database path (defaults to the local temporary data directory)")
    task_sub = p_tasks.add_subparsers(dest="task_action", required=True)
    p_task_add = task_sub.add_parser("add", help="Add a task from plain text")
    p_task_add.add_argument("text", nargs="+")
    p_task_list = task_sub.add_parser("list", help="List local tasks")
    p_task_list.add_argument("--status", choices=("pending", "in_progress", "completed"))
    p_task_export = task_sub.add_parser("export", help="Export pending tasks as iCalendar")
    p_task_export.add_argument("--output", type=Path, help="Write the calendar to this path instead of stdout")

    p_vault = sub.add_parser("vault", help="Index Markdown notes and show wikilink backlinks")
    p_vault.add_argument("directory", type=Path)

    p_git = sub.add_parser("git", help="Show local repository status and an optional commit suggestion")
    p_git.add_argument("--repo", type=Path, default=Path("."))
    p_git.add_argument("--suggest-commit", action="store_true")

    p_symbols = sub.add_parser("symbols", help="Search code symbols in a local codebase")
    p_symbols.add_argument("query")
    p_symbols.add_argument("--root", type=Path, default=Path("."))

    sub.add_parser("redact", help="Redact recognized secrets from text read on stdin")

    p_archive = sub.add_parser("archive-inspect", help="List archive entries without extracting files")
    p_archive.add_argument("archive", type=Path)

    p_dedupe = sub.add_parser("dedupe-report", help="Report identical files without changing them")
    p_dedupe.add_argument("directory", type=Path)

    p_disk = sub.add_parser("disk-report", help="Find reclaimable build and language caches")
    p_disk.add_argument("directory", type=Path)

    p_schedule = sub.add_parser("schedule-preview", help="Preview a supported cron schedule; never installs or runs it")
    p_schedule.add_argument("description", help="For example: 'every 15 minutes' or 'daily at 18:30'")
    p_schedule.add_argument("--command", required=True, help="Command text to include in the generated cron line")

    p_organize = sub.add_parser("organize-preview", help="Preview extension-based file moves without changing files")
    p_organize.add_argument("directory", type=Path)

    args = parser.parse_args(argv)
    if args.cmd == "ask":
        prompt = " ".join(args.prompt)
        print(json.dumps(HybridIntentRouter().classify(prompt), indent=2))
        return 0
    if args.cmd == "pipe":
        data = sys.stdin.read().strip()
        print(json.dumps(HybridIntentRouter().classify(data), indent=2))
        return 0
    if args.cmd == "run":
        cmd = " ".join(args.command)
        ok, detail = ShellCommandSanitizer.inspect(cmd)
        print(json.dumps({"command": cmd, "safe": ok, "detail": detail}, indent=2))
        return 0 if ok else 2
    if args.cmd == "doctor":
        report = SelfHealingDoctor.run_checks(Path.home() / ".bajrang_ai")
        print(json.dumps(report, indent=2))
        return 0 if report["healthy"] else 1
    if args.cmd == "verify":
        root = Path(args.root)
        manifest_path = root / args.manifest
        ok, failures = IntegrityVerifier.verify_manifest(root, manifest_path.read_text(encoding="utf-8"))
        print(json.dumps({"verified": ok, "failures": failures}, indent=2))
        return 0 if ok else 1
    if args.cmd == "tasks":
        manager = NaturalLanguageTaskManager(db_path=str(args.db) if args.db else None)
        if args.task_action == "add":
            text = " ".join(args.text).strip()
            if not text:
                parser.error("task text cannot be empty")
            task = manager.add_task_from_nl(text)
            _print_json(dataclasses.asdict(task))
        elif args.task_action == "list":
            _print_json([dataclasses.asdict(task) for task in manager.list_tasks(args.status)])
        else:
            calendar = manager.export_to_ics()
            if args.output:
                args.output.write_text(calendar, encoding="utf-8")
                _print_json({"written": str(args.output), "pending_tasks": len(manager.list_tasks("pending"))})
            else:
                print(calendar)
        return 0
    if args.cmd == "vault":
        if not args.directory.is_dir():
            parser.error(f"not a directory: {args.directory}")
        graph = MarkdownKnowledgeVault(str(args.directory)).index_vault()
        _print_json({"node_count": len(graph.nodes), "edge_count": len(graph.edges), **dataclasses.asdict(graph)})
        return 0
    if args.cmd == "git":
        if not args.repo.is_dir():
            parser.error(f"not a directory: {args.repo}")
        assistant = LocalGitAssistant(str(args.repo))
        status = assistant.get_status()
        if status.branch == "unknown":
            parser.error(f"could not read Git status for {args.repo}")
        result = dataclasses.asdict(status)
        if args.suggest_commit:
            result["commit_suggestion"] = assistant.generate_conventional_commit()
        _print_json(result)
        return 0
    if args.cmd == "symbols":
        if not args.root.is_dir():
            parser.error(f"not a directory: {args.root}")
        indexer = CodebaseSymbolIndexer(str(args.root))
        total = indexer.index_codebase()
        matches = indexer.search_symbols(args.query)
        _print_json({
            "indexed_symbols": total,
            "query": args.query,
            "matches": [dataclasses.asdict(symbol) for symbol in matches],
        })
        return 0
    if args.cmd == "redact":
        print(SecretPIIRedactor.redact(sys.stdin.read()), end="")
        return 0
    if args.cmd == "archive-inspect":
        if not args.archive.is_file():
            parser.error(f"not a file: {args.archive}")
        if not args.archive.name.lower().endswith((".zip", ".tar", ".tar.gz", ".tar.xz")):
            parser.error("supported archive types are .zip, .tar, .tar.gz, and .tar.xz")
        try:
            entries = NaturalArchiveManager.inspect_archive(str(args.archive))
        except (OSError, tarfile.TarError, zipfile.BadZipFile) as error:
            parser.error(f"could not inspect archive: {error}")
        _print_json(entries)
        return 0
    if args.cmd == "dedupe-report":
        if not args.directory.is_dir():
            parser.error(f"not a directory: {args.directory}")
        result = DeduplicationSweepEngine().run_sweep(str(args.directory), action="report")
        _print_json(result)
        return 0
    if args.cmd == "disk-report":
        if not args.directory.is_dir():
            parser.error(f"not a directory: {args.directory}")
        targets = DiskSpaceAnalyzer.scan_reclaimable_space(str(args.directory))
        _print_json([dataclasses.asdict(target) for target in targets])
        return 0
    if args.cmd == "schedule-preview":
        if not _valid_schedule_description(args.description):
            parser.error("unsupported schedule; use every hour, every 15 minutes, every Friday at 6 pm, or a daily time such as 'daily at 18:30'")
        expression, line = CronSystemdTimerGenerator.generate_cron(args.description, args.command)
        if expression is None:
            parser.error("the schedule could not be converted")
        _print_json({"cron": expression, "line": line, "installed": False, "executed": False})
        return 0
    if args.cmd == "organize-preview":
        if not args.directory.is_dir():
            parser.error(f"not a directory: {args.directory}")
        with tempfile.TemporaryDirectory(prefix="sudharshan-preview-") as undo_dir:
            organizer = BatchFileOrganizer(undo_dir=undo_dir)
            plan = organizer.create_plan_by_extension(str(args.directory))
            _print_json({"preview": organizer.render_dry_run_tree(plan), "moves": len(plan.operations), "changed_files": False})
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
