"""tests for the configuration module."""

from __future__ import annotations

import os
from pathlib import Path

from raiseattention.config import (
    AnalysisConfig,
    CacheConfig,
    Config,
    LspConfig,
)


class TestCacheConfig:
    """tests for the CacheConfig dataclass."""

    def test_defaults(self) -> None:
        """Test default cache configuration values."""
        config = CacheConfig()

        assert config.enabled is True
        assert config.max_file_entries == 10000
        assert config.max_memory_mb == 500
        assert config.ttl_hours == 24

    def test_custom_values(self) -> None:
        """Test custom cache configuration values."""
        config = CacheConfig(
            enabled=False,
            max_file_entries=5000,
            max_memory_mb=250,
            ttl_hours=12,
        )

        assert config.enabled is False
        assert config.max_file_entries == 5000
        assert config.max_memory_mb == 250
        assert config.ttl_hours == 12


class TestLspConfig:
    """tests for the LspConfig dataclass."""

    def test_defaults(self) -> None:
        """Test default lsp configuration values."""
        config = LspConfig()

        assert config.debounce_ms == 500
        assert config.max_diagnostics_per_file == 100


class TestAnalysisConfig:
    """tests for the AnalysisConfig dataclass."""

    def test_defaults(self) -> None:
        """Test default analysis configuration values."""
        config = AnalysisConfig()

        assert config.strict_mode is False
        assert config.allow_bare_except is False
        assert config.require_reraise_after_log is True


class TestConfig:
    """tests for the main Config class."""

    def test_defaults(self) -> None:
        """Test default configuration values."""
        config = Config()

        assert config.python_path == "auto"
        assert config.venv_path == "auto"
        assert isinstance(config.project_root, Path)

    def test_from_pyproject_toml(self, tmp_path: Path) -> None:
        """Test loading configuration from pyproject.toml."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[tool.raiseattention]
python_path = "/usr/bin/python3"
venv_path = "/path/to/venv"

[tool.raiseattention.analysis]
strict_mode = true

[tool.raiseattention.cache]
enabled = false
max_file_entries = 5000

[tool.raiseattention.lsp]
debounce_ms = 1000
""")

        config = Config.from_pyproject_toml(tmp_path)

        assert config is not None
        assert config.python_path == "/usr/bin/python3"
        assert config.venv_path == "/path/to/venv"
        assert config.analysis.strict_mode is True
        assert config.cache.enabled is False
        assert config.cache.max_file_entries == 5000
        assert config.lsp.debounce_ms == 1000

    def test_from_pyproject_toml_not_found(self, tmp_path: Path) -> None:
        """Test loading from non-existent pyproject.toml."""
        config = Config.from_pyproject_toml(tmp_path)

        assert config is None

    def test_from_raiseattention_toml(self, tmp_path: Path) -> None:
        """Test loading configuration from .raiseattention.toml."""
        config_file = tmp_path / ".raiseattention.toml"
        config_file.write_text("""
python_path = "/custom/python"
exclude = ["**/tests/**", "**/docs/**"]
ignore_exceptions = ["KeyboardInterrupt"]
""")

        config = Config.from_raiseattention_toml(tmp_path)

        assert config is not None
        assert config.python_path == "/custom/python"
        assert config.exclude == ["**/tests/**", "**/docs/**"]
        assert config.ignore_exceptions == ["KeyboardInterrupt"]

    def test_from_environment(self) -> None:
        """Test loading configuration from environment variables."""
        env_vars = {
            "RAISEATTENTION_PYTHON_PATH": "/env/python",
            "RAISEATTENTION_VENV_PATH": "/env/venv",
            "RAISEATTENTION_STRICT_MODE": "true",
            "RAISEATTENTION_DEBOUNCE_MS": "750",
        }

        original = {k: os.environ.get(k) for k in env_vars}

        try:
            for k, v in env_vars.items():
                os.environ[k] = v

            config = Config.from_environment()

            assert config.python_path == "/env/python"
            assert config.venv_path == "/env/venv"
            assert config.analysis.strict_mode is True
            assert config.lsp.debounce_ms == 750
        finally:
            for k, v in original.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_load_full(self, tmp_path: Path) -> None:
        """Test loading configuration from all sources."""
        # create pyproject.toml
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[tool.raiseattention]
python_path = "/pyproject/python"
""")

        # create .raiseattention.toml (should override)
        config_file = tmp_path / ".raiseattention.toml"
        config_file.write_text("""
python_path = "/raiseattention/python"
venv_path = "/raiseattention/venv"
""")

        config = Config.load(tmp_path)

        # .raiseattention.toml should override pyproject.toml
        assert config.python_path == "/raiseattention/python"
        assert config.venv_path == "/raiseattention/venv"

    def test_merge_configs(self) -> None:
        """Test merging two configurations."""
        config1 = Config(
            python_path="/path1",
            venv_path="/venv1",
            exclude=["**/a/**"],
        )

        config2 = Config(
            python_path="/path2",
            exclude=["**/b/**"],
        )

        merged = config1.merge(config2)

        # config2 values should take precedence
        assert merged.python_path == "/path2"
        assert merged.venv_path == "/venv1"  # not overridden
        assert merged.exclude == ["**/b/**"]

    def test_project_root_conversion(self) -> None:
        """Test that project_root is converted to Path."""
        config = Config(project_root="/some/path")

        assert isinstance(config.project_root, Path)
        assert config.project_root == Path("/some/path")
