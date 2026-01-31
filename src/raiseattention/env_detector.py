"""
virtual environment detection for raiseattention.

this module re-exports libvenvfinder with compatibility aliases for raiseattention.
"""

from __future__ import annotations

# Re-export everything from libvenvfinder
from libvenvfinder import (
    ToolType,
    VenvInfo,
    find_venv,
    find_all_venvs,
)

# Compatibility alias
EnvironmentInfo = VenvInfo

detect_environment = find_venv

__all__ = [
    "ToolType",
    "VenvInfo",
    "EnvironmentInfo",  # compatibility alias
    "find_venv",
    "find_all_venvs",
    "detect_environment",  # compatibility alias
]
