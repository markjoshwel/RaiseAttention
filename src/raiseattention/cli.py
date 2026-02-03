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

from .analyser import ExceptionAnalyser
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

    subparsers = parser.add_subparsers(dest="command", help="available commands")

    # check command
    check_parser = subparsers.add_parser(
        "check",
        help="analyse python code for unhandled exceptions",
    )
    check_parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="files or directories to analyse (default: current directory)",
    )
    check_parser.add_argument(
        "--include-ignored",
        action="store_true",
        help="include files that are ignored by .gitignore",
    )
    check_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="output in json format (default: text)",
    )
    check_parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="output file (default: stdout)",
    )
    check_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="verbose output",
    )
    check_parser.add_argument(
        "--local",
        action="store_true",
        help="only analyse local/first-party code, skip external modules",
    )
    check_parser.add_argument(
        "--strict",
        action="store_true",
        help="enable strict mode (require all exceptions to be declared)",
    )
    check_parser.add_argument(
        "--absolute",
        action="store_true",
        help="use absolute paths in output (default: cwd-relative for text, absolute for json)",
    )
    check_parser.add_argument(
        "--full-module-path",
        action="store_true",
        help=(
            "show full module path for exceptions (e.g., "
            "'tomlantic.tomlantic.TOMLValidationError' instead of "
            "'tomlantic.TOMLValidationError')"
        ),
    )
    check_parser.add_argument(
        "--no-warn-native",
        action="store_true",
        help="disable warnings about possible native code exceptions",
    )
    check_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="disable caching (useful for readonly environments or fresh analysis)",
    )
    check_parser.add_argument(
        "--debug",
        action="store_true",
        help="enable debug logging for troubleshooting",
    )

    # lsp command
    lsp_parser = subparsers.add_parser(
        "lsp",
        help="start language server protocol server",
    )
    lsp_parser.add_argument(
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

    cache_subparsers.add_parser("status", help="show cache status")
    cache_subparsers.add_parser("clear", help="clear all caches")
    cache_subparsers.add_parser("prune", help="remove stale cache entries")

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
    # enable debug logging if requested
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="[%(name)s] %(message)s",
        )

    # apply cli overrides
    if args.local:
        config.analysis.local_only = True
    if args.strict:
        config.analysis.strict_mode = True
    if args.full_module_path:
        config.analysis.full_module_path = True
    if args.include_ignored:
        config.respect_gitignore = False
    if args.no_warn_native:
        config.analysis.warn_native = False
    if args.no_cache:
        config.cache.enabled = False

    analyzer = ExceptionAnalyser(config)
    all_results = []
    files_to_analyse: list[Path] = []

    # collect all files to analyse
    for path_str in args.paths:
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
        if args.verbose:
            print("no files to analyse")
        return 0

    # analyse each file
    for file_path in files_to_analyse:
        result = analyzer.analyse_file(file_path)
        all_results.append(result)

    # combine results
    combined_diagnostics = []
    files_analysed = []
    total_functions = 0
    total_exceptions = 0

    for result in all_results:
        combined_diagnostics.extend(result.diagnostics)
        files_analysed.extend(result.files_analysed)
        total_functions += result.functions_found
        total_exceptions += result.exceptions_tracked

    # determine path formatting: json always uses absolute, text uses relative by default
    use_absolute = args.absolute or args.json_output

    # output results
    if args.json_output:
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

        if args.output:
            Path(args.output).write_text(json_str)
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

        if args.verbose:
            print("\ndetailed summary:")
            print(f"  files analysed: {len(set(files_analysed))}")
            print(f"  functions found: {total_functions}")
            print(f"  exceptions tracked: {total_exceptions}")

        if args.output:
            # also write text output to file
            lines = []
            for diag in combined_diagnostics:
                path_str = _format_path(diag.file_path, use_absolute)
                lines.append(
                    f"{path_str}:{diag.line}:{diag.column}: {diag.severity}: {diag.message}"
                )

            # always include summary line
            lines.append(f"{issue_count} {issue_word} found")

            if args.verbose:
                lines.append("")
                lines.append("detailed summary:")
                lines.append(f"  files analysed: {len(set(files_analysed))}")
                lines.append(f"  functions found: {total_functions}")
                lines.append(f"  exceptions tracked: {total_exceptions}")

            Path(args.output).write_text("\n".join(lines))

    # return exit code
    if combined_diagnostics:
        return 1
    return 0


def handle_lsp(args: argparse.Namespace, config: Config) -> int:
    """
    handle the lsp command.

    arguments:
        `args: argparse.Namespace`
            parsed arguments
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
    if not args.cache_command:
        print("error: no cache command specified", file=sys.stderr)
        print("use 'raiseattention cache --help' for usage", file=sys.stderr)
        return 2

    file_cache = FileCache(config.cache)

    if args.cache_command == "status":
        stats = file_cache.get_stats()
        print("cache status:")
        print(f"  memory entries: {stats['memory_entries']}")
        print(f"  disk entries: {stats['disk_entries']}")
        print(f"  total entries: {stats['total_entries']}")
        print(f"  cache directory: {file_cache.cache_dir}")

    elif args.cache_command == "clear":
        file_cache.clear()
        print("cache cleared successfully")

    elif args.cache_command == "prune":
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

    if not args.command:
        parser.print_help()
        return 2

    # load configuration
    config = Config.load()

    # dispatch to handler
    if args.command == "check":
        return handle_check(args, config)
    elif args.command == "lsp":
        return handle_lsp(args, config)
    elif args.command == "cache":
        return handle_cache(args, config)
    else:
        parser.print_help()
        return 2


if __name__ == "__main__":
    sys.exit(main())
