"""
tests for libvenvfinder cli.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from libvenvfinder.cli import main


class TestCliBasic:
    """tests for basic cli functionality."""

    def test_help(self, capsys) -> None:
        """test that --help works."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "venvfinder" in captured.out
        assert "--json" in captured.out
        assert "--all" in captured.out

    def test_version(self, capsys) -> None:
        """test that --version works."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "0.1.0" in captured.out

    def test_nonexistent_path(self, capsys) -> None:
        """test error handling for nonexistent path."""
        result = main(["/nonexistent/path/12345"])
        assert result == 1

        captured = capsys.readouterr()
        assert "error" in captured.err


class TestCliJsonOutput:
    """tests for --json output."""

    def test_json_single(self, venv_project: Path, capsys) -> None:
        """test json output for single venv."""
        result = main([str(venv_project), "--json"])
        assert result == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert "tool" in data
        assert "venv_path" in data
        assert "is_valid" in data

    def test_json_all(self, venv_project: Path, capsys) -> None:
        """test json output for --all."""
        result = main([str(venv_project), "--all", "--json"])
        assert result == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert isinstance(data, list)
        assert len(data) > 0

        for item in data:
            assert "tool" in item
            assert "venv_path" in item

    def test_json_no_venv(self, empty_project: Path, capsys) -> None:
        """test json output when no venv found."""
        result = main([str(empty_project), "--json"])
        assert result == 0

        captured = capsys.readouterr()
        assert captured.out.strip() == "null"


class TestCliAllFlag:
    """tests for --all flag."""

    def test_all_shows_multiple(self, venv_project: Path, capsys) -> None:
        """test that --all shows all detected venvs."""
        # add a uv.lock to get multiple detections
        (venv_project / "uv.lock").write_text("")

        result = main([str(venv_project), "--all"])
        assert result == 0

        captured = capsys.readouterr()
        # should show multiple entries
        assert "[1]" in captured.out
        assert "[2]" in captured.out

    def test_all_no_venv(self, empty_project: Path, capsys) -> None:
        """test --all when no venv found."""
        result = main([str(empty_project), "--all"])
        assert result == 0

        captured = capsys.readouterr()
        assert "no virtual environments found" in captured.out


class TestCliToolFilter:
    """tests for --tool filtering."""

    def test_tool_filter_poetry(self, poetry_project: Path, capsys) -> None:
        """test filtering for poetry."""
        result = main([str(poetry_project), "--tool", "poetry"])
        assert result == 0

        captured = capsys.readouterr()
        assert "poetry" in captured.out

    def test_tool_filter_no_match(self, poetry_project: Path, capsys) -> None:
        """test filtering when tool doesn't match."""
        result = main([str(poetry_project), "--tool", "pdm", "--json"])
        assert result == 0

        captured = capsys.readouterr()
        assert captured.out.strip() == "null"
