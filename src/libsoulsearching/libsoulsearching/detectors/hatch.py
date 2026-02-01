"""
hatch virtual environment detector.
"""

from __future__ import annotations

from pathlib import Path

from ..models import ToolType, VenvInfo
from .utils import get_python_executable


def detect_hatch(project_path: Path) -> VenvInfo | None:
    """
    detect hatch virtual environment.

    arguments:
        `project_path: Path`
            path to the project directory

    returns: `VenvInfo | None`
        venvinfo if hatch venv found, none otherwise
    """
    # Check pyproject.toml for hatch config
    pyproject = project_path.joinpath("pyproject.toml")
    if not pyproject.exists():
        return None

    try:
        import tomllib

        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
            envs = data.get("tool", {}).get("hatch", {}).get("envs", {})  # pyright: ignore[reportAny]
            if not envs:
                return None

            default_env = envs.get("default", {})  # pyright: ignore[reportAny]
            venv_path_str = default_env.get("path", ".venv")  # pyright: ignore[reportAny]
            venv_path = project_path.joinpath(venv_path_str)

            if not venv_path.is_absolute():
                venv_path = venv_path.resolve()

            python_exe = get_python_executable(venv_path)

            return VenvInfo(
                tool=ToolType.HATCH,
                venv_path=venv_path,
                python_executable=python_exe,
                python_version=None,
                is_valid=venv_path.exists() and python_exe is not None,
            )
    except Exception:
        pass

    return None
