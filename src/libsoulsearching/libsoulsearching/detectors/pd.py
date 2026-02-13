"""
pdm virtual environment detector.
"""

from __future__ import annotations

from pathlib import Path

from ..models import ToolType, VenvInfo
from .utils import get_python_executable


def _get_nested_dict(parent: dict[str, object], key: str) -> dict[str, object] | None:
    """
    get a nested dict with proper type narrowing.

    pyright cannot infer nested dict types after isinstance checks on
    values from `dict[str, object].get()`, so this helper handles the
    type coercion explicitly.
    """
    value = parent.get(key)
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for k, v in value.items():  # pyright: ignore[reportUnknownVariableType]
            result[str(k)] = v  # pyright: ignore[reportUnknownArgumentType]
        return result
    return None


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
                data: dict[str, object] = tomllib.load(f)
                python_section = _get_nested_dict(data, "python")
                if python_section is not None:
                    python_path_raw = python_section.get("path")
                    if isinstance(python_path_raw, str) and python_path_raw:
                        pdm_python_exe = Path(python_path_raw)
                        venv_path = pdm_python_exe.parent.parent
                        return VenvInfo(
                            tool=ToolType.PDM,
                            venv_path=venv_path,
                            python_executable=pdm_python_exe,
                            python_version=None,
                            is_valid=pdm_python_exe.exists(),
                        )
        except Exception:
            pass

    # Fallback: check for in-project venv
    in_project_venv = project_path.joinpath(".venv")
    if in_project_venv.exists():
        venv_python_exe = get_python_executable(in_project_venv)
        return VenvInfo(
            tool=ToolType.PDM,
            venv_path=in_project_venv,
            python_executable=venv_python_exe,
            python_version=None,
            is_valid=venv_python_exe is not None,
        )

    return None
