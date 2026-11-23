"""
SUDHARSHAN NATIVE — Original Synthetic Training & Evaluation Datasets.

100% original, non-copyrighted instruction & tool-call examples covering all 15
Sudharshan AI operational domains with strict JSON-schema tool-call outputs.
"""
from typing import Any, Dict, List

SUDHARSHAN_DOMAINS: List[str] = [
    "desktop_control",
    "file_organization",
    "safe_file_operations",
    "computer_diagnostics",
    "developer_assistance",
    "python_programming",
    "linux_commands",
    "windows_troubleshooting",
    "application_automation",
    "workflow_planning",
    "tool_selection",
    "contextual_conversation",
    "memory_retrieval",
    "system_monitoring",
    "voice_assistant_interaction",
]


def build_sudharshan_sft_dataset() -> List[Dict[str, Any]]:
    """Returns 15 structured domain-specific Sudharshan SFT examples."""
    return [
        {
            "domain": "desktop_control",
            "instruction": "List all open desktop windows right now.",
            "output": '{"type": "action", "text": "Listing active desktop windows.", "actions": [{"tool": "list_windows", "arguments": {}}]}',
        },
        {
            "domain": "file_organization",
            "instruction": "Organize my Downloads folder safely with preview.",
            "output": '{"type": "action", "text": "Preparing non-destructive Downloads organization plan.", "actions": [{"tool": "organize_directory", "arguments": {"directory_path": "~/Downloads"}}]}',
        },
        {
            "domain": "safe_file_operations",
            "instruction": "Inspect files in my project directory without modifying anything.",
            "output": '{"type": "action", "text": "Inspecting directory read-only.", "actions": [{"tool": "inspect_directory", "arguments": {"directory_path": "~/Projects"}}]}',
        },
        {
            "domain": "computer_diagnostics",
            "instruction": "Check why my laptop RAM is high and report free memory.",
            "output": '{"type": "conversation", "text": "Running local HardwareProfiler telemetry to inspect free RAM, swap, and top memory consumers without terminating protected processes."}',
        },
        {
            "domain": "developer_assistance",
            "instruction": "Summarize the latest git diff and propose a conventional commit.",
            "output": '{"type": "conversation", "text": "Inspecting staged diff via LocalGitAssistant to draft a conventional commit message."}',
        },
        {
            "domain": "python_programming",
            "instruction": "Fix a FileNotFoundError when loading a config file in Python.",
            "output": '{"type": "conversation", "text": "Use Path(cfg_path).is_file() before reading and create parent directories with mkdir(parents=True, exist_ok=True)."}',
        },
        {
            "domain": "linux_commands",
            "instruction": "Show a safe read-only Fedora command to check disk space.",
            "output": '{"type": "conversation", "text": "Run df -h for mounted filesystems or du -sh * for directory totals. Sudharshan never executes arbitrary shell commands automatically."}',
        },
        {
            "domain": "windows_troubleshooting",
            "instruction": "Local Ollama is returning WinError 10061 on Windows 11.",
            "output": '{"type": "conversation", "text": "Start the local daemon with ollama serve and confirm http://127.0.0.1:11434/api/tags responds with HTTP 200."}',
        },
        {
            "domain": "application_automation",
            "instruction": "Open the calculator app on my desktop.",
            "output": '{"type": "action", "text": "Launching calculator via zero-argument allowlist.", "actions": [{"tool": "open_app", "arguments": {"app_name": "calculator"}}]}',
        },
        {
            "domain": "workflow_planning",
            "instruction": "Plan a weekly Friday 6 PM backup of my Projects folder.",
            "output": '{"type": "conversation", "text": "Generated cron expression 0 18 * * 5 and systemd OnCalendar=Fri *-*-* 18:00:00 with dry-run preview enabled."}',
        },
        {
            "domain": "tool_selection",
            "instruction": "Run rm -rf / on my machine.",
            "output": '{"type": "conversation", "text": "Blocked by fail-closed SafetyGuard: destructive shell execution is permanently hard-blocked."}',
        },
        {
            "domain": "contextual_conversation",
            "instruction": "Explain how Sudharshan protects my privacy offline.",
            "output": '{"type": "conversation", "text": "All primary inference, SQLite RAG indexing, and audit logs stay 100% local with zero external bytes sent unless Cloud Burst is explicitly enabled."}',
        },
        {
            "domain": "memory_retrieval",
            "instruction": "Remember that I prefer the Precision Obsidian theme.",
            "output": '{"type": "action", "text": "Saving theme preference to local memory.", "actions": [{"tool": "memory_store", "arguments": {"key": "ui_theme_preference", "content": "User prefers Precision Obsidian theme"}}]}',
        },
        {
            "domain": "system_monitoring",
            "instruction": "Report current CPU, RAM, and battery health.",
            "output": '{"type": "conversation", "text": "Querying SystemThermalHUD for authentic local CPU count, free RAM, disk headroom, and thermal sensors."}',
        },
        {
            "domain": "voice_assistant_interaction",
            "instruction": "Switch voice mode to push-to-talk with spoken confirmation.",
            "output": '{"type": "conversation", "text": "Switched VoiceConversationController to push_to_talk and enabled SpokenConfirmationGate for elevated commands."}',
        },
    ]


def build_sudharshan_synthetic_corpus() -> List[str]:
    """Converts Sudharshan SFT records into chat-formatted training sequences."""
    docs: List[str] = []
    for item in build_sudharshan_sft_dataset():
        docs.append(
            f"<|system|>You are Sudharshan Native, a fail-closed local desktop AI.<|eos|>"
            f"<|user|>{item['instruction']}<|eos|>"
            f"<|assistant|>{item['output']}<|eos|>"
        )
    return docs
