"""
raiseattention: static exception flow analyser for python.

this package provides tools for analysing python code to detect
unhandled exceptions, including lsp server integration for
real-time editor feedback. it can analyse both local code and
external modules (stdlib and third-party packages).
"""

from __future__ import annotations

from .analyser import AnalysisResult, Diagnostic, ExceptionAnalyser
from .config import AnalysisConfig, CacheConfig, Config, LspConfig
from .external_analyser import ExternalAnalyser, ExternalModuleInfo, is_stdlib_module

__version__ = "0.1.0"
__all__ = [
    "AnalysisResult",
    "Diagnostic",
    "ExceptionAnalyser",
    "ExternalAnalyser",
    "ExternalModuleInfo",
    "AnalysisConfig",
    "CacheConfig",
    "Config",
    "LspConfig",
    "is_stdlib_module",
]
