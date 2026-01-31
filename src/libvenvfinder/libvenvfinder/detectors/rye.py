"""
rye virtual environment detector.
"""

from __future__ import annotations

from pathlib import Path

from ..models import ToolType, VenvInfo
from .utils import get_python_executable


def detect_rye(project_path: Path) -> VenvInfo | None:
    """
    detect rye virtual environment.

    arguments:
        `project_path: Path`
            path to the project directory

    returns: `VenvInfo | None`
        venvinfo if rye venv found, none otherwise
    """
    # rye uses .venv in project root (identified by rye.lock or .python-version)
    has_rye_lock = project_path.joinpath("rye.lock").exists()
    has_python_version = project_path.joinpath(".python-version").exists()

    if not (has_rye_lock or has_python_version):
        return None

    # Try local .venv first
    venv_path = project_path.joinpath(".venv")
    if venv_path.exists():
        python_exe = get_python_executable(venv_path)
    else:
        # Rye may use pyenv-managed Python if no local .venv
        # Check for pyenv python with matching version
        python_version = None
        version_file = project_path.joinpath(".python-version")
        if version_file.exists():
            try:
                python_version = version_file.read_text().strip()
            except OSError:
                pass

        if python_version:
            import os

            pyenv_root = os.environ.get("PYENV_ROOT", "~/.pyenv")
            pyenv_root_path = Path(pyenv_root).expanduser()
            pyenv_venv = pyenv_root_path.joinpath("versions", python_version)
            print(f"DEBUG RYE: Looking for pyenv venv at: {pyenv_venv}")
            print(f"DEBUG RYE: PYENV_ROOT={os.environ.get('PYENV_ROOT', 'NOT SET')}")
            print(f"DEBUG RYE: HOME={os.environ.get('HOME', 'NOT SET')}")
            print(f"DEBUG RYE: Path exists: {pyenv_venv.exists()}")
            if pyenv_venv.exists():
                venv_path = pyenv_venv
                python_exe = get_python_executable(venv_path)
            else:
                return None
        else:
            return None

    # Try to get python version from .python-version file
    python_version = None
    version_file = project_path.joinpath(".python-version")
    if version_file.exists():
        try:
            python_version = version_file.read_text().strip()
        except OSError:
            pass

    return VenvInfo(
        tool=ToolType.RYE,
        venv_path=venv_path,
        python_executable=python_exe,
        python_version=python_version,
        is_valid=venv_path.exists() and python_exe is not None,
    )
