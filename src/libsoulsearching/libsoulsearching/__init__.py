"""
universal python virtual environment finder.

libsoulsearching detects virtual environments created by various python tools
including poetry, pipenv, pdm, uv, rye, hatch, standard venv, and pyenv.

functions:
    `def find_venv(project_root: str | Path, tool: ToolType | None = None) -> VenvInfo | None`
        find a virtual environment in the given project directory
    `def find_all_venvs(project_root: str | Path) -> list[VenvInfo]`
        find all virtual environments in the given project directory
"""

from __future__ import annotations

from .core import find_venv, find_all_venvs
from .models import ToolType, VenvInfo

__version__ = "0.1.0"
__all__ = [
    "find_venv",
    "find_all_venvs",
    "ToolType",
    "VenvInfo",
]
