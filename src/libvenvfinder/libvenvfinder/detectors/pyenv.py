"""
pyenv virtual environment detector.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..models import ToolType, VenvInfo
from .utils import get_python_executable


def detect_pyenv(project_path: Path) -> VenvInfo | None:
    """
    detect pyenv environment.

    arguments:
        `project_path: Path`
            path to the project directory

    returns: `VenvInfo | None`
        venvinfo if pyenv environment found, none otherwise
    """
    # Check for .python-version file
    version_file = project_path.joinpath(".python-version")
    if not version_file.exists():
        return None

    # If there's a local .venv directory, another tool is managing it
    # defer to that tool instead of claiming it as pyenv
    if project_path.joinpath(".venv").exists():
        return None

    try:
        python_version = version_file.read_text().strip()

        pyenv_root = os.environ.get("PYENV_ROOT", "~/.pyenv")
        pyenv_root_path = Path(pyenv_root).expanduser()
        venv_path = pyenv_root_path.joinpath("versions", python_version)

        python_exe = get_python_executable(venv_path)

        return VenvInfo(
            tool=ToolType.PYENV,
            venv_path=venv_path,
            python_executable=python_exe,
            python_version=python_version,
            is_valid=venv_path.exists() and python_exe is not None,
        )
    except OSError:
        pass

    return None
