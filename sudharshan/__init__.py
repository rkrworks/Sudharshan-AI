"""Sudharshan AI - Enterprise Core Package
Precision Obsidian & Solar Orange local-first agentic architecture.
Provides full backward and forward compatibility across Waves 1-10 modules
and the modular core engine.
"""

from . import (
    wave1_intelligence,
    wave2_memory_rag,
    wave3_voice_multimodal,
    wave4_security_governance,
    wave5_filesystem_automation,
    wave6_os_ergonomics,
    wave7_developer_suite,
    wave8_productivity,
    wave9_extensibility,
    wave10_packaging_polish,
)

try:
    from . import core
except ImportError:
    core = None

__version__ = "1.0.0"
__author__ = "Kaushik Ram Ravuru"

__all__ = [
    "wave1_intelligence",
    "wave2_memory_rag",
    "wave3_voice_multimodal",
    "wave4_security_governance",
    "wave5_filesystem_automation",
    "wave6_os_ergonomics",
    "wave7_developer_suite",
    "wave8_productivity",
    "wave9_extensibility",
    "wave10_packaging_polish",
    "core",
]
