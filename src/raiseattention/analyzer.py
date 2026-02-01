"""
core exception analysis engine for raiseattention.

this module provides the main analysis logic for detecting unhandled
exceptions in python code, including transitive propagation tracking
through call chains with try-except handling detection.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .ast_visitor import parse_file
from .cache import DependencyCache, FileAnalysis, FileCache
from .config import Config
from .external_analyzer import ExternalAnalyzer

if TYPE_CHECKING:
    from .env_detector import VenvInfo


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
    transitive propagation through function calls with proper
    try-except handling detection. also analyses external modules
    (stdlib and third-party packages) for exception signatures.

    attributes:
        `config: Config`
            configuration settings
        `file_cache: FileCache`
            file-level analysis cache
        `dependency_cache: DependencyCache`
            external library exception cache
        `external_analyzer: ExternalAnalyzer`
            analyser for external modules (stdlib/third-party)
        `_file_analyses: dict[Path, FileAnalysis]`
            current analysis results by file
        `_exception_signatures: dict[str, list[str]]`
            computed exception signatures for functions
    """

    def __init__(
        self,
        config: Config,
        venv_info: VenvInfo | None = None,
    ) -> None:
        """
        initialise the exception analyzer.

        arguments:
            `config: Config`
                configuration settings
            `venv_info: VenvInfo | None`
                virtual environment info for external module analysis
        """
        self.config = config
        self.file_cache = FileCache(config.cache)
        self.dependency_cache = DependencyCache(config.cache)
        self.external_analyzer = ExternalAnalyzer(venv_info, config.cache)
        self._file_analyses: dict[Path, FileAnalysis] = {}
        self._exception_signatures: dict[str, list[str]] = {}

    def _get_ignore_exceptions(self) -> list[str]:
        """
        get the list of exception types to ignore.

        combines the top-level config.ignore_exceptions with any
        exceptions defined in analysis config for compatibility.

        returns: `list[str]`
            combined list of exception types to ignore
        """
        # get base list from config
        ignored = list(self.config.ignore_exceptions)

        # also check analysis config (for backward compatibility with tests)
        if hasattr(self.config.analysis, "ignore_exceptions"):
            analysis_ignored = getattr(self.config.analysis, "ignore_exceptions", [])
            if analysis_ignored:
                # extend without duplicates
                for exc in analysis_ignored:
                    if exc not in ignored:
                        ignored.append(exc)

        return ignored

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
                    exception_types=[],
                    severity="error",
                )
            )
            return result

        # create file analysis with new structure
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
                    "calls": [
                        {
                            "func_name": call.func_name,
                            "location": call.location,
                            "is_async": call.is_async,
                            "containing_try_blocks": call.containing_try_blocks,
                        }
                        for call in func.calls
                    ],
                    "docstring": func.docstring,
                    "is_async": func.is_async,
                }
                for name, func in visitor.functions.items()
            },
            imports=visitor.imports,
            timestamp=time.time(),
            try_except_blocks=[
                {
                    "location": try_info.location,
                    "end_location": try_info.end_location,
                    "handled_types": try_info.handled_types,
                    "has_bare_except": try_info.has_bare_except,
                    "has_except_exception": try_info.has_except_exception,
                    "reraises": try_info.reraises,
                }
                for try_info in visitor.try_except_blocks
            ],
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

    def get_function_signature(
        self,
        qualified_name: str,
        context_file: Path | None = None,
        _recursion_stack: set[str] | None = None,
    ) -> list[str]:
        """
        get the exception signature for a function.

        this computes the transitive exception signature, including
        exceptions from called functions. for functions not found in
        the local codebase, it looks up external modules (stdlib and
        third-party packages). exceptions in the ignore_exceptions
        config are filtered out.

        arguments:
            `qualified_name: str`
                fully qualified function name (or simple name if context_file provided)
            `context_file: Path | None`
                file path for resolving simple function names
            `_recursion_stack: set[str] | None`
                internal use for detecting circular calls

        returns: `list[str]`
            list of exception types the function may raise
        """
        if qualified_name in self._exception_signatures:
            return self._exception_signatures[qualified_name]

        # initialize recursion stack (use a list to maintain shared state)
        if _recursion_stack is None:
            _recursion_stack = set()

        # find function in analyses
        func_info = None
        resolved_name = qualified_name
        imports: dict[str, str] = {}

        # first try exact match
        for _analysis_path, analysis in self._file_analyses.items():
            if qualified_name in analysis.functions:
                func_info = analysis.functions[qualified_name]
                resolved_name = qualified_name
                imports = analysis.imports
                break

        # if not found and context provided, try to resolve relative to context
        if func_info is None and context_file is not None and context_file in self._file_analyses:
            analysis = self._file_analyses[context_file]
            imports = analysis.imports
            # try with module prefix from the context file
            for name in analysis.functions:
                if name.endswith(f".{qualified_name}") or name == qualified_name:
                    func_info = analysis.functions[name]
                    resolved_name = name
                    break

        # if not found locally, try to resolve from external modules
        # if not found locally, try to resolve from external modules
        # (unless local_only mode is enabled)
        if func_info is None:
            if not self.config.analysis.local_only:
                external_exceptions = self._get_external_function_exceptions(
                    qualified_name, imports
                )
                if external_exceptions:
                    # filter out ignored exceptions
                    result = [
                        exc
                        for exc in external_exceptions
                        if exc not in self._get_ignore_exceptions()
                    ]
                    self._exception_signatures[qualified_name] = result
                    return result
            return []

        # detect circular references using resolved name
        if resolved_name in _recursion_stack:
            return []

        # add to recursion stack (modifies the shared set in-place)
        _recursion_stack.add(resolved_name)

        # find the file this function belongs to (for resolving called function names)
        func_file_path = None
        for analysis_path, analysis in self._file_analyses.items():
            if resolved_name in analysis.functions:
                func_file_path = analysis_path
                imports = analysis.imports
                break

        # collect directly raised exceptions
        exceptions: set[str] = set()
        for exc in func_info.get("raises", []):
            exc_type = exc.get("type", "")
            is_re_raise = exc.get("is_re_raise", False)
            if exc_type and not is_re_raise and exc_type not in self._get_ignore_exceptions():
                exceptions.add(exc_type)

        # collect from called functions (transitive)
        for call in func_info.get("calls", []):
            called_func_name = call.get("func_name", "") if isinstance(call, dict) else call

            if called_func_name:
                called_exceptions = self.get_function_signature(
                    called_func_name, func_file_path, _recursion_stack
                )
                # called exceptions are already filtered by their own signature computation
                exceptions.update(called_exceptions)

        # remove empty strings
        exceptions.discard("")

        # cache result
        result = list(exceptions)
        self._exception_signatures[resolved_name] = result

        # remove from recursion stack to allow other calls
        _recursion_stack.discard(resolved_name)

        return result

    def _get_external_function_exceptions(
        self,
        func_name: str,
        imports: dict[str, str],
    ) -> list[str]:
        """
        get exception signature for a function from external modules.

        this method resolves the function name to an external module
        and returns its exception signature. it handles both direct
        module references (e.g., 'json.loads') and imported names
        (e.g., 'loads' when 'from json import loads' was used).

        arguments:
            `func_name: str`
                function name (may be dotted like 'json.loads')
            `imports: dict[str, str]`
                mapping of imported names to full paths

        returns: `list[str]`
            list of exception types, empty if not found
        """
        # try to resolve the module and function
        resolved = self.external_analyzer.resolve_import_to_module(func_name, imports)
        if resolved is None:
            return []

        module_name, function_name = resolved

        # get the exceptions for this function
        return self.external_analyzer.get_function_exceptions(module_name, function_name)

    def invalidate_file(self, file_path: str | Path) -> None:
        """
        Invalidate cache for a file.

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
        """Clear all caches."""
        self.file_cache.clear()
        self._file_analyses.clear()
        self._exception_signatures.clear()

    def _compute_diagnostics(
        self,
        file_path: Path,
        analysis: FileAnalysis,
    ) -> list[Diagnostic]:
        """
                Compute diagnostics for a file analysis.

                this method analyses each function's calls and checks whether
        the exceptions from called functions are handled by try-except blocks
        at the call sites. it also considers exception hierarchies where
        catching a parent class handles child exceptions.

        arguments:
                    `file_path: Path`
                        path to the file
                    `analysis: FileAnalysis`
                        analysis results

                returns: `list[Diagnostic]`
                    list of diagnostics
        """
        diagnostics: list[Diagnostic] = []

        # get try-except blocks from analysis
        try_blocks = getattr(analysis, "try_except_blocks", [])

        # first pass: compute function signatures and find unhandled exceptions at call sites
        # track which functions have unhandled exceptions escaping them
        func_unhandled_exceptions: dict[str, set[str]] = {}
        call_diagnostics: list[Diagnostic] = []

        for func_name, func_info in analysis.functions.items():
            func_location = func_info.get("location", (1, 0))
            func_display_name = func_info.get("name", func_name)
            # note: is_async is available but not used currently
            # _ = func_info.get("is_async", False)

            # get full exception signature for this function (with file context)
            func_exceptions = self.get_function_signature(func_name, file_path)

            # filter out ignored exceptions
            func_exceptions = [
                exc for exc in func_exceptions if exc not in self._get_ignore_exceptions()
            ]

            # track unhandled exceptions for this function
            func_unhandled_exceptions[func_name] = set()

            # check each call in this function
            calls = func_info.get("calls", [])
            for call in calls:
                if isinstance(call, dict):
                    called_func_name = call.get("func_name", "")
                    call_location = call.get("location", (1, 0))
                    containing_tries = call.get("containing_try_blocks", [])
                    # note: is_async is available but not used currently
                    # _ = call.get("is_async", False)
                else:
                    # backward compatibility with string-only calls
                    called_func_name = call
                    call_location = func_location
                    containing_tries = []

                if not called_func_name:
                    continue

                # get the called function's exception signature (with file context)
                called_exceptions = self.get_function_signature(called_func_name, file_path)

                # filter out ignored exceptions
                called_exceptions = [
                    exc for exc in called_exceptions if exc not in self._get_ignore_exceptions()
                ]

                if not called_exceptions:
                    continue

                # check which exceptions are handled at this call site
                unhandled_exceptions = self._get_unhandled_exceptions(
                    called_exceptions, containing_tries, try_blocks
                )

                if unhandled_exceptions:
                    # report diagnostic at the call site
                    call_diagnostics.append(
                        Diagnostic(
                            file_path=file_path,
                            line=call_location[0],
                            column=call_location[1],
                            message=(
                                f"call to '{called_func_name}' may raise "
                                f"unhandled exception(s): {', '.join(unhandled_exceptions)}"
                            ),
                            exception_types=unhandled_exceptions,
                            severity="error",
                        )
                    )
                    # track that these exceptions escape from the current function
                    func_unhandled_exceptions[func_name].update(unhandled_exceptions)

        diagnostics.extend(call_diagnostics)

        # second pass: check for undocumented exceptions in strict mode
        # only flag functions that have unhandled exceptions escaping them
        if self.config.analysis.strict_mode:
            for func_name, func_info in analysis.functions.items():
                func_location = func_info.get("location", (1, 0))
                func_display_name = func_info.get("name", func_name)

                # get this function's exceptions
                func_exceptions = self.get_function_signature(func_name, file_path)
                func_exceptions = [
                    exc for exc in func_exceptions if exc not in self._get_ignore_exceptions()
                ]

                if not func_exceptions:
                    continue

                # check if this function has unhandled exceptions escaping
                has_unhandled_escaping = len(func_unhandled_exceptions.get(func_name, set())) > 0

                # also check if function has no calls (exceptions might escape to external callers)
                calls = func_info.get("calls", [])
                has_no_calls = len(calls) == 0

                if has_unhandled_escaping or has_no_calls:
                    docstring = func_info.get("docstring", "") or ""
                    undocumented = [exc for exc in func_exceptions if exc not in docstring]
                    if undocumented:
                        diagnostics.append(
                            Diagnostic(
                                file_path=file_path,
                                line=func_location[0],
                                column=func_location[1],
                                message=(
                                    f"function '{func_display_name}' may raise "
                                    f"undocumented exceptions: {', '.join(undocumented)}"
                                ),
                                exception_types=undocumented,
                                severity="warning",
                            )
                        )

        return diagnostics

    def _get_unhandled_exceptions(
        self,
        exception_types: list[str],
        containing_try_blocks: list[int],
        try_blocks: list[dict],
    ) -> list[str]:
        """
                Determine which exceptions are not handled by the given try-except blocks.

                this method checks if each exception type would be caught by any of the
        try-except blocks in scope. it considers exception hierarchies where
        catching 'Exception' will catch 'ValueError', etc.

        arguments:
                    `exception_types: list[str]`
                        list of exception types to check
                    `containing_try_blocks: list[int]`
                        indices of try-except blocks containing the call
                    `try_blocks: list[dict]`
                        all try-except blocks in the file

                returns: `list[str]`
                    list of exception types that are NOT handled
        """
        unhandled: list[str] = []

        for exc_type in exception_types:
            is_handled = False

            # check each containing try-except block
            for try_index in containing_try_blocks:
                if try_index >= len(try_blocks):
                    continue

                try_block = try_blocks[try_index]
                handled_types = try_block.get("handled_types", [])
                has_bare_except = try_block.get("has_bare_except", False)
                reraises = try_block.get("reraises", False)

                # bare except catches everything (unless it re-raises)
                if has_bare_except and not reraises:
                    is_handled = True
                    break

                # check if any handler catches this exception type
                for handled_type in handled_types:
                    if self._exception_is_caught(exc_type, handled_type):
                        is_handled = True
                        break

                if is_handled:
                    break

            if not is_handled:
                unhandled.append(exc_type)

        return unhandled

    def _exception_is_caught(self, exception_type: str, handler_type: str) -> bool:
        """
        check if an exception type would be caught by a handler type.

        this considers exception hierarchies. for example:
        - ValueError is caught by Exception
        - ValidationError is caught by BusinessError (if ValidationError is a subclass)

        arguments:
            `exception_type: str`
                the exception type being raised
            `handler_type: str`
                the exception type in the except clause

        returns: `bool`
            true if the exception would be caught
        """
        # exact match
        if exception_type == handler_type:
            return True

        # check built-in exception hierarchy
        # we need to handle common cases where parent classes catch children
        return self._is_subclass_of(exception_type, handler_type)

    def _is_subclass_of(self, child_type: str, parent_type: str) -> bool:
        """
                check if one exception type is a subclass of another.

                this method uses knowledge of python's built-in exception hierarchy
        and common patterns. it attempts to resolve actual class relationships
        where possible.

        arguments:
                    `child_type: str`
                        the potential child exception type
                    `parent_type: str`
                        the potential parent exception type

                returns: `bool`
                    true if child_type is a subclass of parent_type
        """
        # handle multi-type except clauses (e.g., except (ValueError, TypeError))
        if "," in parent_type:
            parent_types = [t.strip() for t in parent_type.split(",")]
            return any(self._is_subclass_of(child_type, pt) for pt in parent_types)

        # built-in exception hierarchy mapping
        # these are the most common parent classes
        exception_hierarchy = {
            "BaseException": [
                "SystemExit",
                "KeyboardInterrupt",
                "GeneratorExit",
                "Exception",
            ],
            "Exception": [
                "ArithmeticError",
                "LookupError",
                "AssertionError",
                "AttributeError",
                "BufferError",
                "EOFError",
                "FloatingPointError",
                "OSError",
                "ImportError",
                "ModuleNotFoundError",
                "IndexError",
                "KeyError",
                "MemoryError",
                "NameError",
                "UnboundLocalError",
                "OverflowError",
                "RecursionError",
                "ReferenceError",
                "RuntimeError",
                "NotImplementedError",
                "StopAsyncIteration",
                "StopIteration",
                "SyntaxError",
                "IndentationError",
                "TabError",
                "SystemError",
                "TypeError",
                "ValueError",
                "UnicodeError",
                "UnicodeDecodeError",
                "UnicodeEncodeError",
                "UnicodeTranslateError",
                "Warning",
                "BytesWarning",
                "DeprecationWarning",
                "FutureWarning",
                "ImportWarning",
                "PendingDeprecationWarning",
                "ResourceWarning",
                "RuntimeWarning",
                "SyntaxWarning",
                "UnicodeWarning",
                "UserWarning",
                "BlockingIOError",
                "ChildProcessError",
                "ConnectionError",
                "BrokenPipeError",
                "ConnectionAbortedError",
                "ConnectionRefusedError",
                "ConnectionResetError",
                "FileExistsError",
                "FileNotFoundError",
                "InterruptedError",
                "IsADirectoryError",
                "NotADirectoryError",
                "PermissionError",
                "ProcessLookupError",
                "TimeoutError",
                "ZeroDivisionError",
                "EnvironmentError",
                "IOError",
                "VMSError",
                "WindowsError",
                "ZeroDivisionError",
            ],
            "ArithmeticError": ["FloatingPointError", "OverflowError", "ZeroDivisionError"],
            "LookupError": ["IndexError", "KeyError"],
            "OSError": [
                "BlockingIOError",
                "ChildProcessError",
                "ConnectionError",
                "FileExistsError",
                "FileNotFoundError",
                "InterruptedError",
                "IsADirectoryError",
                "NotADirectoryError",
                "PermissionError",
                "ProcessLookupError",
                "TimeoutError",
                "EnvironmentError",
                "IOError",
                "VMSError",
                "WindowsError",
            ],
            "ConnectionError": [
                "BrokenPipeError",
                "ConnectionAbortedError",
                "ConnectionRefusedError",
                "ConnectionResetError",
            ],
            "ImportError": ["ModuleNotFoundError"],
            "NameError": ["UnboundLocalError"],
            "UnicodeError": [
                "UnicodeDecodeError",
                "UnicodeEncodeError",
                "UnicodeTranslateError",
            ],
            "Warning": [
                "BytesWarning",
                "DeprecationWarning",
                "FutureWarning",
                "ImportWarning",
                "PendingDeprecationWarning",
                "ResourceWarning",
                "RuntimeWarning",
                "SyntaxWarning",
                "UnicodeWarning",
                "UserWarning",
            ],
            "SyntaxError": ["IndentationError"],
            "IndentationError": ["TabError"],
        }

        # check if child is a known subclass of parent
        if parent_type in exception_hierarchy:
            if child_type in exception_hierarchy[parent_type]:
                return True
            # check transitive relationships
            for intermediate in exception_hierarchy[parent_type]:
                if self._is_subclass_of(child_type, intermediate):
                    return True

        # try to resolve using actual python classes if they're built-in
        try:
            child_class = eval(child_type)  # noqa: S307 - only used for built-in exception types
            parent_class = eval(parent_type)  # noqa: S307 - only used for built-in exception types
            if isinstance(child_class, type) and isinstance(parent_class, type):
                return issubclass(child_class, parent_class)
        except (NameError, TypeError, AttributeError):
            pass

        return False

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
