"""code samples for testing exception detection.

this module provides synthetic codebases and sample files for testing
the exception analyzer, including:
- unhandled exceptions that should be detected
- caught exceptions that should not be flagged
- edge cases and complex scenarios
"""

from __future__ import annotations

from pathlib import Path


def create_unhandled_exception_file(base_path: Path) -> Path:
    """
    create a file with unhandled exceptions that should be detected.

    arguments:
        `base_path: Path`
            directory to create the file in

    returns: `Path`
        path to the created file
    """
    file_path = base_path / "unhandled_exceptions.py"

    code = '''
def risky_function():
    """a function that raises an exception."""
    raise ValueError("something went wrong")

def caller():
    """calls risky_function without handling the exception."""
    risky_function()  # should be flagged - unhandled ValueError

def another_risky():
    """another risky function."""
    if True:
        raise RuntimeError("runtime error")
    return 42

def caller_of_another():
    """calls another_risky without handling."""
    result = another_risky()  # should be flagged - unhandled RuntimeError
    return result
'''

    _ = file_path.write_text(code)
    return file_path


def create_handled_exception_file(base_path: Path) -> Path:
    """
    create a file with properly handled exceptions.

    arguments:
        `base_path: Path`
            directory to create the file in

    returns: `Path`
        path to the created file
    """
    file_path = base_path / "handled_exceptions.py"

    code = '''
def risky_function():
    """a function that raises an exception."""
    raise ValueError("something went wrong")

def safe_caller():
    """calls risky_function with proper exception handling."""
    try:
        risky_function()
    except ValueError:
        print("caught the error")
    return 42

def another_risky():
    """another risky function."""
    raise RuntimeError("runtime error")

def another_safe_caller():
    """calls another_risky with handling."""
    try:
        result = another_risky()
    except RuntimeError as e:
        print(f"caught: {e}")
        result = None
    return result

def multi_exception_handler():
    """handles multiple exception types."""
    try:
        risky_function()
        another_risky()
    except (ValueError, RuntimeError) as e:
        print(f"caught: {e}")

def nested_try_except():
    """nested try-except blocks."""
    try:
        try:
            risky_function()
        except ValueError:
            print("inner catch")
    except Exception:
        print("outer catch")
'''

    _ = file_path.write_text(code)
    return file_path


def create_complex_nesting_file(base_path: Path) -> Path:
    """
    create a file with complex exception handling scenarios.

    arguments:
        `base_path: Path`
            directory to create the file in

    returns: `Path`
        path to the created file
    """
    file_path = base_path / "complex_nesting.py"

    code = '''
def level_one():
    """first level of nesting."""
    raise ValueError("level 1")

def level_two():
    """second level - calls level_one."""
    level_one()  # propagates ValueError

def level_three():
    """third level - calls level_two."""
    level_two()  # propagates ValueError transitively

def deep_call_unhandled():
    """deep call stack without handling."""
    level_three()  # should flag transitive ValueError

def deep_call_handled():
    """deep call stack with handling at top."""
    try:
        level_three()
    except ValueError:
        print("caught at top level")

def partial_handling():
    """handles at intermediate level."""
    try:
        level_two()
    except ValueError:
        print("caught at level 2")

def conditional_raise(flag: bool) -> int:
    """conditionally raises exception."""
    if flag:
        raise ValueError("conditional")
    return 42

def conditional_caller():
    """calls conditional without handling."""
    result = conditional_raise(True)  # might raise
    return result

def loop_with_exception():
    """exception in loop."""
    for i in range(10):
        if i == 5:
            raise ValueError("loop error")

def loop_caller():
    """calls loop function without handling."""
    loop_with_exception()  # should flag
'''

    _ = file_path.write_text(code)
    return file_path


def create_exception_chaining_file(base_path: Path) -> Path:
    """
    create a file with exception chaining (raise ... from ...).

    arguments:
        `base_path: Path`
            directory to create the file in

    returns: `Path`
        path to the created file
    """
    file_path = base_path / "exception_chaining.py"

    code = '''
def original_error():
    """raises original error."""
    raise ValueError("original")

def wrapper_with_chain():
    """wraps exception with chaining."""
    try:
        original_error()
    except ValueError as e:
        raise RuntimeError("wrapped") from e

def wrapper_without_chain():
    """wraps exception without explicit chaining."""
    try:
        original_error()
    except ValueError:
        raise RuntimeError("wrapped implicitly")

def caller_of_chained():
    """calls chained exception without handling."""
    wrapper_with_chain()  # should flag RuntimeError

def caller_handling_both():
    """handles both exception types."""
    try:
        wrapper_with_chain()
    except (RuntimeError, ValueError):
        print("caught both")
'''

    _ = file_path.write_text(code)
    return file_path


def create_custom_exceptions_file(base_path: Path) -> Path:
    """
    create a file with custom exception classes.

    arguments:
        `base_path: Path`
            directory to create the file in

    returns: `Path`
        path to the created file
    """
    file_path = base_path / "custom_exceptions.py"

    code = '''
class BusinessError(Exception):
    """custom business logic error."""
    pass

class ValidationError(BusinessError):
    """validation error subclass."""
    pass

class DatabaseError(Exception):
    """database error."""
    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.code = code

def raise_business_error():
    """raises custom business error."""
    raise BusinessError("business logic failed")

def raise_validation_error():
    """raises validation error."""
    raise ValidationError("invalid input")

def raise_database_error():
    """raises database error."""
    raise DatabaseError("connection failed", 500)

def caller_of_business():
    """calls business error without handling."""
    raise_business_error()  # should flag BusinessError

def caller_handling_parent():
    """handles parent exception class."""
    try:
        raise_validation_error()
    except BusinessError:
        print("caught via parent")

def caller_handling_specific():
    """handles specific exception class."""
    try:
        raise_database_error()
    except DatabaseError as e:
        print(f"caught: {e} (code: {e.code})")
'''

    _ = file_path.write_text(code)
    return file_path


def create_synthetic_codebase(base_path: Path) -> dict[str, Path]:
    """
    create a complete synthetic codebase for testing.

    this creates multiple files with various exception scenarios.

    arguments:
        `base_path: Path`
            directory to create the codebase in

    returns: `dict[str, Path]`
        mapping of file names to paths
    """
    base_path.mkdir(parents=True, exist_ok=True)

    files = {
        "unhandled": create_unhandled_exception_file(base_path),
        "handled": create_handled_exception_file(base_path),
        "complex": create_complex_nesting_file(base_path),
        "chaining": create_exception_chaining_file(base_path),
        "custom": create_custom_exceptions_file(base_path),
    }

    # create an __init__.py to make it a package
    _ = (base_path / "__init__.py").write_text("")

    return files


def create_mixed_scenario_file(base_path: Path) -> Path:
    """
    create a file with both handled and unhandled exceptions.

    useful for testing that only unhandled ones are flagged.

    arguments:
        `base_path: Path`
            directory to create the file in

    returns: `Path`
        path to the created file
    """
    file_path = base_path / "mixed_scenarios.py"

    code = '''
def always_raises():
    """always raises."""
    raise ValueError("always")

def sometimes_raises(condition: bool):
    """sometimes raises."""
    if condition:
        raise RuntimeError("sometimes")
    return 42

def good_caller():
    """properly handles exceptions."""
    try:
        always_raises()
    except ValueError:
        print("handled")

def bad_caller():
    """doesn't handle exceptions - should be flagged."""
    always_raises()  # flag: unhandled ValueError

def mixed_caller(condition: bool):
    """handles one but not the other."""
    try:
        if condition:
            always_raises()  # handled below
        else:
            sometimes_raises(True)  # not handled!
    except ValueError:
        print("caught value error")
    # runtime error from sometimes_raises is NOT caught

def another_bad_caller():
    """another unhandled case."""
    x = always_raises()  # flag: unhandled ValueError
    print(x)
'''

    _ = file_path.write_text(code)
    return file_path


def create_library_mock_file(base_path: Path) -> Path:
    """
    create a mock library file with known exception signatures.

    useful for testing external library exception detection.

    arguments:
        `base_path: Path`
            directory to create the file in

    returns: `Path`
        path to the created file
    """
    file_path = base_path / "mock_library.py"

    code = '''
"""mock library for testing external exception detection."""

class MockLibraryError(Exception):
    """base exception for mock library."""
    pass

class ConnectionError(MockLibraryError):
    """connection failed."""
    pass

class AuthenticationError(MockLibraryError):
    """authentication failed."""
    pass

def connect_to_service(url: str) -> None:
    """connect to external service - raises ConnectionError."""
    raise ConnectionError(f"failed to connect to {url}")

def authenticate(username: str, password: str) -> str:
    """authenticate user - raises AuthenticationError."""
    raise AuthenticationError("invalid credentials")

def fetch_data(query: str) -> list[dict]:
    """fetch data - raises MockLibraryError."""
    raise MockLibraryError("query failed")

def safe_operation() -> str:
    """an operation that doesn't raise."""
    return "success"
'''

    _ = file_path.write_text(code)
    return file_path


def create_async_exceptions_file(base_path: Path) -> Path:
    """
    create a file with async/await exception scenarios.

    arguments:
        `base_path: Path`
            directory to create the file in

    returns: `Path`
        path to the created file
    """
    file_path = base_path / "async_exceptions.py"

    code = '''
import asyncio

async def async_risky():
    """async function that raises."""
    await asyncio.sleep(0.1)
    raise ValueError("async error")

async def async_caller_unhandled():
    """calls async_risky without handling."""
    await async_risky()  # should flag

async def async_caller_handled():
    """calls async_risky with handling."""
    try:
        await async_risky()
    except ValueError:
        print("caught")

async def async_with_result() -> int:
    """async that sometimes returns, sometimes raises."""
    if False:
        return 42
    raise RuntimeError("failed")

async def caller_of_result():
    """calls async_with_result without handling."""
    result = await async_with_result()  # should flag
    return result
'''

    _ = file_path.write_text(code)
    return file_path


def create_decorator_wrapper_file(base_path: Path) -> Path:
    """
    create a file with decorator wrapper patterns.

    tests that decorators are detected and tracked on functions.

    arguments:
        `base_path: Path`
            directory to create the file in

    returns: `Path`
        path to the created file
    """
    file_path = base_path / "decorator_wrappers.py"

    code = '''
from functools import lru_cache, wraps

def my_decorator(func):
    """a simple decorator."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

def logging_decorator(level: str):
    """a decorator with arguments."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            print(f"[{level}] calling {func.__name__}")
            return func(*args, **kwargs)
        return wrapper
    return decorator

@my_decorator
def decorated_risky():
    """decorated function that raises."""
    raise ValueError("decorated error")

@lru_cache(maxsize=128)
def cached_function(x: int) -> int:
    """cached function that may raise."""
    if x < 0:
        raise ValueError("negative input")
    return x * 2

@logging_decorator("DEBUG")
@my_decorator
def multi_decorated():
    """function with multiple decorators."""
    raise RuntimeError("multi-decorated error")

class MyClass:
    @staticmethod
    def static_risky():
        """static method that raises."""
        raise TypeError("static error")

    @classmethod
    def class_risky(cls):
        """class method that raises."""
        raise KeyError("class error")

    @property
    def risky_property(self):
        """property that raises."""
        raise AttributeError("property error")
'''

    _ = file_path.write_text(code)
    return file_path


def create_hof_callable_file(base_path: Path) -> Path:
    """
    create a file with higher-order function patterns.

    tests detection of callables passed to map, filter, sorted, etc.

    arguments:
        `base_path: Path`
            directory to create the file in

    returns: `Path`
        path to the created file
    """
    file_path = base_path / "hof_callables.py"

    code = '''
def risky_transform(x: int) -> int:
    """transform that may raise."""
    if x < 0:
        raise ValueError("negative value")
    return x * 2

def risky_predicate(x: int) -> bool:
    """predicate that may raise."""
    if x == 0:
        raise ZeroDivisionError("cannot check zero")
    return x > 0

def risky_key(item: dict) -> str:
    """key function that may raise."""
    if "key" not in item:
        raise KeyError("missing key")
    return item["key"]

def uses_map_with_risky():
    """uses map with a function that may raise."""
    data = [1, -2, 3]
    result = list(map(risky_transform, data))
    return result

def uses_filter_with_risky():
    """uses filter with a predicate that may raise."""
    data = [1, 0, 3]
    result = list(filter(risky_predicate, data))
    return result

def uses_sorted_with_key():
    """uses sorted with a key function that may raise."""
    data = [{"key": "b"}, {"no_key": "a"}]
    result = sorted(data, key=risky_key)
    return result

def uses_map_with_lambda():
    """uses map with a lambda - lambda exceptions not tracked."""
    data = [1, 2, 3]
    result = list(map(lambda x: x / 0, data))  # lambda that raises
    return result

def uses_min_with_key():
    """uses min with a key function that may raise."""
    data = [{"key": "b"}, {"key": "a"}]
    result = min(data, key=risky_key)
    return result

def uses_max_with_key():
    """uses max with a key function that may raise."""
    data = [{"key": "b"}, {"key": "a"}]
    result = max(data, key=risky_key)
    return result

class Processor:
    def process_item(self, x: int) -> int:
        """method that may raise."""
        if x < 0:
            raise ValueError("negative")
        return x

    def process_all(self, items: list[int]) -> list[int]:
        """uses map with a method reference."""
        return list(map(self.process_item, items))
'''

    _ = file_path.write_text(code)
    return file_path


def create_callable_passing_file(base_path: Path) -> Path:
    """
    create a file with callable passing patterns.

    tests detection of functions passed as arguments to other functions.

    arguments:
        `base_path: Path`
            directory to create the file in

    returns: `Path`
        path to the created file
    """
    file_path = base_path / "callable_passing.py"

    code = '''
from typing import Callable

def risky_callback() -> None:
    """callback that raises."""
    raise RuntimeError("callback error")

def safe_callback() -> None:
    """callback that doesn't raise."""
    print("safe")

def invoke_callback(callback: Callable[[], None]) -> None:
    """invokes a callback function."""
    callback()

def higher_order_function(func: Callable[[int], int], value: int) -> int:
    """higher-order function that invokes the passed function."""
    return func(value)

def caller_with_risky_callback():
    """passes risky callback to another function."""
    invoke_callback(risky_callback)

def caller_with_safe_callback():
    """passes safe callback to another function."""
    invoke_callback(safe_callback)

def risky_int_func(x: int) -> int:
    """int function that may raise."""
    if x < 0:
        raise ValueError("negative")
    return x * 2

def caller_with_hof():
    """uses higher-order function with risky callback."""
    result = higher_order_function(risky_int_func, -1)
    return result

def caller_with_lambda_hof():
    """uses higher-order function with a lambda."""
    result = higher_order_function(lambda x: x / 0, 1)
    return result

class EventHandler:
    def __init__(self, handler: Callable[[], None]):
        self.handler = handler

    def trigger(self):
        """triggers the stored handler."""
        self.handler()

def setup_risky_handler():
    """sets up an event handler with a risky callback."""
    handler = EventHandler(risky_callback)
    handler.trigger()
'''

    _ = file_path.write_text(code)
    return file_path


def create_native_code_test_file(base_path: Path) -> Path:
    """
    create a file that uses native/c extension modules.

    tests detection of calls to c extensions like _json, _csv, etc.

    arguments:
        `base_path: Path`
            directory to create the file in

    returns: `Path`
        path to the created file
    """
    file_path = base_path / "native_code_usage.py"

    code = '''
import json
import math
import re

def parse_json(data: str) -> dict:
    """parses json data - calls into c extension."""
    return json.loads(data)

def compute_sqrt(x: float) -> float:
    """computes square root - math module has c parts."""
    return math.sqrt(x)

def match_pattern(pattern: str, text: str) -> bool:
    """matches regex pattern - re module has c parts."""
    return bool(re.match(pattern, text))

def caller_of_json():
    """calls function that uses json parsing."""
    result = parse_json('{"key": "value"}')
    return result

def caller_of_math():
    """calls function that uses math."""
    result = compute_sqrt(16.0)
    return result

def caller_of_regex():
    """calls function that uses regex."""
    result = match_pattern(r"\\d+", "123")
    return result
'''

    _ = file_path.write_text(code)
    return file_path
