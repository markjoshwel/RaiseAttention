"""
external module analyzer for raiseattention.

this module provides capabilities to analyse third-party and stdlib modules
to extract exception signatures. it uses graph-based algorithms for efficient
transitive exception tracking through call chains and import resolution.

the analyzer skips c extensions (cpython/hpy modules) as they cannot be
statically analysed.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
import sysconfig
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final

from .ast_visitor import ExceptionVisitor, FunctionInfo, parse_file
from .cache import DependencyCache
from .config import CacheConfig
from .stub_resolver import StubResolver, create_stub_resolver

if TYPE_CHECKING:
    from .env_detector import VenvInfo

logger = logging.getLogger(__name__)

# c extension file suffixes that cannot be parsed
_C_EXTENSION_SUFFIXES: Final[frozenset[str]] = frozenset({".so", ".pyd", ".dll", ".dylib"})

# sentinel exception type for native/c extension code that cannot be statically analysed
POSSIBLE_NATIVE_EXCEPTION: Final[str] = "PossibleNativeException"

# higher-order functions where the first positional arg is a callable that gets invoked
_CALLABLE_INVOKING_HOFS: Final[frozenset[str]] = frozenset(
    {
        # builtins
        "map",
        "filter",
        "sorted",
        "min",
        "max",
        "reduce",
        # functools
        "functools.reduce",
        "functools.partial",
        # itertools
        "itertools.filterfalse",
        "itertools.takewhile",
        "itertools.dropwhile",
        "itertools.starmap",
        "itertools.groupby",
        # concurrent
        "concurrent.futures.ThreadPoolExecutor.submit",
        "concurrent.futures.ProcessPoolExecutor.submit",
        "asyncio.create_task",
        "asyncio.ensure_future",
    }
)

# higher-order functions where the 'key' kwarg is a callable
_KEY_CALLABLE_HOFS: Final[frozenset[str]] = frozenset(
    {
        "sorted",
        "min",
        "max",
        "itertools.groupby",
        "heapq.nlargest",
        "heapq.nsmallest",
    }
)


@dataclass(frozen=True, slots=True)
class ModuleLocation:
    """
    immutable location information for a module.

    attributes:
        `module_name: str`
            fully qualified module name
        `file_path: Path | None`
            path to the source file (none for c extensions)
        `is_stdlib: bool`
            whether this is a stdlib module
        `is_c_extension: bool`
            whether this is a c extension
    """

    module_name: str
    file_path: Path | None
    is_stdlib: bool
    is_c_extension: bool


@dataclass
class ModuleAnalysis:
    """
    analysis result for an external module.

    attributes:
        `location: ModuleLocation`
            module location information
        `exception_signatures: dict[str, frozenset[str]]`
            mapping of function names to exception types they raise
        `imports: dict[str, str]`
            mapping of imported names to their full paths
    """

    location: ModuleLocation
    exception_signatures: dict[str, frozenset[str]] = field(default_factory=dict)
    imports: dict[str, str] = field(default_factory=dict)


# legacy compatibility - kept for backwards compatibility with tests
@dataclass
class ExternalModuleInfo:
    """
    information about an external module (legacy compatibility).

    attributes:
        `module_name: str`
            fully qualified module name
        `file_path: Path | None`
            path to the source file
        `is_stdlib: bool`
            whether this is a stdlib module
        `is_c_extension: bool`
            whether this is a c extension
        `functions: dict[str, FunctionInfo]`
            parsed function information
        `exception_signatures: dict[str, list[str]]`
            computed exception signatures
    """

    module_name: str
    file_path: Path | None
    is_stdlib: bool = False
    is_c_extension: bool = False
    functions: dict[str, FunctionInfo] = field(default_factory=dict)
    exception_signatures: dict[str, list[str]] = field(default_factory=dict)


class ExternalAnalyser:
    """
    analyser for external (third-party and stdlib) python modules.

    uses depth-first search with memoisation for efficient transitive
    exception tracking. follows imports and re-exports to find actual
    function implementations.

    attributes:
        `venv_info: VenvInfo | None`
            detected virtual environment information
        `warn_native: bool`
            whether to warn about native code exceptions
    """

    __slots__: tuple[str, ...] = (
        "venv_info",
        "warn_native",
        "_cache",
        "_analysis_cache",
        "_stdlib_path",
        "_stub_resolver",
    )

    def __init__(
        self,
        venv_info: VenvInfo | None = None,
        cache_config: CacheConfig | None = None,
        *,
        warn_native: bool = True,
        stub_resolver: StubResolver | None = None,
        project_root: Path | None = None,
        python_version: str = "3.12",
    ) -> None:
        """
        initialise the external analyser.

        arguments:
            `venv_info: VenvInfo | None`
                virtual environment info (auto-detected if none)
            `cache_config: CacheConfig | None`
                caching configuration
            `warn_native: bool`
                whether to warn about possible native code exceptions
            `stub_resolver: StubResolver | None`
                custom stub resolver (auto-created if none)
            `project_root: Path | None`
                project root for local stub overrides
            `python_version: str`
                python version for stub resolution
        """
        self.venv_info: VenvInfo | None = venv_info
        self.warn_native: bool = warn_native
        self._cache: DependencyCache = DependencyCache(cache_config or CacheConfig())
        self._analysis_cache: dict[str, ModuleAnalysis] = {}
        self._stub_resolver: StubResolver = stub_resolver or create_stub_resolver(
            project_root=project_root,
            python_version=python_version,
        )

        stdlib_str = sysconfig.get_path("stdlib")
        self._stdlib_path: Path | None = Path(stdlib_str) if stdlib_str else None

    def get_function_exceptions(
        self,
        module_name: str,
        function_name: str,
    ) -> list[str]:
        """
        get exception signature for a function in an external module.

        uses a multi-step resolution strategy:
        1. check .pyras stub files first (for c extensions and pre-computed signatures)
        2. analyse the target module
        3. search for the function by name variants
        4. if not found, follow imports to submodules
        5. for c extensions, return PossibleNativeException if warn_native

        arguments:
            `module_name: str`
                fully qualified module name (e.g., 'json')
            `function_name: str`
                function name (e.g., 'load')

        returns: `list[str]`
            list of exception types the function may raise
        """
        logger.debug("resolving exceptions for: %s.%s", module_name, function_name)

        # check stub files first (covers c extensions and pre-computed signatures)
        qualname = f"{module_name}.{function_name}"
        stub_result = self._stub_resolver.get_raises(qualname)
        if stub_result is not None:
            logger.debug(
                "found stub for %s: %s (confidence=%s, source=%s)",
                qualname,
                stub_result.raises,
                stub_result.confidence,
                stub_result.source,
            )
            return list(stub_result.raises)

        # check if module is a c extension
        location = self._resolve_module(module_name)
        if location is not None and location.is_c_extension:
            logger.debug(
                "detected native code in: %s (path=%s)",
                module_name,
                location.file_path,
            )
            if self.warn_native:
                # check if docstring mentions raising exceptions
                if self._check_docstring_for_raises(module_name, function_name):
                    return [POSSIBLE_NATIVE_EXCEPTION]
                # still return PossibleNativeException for c extensions
                return [POSSIBLE_NATIVE_EXCEPTION]
            return []

        # try direct module first
        exceptions = self._lookup_function(module_name, function_name)
        if exceptions:
            logger.debug("found exceptions for %s.%s: %s", module_name, function_name, exceptions)
            return list(exceptions)

        # follow imports to find re-exported functions
        exceptions = self._resolve_through_imports(module_name, function_name)
        if exceptions:
            logger.debug(
                "resolved exceptions through imports for %s.%s: %s",
                module_name,
                function_name,
                exceptions,
            )
            return list(exceptions)

        # no exceptions found - if warn_native and docstring mentions raises, return sentinel
        if self.warn_native and self._check_docstring_for_raises(module_name, function_name):
            logger.debug(
                "docstring heuristic triggered for: %s.%s",
                module_name,
                function_name,
            )
            return [POSSIBLE_NATIVE_EXCEPTION]

        return []

    def _lookup_function(
        self,
        module_name: str,
        function_name: str,
    ) -> frozenset[str]:
        """
        look up a function's exceptions in a specific module.

        arguments:
            `module_name: str`
                module to search in
            `function_name: str`
                function to find

        returns: `frozenset[str]`
            exception types, empty if not found
        """
        analysis = self._analyse_module(module_name)
        if analysis is None:
            return frozenset()

        sigs = analysis.exception_signatures

        # try exact match first
        if function_name in sigs:
            return sigs[function_name]

        # try with module stem prefix (e.g., "decoder.JSONDecoder.decode")
        module_stem = module_name.rsplit(".", 1)[-1]
        qualified = f"{module_stem}.{function_name}"
        if qualified in sigs:
            return sigs[qualified]

        # try suffix match for nested functions/methods
        for name, exceptions in sigs.items():
            if name.endswith(f".{function_name}"):
                return exceptions

        return frozenset()

    def _resolve_through_imports(
        self,
        module_name: str,
        function_name: str,
    ) -> frozenset[str]:
        """
        follow imports to find a re-exported function.

        many packages re-export functions from internal modules
        (e.g., tomllib exports load from tomllib._parser).

        arguments:
            `module_name: str`
                the package module name
            `function_name: str`
                the function to find

        returns: `frozenset[str]`
            exception types from the actual implementation
        """
        analysis = self._analyse_module(module_name)
        if analysis is None:
            return frozenset()

        # check if function is imported from another module
        if function_name in analysis.imports:
            import_path = analysis.imports[function_name]
            logger.debug("following import: %s -> %s", function_name, import_path)
            parts = import_path.rsplit(".", 1)
            if len(parts) == 2:
                submod, func = parts
                # handle relative imports (e.g., '_parser' -> 'tomllib._parser')
                if submod.startswith("_") or submod.startswith("."):
                    submod = f"{module_name}.{submod.lstrip('.')}"
                return self._lookup_function(submod, func)

        # try common submodule patterns
        for suffix in ("_parser", "_impl", "_core", "decoder", "encoder"):
            submod = f"{module_name}.{suffix}"
            exceptions = self._lookup_function(submod, function_name)
            if exceptions:
                return exceptions

        return frozenset()

    def _analyse_module(self, module_name: str) -> ModuleAnalysis | None:
        """
        analyse a module for exception signatures.

        uses caching at multiple levels:
        1. in-memory cache for current session
        2. persistent disk cache for cross-session

        arguments:
            `module_name: str`
                fully qualified module name

        returns: `ModuleAnalysis | None`
            analysis result, or none if module not found
        """
        logger.debug("resolving module: %s", module_name)

        # check in-memory cache
        if module_name in self._analysis_cache:
            logger.debug("cache hit for: %s", module_name)
            return self._analysis_cache[module_name]

        # resolve module location
        location = self._resolve_module(module_name)
        if location is None:
            return None

        logger.debug(
            "module location: path=%s, stdlib=%s, c_ext=%s",
            location.file_path,
            location.is_stdlib,
            location.is_c_extension,
        )

        # c extensions cannot be analysed
        if location.is_c_extension:
            analysis = ModuleAnalysis(location=location)
            self._analysis_cache[module_name] = analysis
            return analysis

        # check persistent cache
        cache_version = "stdlib" if location.is_stdlib else "external"
        cached_sigs = self._cache.get(module_name, cache_version)
        if cached_sigs is not None:
            logger.debug("disk cache hit for: %s", module_name)
            # convert back to frozensets - cached_sigs is dict[str, list[str]]
            sigs: dict[str, frozenset[str]] = {
                str(k): frozenset(
                    str(item)
                    for item in v  # pyright: ignore[reportAny]
                )
                for k, v in cached_sigs.items()  # pyright: ignore[reportAny]
            }
            analysis = ModuleAnalysis(location=location, exception_signatures=sigs)
            self._analysis_cache[module_name] = analysis
            return analysis

        # parse and analyse
        if location.file_path is None or not location.file_path.exists():
            return None

        try:
            visitor = parse_file(location.file_path)
        except (SyntaxError, OSError):
            return None

        # compute transitive exception signatures using dfs with memoisation
        sigs = self._compute_signatures(visitor, module_name)
        imports = dict(visitor.imports)

        analysis = ModuleAnalysis(
            location=location,
            exception_signatures=sigs,
            imports=imports,
        )

        # cache results (convert to lists for serialisation)
        cache_data: dict[str, list[str]] = {k: list(v) for k, v in sigs.items()}
        self._cache.store(module_name, cache_version, cache_data)
        self._analysis_cache[module_name] = analysis

        return analysis

    def _compute_signatures(
        self,
        visitor: ExceptionVisitor,
        module_name: str,
    ) -> dict[str, frozenset[str]]:
        """
        compute transitive exception signatures for all functions.

        uses depth-first search with memoisation to efficiently
        handle call graphs with cycles and shared dependencies.
        exception types are qualified with the module name when not already
        fully qualified.

        arguments:
            `visitor: ExceptionVisitor`
                parsed ast visitor with function information
            `module_name: str`
                the module name to use for qualifying exception types

        returns: `dict[str, frozenset[str]]`
            mapping of function names to their exception types
        """
        functions = visitor.functions
        memo: dict[str, frozenset[str]] = {}

        def _qualify_exception_type(exc_type: str) -> str:
            """qualify an exception type with the module name if needed."""
            if not exc_type:
                return exc_type

            # get the top-level package name (e.g., 'json' from 'json.decoder')
            top_level_package = module_name.split(".")[0]

            # handle relative references like 'decoder.JSONDecodeError' in module 'json'
            # these should become 'json.JSONDecodeError' (using top-level package)
            if "." in exc_type:
                # extract the exception class name (last part after the dot)
                exc_class_name = exc_type.rsplit(".", 1)[-1]
                # check if this looks like a relative submodule reference
                # (first part is lowercase, suggesting a module name not a class)
                first_part = exc_type.split(".")[0]
                if first_part[0].islower():
                    # it's a relative reference like 'decoder.JSONDecodeError'
                    # qualify with the top-level package
                    return f"{top_level_package}.{exc_class_name}"
                # otherwise it's already fully qualified
                return exc_type

            # built-in exceptions don't need qualification
            builtin_exceptions = {
                "BaseException",
                "BaseExceptionGroup",
                "Exception",
                "ExceptionGroup",
                "GeneratorExit",
                "KeyboardInterrupt",
                "SystemExit",
                "ArithmeticError",
                "FloatingPointError",
                "OverflowError",
                "ZeroDivisionError",
                "AssertionError",
                "AttributeError",
                "BufferError",
                "EOFError",
                "ImportError",
                "ModuleNotFoundError",
                "LookupError",
                "IndexError",
                "KeyError",
                "MemoryError",
                "NameError",
                "UnboundLocalError",
                "OSError",
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
                "ReferenceError",
                "RuntimeError",
                "NotImplementedError",
                "PythonFinalizationError",
                "RecursionError",
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
                "EncodingWarning",
                "FutureWarning",
                "ImportWarning",
                "PendingDeprecationWarning",
                "ResourceWarning",
                "RuntimeWarning",
                "SyntaxWarning",
                "UnicodeWarning",
                "UserWarning",
                "EnvironmentError",
                "IOError",
                "VMSError",
                "WindowsError",
            }
            if exc_type in builtin_exceptions:
                return exc_type
            # qualify with module name
            return f"{module_name}.{exc_type}"

        def dfs(func_name: str, visiting: frozenset[str]) -> frozenset[str]:
            """depth-first traversal with cycle detection."""
            # memoised result
            if func_name in memo:
                return memo[func_name]

            # not in this module
            if func_name not in functions:
                return frozenset()

            # cycle detected - return empty to break recursion
            if func_name in visiting:
                return frozenset()

            func_info = functions[func_name]
            visiting = visiting | {func_name}

            # collect direct exceptions
            exceptions: set[str] = set()
            for exc in func_info.raises:
                if exc.exception_type and not exc.is_re_raise:
                    exceptions.add(_qualify_exception_type(exc.exception_type))

            # collect from called functions (transitive)
            for call in func_info.calls:
                called = call.func_name

                # find matching function in module
                for name in functions:
                    if name == called or name.endswith(f".{called}"):
                        exceptions.update(dfs(name, visiting))
                        break

            result = frozenset(exceptions)
            memo[func_name] = result
            return result

        # compute for all functions
        for name in functions:
            _ = dfs(name, frozenset())

        return memo

    def _resolve_module(self, module_name: str) -> ModuleLocation | None:
        """
        resolve a module name to its file location.

        arguments:
            `module_name: str`
                fully qualified module name

        returns: `ModuleLocation | None`
            location info, or none if not found
        """
        if not module_name:
            return None

        try:
            spec = importlib.util.find_spec(module_name)
        except (ImportError, ModuleNotFoundError, ValueError):
            return None

        if spec is None or spec.origin is None:
            return None

        origin = spec.origin

        # handle built-in modules (e.g., '_json', '_csv' on windows)
        # these have origin='built-in' and cannot be statically analysed
        if origin == "built-in":
            return ModuleLocation(
                module_name=module_name,
                file_path=None,
                is_stdlib=True,
                is_c_extension=True,
            )

        file_path = Path(origin)
        is_c_ext = file_path.suffix.lower() in _C_EXTENSION_SUFFIXES
        is_stdlib = self._is_stdlib_path(file_path)

        return ModuleLocation(
            module_name=module_name,
            file_path=file_path if not is_c_ext else None,
            is_stdlib=is_stdlib,
            is_c_extension=is_c_ext,
        )

    def _is_stdlib_path(self, file_path: Path) -> bool:
        """check if a file path is within the stdlib."""
        if self._stdlib_path is None:
            return False
        try:
            _ = file_path.resolve().relative_to(self._stdlib_path.resolve())
            return True
        except ValueError:
            return False

    def _check_docstring_for_raises(self, module_name: str, function_name: str) -> bool:
        """
        check if a function's docstring mentions raising exceptions.

        this is a heuristic for functions we can't statically analyse.

        arguments:
            `module_name: str`
                the module containing the function
            `function_name: str`
                the function name (may be dotted for methods)

        returns: `bool`
            true if the docstring mentions raising exceptions
        """
        logger.debug("checking docstring for: %s.%s", module_name, function_name)
        try:
            module = importlib.import_module(module_name)
            obj = module
            # handle dotted function names (e.g., "JSONDecoder.decode")
            for part in function_name.split("."):
                obj = getattr(obj, part, None)  # pyright: ignore[reportAny]
                if obj is None:
                    return False

            if obj is not None and hasattr(obj, "__doc__") and obj.__doc__:
                doc_lower: str = obj.__doc__.lower()  # pyright: ignore[reportAny]
                has_raises = "raise" in doc_lower or "raises" in doc_lower
                if has_raises:
                    logger.debug("docstring mentions raises for: %s.%s", module_name, function_name)
                return has_raises
        except (ImportError, AttributeError, TypeError):
            pass
        return False

    def _get_builtin_canonical_module(self, func_name: str) -> str:
        """
        get the canonical module for a builtin function using introspection.

        some builtins like `open` are actually defined in other modules
        (e.g., `builtins.open` is `_io.open`). this method uses python's
        `__module__` attribute to find the true origin.

        arguments:
            `func_name: str`
                name of the builtin function (e.g., "open", "input")

        returns: `str`
            the canonical module name (e.g., "_io" for open, "builtins" for input)
        """
        import builtins

        func = getattr(builtins, func_name, None)
        if func is not None:
            canonical = getattr(func, "__module__", None)
            if canonical is not None and isinstance(canonical, str):
                logger.debug("resolved builtin %s to canonical module: %s", func_name, canonical)
                return canonical
        # fallback to builtins
        return "builtins"

    def resolve_import_to_module(
        self,
        import_name: str,
        imports: dict[str, str],
    ) -> tuple[str, str] | None:
        """
        resolve an import reference to (module, function).

        arguments:
            `import_name: str`
                the name as used in code (e.g., 'json.loads')
            `imports: dict[str, str]`
                import map from the source file

        returns: `tuple[str, str] | None`
            (module_name, function_name) or none
        """
        # check explicit import map first
        if import_name in imports:
            full_path = imports[import_name]
            parts = full_path.rsplit(".", 1)
            if len(parts) == 2:
                return parts[0], parts[1]
            return full_path, ""

        # handle dotted names (e.g., 'json.loads')
        if "." not in import_name:
            # only check specific builtins that commonly raise exceptions
            # we don't want to flag every len(), list(), print() etc.
            _INTERESTING_BUILTINS: frozenset[str] = frozenset(
                {
                    "open",
                    "exec",
                    "eval",
                    "compile",
                    "input",
                    "__import__",
                }
            )
            if import_name in _INTERESTING_BUILTINS:
                # use introspection to find the canonical module for this builtin
                # e.g., builtins.open.__module__ == '_io', so we return ('_io', 'open')
                # this avoids needing to maintain a hardcoded redirect map
                canonical_module = self._get_builtin_canonical_module(import_name)
                return canonical_module, import_name
            return None

        # try progressively shorter module prefixes
        parts = import_name.split(".")
        for i in range(len(parts) - 1, 0, -1):
            module = ".".join(parts[:i])
            func = ".".join(parts[i:])
            if self._resolve_module(module) is not None:
                return module, func

        return None

    # legacy compatibility methods for tests
    def resolve_module_path(self, module_name: str) -> ExternalModuleInfo | None:
        """
        resolve a module name to its source file path (legacy api).

        arguments:
            `module_name: str`
                fully qualified module name

        returns: `ExternalModuleInfo | None`
            module information if found
        """
        location = self._resolve_module(module_name)
        if location is None:
            return None

        return ExternalModuleInfo(
            module_name=location.module_name,
            file_path=location.file_path,
            is_stdlib=location.is_stdlib,
            is_c_extension=location.is_c_extension,
        )

    def analyse_module(self, module_name: str) -> ExternalModuleInfo | None:
        """
        analyse an external module for exception signatures (legacy api).

        arguments:
            `module_name: str`
                fully qualified module name

        returns: `ExternalModuleInfo | None`
            analysed module info
        """
        analysis = self._analyse_module(module_name)
        if analysis is None:
            return None

        return ExternalModuleInfo(
            module_name=analysis.location.module_name,
            file_path=analysis.location.file_path,
            is_stdlib=analysis.location.is_stdlib,
            is_c_extension=analysis.location.is_c_extension,
            exception_signatures={k: list(v) for k, v in analysis.exception_signatures.items()},
        )


@lru_cache(maxsize=1)
def get_stdlib_modules() -> frozenset[str]:
    """
    get the set of stdlib module names.

    returns: `frozenset[str]`
        all top-level stdlib module names
    """
    modules: set[str] = set()

    # python 3.10+ has this attribute
    if hasattr(sys, "stdlib_module_names"):
        stdlib_names: frozenset[str] = sys.stdlib_module_names
        modules.update(stdlib_names)

    # ensure common modules are included
    modules.update(
        {
            "abc",
            "ast",
            "asyncio",
            "base64",
            "bz2",
            "calendar",
            "cmath",
            "codecs",
            "collections",
            "configparser",
            "contextlib",
            "copy",
            "csv",
            "ctypes",
            "datetime",
            "decimal",
            "difflib",
            "dis",
            "doctest",
            "email",
            "fnmatch",
            "fractions",
            "functools",
            "glob",
            "gzip",
            "hashlib",
            "hmac",
            "html",
            "http",
            "inspect",
            "io",
            "itertools",
            "json",
            "keyword",
            "linecache",
            "logging",
            "lzma",
            "math",
            "mmap",
            "multiprocessing",
            "numbers",
            "os",
            "pathlib",
            "pickle",
            "pprint",
            "queue",
            "random",
            "re",
            "secrets",
            "select",
            "shutil",
            "signal",
            "socket",
            "sqlite3",
            "ssl",
            "string",
            "struct",
            "subprocess",
            "symtable",
            "sys",
            "tarfile",
            "tempfile",
            "textwrap",
            "threading",
            "time",
            "token",
            "tokenize",
            "tomllib",
            "traceback",
            "typing",
            "unicodedata",
            "unittest",
            "urllib",
            "warnings",
            "xml",
            "zipfile",
        }
    )

    return frozenset(modules)


def is_stdlib_module(module_name: str) -> bool:
    """
    check if a module is part of the standard library.

    arguments:
        `module_name: str`
            module name (may be dotted)

    returns: `bool`
        true if it's a stdlib module
    """
    top_level = module_name.split(".")[0]
    return top_level in get_stdlib_modules()
