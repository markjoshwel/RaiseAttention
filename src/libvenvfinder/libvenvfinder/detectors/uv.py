"""
uv virtual environment detector.
"""

from __future__ import annotations

from pathlib import Path

from ..models import ToolType, VenvInfo
from .utils import get_python_executable


def detect_uv(project_path: Path) -> VenvInfo | None:
    """detect uv virtual environment."""
    # uv uses .venv in project root (identified by uv.lock)
    if not project_path.joinpath("uv.lock").exists():
        return None

    venv_path = project_path.joinpath(".venv")
    if not venv_path.exists():
        return None

    python_exe = get_python_executable(venv_path)

    return VenvInfo(
        tool=ToolType.UV,
        venv_path=venv_path,
        python_executable=python_exe,
        python_version=None,
        is_valid=venv_path.exists() and python_exe is not None,
    )
