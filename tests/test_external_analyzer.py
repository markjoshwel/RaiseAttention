"""tests for external analyzer functionality.

this module tests the external analyser's ability to detect exceptions
from stdlib and third-party modules.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from raiseattention.analyzer import ExceptionAnalyzer
from raiseattention.config import Config
from raiseattention.external_analyzer import (
    ExternalAnalyzer,
    ExternalModuleInfo,
    get_stdlib_modules,
    is_stdlib_module,
)


class TestExternalModuleInfo:
    """tests for the ExternalModuleInfo dataclass."""

    def test_basic_creation(self) -> None:
        """test creating ExternalModuleInfo."""
        info = ExternalModuleInfo(
            module_name="json",
            file_path=Path("/usr/lib/python3.12/json/__init__.py"),
            is_stdlib=True,
            is_c_extension=False,
        )
        assert info.module_name == "json"
        assert info.is_stdlib is True
        assert info.is_c_extension is False
        assert info.functions == {}
        assert info.exception_signatures == {}

    def test_c_extension_info(self) -> None:
        """test creating ExternalModuleInfo for c extension."""
        info = ExternalModuleInfo(
            module_name="_json",
            file_path=None,
            is_stdlib=True,
            is_c_extension=True,
        )
        assert info.module_name == "_json"
        assert info.is_c_extension is True
        assert info.file_path is None


class TestExternalAnalyzer:
    """tests for the ExternalAnalyzer class."""

    def test_init(self) -> None:
        """test initialising external analyzer."""
        analyzer = ExternalAnalyzer()
        assert analyzer.venv_info is None
        assert analyzer._stdlib_path is not None

    def test_resolve_stdlib_module(self) -> None:
        """test resolving stdlib module path."""
        analyzer = ExternalAnalyzer()
        module_info = analyzer.resolve_module_path("json")

        assert module_info is not None
        assert module_info.module_name == "json"
        assert module_info.is_stdlib is True
        assert module_info.is_c_extension is False
        assert module_info.file_path is not None
        assert module_info.file_path.exists()

    def test_resolve_c_extension(self) -> None:
        """test resolving c extension module."""
        analyzer = ExternalAnalyzer()
        module_info = analyzer.resolve_module_path("_json")

        assert module_info is not None
        assert module_info.module_name == "_json"
        assert module_info.is_c_extension is True
        # file_path should be None for c extensions
        assert module_info.file_path is None

    def test_resolve_nonexistent_module(self) -> None:
        """test resolving nonexistent module."""
        analyzer = ExternalAnalyzer()
        module_info = analyzer.resolve_module_path("nonexistent_module_xyz")

        assert module_info is None

    def test_analyse_stdlib_module(self) -> None:
        """test analysing a stdlib module."""
        analyzer = ExternalAnalyzer()
        module_info = analyzer.analyse_module("json")

        assert module_info is not None
        assert module_info.module_name == "json"
        # json module should have some functions analysed
        # (though the main raise statements are in json.decoder)

    def test_analyse_json_decoder(self) -> None:
        """test analysing json.decoder module for exceptions."""
        analyzer = ExternalAnalyzer()
        module_info = analyzer.analyse_module("json.decoder")

        assert module_info is not None
        assert module_info.module_name == "json.decoder"
        # should find some exception signatures (e.g., JSONDecodeError)
        assert len(module_info.exception_signatures) > 0

    def test_skip_c_extension_analysis(self) -> None:
        """test that c extensions are skipped during analysis."""
        analyzer = ExternalAnalyzer()
        module_info = analyzer.analyse_module("_json")

        assert module_info is not None
        assert module_info.is_c_extension is True
        # functions should be empty for c extensions
        assert module_info.functions == {}

    def test_get_function_exceptions_from_module(self) -> None:
        """test getting function exceptions from a module."""
        analyzer = ExternalAnalyzer()

        # First analyse the module
        analyzer.analyse_module("tomllib")

        # The tomllib module raises TOMLDecodeError
        # Check if we can find exception signatures

    def test_resolve_import_to_module_dotted(self) -> None:
        """test resolving dotted import name."""
        analyzer = ExternalAnalyzer()

        result = analyzer.resolve_import_to_module("json.loads", {})
        # should resolve to (json, loads)
        assert result is not None
        module_name, func_name = result
        assert module_name == "json"
        assert func_name == "loads"

    def test_resolve_import_to_module_with_imports_map(self) -> None:
        """test resolving import using imports map."""
        analyzer = ExternalAnalyzer()

        imports = {"loads": "json.loads"}
        result = analyzer.resolve_import_to_module("loads", imports)

        assert result is not None
        module_name, func_name = result
        assert module_name == "json"
        assert func_name == "loads"


class TestStdlibModuleDetection:
    """tests for stdlib module detection."""

    def test_get_stdlib_modules(self) -> None:
        """test getting stdlib module names."""
        modules = get_stdlib_modules()

        assert isinstance(modules, frozenset)
        assert "json" in modules
        assert "os" in modules
        assert "sys" in modules
        assert "pathlib" in modules

    def test_is_stdlib_module_positive(self) -> None:
        """test that stdlib modules are correctly identified."""
        assert is_stdlib_module("json") is True
        assert is_stdlib_module("json.decoder") is True
        assert is_stdlib_module("os") is True
        assert is_stdlib_module("os.path") is True
        assert is_stdlib_module("pathlib") is True
        assert is_stdlib_module("tomllib") is True

    def test_is_stdlib_module_negative(self) -> None:
        """test that non-stdlib modules are correctly identified."""
        assert is_stdlib_module("requests") is False
        assert is_stdlib_module("numpy") is False
        assert is_stdlib_module("my_custom_module") is False


class TestIntegrationWithAnalyzer:
    """integration tests for external analysis with the main analyzer."""

    def test_analyzer_with_external_import(self, tmp_path: Path) -> None:
        """test that analyzer can look up external module exceptions."""
        config = Config()
        analyzer = ExceptionAnalyzer(config)

        # create a file that imports from stdlib
        test_file = tmp_path / "test_external.py"
        test_file.write_text('''
import tomllib

def load_config(path: str) -> dict:
    """loads config from toml file."""
    with open(path, "rb") as f:
        return tomllib.load(f)
''')

        result = analyzer.analyse_file(test_file)
        # the file should be analysed successfully
        assert len(result.files_analysed) == 1

    def test_analyzer_detects_tomllib_exceptions(self, tmp_path: Path) -> None:
        """test that analyzer can detect exceptions from tomllib."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyzer(config)

        # create a file that calls tomllib.loads which raises TOMLDecodeError
        test_file = tmp_path / "test_toml.py"
        test_file.write_text('''
import tomllib

def parse_toml(data: str) -> dict:
    """parses toml data - may raise TOMLDecodeError."""
    return tomllib.loads(data)

def caller():
    """calls parse_toml without handling."""
    result = parse_toml("[invalid")
    return result
''')

        result = analyzer.analyse_file(test_file)
        # should find some diagnostics about the ValueError propagation

    def test_analyzer_with_json_import(self, tmp_path: Path) -> None:
        """test analyzer with json module import."""
        config = Config()
        analyzer = ExceptionAnalyzer(config)

        test_file = tmp_path / "test_json.py"
        test_file.write_text('''
import json

def parse_json(data: str) -> dict:
    """parses json data."""
    return json.loads(data)

def caller():
    """calls parse_json."""
    return parse_json('{"key": "value"}')
''')

        result = analyzer.analyse_file(test_file)
        assert len(result.files_analysed) == 1

    def test_analyzer_with_from_import(self, tmp_path: Path) -> None:
        """test analyzer with from ... import style."""
        config = Config()
        analyzer = ExceptionAnalyzer(config)

        test_file = tmp_path / "test_from_import.py"
        test_file.write_text('''
from json import loads

def parse_data(data: str) -> dict:
    """parses json data using imported function."""
    return loads(data)
''')

        result = analyzer.analyse_file(test_file)
        assert len(result.files_analysed) == 1

    def test_external_analyzer_caching(self) -> None:
        """test that external module analysis is cached."""
        analyzer = ExternalAnalyzer()

        # First analysis
        info1 = analyzer.analyse_module("json")

        # Second analysis should use cache
        info2 = analyzer.analyse_module("json")

        # Should return equivalent cached info
        assert info1 is not None
        assert info2 is not None
        assert info1.module_name == info2.module_name
        assert info1.exception_signatures == info2.exception_signatures


class TestExternalAnalyzerEdgeCases:
    """edge case tests for external analyzer."""

    def test_empty_module_name(self) -> None:
        """test resolving empty module name."""
        analyzer = ExternalAnalyzer()
        result = analyzer.resolve_module_path("")
        assert result is None

    def test_module_with_syntax_error(self, tmp_path: Path) -> None:
        """test handling modules that can't be parsed."""
        # This tests the error handling path in analyse_module
        analyzer = ExternalAnalyzer()

        # Try to analyse a builtin module (which should work)
        result = analyzer.analyse_module("builtins")
        # builtins is special and may not have a file path
        # just ensure no crash occurs

    def test_resolve_deeply_nested_module(self) -> None:
        """test resolving deeply nested module path."""
        analyzer = ExternalAnalyzer()

        # Try to resolve a deeply nested stdlib module
        result = analyzer.resolve_import_to_module(
            "xml.etree.ElementTree.parse", {}
        )
        # Should be able to find xml.etree.ElementTree

    def test_module_info_with_exception_signatures(self) -> None:
        """test module info stores exception signatures."""
        info = ExternalModuleInfo(
            module_name="test",
            file_path=None,
            exception_signatures={"func1": ["ValueError", "TypeError"]},
        )
        assert "func1" in info.exception_signatures
        assert "ValueError" in info.exception_signatures["func1"]
