"""
conftest for libvenvfinder tests.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from unittest import mock

import pytest


def get_tool_path(tool_name: str) -> str | None:
    """get tool binary path from nix env or system path.

    checks nix-provided env vars first, then falls back to system path.

    arguments:
        `tool_name: str`
            name of the tool (e.g., 'poetry', 'pipenv')

    returns: `str | None`
        path to binary or none if not found
    """
    # check nix env vars first (set by flake.nix)
    nix_var = f"{tool_name.upper()}_BINARY"
    if nix_path := os.environ.get(nix_var):
        if Path(nix_path).exists():
            return nix_path

    # fall back to system path
    return shutil.which(tool_name)


def has_tool(tool_name: str) -> bool:
    """check if a tool is available.

    arguments:
        `tool_name: str`
            name of the tool to check

    returns: `bool`
        true if tool is available
    """
    return get_tool_path(tool_name) is not None


# pytest markers for tool availability
requires_poetry = pytest.mark.skipif(not has_tool("poetry"), reason="poetry not available")
requires_pipenv = pytest.mark.skipif(not has_tool("pipenv"), reason="pipenv not available")
requires_pdm = pytest.mark.skipif(not has_tool("pdm"), reason="pdm not available")
requires_uv = pytest.mark.skipif(not has_tool("uv"), reason="uv not available")
requires_rye = pytest.mark.skipif(not has_tool("rye"), reason="rye not available")
requires_hatch = pytest.mark.skipif(not has_tool("hatch"), reason="hatch not available")
requires_pyenv = pytest.mark.skipif(not has_tool("pyenv"), reason="pyenv not available")


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
