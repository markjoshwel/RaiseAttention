"""
rye virtual environment detector.
"""

from __future__ import annotations

from pathlib import Path

from ..models import ToolType, VenvInfo
from .utils import get_python_executable


def detect_rye(project_path: Path) -> VenvInfo | None:
    """detect rye virtual environment."""
    # rye uses .venv in project root (identified by rye.lock or .python-version)
    has_rye_lock = project_path.joinpath("rye.lock").exists()
    has_python_version = project_path.joinpath(".python-version").exists()

    if not (has_rye_lock or has_python_version):
        return None

    venv_path = project_path.joinpath(".venv")
    if not venv_path.exists():
        return None

    python_exe = get_python_executable(venv_path)

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
