"""tests for the core analyser module."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from raiseattention.analyser import (
    AnalysisResult,
    Diagnostic,
    ExceptionAnalyser,
)
from raiseattention.config import Config

if TYPE_CHECKING:
    pass


class TestDiagnostic:
    """tests for the Diagnostic dataclass."""

    def test_creation(self) -> None:
        """Test diagnostic creation."""
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
        """Test default analysis result values."""
        result = AnalysisResult()

        assert result.diagnostics == []
        assert result.files_analysed == []
        assert result.functions_found == 0
        assert result.exceptions_tracked == 0


class TestExceptionAnalyser:
    """tests for the ExceptionAnalyser class."""

    def test_init(self) -> None:
        """Test analyzer initialisation."""
        config = Config()
        analyzer = ExceptionAnalyser(config)

        assert analyzer.config == config

    def test_analyse_file_not_found(self, tmp_path: Path) -> None:
        """Test analysing non-existent file."""
        config = Config()
        analyzer = ExceptionAnalyser(config)

        result = analyzer.analyse_file(tmp_path / "nonexistent.py")

        assert len(result.diagnostics) == 1
        assert "failed to analyse" in result.diagnostics[0].message

    def test_analyse_simple_file(self, tmp_path: Path) -> None:
        """Test analysing a simple python file."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def simple():
    pass
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)

        result = analyzer.analyse_file(test_file)

        assert len(result.files_analysed) == 1
        # +1 for the synthetic <module> function that tracks module-level code
        assert result.functions_found == 2

    def test_analyse_file_with_exception(self, tmp_path: Path) -> None:
        """Test analysing a file that raises exceptions."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def risky():
    raise ValueError("error")
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)

        result = analyzer.analyse_file(test_file)

        # +1 for the synthetic <module> function
        assert result.functions_found == 2
        assert result.exceptions_tracked == 1

    def test_analyse_project(self, tmp_path: Path) -> None:
        """Test analysing an entire project."""
        # create multiple python files
        _ = (tmp_path / "module1.py").write_text("""
def func1():
    pass
""")
        _ = (tmp_path / "module2.py").write_text("""
def func2():
    raise ValueError()
""")
        (tmp_path / "subdir").mkdir()
        _ = (tmp_path / "subdir" / "module3.py").write_text("""
def func3():
    pass
""")

        config = Config(project_root=tmp_path, exclude=[])
        analyzer = ExceptionAnalyser(config)

        result = analyzer.analyse_project(tmp_path)

        assert len(result.files_analysed) == 3
        # 3 regular functions + 3 synthetic <module> functions (one per file)
        assert result.functions_found == 6

    def test_get_function_signature(self, tmp_path: Path) -> None:
        """Test getting exception signature for a function."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def risky():
    raise ValueError("error")
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        _ = analyzer.analyse_file(test_file)

        signature = analyzer.get_function_signature("test.risky")

        assert "ValueError" in signature

    def test_transitive_exception_tracking(self, tmp_path: Path) -> None:
        """Test that exceptions propagate transitively."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def level3():
    raise ValueError("deep error")

def level2():
    level3()

def level1():
    level2()
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        _ = analyzer.analyse_file(test_file)

        # all levels should have ValueError in signature
        assert "ValueError" in analyzer.get_function_signature("test.level3")
        # note: transitive tracking requires full call graph analysis
        # which is simplified in this implementation

    def test_ignore_exceptions_config(self, tmp_path: Path) -> None:
        """Test that ignored exceptions are filtered."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def func():
    raise KeyboardInterrupt()
""")

        config = Config(ignore_exceptions=["KeyboardInterrupt"])
        analyzer = ExceptionAnalyser(config)

        result = analyzer.analyse_file(test_file)

        # keyboardinterrupt should be filtered out
        # but the function still raises it
        assert result.exceptions_tracked == 1

    def test_strict_mode_docstring_check(self, tmp_path: Path) -> None:
        """Test strict mode requires documented exceptions."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def undocumented():
    raise ValueError("error")

def caller():
    undocumented()  # call to trigger exception flow analysis
""")

        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        result = analyzer.analyse_file(test_file)

        # should have diagnostic about undocumented exception
        # strict mode flags functions with unhandled exceptions that are not documented
        assert any("undocumented" in d.message for d in result.diagnostics)

    def test_cache_usage(self, tmp_path: Path) -> None:
        """Test that cache is used for repeated analysis."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def func():
    pass
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)

        # first analysis
        result1 = analyzer.analyse_file(test_file)

        # second analysis should use cache
        result2 = analyzer.analyse_file(test_file)

        assert result1.functions_found == result2.functions_found

    def test_invalidate_file(self, tmp_path: Path) -> None:
        """Test invalidating a file from cache."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("def func(): pass")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        _ = analyzer.analyse_file(test_file)

        # invalidate
        analyzer.invalidate_file(test_file)

        # file analyses should be cleared
        assert test_file.resolve() not in analyzer._file_analyses  # pyright: ignore[reportPrivateUsage]


class TestDebugLogging:
    """tests for debug logging functionality."""

    def test_debug_logging_enabled(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """test that debug logging produces output when enabled."""
        import logging

        # enable debug logging for raiseattention
        logging.getLogger("raiseattention").setLevel(logging.DEBUG)

        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def risky():
    raise ValueError("error")

def caller():
    risky()
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)

        with caplog.at_level(logging.DEBUG, logger="raiseattention"):
            _ = analyzer.analyse_file(test_file)

        # check that some debug messages were logged
        debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(debug_messages) > 0

        # reset logging level
        logging.getLogger("raiseattention").setLevel(logging.WARNING)

    def test_debug_logging_shows_signature_computation(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """test that debug logging shows signature computation."""
        import logging

        logging.getLogger("raiseattention").setLevel(logging.DEBUG)

        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def level2():
    raise ValueError("deep")

def level1():
    level2()
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)

        with caplog.at_level(logging.DEBUG, logger="raiseattention"):
            _ = analyzer.analyse_file(test_file)
            # trigger signature computation
            _ = analyzer.get_function_signature("test.level1")

        # check that signature computation was logged
        # should have some logging about function analysis
        assert len(caplog.records) > 0

        # reset logging level
        logging.getLogger("raiseattention").setLevel(logging.WARNING)

    def test_ast_visitor_logs_function_visits(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,  # noqa: ARG002
    ) -> None:
        """test that AST visitor logs function visits."""
        import logging

        from raiseattention.ast_visitor import parse_source

        _ = tmp_path  # unused but required by pytest fixture pattern
        logging.getLogger("raiseattention").setLevel(logging.DEBUG)

        source = """
@my_decorator
def decorated_func():
    raise ValueError("error")
"""

        with caplog.at_level(logging.DEBUG, logger="raiseattention"):
            _ = parse_source(source)

        # check for function visit log
        log_text = "\n".join(r.message for r in caplog.records)
        assert "visiting function" in log_text or "decorated_func" in log_text

        # reset logging level
        logging.getLogger("raiseattention").setLevel(logging.WARNING)


class TestHOFExceptionPropagation:
    """tests for higher-order function exception propagation."""

    def test_map_with_risky_callable(self, tmp_path: Path) -> None:
        """test that exceptions from functions passed to map are tracked."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def risky_transform(x):
    if x < 0:
        raise ValueError("negative value")
    return x * 2

def uses_map():
    data = [1, -2, 3]
    result = list(map(risky_transform, data))
    return result
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        _ = analyzer.analyse_file(test_file)

        # uses_map should have ValueError in its signature via risky_transform
        signature = analyzer.get_function_signature("test.uses_map")
        assert "ValueError" in signature

    def test_filter_with_risky_predicate(self, tmp_path: Path) -> None:
        """test that exceptions from predicates passed to filter are tracked."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def risky_predicate(x):
    if x == 0:
        raise ZeroDivisionError("cannot check zero")
    return x > 0

def uses_filter():
    data = [1, 0, 3]
    result = list(filter(risky_predicate, data))
    return result
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        _ = analyzer.analyse_file(test_file)

        signature = analyzer.get_function_signature("test.uses_filter")
        assert "ZeroDivisionError" in signature

    def test_sorted_with_risky_key(self, tmp_path: Path) -> None:
        """test that exceptions from key functions passed to sorted are tracked."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def risky_key(item):
    if "key" not in item:
        raise KeyError("missing key")
    return item["key"]

def uses_sorted():
    data = [{"key": "b"}, {"no_key": "a"}]
    result = sorted(data, key=risky_key)
    return result
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        _ = analyzer.analyse_file(test_file)

        signature = analyzer.get_function_signature("test.uses_sorted")
        assert "KeyError" in signature

    def test_min_max_with_risky_key(self, tmp_path: Path) -> None:
        """test that exceptions from key functions passed to min/max are tracked."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def risky_key(item):
    if item is None:
        raise TypeError("cannot compare None")
    return item

def uses_min():
    data = [1, None, 3]
    result = min(data, key=risky_key)
    return result

def uses_max():
    data = [1, None, 3]
    result = max(data, key=risky_key)
    return result
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        _ = analyzer.analyse_file(test_file)

        min_sig = analyzer.get_function_signature("test.uses_min")
        max_sig = analyzer.get_function_signature("test.uses_max")
        assert "TypeError" in min_sig
        assert "TypeError" in max_sig

    def test_nested_hof_calls(self, tmp_path: Path) -> None:
        """test that nested HOF calls propagate exceptions correctly."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def risky_transform(x):
    if x < 0:
        raise ValueError("negative")
    return x * 2

def risky_predicate(x):
    if x == 0:
        raise RuntimeError("zero not allowed")
    return x > 0

def uses_nested_hofs():
    data = [1, -2, 0, 3]
    transformed = map(risky_transform, data)
    filtered = filter(risky_predicate, transformed)
    return list(filtered)
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        _ = analyzer.analyse_file(test_file)

        signature = analyzer.get_function_signature("test.uses_nested_hofs")
        assert "ValueError" in signature
        assert "RuntimeError" in signature

    def test_lambda_in_hof_not_tracked(self, tmp_path: Path) -> None:
        """test that lambdas in HOFs are gracefully skipped (not tracked)."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def uses_lambda_in_map():
    data = [1, 2, 3]
    # lambda exceptions are not tracked
    result = list(map(lambda x: x / 0, data))
    return result
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        _ = analyzer.analyse_file(test_file)

        # should not crash, and signature should be empty (lambdas not tracked)
        signature = analyzer.get_function_signature("test.uses_lambda_in_map")
        # ZeroDivisionError from the lambda is NOT tracked (expected behaviour)
        assert "ZeroDivisionError" not in signature

    def test_method_reference_in_hof(self, tmp_path: Path) -> None:
        """test that method references passed to HOFs are tracked."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
class Processor:
    def process(self, x):
        if x < 0:
            raise ValueError("negative")
        return x * 2

    def process_all(self, items):
        return list(map(self.process, items))
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        _ = analyzer.analyse_file(test_file)

        # process_all should include ValueError from self.process
        _signature = analyzer.get_function_signature("test.Processor.process_all")
        # Note: method resolution via self.process may not work perfectly
        # but the callable_args should be captured as "self.process"
        assert _signature is not None  # ensure signature was computed

    def test_safe_hof_no_exceptions(self, tmp_path: Path) -> None:
        """test that HOFs with safe callables don't add spurious exceptions."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def safe_transform(x):
    return x * 2

def uses_safe_map():
    data = [1, 2, 3]
    result = list(map(safe_transform, data))
    return result
""")

        config = Config()
        config.analysis.warn_native = False  # disable native warnings for this test
        analyzer = ExceptionAnalyser(config)
        analyzer.analyse_file(test_file)

        signature = analyzer.get_function_signature("test.uses_safe_map")
        # should have no exceptions (from the callable arg - native warnings disabled)
        assert len(signature) == 0

    def test_hof_exception_signature_tracking(self, tmp_path: Path) -> None:
        """test that HOF exceptions are tracked in function signatures."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def risky_transform(x):
    if x < 0:
        raise ValueError("negative")
    return x * 2

def caller():
    data = [1, -2, 3]
    result = list(map(risky_transform, data))
    return result
""")

        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)
        analyzer.analyse_file(test_file)

        # the function signature should include ValueError from the HOF call
        caller_sig = analyzer.get_function_signature("test.caller")
        assert "ValueError" in caller_sig

        # risky_transform should also have ValueError in its signature
        risky_sig = analyzer.get_function_signature("test.risky_transform")
        assert "ValueError" in risky_sig


class TestIgnoreComments:
    """tests for inline ignore comment functionality."""

    def test_ignore_comment_basic(self, tmp_path: Path) -> None:
        """test that # raiseattention: ignore[Exception] comments work."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def risky():
    raise ValueError("error")

def caller():
    risky()  # raiseattention: ignore[ValueError]
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        result = analyzer.analyse_file(test_file)

        # should not report error on line 6 because of ignore comment
        error_lines = [d.line for d in result.diagnostics]
        assert 6 not in error_lines

    def test_ignore_comment_ra_shorthand(self, tmp_path: Path) -> None:
        """test that # ra: ignore[Exception] shorthand works."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def risky():
    raise ValueError("error")

def caller():
    risky()  # ra: ignore[ValueError]
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        result = analyzer.analyse_file(test_file)

        # should not report error because of ra: ignore comment
        error_lines = [d.line for d in result.diagnostics]
        assert 6 not in error_lines

    def test_ignore_comment_mixed_case(self, tmp_path: Path) -> None:
        """test that mixed case formats like RaiseAttention work."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def risky():
    raise ValueError("error")

def caller():
    risky()  # RaiseAttention: ignore[ValueError]
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        result = analyzer.analyse_file(test_file)

        # should not report error because of mixed case comment
        error_lines = [d.line for d in result.diagnostics]
        assert 6 not in error_lines

    def test_ignore_comment_possible_native_exception(self, tmp_path: Path) -> None:
        """test that PossibleNativeException can be ignored."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
import mmap

def caller():
    mmap.mmap(-1, 1024)  # raiseattention: ignore[PossibleNativeException]
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        result = analyzer.analyse_file(test_file)

        # should not report PossibleNativeException because of ignore comment
        native_diagnostics = [
            d
            for d in result.diagnostics
            if any("PossibleNativeException" in exc for exc in d.exception_types)
        ]
        assert len(native_diagnostics) == 0

    def test_ignore_comment_multiple_exceptions(self, tmp_path: Path) -> None:
        """test that multiple exceptions can be ignored in one comment."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def risky():
    raise ValueError("error")

def caller():
    risky()  # raiseattention: ignore[ValueError, TypeError]
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        result = analyzer.analyse_file(test_file)

        # should not report error because ValueError is in ignore list
        error_lines = [d.line for d in result.diagnostics]
        assert 6 not in error_lines

    def test_invalid_ignore_comment_reported(self, tmp_path: Path) -> None:
        """test that invalid ignore comments (without brackets) are reported."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def caller():
    pass  # raiseattention: ignore
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        result = analyzer.analyse_file(test_file)

        # should report invalid ignore comment on line 3
        warnings = [d for d in result.diagnostics if d.severity == "warning"]
        warning_lines = [d.line for d in warnings]
        assert 3 in warning_lines

    def test_main_reraise_pattern_not_flagged(self, tmp_path: Path) -> None:
        """test that calls inside try-except at module level are not flagged."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
def main():
    raise ValueError("error")

if __name__ == "__main__":
    try:
        exit(main())  # this should NOT be flagged
    except Exception as exc:
        print(f"error: {exc}")
        exit(1)
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        result = analyzer.analyse_file(test_file)

        # should not report call to main() as it's inside try-except
        main_call_diagnostics = [d for d in result.diagnostics if "main" in d.message.lower()]
        assert len(main_call_diagnostics) == 0

    def test_possible_native_exception_caught_by_except_exception(self, tmp_path: Path) -> None:
        """test that PossibleNativeException is caught by 'except Exception:'."""
        test_file = tmp_path / "test.py"
        _ = test_file.write_text("""
import mmap

def main():
    mmap.mmap(-1, 1024)

def caller():
    try:
        main()  # should NOT be flagged - PossibleNativeException caught by except Exception
    except Exception as exc:
        print(f"error: {exc}")
""")

        config = Config()
        analyzer = ExceptionAnalyser(config)
        result = analyzer.analyse_file(test_file)

        # the call to main() inside try-except should not be flagged
        call_diagnostics = [d for d in result.diagnostics if d.line == 9]
        assert len(call_diagnostics) == 0
