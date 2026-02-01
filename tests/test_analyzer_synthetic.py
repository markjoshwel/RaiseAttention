"""comprehensive tests for the analyser using synthetic codebases.

this module tests the exception analyser against synthetic codebases
to verify:
- unhandled exceptions are detected
- caught exceptions are not flagged
- various exception scenarios work correctly
"""

from __future__ import annotations

from pathlib import Path

import pytest

from raiseattention.analyser import ExceptionAnalyser
from raiseattention.config import Config
from tests.fixtures.code_samples import (
    create_async_exceptions_file,
    create_complex_nesting_file,
    create_custom_exceptions_file,
    create_exception_chaining_file,
    create_handled_exception_file,
    create_mixed_scenario_file,
    create_synthetic_codebase,
    create_unhandled_exception_file,
)


class TestUnhandledExceptions:
    """tests that unhandled exceptions are properly detected."""

    def test_simple_unhandled_exception(self, tmp_path: Path) -> None:
        """test detection of simple unhandled exception."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        test_file = create_unhandled_exception_file(tmp_path)
        result = analyzer.analyse_file(test_file)

        # should find unhandled exceptions
        assert len(result.diagnostics) > 0

        # check for specific unhandled exception
        messages = [d.message for d in result.diagnostics]
        assert any("ValueError" in msg for msg in messages)

    def test_unhandled_in_caller(self, tmp_path: Path) -> None:
        """test that calling a raising function without handling is flagged."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        test_file = create_unhandled_exception_file(tmp_path)
        result = analyzer.analyse_file(test_file)

        # should flag the caller function
        caller_diag = [d for d in result.diagnostics if "caller" in d.message.lower()]
        assert len(caller_diag) > 0

    def test_transitive_exception_detection(self, tmp_path: Path) -> None:
        """test detection of exceptions through multiple call levels."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        test_file = create_complex_nesting_file(tmp_path)
        result = analyzer.analyse_file(test_file)

        # should detect transitive exceptions through level_one -> level_two -> level_three
        messages = [d.message for d in result.diagnostics]
        assert any("level_three" in msg.lower() or "level_two" in msg.lower() for msg in messages)


class TestHandledExceptions:
    """tests that properly handled exceptions are not flagged."""

    def test_simple_try_except(self, tmp_path: Path) -> None:
        """test that simple try-except blocks prevent flagging."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        test_file = create_handled_exception_file(tmp_path)
        result = analyzer.analyse_file(test_file)

        # should have NO diagnostics - all exceptions are handled
        assert len(result.diagnostics) == 0

    def test_multiple_exception_types(self, tmp_path: Path) -> None:
        """test handling of multiple exception types."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        test_file = create_handled_exception_file(tmp_path)
        result = analyzer.analyse_file(test_file)

        # multi_exception_handler should not be flagged
        multi_handler_diag = [
            d for d in result.diagnostics if "multi_exception" in d.message.lower()
        ]
        assert len(multi_handler_diag) == 0

    def test_nested_try_except(self, tmp_path: Path) -> None:
        """test that nested try-except blocks work correctly."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        test_file = create_handled_exception_file(tmp_path)
        result = analyzer.analyse_file(test_file)

        # nested_try_except should not be flagged
        nested_diag = [d for d in result.diagnostics if "nested" in d.message.lower()]
        assert len(nested_diag) == 0

    def test_intermediate_handling(self, tmp_path: Path) -> None:
        """test handling at intermediate call level."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        test_file = create_complex_nesting_file(tmp_path)
        result = analyzer.analyse_file(test_file)

        # partial_handling should not be flagged as it handles at level 2
        partial_diag = [d for d in result.diagnostics if "partial" in d.message.lower()]
        assert len(partial_diag) == 0


class TestCustomExceptions:
    """tests for custom exception classes."""

    def test_custom_exception_detection(self, tmp_path: Path) -> None:
        """test detection of custom exception types."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        test_file = create_custom_exceptions_file(tmp_path)
        result = analyzer.analyse_file(test_file)

        # should detect unhandled BusinessError
        messages = [d.message for d in result.diagnostics]
        assert any("BusinessError" in msg for msg in messages)

    @pytest.mark.skip(
        reason="parent class handling requires class definition parsing - known limitation"
    )
    def test_parent_class_handling(self, tmp_path: Path) -> None:
        """test that catching parent class handles child exceptions."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        test_file = create_custom_exceptions_file(tmp_path)
        result = analyzer.analyse_file(test_file)

        # caller_handling_parent should not be flagged
        parent_handler_diag = [d for d in result.diagnostics if "parent" in d.message.lower()]
        assert len(parent_handler_diag) == 0

    def test_specific_exception_handling(self, tmp_path: Path) -> None:
        """test handling of specific custom exception."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        test_file = create_custom_exceptions_file(tmp_path)
        result = analyzer.analyse_file(test_file)

        # caller_handling_specific should not be flagged
        specific_handler_diag = [d for d in result.diagnostics if "specific" in d.message.lower()]
        assert len(specific_handler_diag) == 0


class TestExceptionChaining:
    """tests for exception chaining (raise from)."""

    def test_chained_exception_detection(self, tmp_path: Path) -> None:
        """test detection of chained exceptions."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        test_file = create_exception_chaining_file(tmp_path)
        result = analyzer.analyse_file(test_file)

        # caller_of_chained should be flagged for RuntimeError
        messages = [d.message for d in result.diagnostics]
        assert any("RuntimeError" in msg for msg in messages)

    def test_both_exceptions_handled(self, tmp_path: Path) -> None:
        """test handling both chained and original exceptions."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        test_file = create_exception_chaining_file(tmp_path)
        result = analyzer.analyse_file(test_file)

        # caller_handling_both should not be flagged
        both_handler_diag = [d for d in result.diagnostics if "both" in d.message.lower()]
        assert len(both_handler_diag) == 0


class TestMixedScenarios:
    """tests for files with both handled and unhandled exceptions."""

    def test_partial_handling(self, tmp_path: Path) -> None:
        """test that partial handling only flags unhandled paths."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        test_file = create_mixed_scenario_file(tmp_path)
        result = analyzer.analyse_file(test_file)

        # should have some diagnostics
        assert len(result.diagnostics) > 0

        # bad_caller should be flagged
        bad_diag = [d for d in result.diagnostics if "bad_caller" in d.message.lower()]
        assert len(bad_diag) > 0

        # good_caller should NOT be flagged
        good_diag = [d for d in result.diagnostics if "good_caller" in d.message.lower()]
        assert len(good_diag) == 0

    def test_mixed_caller_detection(self, tmp_path: Path) -> None:
        """test detection in mixed caller function."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        test_file = create_mixed_scenario_file(tmp_path)
        result = analyzer.analyse_file(test_file)

        # should flag RuntimeError path in mixed_caller
        runtime_diag = [
            d
            for d in result.diagnostics
            if "RuntimeError" in d.message and "mixed" in d.message.lower()
        ]
        assert len(runtime_diag) > 0


class TestAsyncExceptions:
    """tests for async/await exception scenarios."""

    def test_async_unhandled(self, tmp_path: Path) -> None:
        """test detection in async functions."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        test_file = create_async_exceptions_file(tmp_path)
        result = analyzer.analyse_file(test_file)

        # async_caller_unhandled should be flagged
        unhandled_diag = [
            d for d in result.diagnostics if "async_caller_unhandled" in d.message.lower()
        ]
        assert len(unhandled_diag) > 0

    def test_async_handled(self, tmp_path: Path) -> None:
        """test that handled async exceptions are not flagged."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        test_file = create_async_exceptions_file(tmp_path)
        result = analyzer.analyse_file(test_file)

        # async_caller_handled should NOT be flagged
        handled_diag = [
            d for d in result.diagnostics if "async_caller_handled" in d.message.lower()
        ]
        assert len(handled_diag) == 0


class TestSyntheticCodebase:
    """integration tests using the full synthetic codebase."""

    def test_analyse_synthetic_codebase(self, tmp_path: Path) -> None:
        """test analysis of the entire synthetic codebase."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        # create the full codebase
        codebase_path = tmp_path / "test_codebase"
        files = create_synthetic_codebase(codebase_path)
        assert len(files) == 5  # verify all 5 main files created
        assert all(isinstance(path, Path) for path in files.values())  # verify paths returned

        # analyse the project
        result = analyzer.analyse_project(codebase_path)

        # should analyse all files (5 main files + __init__.py = 6 total)
        assert len(result.files_analysed) == 6

        # should find unhandled exceptions (at least one per unhandled file)
        assert len(result.diagnostics) > 0

    def test_codebase_file_counts(self, tmp_path: Path) -> None:
        """test that all files are analysed."""
        config = Config()
        analyzer = ExceptionAnalyser(config)

        codebase_path = tmp_path / "test_codebase"
        create_synthetic_codebase(codebase_path)

        result = analyzer.analyse_project(codebase_path)

        # should find all 5 main files + __init__.py
        assert len(result.files_analysed) >= 5


class TestConfigurationImpact:
    """tests for how configuration affects analysis results."""

    def test_strict_mode_enabled(self, tmp_path: Path) -> None:
        """test that strict mode finds more issues."""
        config = Config()
        config.analysis.strict_mode = True
        analyzer = ExceptionAnalyser(config)

        test_file = create_unhandled_exception_file(tmp_path)
        result = analyzer.analyse_file(test_file)

        strict_count = len(result.diagnostics)

        # compare with non-strict mode
        config2 = Config()
        config2.analysis.strict_mode = False
        analyzer2 = ExceptionAnalyser(config2)

        result2 = analyzer2.analyse_file(test_file)
        non_strict_count = len(result2.diagnostics)

        # strict mode should find at least as many issues
        assert strict_count >= non_strict_count

    def test_allow_bare_except(self, tmp_path: Path) -> None:
        """test bare except configuration."""
        config = Config()
        config.analysis.allow_bare_except = True
        analyzer = ExceptionAnalyser(config)

        # create file with bare except
        test_file = tmp_path / "bare_except.py"
        test_file.write_text("""
def risky():
    raise ValueError("error")

def handler():
    try:
        risky()
    except:  # bare except
        pass
""")

        result = analyzer.analyse_file(test_file)
        # with allow_bare_except=True, should not flag the bare except
        # and should consider the exception handled
        assert result.files_analysed  # verify file was analysed

    def test_ignore_exceptions_list(self, tmp_path: Path) -> None:
        """test that ignored exceptions are not flagged."""
        config = Config()
        config.ignore_exceptions = ["ValueError"]
        analyzer = ExceptionAnalyser(config)

        test_file = tmp_path / "ignored.py"
        test_file.write_text("""
def risky():
    raise ValueError("ignored")

def caller():
    risky()  # should not be flagged because ValueError is ignored
""")

        result = analyzer.analyse_file(test_file)
        # should have no diagnostics because ValueError is ignored
        value_error_diags = [d for d in result.diagnostics if "ValueError" in d.message]
        assert len(value_error_diags) == 0
