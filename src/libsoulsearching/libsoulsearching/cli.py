"""
cli for venvfinder.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from collections.abc import Sequence

from .core import find_all_venvs, find_venv
from .models import ToolType, VenvInfo


def create_parser() -> argparse.ArgumentParser:
    """
    create the argument parser for venvfinder.

    returns: `argparse.ArgumentParser`
        configured argument parser
    """
    parser = argparse.ArgumentParser(
        prog="venvfinder",
        description="universal python virtual environment finder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  venvfinder /path/to/project           # find first venv
  venvfinder /path/to/project --all     # list all detected venvs
  venvfinder /path/to/project --tool poetry  # find specific tool
  venvfinder /path/to/project --json    # output as json
        """,
    )

    _ = parser.add_argument(
        "project_root",
        nargs="?",
        default=".",
        help="project directory to search (default: current directory)",
    )

    _ = parser.add_argument(
        "--tool",
        choices=[t.value for t in ToolType],
        help="detect only this specific tool",
    )

    _ = parser.add_argument(
        "--all",
        action="store_true",
        help="show all detected venvs, not just the first",
    )

    _ = parser.add_argument(
        "--json",
        action="store_true",
        help="output as json",
    )

    _ = parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    return parser


def format_output(info: VenvInfo | None, json_output: bool = False) -> str:
    """
    format venvinfo for output.

    arguments:
        `info: VenvInfo`
            venv information to format
        `json_output: bool`
            whether to output as json

    returns: `str`
        formatted output string
    """
    if info is None:
        return "no virtual environment found" if not json_output else json.dumps({"found": False})

    if json_output:
        return json.dumps(
            {
                "tool": info.tool.value,
                "venv_path": str(info.venv_path) if info.venv_path else None,
                "python_executable": str(info.python_executable)
                if info.python_executable
                else None,
                "python_version": info.python_version,
                "is_valid": info.is_valid,
            },
            indent=2,
        )

    lines = [
        f"tool: {info.tool.value}",
        f"venv_path: {info.venv_path}",
    ]
    if info.python_executable:
        lines.append(f"python_executable: {info.python_executable}")
    if info.python_version:
        lines.append(f"python_version: {info.python_version}")
    lines.append(f"is_valid: {info.is_valid}")

    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """
    main entry point for venvfinder cli.

    arguments:
        `argv: Sequence[str] | None`
            command line arguments. if None, uses sys.argv.

    returns: `int`
        exit code (0 for success, 1 for error)
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    # extract args with getattr to avoid Any propagation from Namespace
    project_root = str(getattr(args, "project_root", "."))
    tool_arg_raw = getattr(args, "tool", None)
    tool_arg = str(tool_arg_raw) if tool_arg_raw is not None else None  # pyright: ignore[reportAny]
    show_all = bool(getattr(args, "all", False))
    json_output = bool(getattr(args, "json", False))

    project_path = Path(project_root)

    if not project_path.exists():
        print(f"error: path not found: {project_path}", file=sys.stderr)
        return 1

    tool: ToolType | None = None
    if tool_arg:
        tool = ToolType(tool_arg)

    if show_all:
        results = find_all_venvs(project_path)
        if not results:
            if not json_output:
                print("no virtual environments found")
            else:
                print("[]")
            return 0

        if json_output:
            output = [
                {
                    "tool": r.tool.value,
                    "venv_path": str(r.venv_path) if r.venv_path else None,
                    "python_executable": str(r.python_executable) if r.python_executable else None,
                    "python_version": r.python_version,
                    "is_valid": r.is_valid,
                }
                for r in results
            ]
            print(json.dumps(output, indent=2))
        else:
            for i, info in enumerate(results, 1):
                print(f"\n[{i}] {info.tool.value}")
                print(format_output(info, json_output=False))
    else:
        result = find_venv(project_path, tool=tool)
        if result is None:
            if not json_output:
                print("no virtual environment found")
            else:
                print("null")
            return 0

        print(format_output(result, json_output=json_output))

    return 0


if __name__ == "__main__":
    sys.exit(main())
