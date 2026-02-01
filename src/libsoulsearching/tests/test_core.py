"""
tests for libsoulsearching core module.
"""

from __future__ import annotations

from pathlib import Path


from libsoulsearching import find_venv, find_all_venvs, ToolType


class TestFindVenv:
    """tests for find_venv function."""

    def test_empty_project(self, empty_project: Path) -> None:
        """test that empty project returns None."""
        result = find_venv(empty_project)
        assert result is None

    def test_poetry_detection(self, poetry_project: Path) -> None:
        """test poetry venv detection."""
        result = find_venv(poetry_project)
        assert result is not None
        assert result.tool == ToolType.POETRY
        assert result.venv_path == poetry_project / ".venv"

    def test_pipenv_detection(self, pipenv_project: Path) -> None:
        """test pipenv venv detection."""
        result = find_venv(pipenv_project)
        assert result is not None
        assert result.tool == ToolType.PIPENV

    def test_pdm_detection(self, pdm_project: Path) -> None:
        """test pdm venv detection."""
        result = find_venv(pdm_project)
        assert result is not None
        assert result.tool == ToolType.PDM

    def test_uv_detection(self, uv_project: Path) -> None:
        """test uv venv detection."""
        result = find_venv(uv_project)
        assert result is not None
        assert result.tool == ToolType.UV

    def test_rye_detection(self, rye_project: Path) -> None:
        """test rye venv detection."""
        result = find_venv(rye_project)
        assert result is not None
        assert result.tool == ToolType.RYE

    def test_specific_tool_filtering(self, poetry_project: Path) -> None:
        """test that tool parameter filters correctly."""
        # poetry project should not match when looking for pdm
        result = find_venv(poetry_project, tool=ToolType.PDM)
        assert result is None

        # but should match when looking for poetry
        result = find_venv(poetry_project, tool=ToolType.POETRY)
        assert result is not None
        assert result.tool == ToolType.POETRY

    def test_nonexistent_path(self) -> None:
        """test that nonexistent path returns None."""
        result = find_venv("/nonexistent/path/12345")
        assert result is None


class TestFindAllVenvs:
    """tests for find_all_venvs function."""

    def test_empty_project(self, empty_project: Path) -> None:
        """test that empty project returns empty list."""
        results = find_all_venvs(empty_project)
        assert results == []

    def test_multiple_tools(self, poetry_project: Path) -> None:
        """test detecting multiple tools (e.g., uv.lock + .venv)."""
        # create a project with both uv.lock and .venv
        (poetry_project / "uv.lock").write_text("")

        results = find_all_venvs(poetry_project)

        # should find both uv and poetry
        tools = {r.tool for r in results}
        assert ToolType.UV in tools
        assert ToolType.POETRY in tools

    def test_returns_list(self, venv_project: Path) -> None:
        """test that function always returns a list."""
        results = find_all_venvs(venv_project)
        assert isinstance(results, list)
        assert len(results) > 0


class TestToolType:
    """tests for ToolType enum."""

    def test_enum_values(self) -> None:
        """test that all expected tools are defined."""
        expected = {"poetry", "pipenv", "pdm", "uv", "rye", "hatch", "venv", "pyenv", "env_var"}
        actual = {t.value for t in ToolType}
        assert actual == expected
