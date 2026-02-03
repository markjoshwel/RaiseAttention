"""
error propagation pattern detection for cpython c source.

provides pattern detectors for common cpython error handling idioms:
- goto-based cleanup patterns
- null check propagation
- macro error detection
- error clearing detection
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clang.cindex import Cursor

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """types of error propagation patterns."""

    GOTO_ERROR = auto()
    NULL_CHECK = auto()
    ERROR_CODE_CHECK = auto()
    MACRO_ERROR = auto()
    PYOBJECT_CALL = auto()
    ERROR_CLEAR = auto()


@dataclass(slots=True)
class PropagationSite:
    """
    a site where error propagation occurs.

    attributes:
        `callee: str`
            name of the called function
        `pattern: PatternType`
            type of pattern detected
        `line: int`
            source line number
        `propagates: bool`
            true if error is propagated, false if handled
    """

    callee: str
    pattern: PatternType
    line: int
    propagates: bool = True


# cpython error macros that propagate errors
CPYTHON_ERROR_MACROS: frozenset[str] = frozenset(
    {
        # return macros
        "Py_RETURN_NONE",
        "Py_RETURN_TRUE",
        "Py_RETURN_FALSE",
        "Py_RETURN_NOTIMPLEMENTED",
        # check macros
        "CHECK",
        "CHECK_STATUS",
        "RETURN_IF_ERROR",
        "FAIL_IF",
        # common patterns in specific modules
        "ENSURE_INITIALIZED",
        "ENTER_SQLITE",
    }
)

# pyobject call functions that can propagate any exception
PYOBJECT_CALL_FUNCS: frozenset[str] = frozenset(
    {
        "PyObject_Call",
        "PyObject_CallFunction",
        "PyObject_CallFunctionObjArgs",
        "PyObject_CallMethod",
        "PyObject_CallMethodObjArgs",
        "PyObject_CallNoArgs",
        "PyObject_CallOneArg",
        "PyObject_CallObject",
        "PyObject_Vectorcall",
        "PyObject_VectorcallMethod",
        "_PyObject_Call",
        "_PyObject_CallMethod",
        "_PyObject_CallMethodId",
        "_PyObject_CallNoArg",
        "_PyObject_FastCall",
        # type calls
        "PyType_GenericNew",
        "PyType_GenericAlloc",
    }
)

# functions that clear/handle errors (not propagate)
ERROR_CLEAR_FUNCS: frozenset[str] = frozenset(
    {
        "PyErr_Clear",
        "PyErr_Fetch",
        "PyErr_NormalizeException",
        "PyErr_GetExcInfo",
        "PyErr_SetExcInfo",
        "_PyErr_Clear",
        "_PyErr_Fetch",
    }
)

# common error label names (lowercase)
ERROR_LABEL_NAMES: frozenset[str] = frozenset(
    {"error", "fail", "failure", "err", "cleanup", "done", "exit", "bail"}
)


@dataclass(slots=True)
class GotoInfo:
    """info about a goto statement for quick lookup."""

    label_name: str
    line: int


@dataclass
class PatternDetector:
    """
    detects error propagation patterns in c code.

    caches analysis results for performance.
    """

    # cache for goto label analysis: label_name -> is_error_label
    _goto_labels: dict[str, bool] = field(default_factory=dict)

    def detect_goto_error_fast(
        self,
        call_line: int,
        callee_name: str,
        goto_after_call: dict[int, list[str]],
    ) -> PropagationSite | None:
        """
        fast goto-based error propagation detection using pre-collected data.

        arguments:
            `call_line: int`
                line number of the call
            `callee_name: str`
                name of the called function
            `goto_after_call: dict[int, list[str]]`
                mapping from line -> list of goto label names that follow

        returns: `PropagationSite | None`
            propagation site if pattern detected
        """
        # check lines [call_line, call_line+5] for gotos to error labels
        for line in range(call_line, call_line + 6):
            labels = goto_after_call.get(line, [])
            for label_name in labels:
                if self._is_error_label_name(label_name):
                    return PropagationSite(
                        callee=callee_name,
                        pattern=PatternType.GOTO_ERROR,
                        line=call_line,
                        propagates=True,
                    )
        return None

    def _is_error_label_name(self, label_name: str) -> bool:
        """check if label name indicates error handling (fast, no AST walk)."""
        if label_name in self._goto_labels:
            return self._goto_labels[label_name]

        name_lower = label_name.lower()
        is_error = any(en in name_lower for en in ERROR_LABEL_NAMES)
        self._goto_labels[label_name] = is_error
        return is_error

    def detect_pyobject_call(self, call_cursor: "Cursor") -> PropagationSite | None:
        """
        detect PyObject_Call* that can propagate any exception.

        arguments:
            `call_cursor: Cursor`
                call expression cursor

        returns: `PropagationSite | None`
            propagation site if detected
        """
        call_name = call_cursor.spelling
        if call_name in PYOBJECT_CALL_FUNCS:
            return PropagationSite(
                callee=call_name,
                pattern=PatternType.PYOBJECT_CALL,
                line=call_cursor.location.line,
                propagates=True,
            )
        return None

    def detect_error_clear(self, call_cursor: "Cursor") -> PropagationSite | None:
        """
        detect error clearing calls (errors handled, not propagated).

        arguments:
            `call_cursor: Cursor`
                call expression cursor

        returns: `PropagationSite | None`
            propagation site with propagates=False if detected
        """
        call_name = call_cursor.spelling
        if call_name in ERROR_CLEAR_FUNCS:
            return PropagationSite(
                callee=call_name,
                pattern=PatternType.ERROR_CLEAR,
                line=call_cursor.location.line,
                propagates=False,
            )
        return None


def collect_goto_map(func_cursor: "Cursor") -> dict[int, list[str]]:
    """
    collect goto statements and map them by line number.

    arguments:
        `func_cursor: Cursor`
            function definition cursor

    returns: `dict[int, list[str]]`
        mapping from line number to list of goto label names
    """
    from clang.cindex import CursorKind

    goto_map: dict[int, list[str]] = {}
    for child in func_cursor.walk_preorder():
        if child.kind == CursorKind.GOTO_STMT:
            line = child.location.line
            label = child.spelling
            if line not in goto_map:
                goto_map[line] = []
            goto_map[line].append(label)
    return goto_map
