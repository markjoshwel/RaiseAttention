"""
core detection logic for libvenvfinder.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from .detectors import (
    detect_hatch,
    detect_pdm,
    detect_pipenv,
    detect_poetry,
    detect_pyenv,
    detect_rye,
    detect_uv,
    detect_venv,
)
from .models import ToolType, VenvInfo

if TYPE_CHECKING:
    pass

# Priority order for detection (first match wins)
DETECTION_ORDER = [
    ToolType.POETRY,
    ToolType.PIPENV,
    ToolType.PDM,
    ToolType.UV,
    ToolType.RYE,
    ToolType.HATCH,
    ToolType.VENV,
    ToolType.PYENV,
]

# Map tool types to detector functions
DETECTORS = {
    ToolType.POETRY: detect_poetry,
    ToolType.PIPENV: detect_pipenv,
    ToolType.PDM: detect_pdm,
    ToolType.UV: detect_uv,
    ToolType.RYE: detect_rye,
    ToolType.HATCH: detect_hatch,
    ToolType.VENV: detect_venv,
    ToolType.PYENV: detect_pyenv,
}


def find_venv(project_root: str | Path, tool: ToolType | None = None) -> VenvInfo | None:
    """
    find a virtual environment in the given project directory.

    arguments:
        `project_root: str | Path`
            path to the project directory
        `tool: ToolType | None`
            specific tool to detect. if None, uses priority order.

    returns: `VenvInfo | None`
        venvinfo if a venv is found, None otherwise
    """
    project_path = Path(project_root)

    if not project_path.exists():
        return None

    # If specific tool requested, only check that one
    if tool is not None:
        detector = DETECTORS.get(tool)
        if detector:
            return detector(project_path)
        return None

    # Check in priority order
    for tool_type in DETECTION_ORDER:
        detector = DETECTORS.get(tool_type)
        if detector:
            result = detector(project_path)
            if result is not None:
                return result

    # Check for currently activated environment
    venv_env = os.environ.get("VIRTUAL_ENV")
    if venv_env:
        venv_path = Path(venv_env)
        from .detectors.utils import get_python_executable

        python_exe = get_python_executable(venv_path)
        return VenvInfo(
            tool=ToolType.ENV_VAR,
            venv_path=venv_path,
            python_executable=python_exe,
            python_version=None,
            is_valid=venv_path.exists(),
        )

    return None


def find_all_venvs(project_root: str | Path) -> list[VenvInfo]:
    """
    find all virtual environments in the given project directory.

    returns all detected venvs in priority order, including potentially
    invalid ones (is_valid=False) if the tool's marker files exist but
    the actual venv is missing.

    arguments:
        `project_root: str | Path`
            path to the project directory

    returns: `list[VenvInfo]`
        list of venvinfo objects (may be empty)
    """
    project_path = Path(project_root)
    results: list[VenvInfo] = []

    if not project_path.exists():
        return results

    # Check all detectors
    for tool_type in DETECTION_ORDER:
        detector = DETECTORS.get(tool_type)
        if detector:
            result = detector(project_path)
            if result is not None:
                results.append(result)

    # Check for currently activated environment
    venv_env = os.environ.get("VIRTUAL_ENV")
    if venv_env:
        venv_path = Path(venv_env)
        # Check if it's already in results
        if not any(str(r.venv_path) == str(venv_path) for r in results):
            from .detectors.utils import get_python_executable

            python_exe = get_python_executable(venv_path)
            results.append(
                VenvInfo(
                    tool=ToolType.ENV_VAR,
                    venv_path=venv_path,
                    python_executable=python_exe,
                    python_version=None,
                    is_valid=venv_path.exists(),
                )
            )

    return results
