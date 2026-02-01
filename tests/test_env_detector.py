"""
tests for the environment detector module.

this module tests the compatibility layer that re-exports libsoulsearching
functionality for raiseattention.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from raiseattention.env_detector import (
    EnvironmentInfo,
    ToolType,
    VenvInfo,
    detect_environment,
    find_all_venvs,
    find_venv,
)


class TestVenvInfo:
    """tests for the VenvInfo dataclass (re-exported from libsoulsearching)."""

    def test_basic_creation(self) -> None:
        """Test basic initialisation of VenvInfo."""
        info = VenvInfo(
            tool=ToolType.POETRY,
            venv_path=Path("/path/to/venv"),
            python_executable=Path("/path/to/venv/bin/python"),
            python_version="3.10.0",
            is_valid=True,
        )
        assert info.tool == ToolType.POETRY
        assert info.venv_path == Path("/path/to/venv")

    def test_venv_info_attributes(self) -> None:
        """Test VenvInfo has expected attributes."""
        info = VenvInfo(
            tool=ToolType.UV,
            venv_path=Path("/home/user/.venv"),
            python_executable=Path("/home/user/.venv/bin/python"),
            python_version="3.11.0",
            is_valid=True,
        )
        assert info.tool.value == "uv"
        # use as_posix() for cross-platform path comparison
        assert info.venv_path.as_posix() == "/home/user/.venv"


class TestEnvironmentInfo:
    """tests for the EnvironmentInfo compatibility alias."""

    def test_environment_info_is_venv_info(self) -> None:
        """Test that EnvironmentInfo is an alias for VenvInfo."""
        info = EnvironmentInfo(
            tool=ToolType.POETRY,
            venv_path=Path("/path/to/venv"),
            python_executable=Path("/path/to/venv/bin/python"),
            python_version="3.10.0",
            is_valid=True,
        )
        assert isinstance(info, VenvInfo)


class TestToolType:
    """tests for the ToolType enum (re-exported from libsoulsearching)."""

    def test_tool_type_values(self) -> None:
        """Test that ToolType has expected values."""
        assert ToolType.POETRY.value == "poetry"
        assert ToolType.PIPENV.value == "pipenv"
        assert ToolType.PDM.value == "pdm"
        assert ToolType.UV.value == "uv"
        assert ToolType.RYE.value == "rye"
        assert ToolType.HATCH.value == "hatch"
        assert ToolType.VENV.value == "venv"
        assert ToolType.PYENV.value == "pyenv"


class TestFindVenv:
    """tests for the find_venv function (re-exported from libsoulsearching)."""

    def test_find_venv_returns_none_for_nonexistent_path(self) -> None:
        """Test that find_venv returns None for non-existent paths."""
        result = find_venv("/nonexistent/path/that/does/not/exist")
        assert result is None

    def test_find_venv_with_no_venv(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test find_venv returns None when no venv exists."""
        # clear VIRTUAL_ENV to ensure we don't detect the test environment
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)
        result = find_venv(tmp_path)
        assert result is None


class TestFindAllVenvs:
    """tests for the find_all_venvs function (re-exported from libsoulsearching)."""

    def test_find_all_venvs_returns_list(self, tmp_path: Path) -> None:
        """Test that find_all_venvs returns a list."""
        result = find_all_venvs(tmp_path)
        assert isinstance(result, list)

    def test_find_all_venvs_empty_for_no_venvs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that find_all_venvs returns empty list when no venvs."""
        # clear VIRTUAL_ENV to ensure we don't detect the test environment
        monkeypatch.delenv("VIRTUAL_ENV", raising=False)
        result = find_all_venvs(tmp_path)
        assert result == []


class TestDetectEnvironment:
    """tests for the detect_environment compatibility alias."""

    def test_detect_environment_is_find_venv(self) -> None:
        """Test that detect_environment works as an alias for find_venv."""
        # both should return None for a path with no venv
        result_detect = detect_environment("/nonexistent/path")
        result_find = find_venv("/nonexistent/path")
        assert result_detect == result_find


class TestIntegrationWithLibvenvfinder:
    """integration tests to verify libsoulsearching re-exports work correctly."""

    def test_poetry_project_detection(self, tmp_path: Path) -> None:
        """Test detection of poetry project with lock file."""
        # create a poetry.lock file
        (tmp_path / "poetry.lock").write_text("")

        # create a .venv directory
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()

        # on windows, create Scripts directory; on unix, create bin
        if hasattr(__import__("os"), "name") and __import__("os").name == "nt":
            scripts_dir = venv_dir / "Scripts"
        else:
            scripts_dir = venv_dir / "bin"
        scripts_dir.mkdir()

        # create a mock python executable
        python_exe = scripts_dir / ("python.exe" if "Scripts" in str(scripts_dir) else "python")
        python_exe.write_text("")

        result = find_venv(tmp_path)

        # should detect poetry tool
        assert result is not None
        assert result.tool == ToolType.POETRY

    def test_uv_project_detection(self, tmp_path: Path) -> None:
        """Test detection of uv project with lock file."""
        # create uv.lock file
        (tmp_path / "uv.lock").write_text("")

        # create .venv directory
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()

        # create bin directory and python executable
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir()
        (bin_dir / "python").write_text("")

        result = find_venv(tmp_path)

        assert result is not None
        assert result.tool == ToolType.UV

    def test_standard_venv_detection(self, tmp_path: Path) -> None:
        """Test detection of standard venv."""
        # create .venv directory with pyvenv.cfg
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        (venv_dir / "pyvenv.cfg").write_text("version = 3.10.0")

        # create bin directory and python executable
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir()
        (bin_dir / "python").write_text("")

        result = find_venv(tmp_path)

        assert result is not None
        assert result.tool == ToolType.VENV

    def test_pipenv_project_detection(self, tmp_path: Path) -> None:
        """Test detection of pipenv project with lock file."""
        # create Pipfile.lock
        (tmp_path / "Pipfile.lock").write_text("{}")

        # create .venv directory
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir()
        (bin_dir / "python").write_text("")

        result = find_venv(tmp_path)

        assert result is not None
        assert result.tool == ToolType.PIPENV

    def test_pdm_project_detection(self, tmp_path: Path) -> None:
        """Test detection of pdm project with lock file."""
        # create pdm.lock
        (tmp_path / "pdm.lock").write_text("")

        # create .venv directory
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir()
        (bin_dir / "python").write_text("")

        result = find_venv(tmp_path)

        assert result is not None
        assert result.tool == ToolType.PDM

    def test_find_all_venvs_finds_multiple(self, tmp_path: Path) -> None:
        """Test that find_all_venvs can find multiple venvs."""
        # create multiple venv indicators
        (tmp_path / "poetry.lock").write_text("")
        (tmp_path / "uv.lock").write_text("")

        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir()
        (bin_dir / "python").write_text("")

        results = find_all_venvs(tmp_path)

        # should find at least one venv
        assert len(results) >= 1
        # first result should be poetry (priority order)
        assert results[0].tool == ToolType.POETRY

    def test_tool_type_filtering(self, tmp_path: Path) -> None:
        """Test that find_venv can filter by tool type."""
        # create poetry.lock file
        (tmp_path / "poetry.lock").write_text("")

        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir()
        (bin_dir / "python").write_text("")

        # should find poetry when filtering for poetry
        result = find_venv(tmp_path, tool=ToolType.POETRY)
        assert result is not None
        assert result.tool == ToolType.POETRY

        # should not find anything when filtering for uv
        result_uv = find_venv(tmp_path, tool=ToolType.UV)
        assert result_uv is None
