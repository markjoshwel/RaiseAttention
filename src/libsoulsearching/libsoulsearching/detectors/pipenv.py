"""
pipenv virtual environment detector.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..models import ToolType, VenvInfo
from .utils import get_python_executable


def detect_pipenv(project_path: Path) -> VenvInfo | None:
    """
    detect pipenv virtual environment.

    arguments:
        `project_path: Path`
            path to the project directory

    returns: `VenvInfo | None`
        venvinfo if pipenv venv found, none otherwise
    """
    # Check for Pipfile.lock
    if not project_path.joinpath("Pipfile.lock").exists():
        return None

    # Try to get venv path from pipenv
    try:
        result = subprocess.run(
            ["pipenv", "--venv"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(project_path),
        )
        if result.returncode == 0:
            venv_path = Path(result.stdout.strip())
            python_exe = get_python_executable(venv_path)
            return VenvInfo(
                tool=ToolType.PIPENV,
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
            tool=ToolType.PIPENV,
            venv_path=in_project_venv,
            python_executable=python_exe,
            python_version=None,
            is_valid=python_exe is not None,
        )

    return None
