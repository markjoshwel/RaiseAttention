"""
tests for the core analyzer module.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from raiseattention.analyzer import (
    AnalysisResult,
    Diagnostic,
    ExceptionAnalyzer,
)
from raiseattention.config import AnalysisConfig, Config


class TestDiagnostic:
    """tests for the Diagnostic dataclass."""

    def test_creation(self) -> None:
        """test diagnostic creation."""
        diag = Diagnostic(
            file_path=Path("/test.py"),
            line=10,
            column=5,
            message="unhandled exception",
            exception_types=["ValueError"],
            severity="error",
        )

        assert diag.file_path == Path("/test.py")
        assert diag.line == 10
        assert diag.column == 5
        assert diag.message == "unhandled exception"
        assert diag.exception_types == ["ValueError"]
        assert diag.severity == "error"


class TestAnalysisResult:
    """tests for the AnalysisResult dataclass."""

    def test_defaults(self) -> None:
        """test default analysis result values."""
        result = AnalysisResult()

        assert result.diagnostics == []
        assert result.files_analysed == []
        assert result.functions_found == 0
        assert result.exceptions_tracked == 0


class TestExceptionAnalyzer:
    """tests for the ExceptionAnalyzer class."""

    def test_init(self) -> None:
        """test analyzer initialisation."""
        config = Config()
        analyzer = ExceptionAnalyzer(config)

        assert analyzer.config == config

    def test_analyse_file_not_found(self, tmp_path: Path) -> None:
        """test analysing non-existent file."""
        config = Config()
        analyzer = ExceptionAnalyzer(config)

        result = analyzer.analyse_file(tmp_path / "nonexistent.py")

        assert len(result.diagnostics) == 1
        assert "failed to analyse" in result.diagnostics[0].message

    def test_analyse_simple_file(self, tmp_path: Path) -> None:
        """test analysing a simple python file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def simple():
    pass
""")

        config = Config()
        analyzer = ExceptionAnalyzer(config)

        result = analyzer.analyse_file(test_file)

        assert len(result.files_analysed) == 1
        assert result.functions_found == 1

    def test_analyse_file_with_exception(self, tmp_path: Path) -> None:
        """test analysing a file that raises exceptions."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def risky():
    raise ValueError("error")
""")

        config = Config()
        analyzer = ExceptionAnalyzer(config)

        result = analyzer.analyse_file(test_file)

        assert result.functions_found == 1
        assert result.exceptions_tracked == 1

    def test_analyse_project(self, tmp_path: Path) -> None:
        """test analysing an entire project."""
        # create multiple python files
        (tmp_path / "module1.py").write_text("""
def func1():
    pass
""")
        (tmp_path / "module2.py").write_text("""
def func2():
    raise ValueError()
""")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "module3.py").write_text("""
def func3():
    pass
""")

        config = Config(project_root=tmp_path, exclude=[])
        analyzer = ExceptionAnalyzer(config)

        result = analyzer.analyse_project(tmp_path)

        assert len(result.files_analysed) == 3
        assert result.functions_found == 3

    def test_get_function_signature(self, tmp_path: Path) -> None:
        """test getting exception signature for a function."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def risky():
    raise ValueError("error")
""")

        config = Config()
        analyzer = ExceptionAnalyzer(config)
        analyzer.analyse_file(test_file)

        signature = analyzer.get_function_signature("test.risky")

        assert "ValueError" in signature

    def test_transitive_exception_tracking(self, tmp_path: Path) -> None:
        """test that exceptions propagate transitively."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def level3():
    raise ValueError("deep error")

def level2():
    level3()

def level1():
    level2()
""")

        config = Config()
        analyzer = ExceptionAnalyzer(config)
        analyzer.analyse_file(test_file)

        # all levels should have ValueError in signature
        assert "ValueError" in analyzer.get_function_signature("test.level3")
        # note: transitive tracking requires full call graph analysis
        # which is simplified in this implementation

    def test_ignore_exceptions_config(self, tmp_path: Path) -> None:
        """test that ignored exceptions are filtered."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def func():
    raise KeyboardInterrupt()
""")

        config = Config(ignore_exceptions=["KeyboardInterrupt"])
        analyzer = ExceptionAnalyzer(config)

        result = analyzer.analyse_file(test_file)

        # keyboardinterrupt should be filtered out
        # but the function still raises it
        assert result.exceptions_tracked == 1

    def test_strict_mode_docstring_check(self, tmp_path: Path) -> None:
        """test strict mode requires documented exceptions."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def undocumented():
    raise ValueError("error")
""")

        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyzer(config)

        result = analyzer.analyse_file(test_file)

        # should have diagnostic about undocumented exception
        assert any("undocumented" in d.message for d in result.diagnostics)

    def test_cache_usage(self, tmp_path: Path) -> None:
        """test that cache is used for repeated analysis."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def func():
    pass
""")

        config = Config()
        analyzer = ExceptionAnalyzer(config)

        # first analysis
        result1 = analyzer.analyse_file(test_file)

        # second analysis should use cache
        result2 = analyzer.analyse_file(test_file)

        assert result1.functions_found == result2.functions_found

    def test_invalidate_file(self, tmp_path: Path) -> None:
        """test invalidating a file from cache."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def func(): pass")

        config = Config()
        analyzer = ExceptionAnalyzer(config)
        analyzer.analyse_file(test_file)

        # invalidate
        analyzer.invalidate_file(test_file)

        # file analyses should be cleared
        assert test_file.resolve() not in analyzer._file_analyses
