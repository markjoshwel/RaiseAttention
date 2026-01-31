"""
standard venv virtual environment detector.
"""

from __future__ import annotations

from pathlib import Path

from ..models import ToolType, VenvInfo
from .utils import get_python_executable


def detect_venv(project_path: Path) -> VenvInfo | None:
    """detect standard venv virtual environment."""
    # Check for .venv with pyvenv.cfg
    venv_path = project_path.joinpath(".venv")
    pyvenv_cfg = venv_path.joinpath("pyvenv.cfg")

    if not pyvenv_cfg.exists():
        return None

    python_exe = get_python_executable(venv_path)

    return VenvInfo(
        tool=ToolType.VENV,
        venv_path=venv_path,
        python_executable=python_exe,
        python_version=None,
        is_valid=venv_path.exists() and python_exe is not None,
    )
