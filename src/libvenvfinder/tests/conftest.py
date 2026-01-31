"""
conftest for libvenvfinder tests.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def clear_virtual_env():
    """clear VIRTUAL_ENV to avoid detecting the test runner's venv."""
    with mock.patch.dict(os.environ, {"VIRTUAL_ENV": ""}, clear=False):
        yield


@pytest.fixture
def empty_project(tmp_path: Path) -> Path:
    """create an empty project directory."""
    return tmp_path


@pytest.fixture
def poetry_project(tmp_path: Path) -> Path:
    """create a mock poetry project."""
    (tmp_path / "poetry.lock").write_text("")
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("")
    return tmp_path


@pytest.fixture
def pipenv_project(tmp_path: Path) -> Path:
    """create a mock pipenv project."""
    (tmp_path / "Pipfile.lock").write_text("")
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("")
    return tmp_path


@pytest.fixture
def pdm_project(tmp_path: Path) -> Path:
    """create a mock pdm project."""
    (tmp_path / "pdm.lock").write_text("")
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("")
    return tmp_path


@pytest.fixture
def uv_project(tmp_path: Path) -> Path:
    """create a mock uv project."""
    (tmp_path / "uv.lock").write_text("")
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("")
    return tmp_path


@pytest.fixture
def rye_project(tmp_path: Path) -> Path:
    """create a mock rye project."""
    (tmp_path / "rye.lock").write_text("")
    (tmp_path / ".python-version").write_text("3.10.5")
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("")
    return tmp_path


@pytest.fixture
def hatch_project(tmp_path: Path) -> Path:
    """create a mock hatch project."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("""
[tool.hatch.envs.default]
type = "virtual"
""")
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("")
    return tmp_path


@pytest.fixture
def venv_project(tmp_path: Path) -> Path:
    """create a mock standard venv project."""
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("")
    return tmp_path


@pytest.fixture
def pyenv_project(tmp_path: Path) -> Path:
    """create a mock pyenv project."""
    (tmp_path / ".python-version").write_text("3.10.5")
    return tmp_path
