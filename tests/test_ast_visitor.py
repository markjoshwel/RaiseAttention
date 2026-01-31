"""tests for the ast visitor module."""

from __future__ import annotations

import pytest

from raiseattention.ast_visitor import (
    ExceptionInfo,
    ExceptionVisitor,
    TryExceptInfo,
    parse_source,
)


class TestExceptionInfo:
    """tests for the ExceptionInfo dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic exception info creation."""
        info = ExceptionInfo(
            exception_type="ValueError",
            location=(10, 5),
        )

        assert info.exception_type == "ValueError"
        assert info.location == (10, 5)
        assert info.message is None
        assert info.is_re_raise is False


class TestExceptionVisitor:
    """tests for the ExceptionVisitor class."""

    def test_import_tracking(self) -> None:
        """Test that imports are tracked correctly."""
        source = """
import os
import sys as system
from pathlib import Path
from typing import Optional, List
"""

        visitor = parse_source(source)

        assert visitor.imports["os"] == "os"
        assert visitor.imports["system"] == "sys"
        assert visitor.imports["Path"] == "pathlib.Path"
        assert visitor.imports["Optional"] == "typing.Optional"

    def test_function_detection(self) -> None:
        """Test that functions are detected."""
        source = """
def simple_function():
    pass

async def async_function():
    pass
"""

        visitor = parse_source(source)

        assert len(visitor.functions) == 2
        assert "<string>.simple_function" in visitor.functions
        assert "<string>.async_function" in visitor.functions

    def test_raise_detection(self) -> None:
        """Test that raise statements are detected."""
        source = """
def risky_function():
    raise ValueError("something went wrong")
"""

        visitor = parse_source(source)

        func = visitor.functions["<string>.risky_function"]
        assert len(func.raises) == 1
        assert func.raises[0].exception_type == "ValueError"
        assert func.raises[0].message == "something went wrong"

    def test_re_raise_detection(self) -> None:
        """Test that bare raise statements are detected as re-raises."""
        source = """
def handle_error():
    try:
        risky()
    except ValueError:
        print("caught")
        raise
"""

        visitor = parse_source(source)

        func = visitor.functions["<string>.handle_error"]
        assert len(func.raises) == 1
        assert func.raises[0].is_re_raise is True

    def test_try_except_detection(self) -> None:
        """Test that try-except blocks are detected."""
        source = """
def handle_errors():
    try:
        risky()
    except ValueError:
        pass
    except KeyError:
        pass
"""

        visitor = parse_source(source)

        assert len(visitor.try_except_blocks) == 1
        block = visitor.try_except_blocks[0]
        assert "ValueError" in block.handled_types
        assert "KeyError" in block.handled_types

    def test_bare_except_detection(self) -> None:
        """Test that bare except clauses are detected."""
        source = """
def handle_all():
    try:
        risky()
    except:
        pass
"""

        visitor = parse_source(source)

        assert len(visitor.try_except_blocks) == 1
        assert visitor.try_except_blocks[0].has_bare_except is True

    def test_function_calls_tracking(self) -> None:
        """Test that function calls are tracked."""
        source = """
def caller():
    helper()
    obj.method()
    module.function()
"""

        visitor = parse_source(source)

        func = visitor.functions["<string>.caller"]
        assert "helper" in func.calls
        assert "obj.method" in func.calls
        assert "module.function" in func.calls

    def test_class_method_detection(self) -> None:
        """Test that class methods are detected with qualified names."""
        source = """
class MyClass:
    def method(self):
        pass

    async def async_method(self):
        pass
"""

        visitor = parse_source(source)

        assert "<string>.MyClass.method" in visitor.functions
        assert "<string>.MyClass.async_method" in visitor.functions

    def test_qualified_exception_type(self) -> None:
        """Test that qualified exception types are resolved."""
        source = """
import requests

def fetch():
    raise requests.RequestException("failed")
"""

        visitor = parse_source(source)

        func = visitor.functions["<string>.fetch"]
        assert len(func.raises) == 1
        assert func.raises[0].exception_type == "requests.RequestException"

    def test_docstring_extraction(self) -> None:
        """Test that function docstrings are extracted."""
        source = '''
def documented():
    """
    this function does something.

    raises:
        ValueError: when input is invalid
    """
    pass
'''

        visitor = parse_source(source)

        func = visitor.functions["<string>.documented"]
        assert func.docstring is not None
        assert "this function does something" in func.docstring


class TestParseSource:
    """tests for the parse_source function."""

    def test_valid_source(self) -> None:
        """Test parsing valid python source."""
        source = "x = 1 + 2"

        visitor = parse_source(source)

        assert isinstance(visitor, ExceptionVisitor)
        assert visitor.module_name == "<string>"

    def test_custom_module_name(self) -> None:
        """Test parsing with custom module name."""
        source = "pass"

        visitor = parse_source(source, module_name="my_module")

        assert visitor.module_name == "my_module"

    def test_invalid_syntax(self) -> None:
        """Test that invalid syntax raises SyntaxError."""
        source = "def broken("

        with pytest.raises(SyntaxError):
            parse_source(source)


class TestTryExceptInfo:
    """tests for the TryExceptInfo dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic try-except info creation."""
        info = TryExceptInfo(
            location=(20, 4),
            handled_types=["ValueError", "TypeError"],
        )

        assert info.location == (20, 4)
        assert info.handled_types == ["ValueError", "TypeError"]
        assert info.has_bare_except is False
        assert info.reraises is False
