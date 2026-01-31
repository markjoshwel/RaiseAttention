"""
core exception analysis engine for raiseattention.

this module provides the main analysis logic for detecting unhandled
exceptions in python code, including transitive propagation tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .ast_visitor import parse_file
from .cache import DependencyCache, FileAnalysis, FileCache
from .config import Config

if TYPE_CHECKING:
    from .ast_visitor import ExceptionInfo, ExceptionVisitor, FunctionInfo
    from .config import AnalysisConfig


@dataclass
class Diagnostic:
    """
    a diagnostic message for an unhandled exception.

    attributes:
        `file_path: Path`
            file where the issue was found
        `line: int`
            line number (1-indexed)
        `column: int`
            column number (0-indexed)
        `message: str`
            human-readable diagnostic message
        `exception_types: list[str]`
            exception types that are unhandled
        `severity: str`
            'error', 'warning', or 'info'
    """

    file_path: Path
    line: int
    column: int
    message: str
    exception_types: list[str] = field(default_factory=list)
    severity: str = "error"


@dataclass
class AnalysisResult:
    """
    result of analysing a file or project.

    attributes:
        `diagnostics: list[Diagnostic]`
            all diagnostics found
        `files_analysed: list[Path]`
            files that were analysed
        `functions_found: int`
            total number of functions found
        `exceptions_tracked: int`
            total number of exceptions tracked
    """

    diagnostics: list[Diagnostic] = field(default_factory=list)
    files_analysed: list[Path] = field(default_factory=list)
    functions_found: int = 0
    exceptions_tracked: int = 0


class ExceptionAnalyzer:
    """
    core exception analysis engine.

    analyses python code to detect unhandled exceptions, including
    transitive propagation through function calls.

    attributes:
        `config: Config`
            configuration settings
        `file_cache: FileCache`
            file-level analysis cache
        `dependency_cache: DependencyCache`
            external library exception cache
        `_file_analyses: dict[Path, FileAnalysis]`
            current analysis results by file
        `_exception_signatures: dict[str, list[str]]`
            computed exception signatures for functions
    """

    def __init__(self, config: Config) -> None:
        """
        initialise the exception analyzer.

        arguments:
            `config: Config`
                configuration settings
        """
        self.config = config
        self.file_cache = FileCache(config.cache)
        self.dependency_cache = DependencyCache(config.cache)
        self._file_analyses: dict[Path, FileAnalysis] = {}
        self._exception_signatures: dict[str, list[str]] = {}

    def analyse_file(self, file_path: str | Path) -> AnalysisResult:
        """
        analyse a single file for unhandled exceptions.

        arguments:
            `file_path: str | Path`
                path to the python file

        returns: `AnalysisResult`
            analysis results with diagnostics
        """
        file_path = Path(file_path).resolve()
        result = AnalysisResult()

        # check cache first
        if cached := self.file_cache.get(file_path):
            self._file_analyses[file_path] = cached
            result.files_analysed.append(file_path)
            result.functions_found = len(cached.functions)

            # recompute diagnostics from cached analysis
            diagnostics = self._compute_diagnostics(file_path, cached)
            result.diagnostics.extend(diagnostics)
            return result

        # parse and analyse
        try:
            visitor = parse_file(file_path)
        except (SyntaxError, FileNotFoundError, OSError) as e:
            result.diagnostics.append(
                Diagnostic(
                    file_path=file_path,
                    line=1,
                    column=0,
                    message=f"failed to analyse file: {e}",
                    severity="error",
                )
            )
            return result

        # create file analysis
        analysis = FileAnalysis(
            file_path=file_path,
            functions={
                name: {
                    "name": func.name,
                    "qualified_name": func.qualified_name,
                    "location": func.location,
                    "raises": [
                        {
                            "type": exc.exception_type,
                            "location": exc.location,
                            "is_re_raise": exc.is_re_raise,
                        }
                        for exc in func.raises
                    ],
                    "calls": func.calls,
                    "docstring": func.docstring,
                }
                for name, func in visitor.functions.items()
            },
            imports=visitor.imports,
            timestamp=time.time(),
        )

        # store in cache and memory
        self.file_cache.store(file_path, analysis)
        self._file_analyses[file_path] = analysis

        result.files_analysed.append(file_path)
        result.functions_found = len(visitor.functions)
        result.exceptions_tracked = sum(len(func.raises) for func in visitor.functions.values())

        # compute diagnostics
        diagnostics = self._compute_diagnostics(file_path, analysis)
        result.diagnostics.extend(diagnostics)

        return result

    def analyse_project(self, project_root: str | Path | None = None) -> AnalysisResult:
        """
        analyse an entire project for unhandled exceptions.

        arguments:
            `project_root: str | Path | None`
                project root directory (default: from config)

        returns: `AnalysisResult`
            combined analysis results
        """
        if project_root is None:
            project_root = self.config.project_root

        project_path = Path(project_root).resolve()
        result = AnalysisResult()

        # find all python files
        python_files = self._find_python_files(project_path)

        # analyse each file
        for file_path in python_files:
            file_result = self.analyse_file(file_path)
            result.diagnostics.extend(file_result.diagnostics)
            result.files_analysed.extend(file_result.files_analysed)
            result.functions_found += file_result.functions_found
            result.exceptions_tracked += file_result.exceptions_tracked

        return result

    def get_function_signature(self, qualified_name: str) -> list[str]:
        """
        get the exception signature for a function.

        this computes the transitive exception signature, including
        exceptions from called functions.

        arguments:
            `qualified_name: str`
                fully qualified function name

        returns: `list[str]`
            list of exception types the function may raise
        """
        if qualified_name in self._exception_signatures:
            return self._exception_signatures[qualified_name]

        # find function in analyses
        func_info = None
        for analysis in self._file_analyses.values():
            if qualified_name in analysis.functions:
                func_info = analysis.functions[qualified_name]
                break

        if func_info is None:
            return []

        # collect directly raised exceptions
        exceptions: set[str] = set()
        for exc in func_info.get("raises", []):  # pyright: ignore[reportAny]
            if not exc.get("is_re_raise", False):  # pyright: ignore[reportAny]
                exceptions.add(exc.get("type", ""))  # pyright: ignore[reportAny]

        # collect from called functions (transitive)
        for called_func in func_info.get("calls", []):  # pyright: ignore[reportAny]
            called_exceptions = self.get_function_signature(called_func)
            exceptions.update(called_exceptions)

        # remove empty strings
        exceptions.discard("")

        # cache result
        result = list(exceptions)
        self._exception_signatures[qualified_name] = result

        return result

    def invalidate_file(self, file_path: str | Path) -> None:
        """
        invalidate cache for a file.

        arguments:
            `file_path: str | Path`
                path to the file
        """
        file_path = Path(file_path).resolve()
        self.file_cache.invalidate(file_path)

        if file_path in self._file_analyses:
            del self._file_analyses[file_path]

        # clear computed signatures (they may depend on this file)
        self._exception_signatures.clear()

    def clear_cache(self) -> None:
        """clear all caches."""
        self.file_cache.clear()
        self._file_analyses.clear()
        self._exception_signatures.clear()

    def _compute_diagnostics(
        self,
        file_path: Path,
        analysis: FileAnalysis,
    ) -> list[Diagnostic]:
        """
        compute diagnostics for a file analysis.

        arguments:
            `file_path: Path`
                path to the file
            `analysis: FileAnalysis`
                analysis results

        returns: `list[Diagnostic]`
            list of diagnostics
        """
        diagnostics: list[Diagnostic] = []

        for func_name, func_info in analysis.functions.items():
            # get full exception signature
            exceptions = self.get_function_signature(func_name)

            # filter out ignored exceptions
            exceptions = [exc for exc in exceptions if exc not in self.config.ignore_exceptions]

            if not exceptions:
                continue

            # check if exceptions are documented
            if self.config.analysis.strict_mode:
                docstring = func_info.get("docstring", "") or ""  # pyright: ignore[reportAny]
                undocumented = [exc for exc in exceptions if exc not in docstring]
                if undocumented:
                    location = func_info.get("location", (1, 0))  # pyright: ignore[reportAny]
                    diagnostics.append(
                        Diagnostic(
                            file_path=file_path,
                            line=location[0],
                            column=location[1],
                            message=(
                                f"function '{func_info['name']}' may raise "
                                f"undocumented exceptions: {', '.join(undocumented)}"
                            ),
                            exception_types=undocumented,
                            severity="warning",
                        )
                    )

            # check for bare except clauses
            if not self.config.analysis.allow_bare_except:
                # this would require more detailed ast info
                # for now, we skip this check
                pass

        return diagnostics

    def _find_python_files(self, project_path: Path) -> list[Path]:
        """
        find all python files in a project, respecting excludes.

        arguments:
            `project_path: Path`
                project root directory

        returns: `list[Path]`
            list of python file paths
        """
        import fnmatch

        python_files: list[Path] = []

        for py_file in project_path.rglob("*.py"):
            # check exclusions
            rel_path = py_file.relative_to(project_path)
            excluded = False

            for pattern in self.config.exclude:
                # convert glob pattern to match relative path
                if fnmatch.fnmatch(str(rel_path), pattern):
                    excluded = True
                    break
                if fnmatch.fnmatch(str(rel_path.as_posix()), pattern):
                    excluded = True
                    break

            if not excluded:
                python_files.append(py_file)

        return sorted(python_files)


# need to import time for timestamps
import time
