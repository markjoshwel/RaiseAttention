"""
stub resolver for loading .pyras files at check-time.

provides version-aware resolution of exception stubs from .pyras files,
with support for project-local overrides and vendored stdlib stubs.
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Final

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from .models import Confidence, FunctionStub, StubFile, StubLookupResult

logger = logging.getLogger(__name__)

# default stub search paths (relative to package root)
DEFAULT_STDLIB_STUBS_PATH: Final[str] = "stubs/stdlib"
DEFAULT_THIRDPARTY_STUBS_PATH: Final[str] = "stubs/third-party"


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
        if not self.name:
            self.name = str(self.path)


@dataclass
class StubResolver:
    """
    resolve .pyras stub files by version and module.

    searches multiple stub sources in priority order:
    1. project-local overrides (.raiseattention/stubs/)
    2. shipped stdlib stubs (raiseattention/stubs/stdlib/)
    3. third-party stubs (raiseattention/stubs/third-party/)

    attributes:
        `sources: list[StubSource]`
            ordered list of stub sources
        `target_version: Version`
            python version to resolve stubs for
    """

    sources: list[StubSource] = field(default_factory=list)
    target_version: Version = field(default_factory=lambda: Version("3.12.0"))
    _cache: dict[str, StubFile | None] = field(default_factory=dict, repr=False)
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
        self._cache.clear()
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
        # check cache first
        cache_key = f"{module}@{self.target_version}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            return None  # we cache StubFile, not Path

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
                        data = tomllib.load(f)

                    metadata = data.get("metadata", {})
                    version_spec = metadata.get("version", "*")
                    specifier = SpecifierSet(str(version_spec))

                    if self.target_version in specifier:
                        specificity = self._specificity(specifier)
                        candidates.append((specificity, stub_file))
                except (OSError, tomllib.TOMLDecodeError, KeyError):
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
        look up exception signature for a function.

        arguments:
            `qualname: str`
                fully qualified function name (e.g., "json.loads")

        returns: `StubLookupResult | None`
            lookup result with raises set, or none if not found
        """
        # check function cache
        if qualname in self._function_cache:
            return self._function_cache[qualname]

        # extract module from qualname
        parts = qualname.split(".")
        if len(parts) < 2:
            return None

        module = parts[0]

        # find stub file for this module
        stub_file = self.find_stub_file(module)
        if stub_file is None:
            self._function_cache[qualname] = None
            return None

        # load and cache stub file
        stub = self._load_stub(stub_file)
        if stub is None:
            self._function_cache[qualname] = None
            return None

        # look up function
        for func_stub in stub.stubs:
            if func_stub.qualname == qualname:
                result = StubLookupResult(
                    raises=func_stub.raises,
                    confidence=func_stub.confidence,
                    source=stub_file,
                )
                self._function_cache[qualname] = result
                return result

        # function not found in stub file
        self._function_cache[qualname] = None
        return None

    def _load_stub(self, path: Path) -> StubFile | None:
        """
        load a stub file with caching.

        arguments:
            `path: Path`
                path to .pyras file

        returns: `StubFile | None`
            loaded stub file, or none on error
        """
        cache_key = str(path)
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            stub = StubFile.load(path)
            self._cache[cache_key] = stub
            return stub
        except (OSError, tomllib.TOMLDecodeError, KeyError) as e:
            logger.debug("failed to load stub file %s: %s", path, e)
            self._cache[cache_key] = None
            return None

    def clear_cache(self) -> None:
        """clear all cached stub files."""
        self._cache.clear()
        self._function_cache.clear()


def create_default_resolver(
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
    # these are vendored in the package installation
    import raiseattention

    package_root = Path(raiseattention.__file__).parent
    stdlib_stubs = package_root / "stubs" / "stdlib"
    if stdlib_stubs.exists():
        resolver.add_source(stdlib_stubs, priority=50, name="shipped-stdlib")

    thirdparty_stubs = package_root / "stubs" / "third-party"
    if thirdparty_stubs.exists():
        resolver.add_source(thirdparty_stubs, priority=40, name="shipped-thirdparty")

    return resolver
