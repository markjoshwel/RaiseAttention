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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


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
    """

    strict_mode: bool = False
    allow_bare_except: bool = False
    require_reraise_after_log: bool = True
    local_only: bool = False
    full_module_path: bool = False


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
        `exclude: list[str]`
            glob patterns for files/directories to exclude
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
    exclude: list[str] = field(default_factory=list)
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
                data = tomllib.load(f)

            tool_config = data.get("tool", {}).get("raiseattention", {})  # pyright: ignore[reportAny]
            return cls._from_dict(tool_config, project_path)
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
                data = tomllib.load(f)

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
            exclude=other.exclude if other.exclude else self.exclude,
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
            )
            if other.analysis != AnalysisConfig()
            else self.analysis,
        )

    @classmethod
    def _from_dict(cls, data: dict[str, Any], project_root: Path) -> Config:
        """
        Create configuration from a dictionary.

        arguments:
            `data: dict[str, Any]`
                configuration dictionary
            `project_root: Path`
                project root path

        returns: `Config`
            configuration object
        """
        config = cls(project_root=project_root)

        # basic settings
        if "python_path" in data:
            config.python_path = data["python_path"]
        if "venv_path" in data:
            config.venv_path = data["venv_path"]
        if "exclude" in data:
            config.exclude = data["exclude"]
        if "ignore_exceptions" in data:
            config.ignore_exceptions = data["ignore_exceptions"]
        if "ignore_modules" in data:
            config.ignore_modules = data["ignore_modules"]

        # cache settings
        if cache_data := data.get("cache", {}):  # pyright: ignore[reportAny]
            config.cache = CacheConfig(
                enabled=cache_data.get("enabled", True),  # pyright: ignore[reportAny]
                max_file_entries=cache_data.get("max_file_entries", 10000),  # pyright: ignore[reportAny]
                max_memory_mb=cache_data.get("max_memory_mb", 500),  # pyright: ignore[reportAny]
                ttl_hours=cache_data.get("ttl_hours", 24),  # pyright: ignore[reportAny]
            )

        # lsp settings
        if lsp_data := data.get("lsp", {}):  # pyright: ignore[reportAny]
            config.lsp = LspConfig(
                debounce_ms=lsp_data.get("debounce_ms", 500),  # pyright: ignore[reportAny]
                max_diagnostics_per_file=lsp_data.get("max_diagnostics_per_file", 100),  # pyright: ignore[reportAny]
            )

        # analysis settings
        if analysis_data := data.get("analysis", {}):  # pyright: ignore[reportAny]
            config.analysis = AnalysisConfig(
                strict_mode=analysis_data.get("strict_mode", False),  # pyright: ignore[reportAny]
                allow_bare_except=analysis_data.get("allow_bare_except", False),  # pyright: ignore[reportAny]
                require_reraise_after_log=analysis_data.get("require_reraise_after_log", True),  # pyright: ignore[reportAny]
                local_only=analysis_data.get("local_only", False),  # pyright: ignore[reportAny]
                full_module_path=analysis_data.get("full_module_path", False),  # pyright: ignore[reportAny]
            )

        return config
