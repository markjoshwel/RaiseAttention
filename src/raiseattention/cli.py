"""
command-line interface for raiseattention.

provides commands for analysing python code, managing cache,
and running the lsp server.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from libsightseeing import find_files

from .analyser import AnalysisResult, Diagnostic, ExceptionAnalyser
from .cache import FileCache
from .config import Config
from .lsp_server import run_server_stdio


def create_parser() -> argparse.ArgumentParser:
    """
    create the argument parser for the cli.

    returns: `argparse.ArgumentParser`
        configured argument parser
    """
    parser = argparse.ArgumentParser(
        prog="raiseattention",
        description="static exception flow analyser for python",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  raiseattention check .                    # analyse entire project
  raiseattention check src/main.py          # analyse specific file
  raiseattention check --format=json .      # output as json
  raiseattention lsp                        # start lsp server
  raiseattention cache status               # show cache status
  raiseattention cache clear                # clear cache
        """,
    )
    _ = parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 2026.2.14",
    )

    subparsers = parser.add_subparsers(dest="command", help="available commands")

    # check command
    check_parser = subparsers.add_parser(
        "check",
        help="analyse python code for unhandled exceptions",
    )
    _ = check_parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="files or directories to analyse (default: current directory)",
    )
    _ = check_parser.add_argument(
        "--include-ignored",
        action="store_true",
        help="include files that are ignored by .gitignore",
    )
    _ = check_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="output in json format (default: text)",
    )
    _ = check_parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="output file (default: stdout)",
    )
    _ = check_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="verbose output",
    )
    _ = check_parser.add_argument(
        "--local",
        action="store_true",
        help="only analyse local/first-party code, skip external modules",
    )
    _ = check_parser.add_argument(
        "--strict",
        action="store_true",
        help="enable strict mode (require all exceptions to be declared)",
    )
    _ = check_parser.add_argument(
        "--absolute",
        action="store_true",
        help="use absolute paths in output (default: cwd-relative for text, absolute for json)",
    )
    _ = check_parser.add_argument(
        "--full-module-path",
        action="store_true",
        help=(
            "show full module path for exceptions (e.g., "
            "'tomlantic.tomlantic.TOMLValidationError' instead of "
            "'tomlantic.TOMLValidationError')"
        ),
    )
    _ = check_parser.add_argument(
        "--no-warn-native",
        action="store_true",
        help="disable warnings about possible native code exceptions",
    )
    _ = check_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="disable caching (useful for readonly environments or fresh analysis)",
    )
    _ = check_parser.add_argument(
        "--debug",
        action="store_true",
        help="enable debug logging for troubleshooting",
    )

    # lsp command
    lsp_parser = subparsers.add_parser(
        "lsp",
        help="start language server protocol server",
    )
    _ = lsp_parser.add_argument(
        "--stdio",
        action="store_true",
        default=True,
        help="use stdio for communication (default)",
    )

    # cache command
    cache_parser = subparsers.add_parser(
        "cache",
        help="manage analysis cache",
    )
    cache_subparsers = cache_parser.add_subparsers(dest="cache_command")

    _ = cache_subparsers.add_parser("status", help="show cache status")
    _ = cache_subparsers.add_parser("clear", help="clear all caches")
    _ = cache_subparsers.add_parser("prune", help="remove stale cache entries")

    return parser


def _format_path(file_path: Path, use_absolute: bool) -> str:
    """
    format a path for output.

    uses cwd-relative paths by default for human readability,
    or absolute paths when explicitly requested or for machine output.

    arguments:
        `file_path: Path`
            the path to format
        `use_absolute: bool`
            whether to use absolute paths

    returns: `str`
        formatted path string
    """
    if use_absolute:
        return str(file_path.resolve())

    try:
        return str(file_path.resolve().relative_to(Path.cwd()))
    except ValueError:
        # path is not under cwd, use absolute
        return str(file_path.resolve())


def handle_check(args: argparse.Namespace, config: Config) -> int:
    """
    handle the check command.

    arguments:
        `args: argparse.Namespace`
            parsed arguments
        `config: Config`
            configuration

    returns: `int`
        exit code (0 = no issues, 1 = issues found, 2 = error)
    """
    # extract args with getattr to avoid Any propagation from Namespace
    debug = bool(getattr(args, "debug", False))
    local = bool(getattr(args, "local", False))
    strict = bool(getattr(args, "strict", False))
    full_module_path = bool(getattr(args, "full_module_path", False))
    include_ignored = bool(getattr(args, "include_ignored", False))
    no_warn_native = bool(getattr(args, "no_warn_native", False))
    no_cache = bool(getattr(args, "no_cache", False))
    paths_raw = getattr(args, "paths", None)
    paths: list[str] = list(paths_raw) if paths_raw else []  # pyright: ignore[reportAny]
    verbose = bool(getattr(args, "verbose", False))
    absolute = bool(getattr(args, "absolute", False))
    json_output = bool(getattr(args, "json_output", False))
    output_raw = getattr(args, "output", None)
    output_file = str(output_raw) if output_raw is not None else None  # pyright: ignore[reportAny]

    # enable debug logging if requested
    if debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="[%(name)s] %(message)s",
        )

    # apply cli overrides
    if local:
        config.analysis.local_only = True
    if strict:
        config.analysis.strict_mode = True
    if full_module_path:
        config.analysis.full_module_path = True
    if include_ignored:
        config.respect_gitignore = False
    if no_warn_native:
        config.analysis.warn_native = False
    if no_cache:
        config.cache.enabled = False

    analyzer = ExceptionAnalyser(config)
    all_results: list[AnalysisResult] = []
    files_to_analyse: list[Path] = []

    # collect all files to analyse
    for path_str in paths:
        path = Path(path_str)

        if not path.exists():
            print(
                f"raiseattention: warning: skipping '{path_str}', path does not exist",
                file=sys.stderr,
            )
            continue

        if path.is_file():
            files_to_analyse.append(path)
        else:
            # use libsightseeing to find python files
            found_files = find_files(
                root=path,
                include=config.include,
                exclude=config.exclude,
                respect_gitignore=config.respect_gitignore,
            )
            files_to_analyse.extend(found_files)

    if not files_to_analyse:
        if verbose:
            print("no files to analyse")
        return 0

    # analyse each file
    for file_path in files_to_analyse:
        result = analyzer.analyse_file(file_path)
        all_results.append(result)

    # combine results
    combined_diagnostics: list[Diagnostic] = []
    files_analysed: list[Path] = []
    total_functions = 0
    total_exceptions = 0

    for result in all_results:
        combined_diagnostics.extend(result.diagnostics)
        files_analysed.extend(result.files_analysed)
        total_functions += result.functions_found
        total_exceptions += result.exceptions_tracked

    # determine path formatting: json always uses absolute, text uses relative by default
    use_absolute = absolute or json_output

    # output results
    if json_output:
        output = {
            "diagnostics": [
                {
                    "file": _format_path(d.file_path, use_absolute=True),
                    "line": d.line,
                    "column": d.column,
                    "message": d.message,
                    "exception_types": d.exception_types,
                    "severity": d.severity,
                }
                for d in combined_diagnostics
            ],
            "summary": {
                "files_analysed": len(set(files_analysed)),
                "functions_found": total_functions,
                "exceptions_tracked": total_exceptions,
                "issues_found": len(combined_diagnostics),
            },
        }

        json_str = json.dumps(output, indent=2)

        if output_file:
            _ = Path(output_file).write_text(json_str)
        else:
            print(json_str)
    else:
        # text format
        if combined_diagnostics:
            for diag in combined_diagnostics:
                path_str = _format_path(diag.file_path, use_absolute)
                print(f"{path_str}:{diag.line}:{diag.column}: {diag.severity}: {diag.message}")

        # always print summary line (like basedpyright)
        issue_count = len(combined_diagnostics)
        issue_word = "issue" if issue_count == 1 else "issues"
        print(f"{issue_count} {issue_word} found")

        if verbose:
            print("\ndetailed summary:")
            print(f"  files analysed: {len(set(files_analysed))}")
            print(f"  functions found: {total_functions}")
            print(f"  exceptions tracked: {total_exceptions}")

        if output_file:
            # also write text output to file
            lines: list[str] = []
            for diag in combined_diagnostics:
                path_str = _format_path(diag.file_path, use_absolute)
                lines.append(
                    f"{path_str}:{diag.line}:{diag.column}: {diag.severity}: {diag.message}"
                )

            # always include summary line
            lines.append(f"{issue_count} {issue_word} found")

            if verbose:
                lines.append("")
                lines.append("detailed summary:")
                lines.append(f"  files analysed: {len(set(files_analysed))}")
                lines.append(f"  functions found: {total_functions}")
                lines.append(f"  exceptions tracked: {total_exceptions}")

            _ = Path(output_file).write_text("\n".join(lines))

    # return exit code
    if combined_diagnostics:
        return 1
    return 0


def handle_lsp(_args: argparse.Namespace, config: Config) -> int:
    """
    handle the lsp command.

    arguments:
        `_args: argparse.Namespace`
            parsed arguments (unused)
        `config: Config`
            configuration

    returns: `int`
        exit code
    """
    try:
        run_server_stdio(config)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"error: lsp server failed: {e}", file=sys.stderr)
        return 2


def handle_cache(args: argparse.Namespace, config: Config) -> int:
    """
    handle cache subcommands.

    arguments:
        `args: argparse.Namespace`
            parsed arguments
        `config: Config`
            configuration

    returns: `int`
        exit code
    """
    cache_cmd_raw = getattr(args, "cache_command", None)
    cache_command = str(cache_cmd_raw) if cache_cmd_raw is not None else None  # pyright: ignore[reportAny]

    if not cache_command:
        print("error: no cache command specified", file=sys.stderr)
        print("use 'raiseattention cache --help' for usage", file=sys.stderr)
        return 2

    file_cache = FileCache(config.cache)

    if cache_command == "status":
        stats = file_cache.get_stats()
        print("cache status:")
        print(f"  memory entries: {stats['memory_entries']}")
        print(f"  disk entries: {stats['disk_entries']}")
        print(f"  total entries: {stats['total_entries']}")
        print(f"  cache directory: {file_cache.cache_dir}")

    elif cache_command == "clear":
        file_cache.clear()
        print("cache cleared successfully")

    elif cache_command == "prune":
        pruned = file_cache.prune()
        print(f"pruned {pruned} stale entries")

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """
    run the cli main entry point.

    arguments:
        `argv: Sequence[str] | None`
            command-line arguments (default: sys.argv[1:])

    returns: `int`
        exit code
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    cmd_raw = getattr(args, "command", None)
    command = str(cmd_raw) if cmd_raw is not None else None  # pyright: ignore[reportAny]

    if not command:
        parser.print_help()
        return 2

    # load configuration
    config = Config.load()

    # dispatch to handler
    if command == "check":
        return handle_check(args, config)
    elif command == "lsp":
        return handle_lsp(args, config)
    elif command == "cache":
        return handle_cache(args, config)
    else:
        parser.print_help()
        return 2


if __name__ == "__main__":
    sys.exit(main())
