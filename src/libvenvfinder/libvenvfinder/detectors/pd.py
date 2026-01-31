"""
pdm virtual environment detector.
"""

from __future__ import annotations

from pathlib import Path

from ..models import ToolType, VenvInfo
from .utils import get_python_executable


def detect_pdm(project_path: Path) -> VenvInfo | None:
    """
    detect pdm virtual environment.

    arguments:
        `project_path: Path`
            path to the project directory

    returns: `VenvInfo | None`
        venvinfo if pdm venv found, none otherwise
    """
    # Check for pdm.lock
    if not project_path.joinpath("pdm.lock").exists():
        return None

    # Check .pdm.toml for stored python path
    pdm_config = project_path.joinpath(".pdm.toml")
    if pdm_config.exists():
        try:
            import tomllib

            with open(pdm_config, "rb") as f:
                data = tomllib.load(f)
                python_path = data.get("python", {}).get("path")
                if python_path:
                    python_exe = Path(python_path)
                    venv_path = python_exe.parent.parent
                    return VenvInfo(
                        tool=ToolType.PDM,
                        venv_path=venv_path,
                        python_executable=python_exe,
                        python_version=None,
                        is_valid=python_exe.exists(),
                    )
        except Exception:
            pass

    # Fallback: check for in-project venv
    in_project_venv = project_path.joinpath(".venv")
    if in_project_venv.exists():
        python_exe = get_python_executable(in_project_venv)
        return VenvInfo(
            tool=ToolType.PDM,
            venv_path=in_project_venv,
            python_executable=python_exe,
            python_version=None,
            is_valid=python_exe is not None,
        )

    return None
