"""
poetry virtual environment detector.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from ..models import ToolType, VenvInfo
from .utils import get_python_executable

if TYPE_CHECKING:
    pass


def detect_poetry(project_path: Path) -> VenvInfo | None:
    """
    detect poetry virtual environment.

    arguments:
        project_path: path to the project directory

    returns: VenvInfo if poetry venv found, None otherwise
    """
    # Check for poetry.lock
    if not (project_path.joinpath("poetry.lock")).exists():
        return None

    # Try to get venv path from poetry
    try:
        result = subprocess.run(
            ["poetry", "env", "info", "-p"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(project_path),
        )
        if result.returncode == 0:
            venv_path = Path(result.stdout.strip())
            python_exe = get_python_executable(venv_path)
            return VenvInfo(
                tool=ToolType.POETRY,
                venv_path=venv_path,
                python_executable=python_exe,
                python_version=None,
                is_valid=venv_path.exists() and python_exe is not None,
            )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Fallback: check for in-project venv
    in_project_venv = project_path.joinpath(".venv")
    if in_project_venv.exists():
        python_exe = get_python_executable(in_project_venv)
        return VenvInfo(
            tool=ToolType.POETRY,
            venv_path=in_project_venv,
            python_executable=python_exe,
            python_version=None,
            is_valid=python_exe is not None,
        )

    return None
