"""
tests for the environment detector module.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from raiseattention.env_detector import (
    EnvironmentInfo,
    ToolType,
    _detect_hatch,
    _detect_pdm,
    _detect_poetry,
    _detect_pyenv,
    _detect_venv,
    _get_python_executable,
    _is_hatch_project,
    detect_environment,
)


class TestEnvironmentInfo:
    """tests for the EnvironmentInfo dataclass."""

    def test_init(self) -> None:
        """test basic initialisation."""
        info = EnvironmentInfo(ToolType.POETRY)
        assert info.tool == ToolType.POETRY
        assert info.venv_path is None
        assert info.is_valid is False

    def test_to_dict(self) -> None:
        """test conversion to dictionary."""
        info = EnvironmentInfo(
            tool=ToolType.POETRY,
            venv_path=Path("/path/to/venv"),
            python_version="3.10.5",
            is_valid=True,
        )

        result = info.to_dict()

        assert result["tool"] == "poetry"
        assert result["venv_path"] == str(Path("/path/to/venv"))
        assert result["python_version"] == "3.10.5"
        assert result["is_valid"] is True


class TestDetectEnvironment:
    """tests for the detect_environment function."""

    def test_nonexistent_path(self) -> None:
        """test detection with non-existent path."""
        result = detect_environment("/nonexistent/path")
        assert result.tool == ToolType.UNKNOWN

    def test_poetry_detection(self, tmp_path: Path) -> None:
        """test poetry environment detection via lock file."""
        # create poetry.lock file
        (tmp_path / "poetry.lock").write_text("")

        with mock.patch("raiseattention.env_detector._detect_poetry") as mock_detect:
            mock_detect.return_value = EnvironmentInfo(ToolType.POETRY)
            result = detect_environment(tmp_path)

        assert result.tool == ToolType.POETRY

    def test_pipenv_detection(self, tmp_path: Path) -> None:
        """test pipenv environment detection via lock file."""
        # create Pipfile.lock file
        (tmp_path / "Pipfile.lock").write_text("")

        with mock.patch("raiseattention.env_detector._detect_pipenv") as mock_detect:
            mock_detect.return_value = EnvironmentInfo(ToolType.PIPENV)
            result = detect_environment(tmp_path)

        assert result.tool == ToolType.PIPENV

    def test_pdm_detection(self, tmp_path: Path) -> None:
        """test pdm environment detection via lock file."""
        # create pdm.lock file
        (tmp_path / "pdm.lock").write_text("")

        with mock.patch("raiseattention.env_detector._detect_pdm") as mock_detect:
            mock_detect.return_value = EnvironmentInfo(ToolType.PDM)
            result = detect_environment(tmp_path)

        assert result.tool == ToolType.PDM

    def test_uv_detection(self, tmp_path: Path) -> None:
        """test uv environment detection."""
        # create uv.lock and .venv directory
        (tmp_path / "uv.lock").write_text("")
        (tmp_path / ".venv").mkdir()

        result = detect_environment(tmp_path)

        assert result.tool == ToolType.UV

    def test_rye_detection(self, tmp_path: Path) -> None:
        """test rye environment detection."""
        # create rye.lock and .venv directory
        (tmp_path / "rye.lock").write_text("")
        (tmp_path / ".venv").mkdir()

        result = detect_environment(tmp_path)

        assert result.tool == ToolType.RYE

    def test_venv_detection(self, tmp_path: Path) -> None:
        """test standard venv detection."""
        # create .venv with pyvenv.cfg
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        (venv_dir / "pyvenv.cfg").write_text("")

        result = detect_environment(tmp_path)

        assert result.tool == ToolType.VENV

    def test_pyenv_detection(self, tmp_path: Path) -> None:
        """test pyenv detection via .python-version."""
        # create .python-version file
        (tmp_path / ".python-version").write_text("3.10.5")

        with mock.patch("raiseattention.env_detector._detect_pyenv") as mock_detect:
            mock_detect.return_value = EnvironmentInfo(ToolType.PYENV)
            result = detect_environment(tmp_path)

        assert result.tool == ToolType.PYENV

    def test_virtual_env_variable(self, tmp_path: Path) -> None:
        """test detection via VIRTUAL_ENV environment variable."""
        with mock.patch.dict(os.environ, {"VIRTUAL_ENV": str(tmp_path)}):
            result = detect_environment(tmp_path)

        assert result.tool == ToolType.UNKNOWN
        assert result.venv_path == tmp_path


class TestHelperFunctions:
    """tests for helper functions."""

    def test_is_hatch_project_true(self, tmp_path: Path) -> None:
        """test hatch project detection with valid config."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[tool.hatch.envs.default]
type = "virtual"
""")

        assert _is_hatch_project(tmp_path) is True

    def test_is_hatch_project_false(self, tmp_path: Path) -> None:
        """test hatch project detection without config."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[project]
name = "test"
""")

        assert _is_hatch_project(tmp_path) is False

    def test_get_python_executable(self, tmp_path: Path) -> None:
        """test getting python executable path."""
        venv_path = tmp_path / "venv"

        if sys.platform == "win32":
            # on windows, should look in Scripts/
            scripts_dir = venv_path / "Scripts"
            scripts_dir.mkdir(parents=True)
            (scripts_dir / "python.exe").write_text("")
            result = _get_python_executable(venv_path)
            assert result == scripts_dir / "python.exe"
        else:
            # on unix, should look in bin/
            bin_dir = venv_path / "bin"
            bin_dir.mkdir(parents=True)
            (bin_dir / "python").write_text("")
            result = _get_python_executable(venv_path)
            assert result == bin_dir / "python"


class TestDetectUV:
    """tests for uv detection."""

    def test_detect_uv_success(self, tmp_path: Path) -> None:
        """test successful uv detection."""
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir()
        (bin_dir / "python").write_text("")

        from raiseattention.env_detector import _detect_uv

        result = _detect_uv(tmp_path)

        assert result.tool == ToolType.UV
        assert result.venv_path == venv_dir.resolve()


class TestDetectRye:
    """tests for rye detection."""

    def test_detect_rye_with_version(self, tmp_path: Path) -> None:
        """test rye detection with .python-version file."""
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        (tmp_path / ".python-version").write_text("3.11.0")

        from raiseattention.env_detector import _detect_rye

        result = _detect_rye(tmp_path)

        assert result.tool == ToolType.RYE
        assert result.python_version == "3.11.0"


class TestDetectVenv:
    """tests for standard venv detection."""

    def test_detect_venv_success(self, tmp_path: Path) -> None:
        """test successful venv detection."""
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()

        from raiseattention.env_detector import _detect_venv

        result = _detect_venv(tmp_path)

        assert result.tool == ToolType.VENV
        assert result.venv_path == venv_dir.resolve()
