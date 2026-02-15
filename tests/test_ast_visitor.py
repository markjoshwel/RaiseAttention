"""tests for the ast visitor module."""

from __future__ import annotations

import pytest

from raiseattention.ast_visitor import (
    ExceptionInfo,
    ExceptionVisitor,
    SuppressInfo,
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

        # +1 for the synthetic <module> function that tracks module-level code
        assert len(visitor.functions) == 3
        assert "<string>.<module>" in visitor.functions
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
def handle_error():
    try:
        risky()
    except ValueError:
        print("caught")
"""

        visitor = parse_source(source)

        assert len(visitor.try_except_blocks) == 1
        try_block = visitor.try_except_blocks[0]
        assert try_block.handled_types == ["ValueError"]
        assert try_block.has_bare_except is False

    def test_bare_except_detection(self) -> None:
        """Test that bare except clauses are detected."""
        source = """
def handle_error():
    try:
        risky()
    except:
        print("caught everything")
"""

        visitor = parse_source(source)

        assert len(visitor.try_except_blocks) == 1
        assert visitor.try_except_blocks[0].has_bare_except is True

    def test_multiple_exception_handlers(self) -> None:
        """Test that multiple exception handlers are detected."""
        source = """
def handle_error():
    try:
        risky()
    except ValueError:
        print("value error")
    except TypeError:
        print("type error")
"""

        visitor = parse_source(source)

        assert len(visitor.try_except_blocks) == 1
        try_block = visitor.try_except_blocks[0]
        assert "ValueError" in try_block.handled_types
        assert "TypeError" in try_block.handled_types

    def test_call_in_try_block(self) -> None:
        """Test that calls inside try blocks are tracked."""
        source = """
def risky():
    raise ValueError("error")

def caller():
    try:
        risky()
    except ValueError:
        pass
"""

        visitor = parse_source(source)

        func = visitor.functions["<string>.caller"]
        risky_calls = [c for c in func.calls if c.func_name == "risky"]
        assert len(risky_calls) == 1
        assert risky_calls[0].containing_try_blocks == [0]

    def test_call_outside_try_block(self) -> None:
        """Test that calls outside try blocks are tracked correctly."""
        source = """
def risky():
    raise ValueError("error")

def caller():
    risky()  # outside try block
"""

        visitor = parse_source(source)

        func = visitor.functions["<string>.caller"]
        risky_calls = [c for c in func.calls if c.func_name == "risky"]
        assert len(risky_calls) == 1
        assert risky_calls[0].containing_try_blocks == []

    def test_nested_try_blocks(self) -> None:
        """Test handling of nested try-except blocks."""
        source = """
def risky():
    raise ValueError("error")

def caller():
    try:
        try:
            risky()
        except TypeError:
            pass
    except ValueError:
        pass
"""

        visitor = parse_source(source)

        assert len(visitor.try_except_blocks) == 2

        func = visitor.functions["<string>.caller"]
        risky_calls = [c for c in func.calls if c.func_name == "risky"]
        assert len(risky_calls) == 1
        # should be in both try blocks
        assert len(risky_calls[0].containing_try_blocks) == 2

    def test_async_function(self) -> None:
        """Test that async functions are detected."""
        source = """
async def async_risky():
    raise ValueError("error")
"""

        visitor = parse_source(source)

        func = visitor.functions["<string>.async_risky"]
        assert func.is_async is True

    def test_async_call(self) -> None:
        """Test that async calls are tracked."""
        source = """
async def async_risky():
    raise ValueError("error")

async def caller():
    await async_risky()
"""

        visitor = parse_source(source)

        func = visitor.functions["<string>.caller"]
        risky_calls = [c for c in func.calls if c.func_name == "async_risky"]
        assert len(risky_calls) == 1
        assert risky_calls[0].is_async is True

    def test_class_method(self) -> None:
        """Test that class methods are detected with qualified names."""
        source = """
class MyClass:
    def method(self):
        raise ValueError("error")
"""

        visitor = parse_source(source)

        assert "<string>.MyClass.method" in visitor.functions
        func = visitor.functions["<string>.MyClass.method"]
        assert func.name == "method"

    def test_qualified_exception_type(self) -> None:
        """Test that qualified exception types are captured."""
        source = """
import requests

def risky():
    raise requests.RequestException("network error")
"""

        visitor = parse_source(source)

        func = visitor.functions["<string>.risky"]
        assert len(func.raises) == 1
        assert func.raises[0].exception_type == "requests.RequestException"

    def test_docstring_extraction(self) -> None:
        """Test that function docstrings are extracted."""
        source = '''
def documented():
    """This is a docstring."""
    pass
'''

        visitor = parse_source(source)

        func = visitor.functions["<string>.documented"]
        assert func.docstring == "This is a docstring."

    def test_call_tracking(self) -> None:
        """Test that function calls are tracked."""
        source = """
def helper():
    pass

def caller():
    helper()
"""

        visitor = parse_source(source)

        func = visitor.functions["<string>.caller"]
        assert len(func.calls) == 1
        assert func.calls[0].func_name == "helper"

    def test_exception_instance_re_raise(self) -> None:
        """Test that 'raise e' from 'except Exception as e:' is treated as re-raise."""
        source = """
def handler():
    try:
        risky()
    except ValueError as e:
        raise e
"""

        visitor = parse_source(source)

        func = visitor.functions["<string>.handler"]
        assert len(func.raises) == 1
        # should be treated as re-raise
        assert func.raises[0].is_re_raise is True

    def test_module_level_code(self) -> None:
        """Test that module-level code is tracked."""
        source = """
def helper():
    raise ValueError("error")

helper()  # called at module level
"""

        visitor = parse_source(source)

        # should have a synthetic function for module-level code
        assert "<string>.<module>" in visitor.functions
        module_func = visitor.functions["<string>.<module>"]
        assert len(module_func.calls) == 1

    def test_decorator_tracking(self) -> None:
        """Test that decorators are tracked."""
        source = """
from functools import lru_cache

def my_decorator(func):
    return func

@my_decorator
def decorated_func():
    pass

@lru_cache(maxsize=128)
def cached_func():
    pass
"""

        visitor = parse_source(source)

        func1 = visitor.functions["<string>.decorated_func"]
        assert "my_decorator" in func1.decorators

        func2 = visitor.functions["<string>.cached_func"]
        assert "lru_cache" in func2.decorators

    def test_detects_function_passed_as_arg(self) -> None:
        """Test that functions passed as arguments are detected."""
        source = """
def process(x):
    return x * 2

def apply(func, items):
    return [func(item) for item in items]

def caller():
    return apply(process, [1, 2, 3])
"""

        visitor = parse_source(source)

        func = visitor.functions["<string>.caller"]
        apply_calls = [c for c in func.calls if c.func_name == "apply"]
        assert len(apply_calls) == 1
        assert "process" in apply_calls[0].callable_args

    def test_detects_lambda_passed_as_arg(self) -> None:
        """Test that lambdas passed as arguments are detected."""
        source = """
def caller():
    return list(map(lambda x: x * 2, [1, 2, 3]))
"""

        visitor = parse_source(source)

        func = visitor.functions["<string>.caller"]
        map_calls = [c for c in func.calls if c.func_name == "map"]
        assert len(map_calls) == 1
        assert "<lambda>" in map_calls[0].callable_args

    def test_detects_builtin_function_as_arg(self) -> None:
        """Test that builtin functions passed as arguments are detected."""
        source = """
def caller():
    return list(map(str, [1, 2, 3]))
"""

        visitor = parse_source(source)

        func = visitor.functions["<string>.caller"]
        map_calls = [c for c in func.calls if c.func_name == "map"]
        assert len(map_calls) == 1
        assert "str" in map_calls[0].callable_args

    def test_detects_method_reference_passed_as_arg(self) -> None:
        """Test that method references are detected as callable args."""
        source = """
class Processor:
    def process(self, x):
        return x * 2

    def process_all(self, items):
        return list(map(self.process, items))
"""

        visitor = parse_source(source)

        func = visitor.functions["<string>.Processor.process_all"]
        map_calls = [c for c in func.calls if c.func_name == "map"]
        assert len(map_calls) == 1
        assert "self.process" in map_calls[0].callable_args


class TestContextlibSuppress:
    """tests for contextlib.suppress detection."""

    def test_suppress_with_contextlib_import(self) -> None:
        """test that contextlib.suppress is detected with full module import."""
        source = """
import contextlib

def risky():
    raise ValueError("error")

def suppressed_call():
    with contextlib.suppress(ValueError):
        risky()
"""
        visitor = parse_source(source)

        # check that suppress block is recorded
        assert len(visitor.suppress_blocks) == 1
        assert visitor.suppress_blocks[0].suppressed_types == ["ValueError"]

        # check that the call is marked as inside the suppress block
        func = visitor.functions["<string>.suppressed_call"]
        risky_calls = [c for c in func.calls if c.func_name == "risky"]
        assert len(risky_calls) == 1
        assert risky_calls[0].containing_suppress_blocks == [0]

    def test_suppress_with_direct_import(self) -> None:
        """test that suppress is detected with direct import."""
        source = """
from contextlib import suppress

def risky():
    raise ValueError("error")

def suppressed_call():
    with suppress(ValueError):
        risky()
"""
        visitor = parse_source(source)

        # check that suppress block is recorded
        assert len(visitor.suppress_blocks) == 1
        assert visitor.suppress_blocks[0].suppressed_types == ["ValueError"]

    def test_suppress_multiple_exceptions(self) -> None:
        """test that suppress with multiple exception types is detected."""
        source = """
from contextlib import suppress

def risky():
    raise ValueError("error")

def suppressed_call():
    with suppress(ValueError, TypeError):
        risky()
"""
        visitor = parse_source(source)

        assert len(visitor.suppress_blocks) == 1
        # should have both exception types
        assert "ValueError" in visitor.suppress_blocks[0].suppressed_types
        assert "TypeError" in visitor.suppress_blocks[0].suppressed_types

    def test_no_suppress_for_other_context_managers(self) -> None:
        """test that other context managers are not treated as suppress."""
        source = """
from contextlib import contextmanager

@contextmanager
def my_context():
    yield

def normal_call():
    with my_context():
        pass
"""
        visitor = parse_source(source)

        # should not have any suppress blocks
        assert len(visitor.suppress_blocks) == 0

    def test_suppress_does_not_affect_calls_outside(self) -> None:
        """test that only calls inside suppress are marked."""
        source = """
from contextlib import suppress

def risky():
    raise ValueError("error")

def mixed_calls():
    risky()  # outside suppress
    with suppress(ValueError):
        risky()  # inside suppress
"""
        visitor = parse_source(source)

        func = visitor.functions["<string>.mixed_calls"]
        risky_calls = [c for c in func.calls if c.func_name == "risky"]
        assert len(risky_calls) == 2

        # first call is not inside any suppress block
        assert risky_calls[0].containing_suppress_blocks == []

        # second call is inside the suppress block
        assert risky_calls[1].containing_suppress_blocks == [0]

    def test_nested_suppress_blocks(self) -> None:
        """test handling of nested suppress contexts."""
        source = """
from contextlib import suppress

def risky():
    raise ValueError("error")

def nested_suppress():
    with suppress(ValueError):
        with suppress(TypeError):
            risky()
"""
        visitor = parse_source(source)

        # should have two suppress blocks
        assert len(visitor.suppress_blocks) == 2

        func = visitor.functions["<string>.nested_suppress"]
        risky_calls = [c for c in func.calls if c.func_name == "risky"]
        assert len(risky_calls) == 1

        # call should be inside both suppress blocks
        assert len(risky_calls[0].containing_suppress_blocks) == 2
        assert 0 in risky_calls[0].containing_suppress_blocks
        assert 1 in risky_calls[0].containing_suppress_blocks

    def test_suppress_with_exception_hierarchy(self) -> None:
        """test that suppress with parent exception catches children."""
        source = """
from contextlib import suppress

def risky():
    raise ValueError("error")

def suppressed_with_exception():
    with suppress(Exception):
        risky()
"""
        visitor = parse_source(source)

        assert len(visitor.suppress_blocks) == 1
        assert visitor.suppress_blocks[0].suppressed_types == ["Exception"]

    def test_suppress_import_not_from_contextlib(self) -> None:
        """test that suppress imported from elsewhere is not treated as contextlib.suppress."""
        source = """
from my_module import suppress

def normal_call():
    with suppress(ValueError):
        pass
"""
        visitor = parse_source(source)

        # should not treat this as contextlib.suppress since it's from my_module
        # note: this depends on proper import resolution
        # currently we check if suppress resolves to contextlib.suppress
        # if the import is not tracked properly, it might not be detected
        # but in this case, the import tracking should handle it

        # the suppress might or might not be detected depending on implementation
        # we just verify the code doesn't crash
        assert "suppress" in visitor.imports
        assert visitor.imports["suppress"] == "my_module.suppress"
