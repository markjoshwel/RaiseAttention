"""
command-line interface for raiseattention.

provides commands for analysing python code, managing cache,
and running the lsp server.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .analyzer import ExceptionAnalyzer
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
        nargs="+",
        help="files or directories to analyse",
    )
    check_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="output format (default: text)",
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
    # apply cli overrides
    if args.local:
        config.analysis.local_only = True
    if args.strict:
        config.analysis.strict_mode = True

    analyzer = ExceptionAnalyzer(config)
    all_results = []

    for path_str in args.paths:
        path = Path(path_str)

        if not path.exists():
            print(f"error: path not found: {path}", file=sys.stderr)
            return 2

        result = analyzer.analyse_file(path) if path.is_file() else analyzer.analyse_project(path)

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

    # output results
    if args.format == "json":
        output = {
            "diagnostics": [
                {
                    "file": str(d.file_path),
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
                print(
                    f"{diag.file_path}:{diag.line}:{diag.column}: {diag.severity}: {diag.message}"
                )

        if args.verbose:
            print("\nsummary:")
            print(f"  files analysed: {len(set(files_analysed))}")
            print(f"  functions found: {total_functions}")
            print(f"  exceptions tracked: {total_exceptions}")
            print(f"  issues found: {len(combined_diagnostics)}")

        if args.output:
            # also write text output to file
            lines = []
            for diag in combined_diagnostics:
                lines.append(
                    f"{diag.file_path}:{diag.line}:{diag.column}: {diag.severity}: {diag.message}"
                )

            if args.verbose:
                lines.append("")
                lines.append("summary:")
                lines.append(f"  files analysed: {len(set(files_analysed))}")
                lines.append(f"  functions found: {total_functions}")
                lines.append(f"  exceptions tracked: {total_exceptions}")
                lines.append(f"  issues found: {len(combined_diagnostics)}")

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
