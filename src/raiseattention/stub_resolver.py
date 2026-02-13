"""
stub resolver for loading .pyras exception stub files (v2.0).

provides version-aware resolution of exception stubs from .pyras files,
with support for project-local overrides, vendored stdlib stubs,
and fuzzy matching for class name mismatches.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from packaging.specifiers import SpecifierSet
from packaging.version import Version

logger = logging.getLogger(__name__)


def _get_nested_dict(parent: dict[str, object], key: str) -> dict[str, object] | None:
    """
    get a nested dict with proper type narrowing.

    pyright cannot infer nested dict types after isinstance checks on
    values from `dict[str, object].get()`, so this helper handles the
    type coercion explicitly.
    """
    value = parent.get(key)
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for k, v in value.items():  # pyright: ignore[reportUnknownVariableType]
            result[str(k)] = v  # pyright: ignore[reportUnknownArgumentType]
        return result
    return None


def _to_str_list(value: object) -> list[str] | None:
    """
    convert a value to a list of strings with proper type narrowing.

    pyright cannot infer list element types after isinstance checks on
    values from `dict[str, object].get()`, so this helper handles the
    type coercion explicitly.
    """
    if isinstance(value, list):
        result: list[str] = []
        for item in value:  # pyright: ignore[reportUnknownVariableType]
            result.append(str(item))  # pyright: ignore[reportUnknownArgumentType]
        return result
    return None


def _to_str_dict(value: object) -> dict[str, str] | None:
    """
    convert a value to a dict of strings with proper type narrowing.

    used for exception confidence mappings like {"TypeError": "exact"}.
    """
    if isinstance(value, dict):
        result: dict[str, str] = {}
        for k, v in value.items():  # pyright: ignore[reportUnknownVariableType]
            result[str(k)] = str(v)  # pyright: ignore[reportUnknownArgumentType]
        return result
    return None


# confidence levels (v2.0: default is "likely")
class Confidence:
    """
    confidence level for exception signature extraction.

    v2.0 changes:
    - default is LIKELY (was EXACT in v1.0)
    - per-exception confidence in nested structure
    """

    EXACT: str = "exact"
    LIKELY: str = "likely"
    CONSERVATIVE: str = "conservative"
    MANUAL: str = "manual"


class StubLookupResult(NamedTuple):
    """
    result of looking up a function in stub files.

    attributes:
        `raises: frozenset[str]`
            exception types the function may raise
        `confidence: str`
            overall confidence level (highest of all exceptions)
        `source: Path | None`
            path to the stub file (none if not from file)
        `per_exception_confidence: dict[str, str] | None`
            mapping of exception -> confidence (v2.0 feature)
    """

    raises: frozenset[str]
    confidence: str
    source: Path | None = None
    per_exception_confidence: dict[str, str] | None = None


@dataclass
class StubSource:
    """
    a source of stub files with priority.

    attributes:
        `path: Path`
            directory containing .pyras files
        `priority: int`
            higher priority sources are checked first
        `name: str`
            human-readable name for logging
    """

    path: Path
    priority: int = 0
    name: str = ""

    def __post_init__(self) -> None:
        """set default name from path if not provided."""
        if not self.name:
            self.name = str(self.path)


@dataclass
class CachedStubFile:
    """
    cached stub file data (v2.0 nested format).

    structure: module -> class_or_func -> method -> exception -> confidence
    for module-level functions: module -> "" -> func_name -> exception -> confidence

    attributes:
        `path: Path`
            path to the .pyras file
        `data: dict[str, object]`
            raw json data with metadata and module stubs
        `format_version: str`
            pyras format version ("2.0")
    """

    path: Path
    data: dict[str, object] = field(default_factory=dict)
    format_version: str = "2.0"


@dataclass
class StubResolver:
    """
    resolve .pyras stub files by version and module (v2.0).

    searches multiple stub sources in priority order:
    1. project-local overrides (.raiseattention/stubs/)
    2. shipped stdlib stubs (raiseattention/stubs/stdlib/)
    3. third-party stubs (raiseattention/stubs/third-party/)

    fuzzy matching:
    - exact match first (O(1) dict lookup)
    - fallback to fuzzy matching on miss (O(n) scan)
    - caches fuzzy results for O(1) subsequent lookups

    v2.0 changes:
    - parses json instead of toml (faster)
    - handles nested structure (module.class.method.exception.confidence)
    - per-exception confidence levels
    - fuzzy matching for class name mismatches (e.g., mmap.mmap vs mmap.Mmap_object)
    - module underscore prefix normalization (_io vs io)

    attributes:
        `sources: list[StubSource]`
            ordered list of stub sources
        `target_version: Version`
            python version to resolve stubs for
    """

    sources: list[StubSource] = field(default_factory=list)
    target_version: Version = field(default_factory=lambda: Version("3.12.0"))
    _file_cache: dict[str, CachedStubFile | None] = field(default_factory=dict, repr=False)
    _function_cache: dict[str, StubLookupResult | None] = field(default_factory=dict, repr=False)

    def add_source(self, path: Path, priority: int = 0, name: str = "") -> None:
        """
        add a stub source directory.

        arguments:
            `path: Path`
                directory containing .pyras files
            `priority: int`
                higher priority sources are checked first
            `name: str`
                human-readable name for logging
        """
        source = StubSource(path=path, priority=priority, name=name or str(path))
        self.sources.append(source)
        # re-sort by priority (highest first)
        self.sources.sort(key=lambda s: s.priority, reverse=True)
        # clear caches when sources change
        self._file_cache.clear()
        self._function_cache.clear()

    def find_stub_file(self, module: str) -> Path | None:
        """
        find best matching stub file for a module.

        arguments:
            `module: str`
                top-level module name (e.g., "json", "pydantic_core")

        returns: `Path | None`
            path to matching .pyras file, or none if not found
        """
        for source in self.sources:
            if not source.path.exists():
                continue

            # look for .pyras files matching module name patterns
            candidates: list[tuple[int, Path]] = []

            for stub_file in source.path.glob("**/*.pyras"):
                # check if this stub file covers the target module
                if not self._stub_matches_module(stub_file, module):
                    continue

                # check version compatibility
                try:
                    with open(stub_file, "rb") as f:
                        data_raw: object = json.load(f)  # pyright: ignore[reportAny]

                    if not isinstance(data_raw, dict):
                        continue
                    # use helper for nested dict access
                    data_typed: dict[str, object] = {}
                    for dk, dv in data_raw.items():  # pyright: ignore[reportUnknownVariableType]
                        data_typed[str(dk)] = dv  # pyright: ignore[reportUnknownArgumentType]
                    metadata = _get_nested_dict(data_typed, "metadata")
                    if metadata is None:
                        continue
                    version_spec = metadata.get("version", "*")
                    specifier = SpecifierSet(str(version_spec))

                    if self.target_version in specifier:
                        specificity = self._specificity(specifier)
                        candidates.append((specificity, stub_file))
                except (OSError, json.JSONDecodeError, KeyError):
                    logger.debug("failed to parse stub file: %s", stub_file)
                    continue

            if candidates:
                # return most specific match
                candidates.sort(key=lambda x: x[0], reverse=True)
                return candidates[0][1]

        return None

    def _stub_matches_module(self, stub_file: Path, module: str) -> bool:
        """
        check if a stub file might contain stubs for a module.

        arguments:
            `stub_file: Path`
                path to .pyras file
            `module: str`
                module name to check

        returns: `bool`
            true if stub file might contain stubs for module
        """
        stem = stub_file.stem.lower()

        # stdlib stubs are named like "python-3.12.pyras"
        if stem.startswith("python-"):
            return True  # stdlib stubs contain all stdlib modules

        # third-party stubs are named like "pydantic-core-2.x.pyras"
        # normalise module name (underscores to dashes)
        normalised = module.lower().replace("_", "-")
        return stem.startswith(normalised)

    def _specificity(self, spec: SpecifierSet) -> int:
        """
        score how specific a specifier is (higher = more specific).

        arguments:
            `spec: SpecifierSet`
                version specifier to score

        returns: `int`
                specificity score
        """
        score = 0
        for s in spec:
            if s.operator == "==":
                score += 10
            elif s.operator == "~=":
                score += 5
            elif s.operator in (">=", "<=", ">", "<"):
                score += 1
        return score

    def get_raises(self, qualname: str) -> StubLookupResult | None:
        """
        look up exception signature for a function with fuzzy matching.

        resolution order:
        1. exact match (O(1) dict lookup)
        2. fuzzy match (O(n) scan, caches result)

        fuzzy matching handles:
        - module underscore prefix: _io.BufferedReader -> io.BufferedReader
        - class name mismatches: mmap.mmap -> mmap.Mmap_object (found by method match)

        arguments:
            `qualname: str`
                fully qualified function name (e.g., "json.loads", "mmap.mmap.readline")

        returns: `StubLookupResult | None`
            lookup result with raises set and per-exception confidence, or none if not found
        """
        # check function cache
        if qualname in self._function_cache:
            return self._function_cache[qualname]

        result = self._lookup_qualname(qualname)
        self._function_cache[qualname] = result
        return result

    def _lookup_qualname(self, qualname: str) -> StubLookupResult | None:
        """
        look up a qualname without redirect handling.

        arguments:
            `qualname: str`
                fully qualified function name

        returns: `StubLookupResult | None`
            lookup result or none if not found
        """
        # extract module from qualname
        parts = qualname.split(".")
        if len(parts) < 1:
            return None

        module = parts[0]

        # find stub file for this module
        stub_file_path = self.find_stub_file(module)
        if stub_file_path is None:
            # try with underscore prefix removed (e.g., "io" -> "_io")
            if not module.startswith("_"):
                stub_file_path = self.find_stub_file(f"_{module}")
            if stub_file_path is None:
                return None

        # load and cache stub file
        cached = self._load_stub(stub_file_path)
        if cached is None:
            return None

        # 1. try exact match first (O(1))
        result = self._exact_match(cached, qualname)
        if result:
            return result

        # 2. try fuzzy matching (O(n) but cached)
        result = self._fuzzy_match(cached, qualname)
        if result:
            return result

        # function not found in stub file
        return None

    def _is_exception_dict(self, data: dict[str, object]) -> bool:
        """
        check if dict is exception -> confidence mapping vs class -> methods mapping.

        exception dicts have string confidence values ("exact", "likely", etc.)
        class dicts have nested dicts or lists as values (methods with their exceptions).

        arguments:
            `data: dict[str, object]`
                dict to check

        returns: `bool`
            true if this is an exception dict, false if it's a class dict
        """
        if not data:
            return False
        for val in data.values():
            # exception dicts have string confidence values
            if isinstance(val, str) and val in (
                Confidence.EXACT,
                Confidence.LIKELY,
                Confidence.CONSERVATIVE,
                Confidence.MANUAL,
            ):
                return True
            # if value is a dict, it's likely a class with methods (not exception dict)
            if isinstance(val, dict):
                return False
            # lists are old-style exception lists (still valid)
            if isinstance(val, list):
                return True
        return False

    def _exact_match(self, cached: CachedStubFile, qualname: str) -> StubLookupResult | None:
        """
        attempt exact match on qualname.

        handles both old-style flat qualnames (for backward compat detection)
        and new nested structure.
        """
        parts = qualname.split(".")
        if len(parts) < 2:
            return None

        module = parts[0]

        # check if this is the correct stub file
        if module not in cached.data and f"_{module}" not in cached.data:
            return None

        # get module data (try both with and without underscore prefix)
        module_data = _get_nested_dict(cached.data, module) or _get_nested_dict(
            cached.data, f"_{module}"
        )
        if module_data is None:
            return None

        # try to navigate the nested structure
        if len(parts) == 2:
            # module.function - check for module-level function
            func_name = parts[1]
            empty_section = _get_nested_dict(module_data, "")
            if empty_section is not None and func_name in empty_section:
                exc_data = empty_section.get(func_name)
                exc_list = _to_str_list(exc_data)
                if exc_list is not None:
                    return self._build_result(cached.path, exc_list)
                exc_dict = _to_str_dict(exc_data)
                if exc_dict is not None:
                    return self._build_result(cached.path, exc_dict)
            # check for module-level function stored directly (not under "")
            if func_name in module_data:
                val = module_data.get(func_name)
                # accept if it's a list or an exception dict (not a class dict)
                val_list = _to_str_list(val)
                if val_list is not None:
                    return self._build_result(cached.path, val_list)
                typed_val = _get_nested_dict(module_data, func_name)
                if typed_val is not None and self._is_exception_dict(typed_val):
                    val_dict = _to_str_dict(val)
                    if val_dict is not None:
                        return self._build_result(cached.path, val_dict)
        elif len(parts) >= 3:
            # module.class.method
            class_name = parts[1]
            method_name = ".".join(parts[2:])  # handle nested methods

            class_data = _get_nested_dict(module_data, class_name)
            if class_data is not None and method_name in class_data:
                method_data = class_data.get(method_name)
                method_list = _to_str_list(method_data)
                if method_list is not None:
                    return self._build_result(cached.path, method_list)
                method_dict = _to_str_dict(method_data)
                if method_dict is not None:
                    return self._build_result(cached.path, method_dict)

        return None

    def _fuzzy_match(self, cached: CachedStubFile, qualname: str) -> StubLookupResult | None:
        """
        fuzzy match for class name mismatches.

        e.g., user asks for "mmap.mmap.readline"
        stub has "mmap.Mmap_object.readline"
        we find it by scanning all classes in mmap for "readline" method
        """
        parts = qualname.split(".")
        if len(parts) < 3:
            return None

        module = parts[0]
        method_parts = parts[2:]  # handle deeply nested methods
        method_name = ".".join(method_parts)

        # get module data (try both with and without underscore prefix)
        module_data = _get_nested_dict(cached.data, module) or _get_nested_dict(
            cached.data, f"_{module}"
        )
        if module_data is None:
            return None

        # scan all classes in the module for the method
        for class_name in module_data:
            if class_name == "metadata":
                continue
            class_data = _get_nested_dict(module_data, class_name)
            if class_data is None:
                continue

            if method_name in class_data:
                logger.debug(
                    "fuzzy match: %s -> %s.%s.%s",
                    qualname,
                    module,
                    class_name,
                    method_name,
                )
                method_exc_data = class_data.get(method_name)
                method_list = _to_str_list(method_exc_data)
                if method_list is not None:
                    return self._build_result(cached.path, method_list)
                method_dict = _to_str_dict(method_exc_data)
                if method_dict is not None:
                    return self._build_result(cached.path, method_dict)

        return None

    def _build_result(
        self, source: Path, exc_data: list[str] | dict[str, str]
    ) -> StubLookupResult | None:
        """
        build StubLookupResult from exception data.

        handles both formats:
        - list: ["TypeError", "ValueError"] -> all "likely" (default)
        - dict: {"TypeError": "likely", "ValueError": "exact"}
        """
        if isinstance(exc_data, list):
            # all exceptions have default confidence (likely)
            raises = frozenset(exc_data)
            per_exc_conf = dict.fromkeys(exc_data, Confidence.LIKELY)
            # overall confidence is highest (likely)
            overall_conf = Confidence.LIKELY
        else:
            # exc_data is dict[str, str]
            raises = frozenset(exc_data.keys())
            per_exc_conf = dict(exc_data)
            # overall confidence is highest
            overall_conf = self._highest_confidence(list(exc_data.values()))

        return StubLookupResult(
            raises=raises,
            confidence=overall_conf,
            source=source,
            per_exception_confidence=per_exc_conf,
        )

    def _highest_confidence(self, confidences: list[str]) -> str:
        """
        get highest confidence from list.

        hierarchy: conservative < likely < exact < manual
        """
        order = [Confidence.CONSERVATIVE, Confidence.LIKELY, Confidence.EXACT, Confidence.MANUAL]
        best_idx = 0
        for conf in confidences:
            try:
                idx = order.index(conf)
                if idx > best_idx:
                    best_idx = idx
            except ValueError:
                pass
        return order[best_idx]

    def _load_stub(self, path: Path) -> CachedStubFile | None:
        """
        load a stub file with caching (v2.0 json format).

        arguments:
            `path: Path`
                path to .pyras file

        returns: `CachedStubFile | None`
            cached stub data, or none on error
        """
        cache_key = str(path)
        if cache_key in self._file_cache:
            return self._file_cache[cache_key]

        try:
            with open(path, encoding="utf-8") as f:
                data_raw: object = json.load(f)  # pyright: ignore[reportAny]

            if not isinstance(data_raw, dict):
                self._file_cache[cache_key] = None
                return None

            # convert to properly typed dict
            data_typed: dict[str, object] = {}
            for dk, dv in data_raw.items():  # pyright: ignore[reportUnknownVariableType]
                data_typed[str(dk)] = dv  # pyright: ignore[reportUnknownArgumentType]

            # extract metadata for format version
            metadata = _get_nested_dict(data_typed, "metadata")
            format_version = "2.0"
            if metadata is not None:
                fmt_raw = metadata.get("format_version")
                if isinstance(fmt_raw, str):
                    format_version = fmt_raw

            cached = CachedStubFile(
                path=path,
                data=data_typed,
                format_version=format_version,
            )
            self._file_cache[cache_key] = cached
            return cached

        except (OSError, json.JSONDecodeError, KeyError) as e:
            logger.debug("failed to load stub file %s: %s", path, e)
            self._file_cache[cache_key] = None
            return None

    def clear_cache(self) -> None:
        """clear all cached stub files."""
        self._file_cache.clear()
        self._function_cache.clear()


def create_stub_resolver(
    project_root: Path | None = None,
    python_version: str = "3.12",
) -> StubResolver:
    """
    create a stub resolver with default sources.

    arguments:
        `project_root: Path | None`
            project root directory (for local overrides)
        `python_version: str`
            python version string (e.g., "3.12")

    returns: `StubResolver`
        configured stub resolver
    """
    resolver = StubResolver(target_version=Version(python_version))

    # add project-local overrides (highest priority)
    if project_root:
        local_stubs = project_root / ".raiseattention" / "stubs"
        if local_stubs.exists():
            resolver.add_source(local_stubs, priority=100, name="project-local")

    # add shipped stubs (from raiseattention package)
    package_root = Path(__file__).parent
    stdlib_stubs = package_root / "stubs" / "stdlib"
    if stdlib_stubs.exists():
        resolver.add_source(stdlib_stubs, priority=50, name="shipped-stdlib")

    thirdparty_stubs = package_root / "stubs" / "third-party"
    if thirdparty_stubs.exists():
        resolver.add_source(thirdparty_stubs, priority=40, name="shipped-thirdparty")

    return resolver
