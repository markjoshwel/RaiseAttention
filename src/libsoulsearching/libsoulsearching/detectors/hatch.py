"""
hatch virtual environment detector.
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
            data: dict[str, object] = tomllib.load(f)
            tool_section = _get_nested_dict(data, "tool")
            if tool_section is None:
                return None
            hatch_section = _get_nested_dict(tool_section, "hatch")
            if hatch_section is None:
                return None
            envs = _get_nested_dict(hatch_section, "envs")
            if envs is None or len(envs) == 0:
                return None

            default_env = _get_nested_dict(envs, "default")
            if default_env is None:
                venv_path_str = ".venv"
            else:
                path_val = default_env.get("path", ".venv")
                venv_path_str = str(path_val) if path_val else ".venv"
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
