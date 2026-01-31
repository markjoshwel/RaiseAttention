"""
utility functions for detectors.
"""

from __future__ import annotations

import sys
from pathlib import Path


def get_python_executable(venv_path: Path) -> Path | None:
    """
    get the python executable path for a virtual environment.

    handles cross-platform differences between windows and unix.

    arguments:
        venv_path: path to the virtual environment

    returns: path to python executable, or none if not found
    """
    if sys.platform == "win32":
        # windows: scripts/python.exe
        python_exe = venv_path.joinpath("Scripts", "python.exe")
    else:
        # unix: bin/python
        python_exe = venv_path.joinpath("bin", "python")

    if python_exe.exists():
        return python_exe

    return None
