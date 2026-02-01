"""
detectors for various python environment management tools.

functions:
    `def detect_poetry(project_path: Path) -> VenvInfo | None`
        detect poetry virtual environment
    `def detect_pipenv(project_path: Path) -> VenvInfo | None`
        detect pipenv virtual environment
    `def detect_pdm(project_path: Path) -> VenvInfo | None`
        detect pdm virtual environment
    `def detect_uv(project_path: Path) -> VenvInfo | None`
        detect uv virtual environment
    `def detect_rye(project_path: Path) -> VenvInfo | None`
        detect rye virtual environment
    `def detect_hatch(project_path: Path) -> VenvInfo | None`
        detect hatch virtual environment
    `def detect_venv(project_path: Path) -> VenvInfo | None`
        detect standard venv virtual environment
    `def detect_pyenv(project_path: Path) -> VenvInfo | None`
        detect pyenv environment
"""

from __future__ import annotations

from .hatch import detect_hatch
from .pd import detect_pdm
from .pipenv import detect_pipenv
from .poetry import detect_poetry
from .pyenv import detect_pyenv
from .rye import detect_rye
from .uv import detect_uv
from .venv import detect_venv

__all__ = [
    "detect_poetry",
    "detect_pipenv",
    "detect_pdm",
    "detect_uv",
    "detect_rye",
    "detect_hatch",
    "detect_venv",
    "detect_pyenv",
]
