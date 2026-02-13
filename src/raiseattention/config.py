"""
configuration loading for raiseattention.

this module handles loading and validation of configuration from
pyproject.toml, .raiseattention.toml, and environment variables.
"""

from __future__ import annotations

import os
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def _get_nested_dict(parent: dict[str, object], key: str) -> dict[str, object] | None:
    """
    get a nested dict from a parent dict with proper type narrowing.

    this helper exists because pyright cannot infer the type of nested dicts
    after isinstance checks on values from `dict[str, object].get()`.

    arguments:
        `parent: dict[str, object]`
            parent dictionary
        `key: str`
            key to look up

    returns: `dict[str, object] | None`
        the nested dict if it exists and is a dict, otherwise none
    """
    value = parent.get(key)
    if isinstance(value, dict):
        # pyright cannot infer nested dict types after isinstance check
        result: dict[str, object] = {}
        for k, v in value.items():  # pyright: ignore[reportUnknownVariableType]
            result[str(k)] = v  # pyright: ignore[reportUnknownArgumentType]
        return result
    return None


def _get_str_list(parent: dict[str, object], key: str) -> list[str] | None:
    """
    get a list of strings from a parent dict with proper type narrowing.

    arguments:
        `parent: dict[str, object]`
            parent dictionary
        `key: str`
            key to look up

    returns: `list[str] | None`
        the list of strings if it exists and is a list, otherwise none
    """
    value = parent.get(key)
    if isinstance(value, list):
        # pyright cannot infer list element types after isinstance check
        result: list[str] = []
        for item in value:  # pyright: ignore[reportUnknownVariableType]
            result.append(str(item))  # pyright: ignore[reportUnknownArgumentType]
        return result
    return None


@dataclass
class CacheConfig:
    """
    caching configuration settings.

    attributes:
        `enabled: bool`
            whether caching is enabled
        `max_file_entries: int`
            maximum number of file cache entries (lru eviction)
        `max_memory_mb: int`
            maximum memory usage in megabytes
        `ttl_hours: int`
            time-to-live for unused cache entries
    """

    enabled: bool = True
    max_file_entries: int = 10000
    max_memory_mb: int = 500
    ttl_hours: int = 24


@dataclass
class LspConfig:
    """
    lsp server configuration settings.

    attributes:
        `debounce_ms: int`
            debounce interval in milliseconds
        `max_diagnostics_per_file: int`
            maximum number of diagnostics per file
    """

    debounce_ms: int = 500
    max_diagnostics_per_file: int = 100


@dataclass
class AnalysisConfig:
    """
    analysis configuration settings.

    attributes:
        `strict_mode: bool`
            require all exceptions to be declared in docstrings
        `allow_bare_except: bool`
            allow bare 'except:' clauses
        `require_reraise_after_log: bool`
            require re-raise after logging exceptions
        `local_only: bool`
            only analyse local/first-party code, skip external modules
        `full_module_path: bool`
            show full module path for exceptions (e.g.,
            'pkg.mod.Exception' instead of 'pkg.Exception')
        `warn_native: bool`
            warn about possible exceptions from native/c extension code
        `ignore_include: list[str]`
            list of builtin functions to always ignore (e.g., ['str', 'print'])
        `ignore_exclude: list[str]`
            list of builtin functions to never ignore (override ignore_include)
    """

    strict_mode: bool = False
    allow_bare_except: bool = False
    require_reraise_after_log: bool = True
    local_only: bool = False
    full_module_path: bool = False
    warn_native: bool = True
    ignore_include: list[str] = field(default_factory=list)
    ignore_exclude: list[str] = field(default_factory=list)


@dataclass
class Config:
    """
    main configuration class for raiseattention.

    this class holds all configuration settings and provides methods
    for loading from various sources.

    attributes:
        `project_root: Path`
            root directory of the project
        `python_path: str`
            path to python executable (or 'auto' for auto-detection)
        `venv_path: str`
            path to virtual environment (or 'auto' for auto-detection)
        `include: list[str]`
            glob patterns for files to include
        `exclude: list[str]`
            glob patterns for files/directories to exclude
        `respect_gitignore: bool`
            whether to respect .gitignore files
        `ignore_exceptions: list[str]`
            exception types to ignore globally
        `ignore_modules: list[str]`
            module patterns to ignore
        `cache: CacheConfig`
            caching configuration
        `lsp: LspConfig`
            lsp server configuration
        `analysis: AnalysisConfig`
            analysis behaviour configuration
    """

    project_root: Path = field(default_factory=lambda: Path(".").resolve())
    python_path: str = "auto"
    venv_path: str = "auto"
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    respect_gitignore: bool = True
    ignore_exceptions: list[str] = field(default_factory=list)
    ignore_modules: list[str] = field(default_factory=list)
    cache: CacheConfig = field(default_factory=CacheConfig)
    lsp: LspConfig = field(default_factory=LspConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)

    def __post_init__(self) -> None:
        """Ensure project_root is a path object."""
        if isinstance(self.project_root, str):
            self.project_root = Path(self.project_root)

    @classmethod
    def from_pyproject_toml(cls, project_root: str | Path) -> Config | None:
        """
        Load configuration from pyproject.toml.

        arguments:
            `project_root: str | Path`
                project root directory containing pyproject.toml

        returns: `Config | None`
            configuration object if found, none otherwise
        """
        project_path = Path(project_root)
        pyproject = project_path.joinpath("pyproject.toml")

        if not pyproject.exists():
            return None

        try:
            import tomllib

            with open(pyproject, "rb") as f:
                data: dict[str, object] = tomllib.load(f)

            tool_section = _get_nested_dict(data, "tool")
            if tool_section is None:
                return None
            config_dict = _get_nested_dict(tool_section, "raiseattention")
            if config_dict is None:
                return None
            return cls._from_dict(config_dict, project_path)
        except Exception:
            return None

    @classmethod
    def from_raiseattention_toml(cls, project_root: str | Path) -> Config | None:
        """
        Load configuration from .raiseattention.toml.

        arguments:
            `project_root: str | Path`
                project root directory containing .raiseattention.toml

        returns: `Config | None`
            configuration object if found, none otherwise
        """
        project_path = Path(project_root)
        config_file = project_path.joinpath(".raiseattention.toml")

        if not config_file.exists():
            return None

        try:
            import tomllib

            with open(config_file, "rb") as f:
                data: dict[str, object] = tomllib.load(f)

            return cls._from_dict(data, project_path)
        except Exception:
            return None

    @classmethod
    def from_environment(cls) -> Config:
        """
        Load configuration from environment variables.

        returns: `Config`
            configuration with values from environment
        """
        config = cls()

        if python_path := os.environ.get("RAISEATTENTION_PYTHON_PATH"):
            config.python_path = python_path

        if venv_path := os.environ.get("RAISEATTENTION_VENV_PATH"):
            config.venv_path = venv_path

        if strict_mode := os.environ.get("RAISEATTENTION_STRICT_MODE"):
            config.analysis.strict_mode = strict_mode.lower() in ("true", "1", "yes")

        if debounce := os.environ.get("RAISEATTENTION_DEBOUNCE_MS"):
            with suppress(ValueError):
                config.lsp.debounce_ms = int(debounce)

        return config

    @classmethod
    def load(cls, project_root: str | Path = ".") -> Config:
        """
        Load configuration from all available sources.

        sources are loaded in order of priority (later overrides earlier):
        1. default values
        2. pyproject.toml
        3. .raiseattention.toml
        4. environment variables

        arguments:
            `project_root: str | Path`
                project root directory

        returns: `Config`
            merged configuration from all sources
        """
        project_path = Path(project_root).resolve()

        # start with defaults
        config = cls(project_root=project_path)

        # apply default exclusions
        config.exclude = [
            "**/tests/**",
            "**/migrations/**",
            "**/__pycache__/**",
            "**/.venv/**",
            "**/.git/**",
        ]
        config.include = ["**/*.py"]
        config.ignore_exceptions = ["KeyboardInterrupt", "SystemExit"]

        # load from pyproject.toml
        if pyproject_config := cls.from_pyproject_toml(project_path):
            config = config.merge(pyproject_config)

        # load from .raiseattention.toml (overrides pyproject.toml)
        if raiseattention_config := cls.from_raiseattention_toml(project_path):
            config = config.merge(raiseattention_config)

        # load from environment (highest priority)
        env_config = cls.from_environment()
        config = config.merge(env_config)

        return config

    def merge(self, other: Config) -> Config:
        """
        merge another configuration into this one.

        values from 'other' take precedence over this config.

        arguments:
            `other: Config`
                configuration to merge

        returns: `Config`
            new merged configuration
        """
        return Config(
            project_root=other.project_root
            if other.project_root != Path(".").resolve()
            else self.project_root,
            python_path=other.python_path if other.python_path != "auto" else self.python_path,
            venv_path=other.venv_path if other.venv_path != "auto" else self.venv_path,
            include=other.include if other.include else self.include,
            exclude=other.exclude if other.exclude else self.exclude,
            respect_gitignore=other.respect_gitignore
            if not other.respect_gitignore
            else self.respect_gitignore,
            ignore_exceptions=other.ignore_exceptions
            if other.ignore_exceptions
            else self.ignore_exceptions,
            ignore_modules=other.ignore_modules if other.ignore_modules else self.ignore_modules,
            cache=CacheConfig(
                enabled=other.cache.enabled,
                max_file_entries=other.cache.max_file_entries,
                max_memory_mb=other.cache.max_memory_mb,
                ttl_hours=other.cache.ttl_hours,
            )
            if other.cache != CacheConfig()
            else self.cache,
            lsp=LspConfig(
                debounce_ms=other.lsp.debounce_ms,
                max_diagnostics_per_file=other.lsp.max_diagnostics_per_file,
            )
            if other.lsp != LspConfig()
            else self.lsp,
            analysis=AnalysisConfig(
                strict_mode=other.analysis.strict_mode,
                allow_bare_except=other.analysis.allow_bare_except,
                require_reraise_after_log=other.analysis.require_reraise_after_log,
                local_only=other.analysis.local_only,
                full_module_path=other.analysis.full_module_path,
                warn_native=other.analysis.warn_native,
                ignore_include=other.analysis.ignore_include
                if other.analysis.ignore_include
                else self.analysis.ignore_include,
                ignore_exclude=other.analysis.ignore_exclude
                if other.analysis.ignore_exclude
                else self.analysis.ignore_exclude,
            )
            if other.analysis != AnalysisConfig()
            else self.analysis,
        )

    @classmethod
    def _from_dict(cls, data: dict[str, object], project_root: Path) -> Config:
        """
        Create configuration from a dictionary.

        arguments:
            `data: dict[str, object]`
                configuration dictionary
            `project_root: Path`
                project root path

        returns: `Config`
            configuration object
        """
        config = cls(project_root=project_root)

        # basic settings with type narrowing
        python_path = data.get("python_path")
        if isinstance(python_path, str):
            config.python_path = python_path
        venv_path = data.get("venv_path")
        if isinstance(venv_path, str):
            config.venv_path = venv_path
        include = _get_str_list(data, "include")
        if include is not None:
            config.include = include
        exclude = _get_str_list(data, "exclude")
        if exclude is not None:
            config.exclude = exclude
        respect_gitignore = data.get("respect_gitignore")
        if isinstance(respect_gitignore, bool):
            config.respect_gitignore = respect_gitignore
        ignore_exceptions = _get_str_list(data, "ignore_exceptions")
        if ignore_exceptions is not None:
            config.ignore_exceptions = ignore_exceptions
        ignore_modules = _get_str_list(data, "ignore_modules")
        if ignore_modules is not None:
            config.ignore_modules = ignore_modules

        # cache settings
        cache_data = _get_nested_dict(data, "cache")
        if cache_data is not None:
            enabled = cache_data.get("enabled")
            max_file = cache_data.get("max_file_entries")
            max_mem = cache_data.get("max_memory_mb")
            ttl = cache_data.get("ttl_hours")
            config.cache = CacheConfig(
                enabled=bool(enabled) if isinstance(enabled, bool) else True,
                max_file_entries=int(max_file) if isinstance(max_file, int) else 10000,
                max_memory_mb=int(max_mem) if isinstance(max_mem, int) else 500,
                ttl_hours=int(ttl) if isinstance(ttl, int) else 24,
            )

        # lsp settings
        lsp_data = _get_nested_dict(data, "lsp")
        if lsp_data is not None:
            debounce = lsp_data.get("debounce_ms")
            max_diag = lsp_data.get("max_diagnostics_per_file")
            config.lsp = LspConfig(
                debounce_ms=int(debounce) if isinstance(debounce, int) else 500,
                max_diagnostics_per_file=int(max_diag) if isinstance(max_diag, int) else 100,
            )

        # analysis settings
        analysis_data = _get_nested_dict(data, "analysis")
        if analysis_data is not None:
            strict_mode = analysis_data.get("strict_mode")
            allow_bare = analysis_data.get("allow_bare_except")
            require_reraise = analysis_data.get("require_reraise_after_log")
            local_only = analysis_data.get("local_only")
            full_module = analysis_data.get("full_module_path")
            warn_native = analysis_data.get("warn_native")
            ignore_include = _get_str_list(analysis_data, "ignore_include")
            ignore_exclude = _get_str_list(analysis_data, "ignore_exclude")
            config.analysis = AnalysisConfig(
                strict_mode=bool(strict_mode) if isinstance(strict_mode, bool) else False,
                allow_bare_except=bool(allow_bare) if isinstance(allow_bare, bool) else False,
                require_reraise_after_log=bool(require_reraise)
                if isinstance(require_reraise, bool)
                else True,
                local_only=bool(local_only) if isinstance(local_only, bool) else False,
                full_module_path=bool(full_module) if isinstance(full_module, bool) else False,
                warn_native=bool(warn_native) if isinstance(warn_native, bool) else True,
                ignore_include=ignore_include if ignore_include is not None else [],
                ignore_exclude=ignore_exclude if ignore_exclude is not None else [],
            )

        return config
