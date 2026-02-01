"""
models for libsoulsearching.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import final


class ToolType(Enum):
    """
    enumeration of supported python environment management tools.

    attributes:
        `POETRY: str`
            poetry package manager
        `PIPENV: str`
            pipenv package manager
        `PDM: str`
            pdm package manager
        `UV: str`
            uv package manager
        `RYE: str`
            rye package manager
        `HATCH: str`
            hatch package manager
        `VENV: str`
            standard venv module
        `PYENV: str`
            pyenv version manager
        `ENV_VAR: str`
            virtual environment from environment variable
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
        `tool: ToolType`
            the detected tool type
        `venv_path: Path | None`
            path to the virtual environment directory
        `python_executable: Path | None`
            path to the python executable
        `python_version: str | None`
            python version string (e.g., "3.10.5")
        `is_valid: bool`
            whether the detected environment exists and is valid
    """

    tool: ToolType
    venv_path: Path | None
    python_executable: Path | None
    python_version: str | None
    is_valid: bool
