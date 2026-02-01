"""
external module analyzer for raiseattention.

this module provides capabilities to analyse third-party and stdlib modules
to extract exception signatures. it uses graph-based algorithms for efficient
transitive exception tracking through call chains and import resolution.

the analyzer skips c extensions (cpython/hpy modules) as they cannot be
statically analysed.
"""

from __future__ import annotations

import importlib.util
import sys
import sysconfig
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final

from .ast_visitor import ExceptionVisitor, FunctionInfo, parse_file
from .cache import DependencyCache
from .config import CacheConfig

if TYPE_CHECKING:
    from .env_detector import VenvInfo


# c extension file suffixes that cannot be parsed
_C_EXTENSION_SUFFIXES: Final[frozenset[str]] = frozenset({".so", ".pyd", ".dll", ".dylib"})


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


class ExternalAnalyzer:
    """
    analyser for external (third-party and stdlib) python modules.

    uses depth-first search with memoisation for efficient transitive
    exception tracking. follows imports and re-exports to find actual
    function implementations.

    attributes:
        `venv_info: VenvInfo | None`
            detected virtual environment information
    """

    __slots__: tuple[str, ...] = ("venv_info", "_cache", "_analysis_cache", "_stdlib_path")

    def __init__(
        self,
        venv_info: VenvInfo | None = None,
        cache_config: CacheConfig | None = None,
    ) -> None:
        """
        initialise the external analyser.

        arguments:
            `venv_info: VenvInfo | None`
                virtual environment info (auto-detected if none)
            `cache_config: CacheConfig | None`
                caching configuration
        """
        self.venv_info: VenvInfo | None = venv_info
        self._cache: DependencyCache = DependencyCache(cache_config or CacheConfig())
        self._analysis_cache: dict[str, ModuleAnalysis] = {}

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
        1. analyse the target module
        2. search for the function by name variants
        3. if not found, follow imports to submodules

        arguments:
            `module_name: str`
                fully qualified module name (e.g., 'json')
            `function_name: str`
                function name (e.g., 'load')

        returns: `list[str]`
            list of exception types the function may raise
        """
        # try direct module first
        exceptions = self._lookup_function(module_name, function_name)
        if exceptions:
            return list(exceptions)

        # follow imports to find re-exported functions
        return list(self._resolve_through_imports(module_name, function_name))

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
        # check in-memory cache
        if module_name in self._analysis_cache:
            return self._analysis_cache[module_name]

        # resolve module location
        location = self._resolve_module(module_name)
        if location is None:
            return None

        # c extensions cannot be analysed
        if location.is_c_extension:
            analysis = ModuleAnalysis(location=location)
            self._analysis_cache[module_name] = analysis
            return analysis

        # check persistent cache
        cache_version = "stdlib" if location.is_stdlib else "external"
        cached_sigs = self._cache.get(module_name, cache_version)
        if cached_sigs is not None:
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
        sigs = self._compute_signatures(visitor)
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
    ) -> dict[str, frozenset[str]]:
        """
        compute transitive exception signatures for all functions.

        uses depth-first search with memoisation to efficiently
        handle call graphs with cycles and shared dependencies.

        arguments:
            `visitor: ExceptionVisitor`
                parsed ast visitor with function information

        returns: `dict[str, frozenset[str]]`
            mapping of function names to their exception types
        """
        functions = visitor.functions
        memo: dict[str, frozenset[str]] = {}

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
                    exceptions.add(exc.exception_type)

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
