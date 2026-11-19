#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from sudharshan.wave1_intelligence import HybridIntentRouter
from sudharshan.wave4_security_governance import IntegrityVerifier, ShellCommandSanitizer
from sudharshan.wave10_packaging_polish import SelfHealingDoctor


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
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
