"""tests for the cli module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from raiseattention.cli import (
    create_parser,
    handle_cache,
    handle_check,
    main,
)
from raiseattention.config import Config


class TestCreateParser:
    """tests for the create_parser function."""

    def test_parser_creation(self) -> None:
        """Test that parser is created successfully."""
        parser = create_parser()

        assert parser is not None
        assert parser.prog == "raiseattention"

    def test_check_subcommand(self) -> None:
        """Test check subcommand parsing."""
        parser = create_parser()
        args = parser.parse_args(["check", "."])

        assert args.command == "check"
        assert args.paths == ["."]

    def test_check_with_options(self) -> None:
        """Test check subcommand with options."""
        parser = create_parser()
        args = parser.parse_args(
            [
                "check",
                "--format",
                "json",
                "--output",
                "report.json",
                "--verbose",
                "src/",
            ]
        )

        assert args.format == "json"
        assert args.output == "report.json"
        assert args.verbose is True

    def test_lsp_subcommand(self) -> None:
        """Test lsp subcommand parsing."""
        parser = create_parser()
        args = parser.parse_args(["lsp"])

        assert args.command == "lsp"

    def test_cache_subcommand(self) -> None:
        """Test cache subcommand parsing."""
        parser = create_parser()

        args = parser.parse_args(["cache", "status"])
        assert args.command == "cache"
        assert args.cache_command == "status"

        args = parser.parse_args(["cache", "clear"])
        assert args.cache_command == "clear"

        args = parser.parse_args(["cache", "prune"])
        assert args.cache_command == "prune"


class TestHandleCheck:
    """tests for the handle_check function."""

    def test_check_nonexistent_path(self, capsys) -> None:
        """Test check with non-existent path."""
        parser = create_parser()
        args = parser.parse_args(["check", "/nonexistent/path"])
        config = Config()

        result = handle_check(args, config)

        assert result == 2
        captured = capsys.readouterr()
        assert "path not found" in captured.err

    def test_check_valid_file(self, tmp_path: Path, capsys) -> None:
        """Test check with valid file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def func(): pass")

        parser = create_parser()
        args = parser.parse_args(["check", str(test_file)])
        config = Config()

        result = handle_check(args, config)

        assert result == 0  # no issues found

    def test_check_json_output(self, tmp_path: Path) -> None:
        """Test check with json output format."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def func(): pass")

        output_file = tmp_path / "output.json"

        parser = create_parser()
        args = parser.parse_args(
            [
                "check",
                "--format",
                "json",
                "--output",
                str(output_file),
                str(test_file),
            ]
        )
        config = Config()

        result = handle_check(args, config)

        assert result == 0
        assert output_file.exists()

        data = json.loads(output_file.read_text())
        assert "diagnostics" in data
        assert "summary" in data

    def test_check_with_issues(self, tmp_path: Path, capsys) -> None:
        """Test check when issues are found."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def risky():
    raise ValueError("error")
""")

        parser = create_parser()
        args = parser.parse_args(["check", str(test_file)])
        config = Config()
        config.analysis.strict_mode = True

        result = handle_check(args, config)

        assert result == 1  # issues found


class TestHandleCache:
    """tests for the handle_cache function."""

    def test_cache_status(self, tmp_path: Path, capsys) -> None:
        """Test cache status command."""
        parser = create_parser()
        args = parser.parse_args(["cache", "status"])
        args.cache_command = "status"
        config = Config()

        result = handle_cache(args, config)

        assert result == 0
        captured = capsys.readouterr()
        assert "cache status" in captured.out

    def test_cache_clear(self, tmp_path: Path, capsys) -> None:
        """Test cache clear command."""
        parser = create_parser()
        args = parser.parse_args(["cache", "clear"])
        args.cache_command = "clear"
        config = Config()

        result = handle_cache(args, config)

        assert result == 0
        captured = capsys.readouterr()
        assert "cleared successfully" in captured.out

    def test_cache_prune(self, tmp_path: Path, capsys) -> None:
        """Test cache prune command."""
        parser = create_parser()
        args = parser.parse_args(["cache", "prune"])
        args.cache_command = "prune"
        config = Config()

        result = handle_cache(args, config)

        assert result == 0
        captured = capsys.readouterr()
        assert "pruned" in captured.out

    def test_cache_no_command(self, capsys) -> None:
        """Test cache with no subcommand."""
        parser = create_parser()
        args = parser.parse_args(["cache"])
        args.cache_command = None
        config = Config()

        result = handle_cache(args, config)

        assert result == 2
        captured = capsys.readouterr()
        assert "no cache command specified" in captured.err


class TestMain:
    """tests for the main function."""

    def test_main_no_args(self, capsys) -> None:
        """Test main with no arguments."""
        result = main([])

        assert result == 2
        captured = capsys.readouterr()
        assert "usage:" in captured.out.lower()

    def test_main_check_command(self, tmp_path: Path) -> None:
        """Test main with check command."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def func(): pass")

        result = main(["check", str(test_file)])

        assert result == 0

    def test_main_help(self, capsys) -> None:
        """Test main with help flag."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])

        assert exc_info.value.code == 0
