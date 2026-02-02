"""
standardstubber: cpython standard library exception stub generator.

this package provides tools to extract exception signatures from cpython's
c extension modules and generate .pyras stub files for raiseattention.
"""

from __future__ import annotations

from .models import (
    Confidence,
    FunctionStub,
    StubFile,
    StubLookupResult,
    StubMetadata,
)
from .resolver import StubResolver, StubSource, create_default_resolver

__all__ = [
    "Confidence",
    "FunctionStub",
    "StubFile",
    "StubLookupResult",
    "StubMetadata",
    "StubResolver",
    "StubSource",
    "create_default_resolver",
]
