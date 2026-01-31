"""
raiseattention: static exception flow analyser for python.

this package provides tools for analysing python code to detect
unhandled exceptions, including lsp server integration for
real-time editor feedback.
"""

from __future__ import annotations

from .analyzer import AnalysisResult, Diagnostic, ExceptionAnalyzer
from .config import AnalysisConfig, CacheConfig, Config, LspConfig

__version__ = "0.1.0"
__all__ = [
    "AnalysisResult",
    "Diagnostic",
    "ExceptionAnalyzer",
    "AnalysisConfig",
    "CacheConfig",
    "Config",
    "LspConfig",
]
