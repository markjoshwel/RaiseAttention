"""test fixtures and utilities for raiseattention.

this package contains synthetic codebases, mock objects, and test utilities
for comprehensive testing of the exception analyzer.
"""

from __future__ import annotations

# import commonly used fixtures for convenience
from .code_samples import (
    create_async_exceptions_file,
    create_complex_nesting_file,
    create_custom_exceptions_file,
    create_exception_chaining_file,
    create_handled_exception_file,
    create_library_mock_file,
    create_mixed_scenario_file,
    create_synthetic_codebase,
    create_unhandled_exception_file,
)

__all__ = [
    "create_async_exceptions_file",
    "create_complex_nesting_file",
    "create_custom_exceptions_file",
    "create_exception_chaining_file",
    "create_handled_exception_file",
    "create_library_mock_file",
    "create_mixed_scenario_file",
    "create_synthetic_codebase",
    "create_unhandled_exception_file",
]
