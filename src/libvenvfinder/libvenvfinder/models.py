"""
models for libvenvfinder.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import final


class ToolType(Enum):
    """
    enumeration of supported python environment management tools.
    """

    POETRY = "poetry"
    PIPENV = "pipenv"
    PDM = "pdm"
    UV = "uv"
    RYE = "rye"
    HATCH = "hatch"
    VENV = "venv"
    PYENV = "pyenv"
    ENV_VAR = "env_var"


@final
@dataclass
class VenvInfo:
    """
    information about a detected python virtual environment.

    attributes:
        tool: the detected tool type
        venv_path: path to the virtual environment directory
        python_version: python version string (e.g., "3.10.5")
        python_executable: path to the python executable
        is_valid: whether the detected environment exists and is valid
    """

    tool: ToolType
    venv_path: Path | None
    python_executable: Path | None
    python_version: str | None
    is_valid: bool
