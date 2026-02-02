"""
cpython c source analyser using libclang.

extracts exception signatures from cpython's c extension modules
by parsing c source code and identifying PyErr_* function calls.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from clang.cindex import (
    Config,
    Cursor,
    CursorKind,
    Index,
    TranslationUnit,
    TypeKind,
)

from .models import Confidence, FunctionStub

logger = logging.getLogger(__name__)


# mapping from PyExc_* c names to python exception names
PYEXC_MAP: Final[dict[str, str]] = {
    "PyExc_BaseException": "BaseException",
    "PyExc_BaseExceptionGroup": "BaseExceptionGroup",
    "PyExc_Exception": "Exception",
    "PyExc_ExceptionGroup": "ExceptionGroup",
    "PyExc_GeneratorExit": "GeneratorExit",
    "PyExc_KeyboardInterrupt": "KeyboardInterrupt",
    "PyExc_SystemExit": "SystemExit",
    "PyExc_ArithmeticError": "ArithmeticError",
    "PyExc_FloatingPointError": "FloatingPointError",
    "PyExc_OverflowError": "OverflowError",
    "PyExc_ZeroDivisionError": "ZeroDivisionError",
    "PyExc_AssertionError": "AssertionError",
    "PyExc_AttributeError": "AttributeError",
    "PyExc_BufferError": "BufferError",
    "PyExc_EOFError": "EOFError",
    "PyExc_ImportError": "ImportError",
    "PyExc_ModuleNotFoundError": "ModuleNotFoundError",
    "PyExc_LookupError": "LookupError",
    "PyExc_IndexError": "IndexError",
    "PyExc_KeyError": "KeyError",
    "PyExc_MemoryError": "MemoryError",
    "PyExc_NameError": "NameError",
    "PyExc_UnboundLocalError": "UnboundLocalError",
    "PyExc_OSError": "OSError",
    "PyExc_BlockingIOError": "BlockingIOError",
    "PyExc_ChildProcessError": "ChildProcessError",
    "PyExc_ConnectionError": "ConnectionError",
    "PyExc_BrokenPipeError": "BrokenPipeError",
    "PyExc_ConnectionAbortedError": "ConnectionAbortedError",
    "PyExc_ConnectionRefusedError": "ConnectionRefusedError",
    "PyExc_ConnectionResetError": "ConnectionResetError",
    "PyExc_FileExistsError": "FileExistsError",
    "PyExc_FileNotFoundError": "FileNotFoundError",
    "PyExc_InterruptedError": "InterruptedError",
    "PyExc_IsADirectoryError": "IsADirectoryError",
    "PyExc_NotADirectoryError": "NotADirectoryError",
    "PyExc_PermissionError": "PermissionError",
    "PyExc_ProcessLookupError": "ProcessLookupError",
    "PyExc_TimeoutError": "TimeoutError",
    "PyExc_ReferenceError": "ReferenceError",
    "PyExc_RuntimeError": "RuntimeError",
    "PyExc_NotImplementedError": "NotImplementedError",
    "PyExc_RecursionError": "RecursionError",
    "PyExc_StopAsyncIteration": "StopAsyncIteration",
    "PyExc_StopIteration": "StopIteration",
    "PyExc_SyntaxError": "SyntaxError",
    "PyExc_IndentationError": "IndentationError",
    "PyExc_TabError": "TabError",
    "PyExc_SystemError": "SystemError",
    "PyExc_TypeError": "TypeError",
    "PyExc_ValueError": "ValueError",
    "PyExc_UnicodeError": "UnicodeError",
    "PyExc_UnicodeDecodeError": "UnicodeDecodeError",
    "PyExc_UnicodeEncodeError": "UnicodeEncodeError",
    "PyExc_UnicodeTranslateError": "UnicodeTranslateError",
    # warnings
    "PyExc_Warning": "Warning",
    "PyExc_BytesWarning": "BytesWarning",
    "PyExc_DeprecationWarning": "DeprecationWarning",
    "PyExc_EncodingWarning": "EncodingWarning",
    "PyExc_FutureWarning": "FutureWarning",
    "PyExc_ImportWarning": "ImportWarning",
    "PyExc_PendingDeprecationWarning": "PendingDeprecationWarning",
    "PyExc_ResourceWarning": "ResourceWarning",
    "PyExc_RuntimeWarning": "RuntimeWarning",
    "PyExc_SyntaxWarning": "SyntaxWarning",
    "PyExc_UnicodeWarning": "UnicodeWarning",
    "PyExc_UserWarning": "UserWarning",
    # legacy aliases
    "PyExc_EnvironmentError": "OSError",
    "PyExc_IOError": "OSError",
}


# pyerr functions that set an exception
PYERR_SETTERS: Final[frozenset[str]] = frozenset(
    {
        "PyErr_SetString",
        "PyErr_SetObject",
        "PyErr_Format",
        "PyErr_FormatV",
        "PyErr_SetNone",
    }
)


# pyerr functions that set specific exception types
PYERR_SPECIFIC: Final[dict[str, str]] = {
    "PyErr_NoMemory": "MemoryError",
    "PyErr_SetFromErrno": "OSError",
    "PyErr_SetFromErrnoWithFilename": "OSError",
    "PyErr_SetFromErrnoWithFilenameObject": "OSError",
    "PyErr_SetFromErrnoWithFilenameObjects": "OSError",
    "PyErr_SetFromWindowsErr": "OSError",
    "PyErr_SetFromWindowsErrWithFilename": "OSError",
    "PyErr_SetExcFromWindowsErr": "OSError",
    "PyErr_SetExcFromWindowsErrWithFilename": "OSError",
    "PyErr_SetExcFromWindowsErrWithFilenameObject": "OSError",
    "PyErr_SetExcFromWindowsErrWithFilenameObjects": "OSError",
    "PyErr_BadArgument": "TypeError",
    "PyErr_BadInternalCall": "SystemError",
}


@dataclass
class ParsedFunction:
    """
    parsed c function with exception information.

    attributes:
        `c_name: str`
            c function name
        `py_name: str`
            python-visible name (from PyMethodDef)
        `raises: set[str]`
            exception types this function may raise
        `has_arg_parsing: bool`
            whether function uses PyArg_Parse*
        `has_clinic: bool`
            whether function uses argument clinic
    """

    c_name: str
    py_name: str = ""
    raises: set[str] = field(default_factory=set)
    has_arg_parsing: bool = False
    has_clinic: bool = False


@dataclass
class CPythonAnalyser:
    """
    analyser for cpython c extension modules.

    uses libclang to parse c source files and extract exception signatures
    from PyErr_* function calls.

    attributes:
        `cpython_root: Path`
            root directory of cpython source tree
    """

    cpython_root: Path
    _index: Index = field(init=False, repr=False)
    _functions: dict[str, ParsedFunction] = field(default_factory=dict, repr=False)
    _method_defs: dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        """initialise clang index."""
        self._index = Index.create()

    def parse_module(self, c_file: Path) -> TranslationUnit:
        """
        parse a cpython c module file.

        arguments:
            `c_file: Path`
                path to .c file

        returns: `TranslationUnit`
            parsed translation unit

        raises:
            `FileNotFoundError`
                if file does not exist
            `RuntimeError`
                if parsing fails
        """
        if not c_file.exists():
            raise FileNotFoundError(f"c file not found: {c_file}")

        args: list[str] = [
            f"-I{self.cpython_root / 'Include'}",
            f"-I{self.cpython_root / 'Include' / 'internal'}",
            f"-I{self.cpython_root / 'Modules'}",
            f"-I{self.cpython_root / 'PC'}",
            "-DPy_BUILD_CORE",
            "-DPy_BUILD_CORE_MODULE",
            # suppress diagnostics for missing includes
            "-Wno-everything",
        ]

        tu = self._index.parse(
            str(c_file),
            args=args,
            options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD,
        )

        if tu is None:
            raise RuntimeError(f"failed to parse: {c_file}")

        return tu

    def find_exported_functions(self, tu: TranslationUnit) -> dict[str, str]:
        """
        find PyMethodDef arrays and map python names to c function names.

        arguments:
            `tu: TranslationUnit`
                parsed translation unit

        returns: `dict[str, str]`
            mapping from python names to c function names
        """
        exports: dict[str, str] = {}

        for cursor in tu.cursor.walk_preorder():
            # look for PyMethodDef array declarations
            if cursor.kind == CursorKind.VAR_DECL:
                type_spelling = cursor.type.spelling
                # check for PyMethodDef arrays - may be spelled differently
                if "PyMethodDef" in type_spelling or "MethodDef" in cursor.spelling.lower():
                    logger.debug(
                        "found potential method def: %s (type=%s)",
                        cursor.spelling,
                        type_spelling,
                    )
                    if "[" in type_spelling or type_spelling.endswith("[]"):
                        # parse the array initialiser
                        exports.update(self._parse_method_def_array(cursor))

        # also search by variable name patterns (fallback)
        if not exports:
            for cursor in tu.cursor.walk_preorder():
                if cursor.kind == CursorKind.VAR_DECL:
                    name = cursor.spelling.lower()
                    if name.endswith("_methods") or name.endswith("methods"):
                        logger.debug(
                            "found methods array by name: %s (type=%s)",
                            cursor.spelling,
                            cursor.type.spelling,
                        )
                        exports.update(self._parse_method_def_array(cursor))

        self._method_defs.update(exports)
        return exports

    def _parse_method_def_array(self, var_cursor: Cursor) -> dict[str, str]:
        """
        parse a PyMethodDef array initialiser.

        arguments:
            `var_cursor: Cursor`
                variable declaration cursor

        returns: `dict[str, str]`
            mapping from python names to c function names
        """
        methods: dict[str, str] = {}

        for child in var_cursor.get_children():
            if child.kind == CursorKind.INIT_LIST_EXPR:
                # iterate over each {name, func, flags, doc} entry
                for item in child.get_children():
                    if item.kind == CursorKind.INIT_LIST_EXPR:
                        children = list(item.get_children())
                        if len(children) >= 2:
                            py_name = self._extract_string_literal(children[0])
                            c_func = self._extract_function_ref(children[1])
                            if py_name and c_func:
                                methods[py_name] = c_func

        return methods

    def _extract_string_literal(self, cursor: Cursor) -> str:
        """
        extract string value from a cursor that may contain a string literal.

        the string may be wrapped in UNEXPOSED_EXPR nodes, so we need to
        either check tokens or recursively dig through child nodes.

        arguments:
            `cursor: Cursor`
                expression cursor

        returns: `str`
            extracted string value, or empty string if not found
        """
        # direct string literal
        if cursor.kind == CursorKind.STRING_LITERAL:
            spelling = cursor.spelling
            if spelling.startswith('"') and spelling.endswith('"'):
                return spelling[1:-1]
            return spelling

        # try to extract from tokens (most reliable method)
        try:
            tokens = list(cursor.get_tokens())
            for token in tokens:
                spelling = token.spelling
                if spelling.startswith('"') and spelling.endswith('"'):
                    return spelling[1:-1]
        except Exception:
            pass

        # recursively search children (for UNEXPOSED_EXPR wrappers)
        for child in cursor.get_children():
            result = self._extract_string_literal(child)
            if result:
                return result

        return ""

    def _extract_function_ref(self, cursor: Cursor) -> str:
        """
        extract function name from a function reference cursor.

        handles various wrapping patterns:
        - CSTYLE_CAST_EXPR: (PyCFunction)func_name
        - PAREN_EXPR: ((PyCFunction)func_name)
        - UNEXPOSED_EXPR: implicit conversions
        - DECL_REF_EXPR: direct function reference

        arguments:
            `cursor: Cursor`
                expression cursor

        returns: `str`
            function name, or empty string if not found
        """
        # direct function reference
        if cursor.kind == CursorKind.DECL_REF_EXPR:
            return cursor.spelling

        # UNEXPOSED_EXPR may have the function name in its spelling
        if cursor.kind == CursorKind.UNEXPOSED_EXPR:
            # if this UNEXPOSED_EXPR has a meaningful spelling, it's the func name
            if cursor.spelling and not cursor.spelling.startswith('"'):
                # check if it looks like a function/variable name
                # (has underscores or starts with a letter)
                if cursor.spelling[0].isalpha():
                    return cursor.spelling

            # otherwise dig into children
            for child in cursor.get_children():
                result = self._extract_function_ref(child)
                if result:
                    return result

        # handle casts like (PyCFunction)func_name
        if cursor.kind == CursorKind.CSTYLE_CAST_EXPR:
            for child in cursor.get_children():
                # skip TYPE_REF children, look for expression children
                if child.kind != CursorKind.TYPE_REF:
                    result = self._extract_function_ref(child)
                    if result:
                        return result

        # handle parenthesised expressions like ((PyCFunction)func_name)
        if cursor.kind == CursorKind.PAREN_EXPR:
            for child in cursor.get_children():
                result = self._extract_function_ref(child)
                if result:
                    return result

        return ""

    def analyse_function_cursor(
        self, func_cursor: Cursor, file_content: str | None = None
    ) -> ParsedFunction:
        """
        analyse a function cursor for exception signatures.

        arguments:
            `func_cursor: Cursor`
                function definition cursor
            `file_content: str | None`
                cached file content for clinic detection

        returns: `ParsedFunction`
            analysis result with exception types
        """
        func_name = func_cursor.spelling
        result = ParsedFunction(c_name=func_name)

        # check source for argument clinic markers
        result.has_clinic = self._check_argument_clinic_cached(func_cursor, file_content)
        if result.has_clinic:
            result.raises.add("TypeError")

        # walk function body for PyErr_* calls
        for child in func_cursor.walk_preorder():
            if child.kind == CursorKind.CALL_EXPR:
                self._analyse_call(child, result)

        # if function can return null but no exceptions found, be conservative
        if not result.raises and self._can_return_null(func_cursor):
            result.raises.add("Exception")

        return result

    def _check_argument_clinic_cached(self, func_cursor: Cursor, file_content: str | None) -> bool:
        """
        check if function uses argument clinic (with cached file content).

        arguments:
            `func_cursor: Cursor`
                function cursor
            `file_content: str | None`
                cached file content, or none to read file

        returns: `bool`
            true if clinic markers found
        """
        location = func_cursor.location
        if location.file is None:
            return False

        try:
            if file_content is None:
                source_file = Path(str(location.file))
                file_content = source_file.read_text(encoding="utf-8", errors="replace")

            # look for clinic markers near function
            func_line = location.line
            lines = file_content.split("\n")

            # check 50 lines before function for clinic markers
            start = max(0, func_line - 50)
            end = min(len(lines), func_line)
            region = "\n".join(lines[start:end])

            return "[clinic start generated code]" in region

        except OSError:
            return False

    def analyse_function(self, tu: TranslationUnit, func_name: str) -> ParsedFunction:
        """
        analyse a c function for exception signatures.

        note: this method is kept for backwards compatibility but is slower
        than analyse_all_functions which does a single pass.

        arguments:
            `tu: TranslationUnit`
                parsed translation unit
            `func_name: str`
                name of function to analyse

        returns: `ParsedFunction`
            analysis result with exception types
        """
        # check cache
        if func_name in self._functions:
            return self._functions[func_name]

        result = ParsedFunction(c_name=func_name)

        # find the function definition
        func_cursor: Cursor | None = None
        for cursor in tu.cursor.walk_preorder():
            if cursor.kind == CursorKind.FUNCTION_DECL and cursor.spelling == func_name:
                # only use definition (has children), not declaration
                if cursor.is_definition():
                    func_cursor = cursor
                    break

        if func_cursor is None:
            logger.debug("function not found: %s", func_name)
            result.raises.add("Exception")  # conservative fallback
            self._functions[func_name] = result
            return result

        result = self.analyse_function_cursor(func_cursor)
        self._functions[func_name] = result
        return result

    def analyse_all_functions(
        self,
        tu: TranslationUnit,
        target_funcs: set[str],
        c_file: Path,
    ) -> dict[str, ParsedFunction]:
        """
        analyse multiple functions in a single pass over the ast.

        much faster than calling analyse_function repeatedly.

        arguments:
            `tu: TranslationUnit`
                parsed translation unit
            `target_funcs: set[str]`
                c function names to analyse
            `c_file: Path`
                path to source file for clinic detection

        returns: `dict[str, ParsedFunction]`
            mapping from function name to analysis result
        """
        results: dict[str, ParsedFunction] = {}
        found_funcs: dict[str, Cursor] = {}

        # single pass to find all target function definitions
        for cursor in tu.cursor.walk_preorder():
            if cursor.kind == CursorKind.FUNCTION_DECL:
                if cursor.spelling in target_funcs and cursor.is_definition():
                    found_funcs[cursor.spelling] = cursor

        # read file content once for clinic detection
        try:
            file_content = c_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            file_content = None

        # analyse each found function
        for func_name, func_cursor in found_funcs.items():
            result = self.analyse_function_cursor(func_cursor, file_content)
            results[func_name] = result
            self._functions[func_name] = result

        # mark not-found functions with conservative fallback
        for func_name in target_funcs - found_funcs.keys():
            logger.debug("function not found: %s", func_name)
            result = ParsedFunction(c_name=func_name)
            result.raises.add("Exception")
            results[func_name] = result
            self._functions[func_name] = result

        return results

    def _analyse_call(self, call_cursor: Cursor, result: ParsedFunction) -> None:
        """
        analyse a call expression for exception-setting behaviour.

        arguments:
            `call_cursor: Cursor`
                call expression cursor
            `result: ParsedFunction`
                result to update
        """
        call_name = call_cursor.spelling

        # check for PyErr_SetString, PyErr_Format, etc.
        if call_name in PYERR_SETTERS:
            exc_type = self._extract_exception_type(call_cursor)
            if exc_type:
                result.raises.add(exc_type)

        # check for PyErr_NoMemory, PyErr_SetFromErrno, etc.
        elif call_name in PYERR_SPECIFIC:
            result.raises.add(PYERR_SPECIFIC[call_name])

        # check for PyArg_Parse*
        elif call_name.startswith("PyArg_Parse"):
            result.has_arg_parsing = True
            result.raises.add("TypeError")

        # check for _PyArg_* functions (internal argument parsing)
        elif call_name.startswith("_PyArg_"):
            result.has_arg_parsing = True
            result.raises.add("TypeError")

    def _extract_exception_type(self, call_cursor: Cursor) -> str | None:
        """
        extract exception type from PyErr_* call.

        arguments:
            `call_cursor: Cursor`
                call expression cursor

        returns: `str | None`
            python exception name, or none if not found
        """
        args = list(call_cursor.get_arguments())
        if not args:
            return None

        first_arg = args[0]
        exc_name = self._extract_pyexc_ref(first_arg)

        if exc_name:
            return PYEXC_MAP.get(exc_name, exc_name)

        return None

    def _extract_pyexc_ref(self, cursor: Cursor) -> str | None:
        """
        extract PyExc_* reference from cursor.

        arguments:
            `cursor: Cursor`
                expression cursor

        returns: `str | None`
            PyExc_* name, or none if not found
        """
        # direct reference to PyExc_*
        if cursor.kind == CursorKind.DECL_REF_EXPR:
            spelling = cursor.spelling
            if spelling.startswith("PyExc_"):
                return spelling

        # unexposed expression (may wrap decl ref)
        if cursor.kind == CursorKind.UNEXPOSED_EXPR:
            for child in cursor.get_children():
                result = self._extract_pyexc_ref(child)
                if result:
                    return result

        return None

    def _check_argument_clinic(self, func_cursor: Cursor) -> bool:
        """
        check if function uses argument clinic.

        argument clinic generates argument-parsing boilerplate that
        can raise TypeError/ValueError.

        arguments:
            `func_cursor: Cursor`
                function cursor

        returns: `bool`
            true if clinic markers found
        """
        # check for clinic comment markers in source
        location = func_cursor.location
        if location.file is None:
            return False

        try:
            source_file = Path(str(location.file))
            content = source_file.read_text(encoding="utf-8", errors="replace")

            # look for clinic markers near function
            func_line = location.line
            lines = content.split("\n")

            # check 50 lines before function for clinic markers
            start = max(0, func_line - 50)
            end = min(len(lines), func_line)
            region = "\n".join(lines[start:end])

            return "[clinic start generated code]" in region

        except OSError:
            return False

    def _can_return_null(self, func_cursor: Cursor) -> bool:
        """
        check if function can return null (implies potential error).

        arguments:
            `func_cursor: Cursor`
                function cursor

        returns: `bool`
            true if return type is a pointer
        """
        return_type = func_cursor.result_type
        return return_type.kind == TypeKind.POINTER

    def analyse_module_file(self, c_file: Path, module_name: str) -> list[FunctionStub]:
        """
        analyse a complete c module file.

        arguments:
            `c_file: Path`
                path to .c file
            `module_name: str`
                python module name (e.g., "_json")

        returns: `list[FunctionStub]`
            function stubs for all exported functions
        """
        logger.info("analysing: %s", c_file)

        try:
            tu = self.parse_module(c_file)
        except (FileNotFoundError, RuntimeError) as e:
            logger.warning("failed to parse %s: %s", c_file, e)
            return []

        # find exported functions
        exports = self.find_exported_functions(tu)
        logger.debug("found %d exported functions in %s", len(exports), c_file.name)

        if not exports:
            return []

        # analyse all functions in a single pass (much faster)
        target_funcs = set(exports.values())
        parsed_funcs = self.analyse_all_functions(tu, target_funcs, c_file)

        stubs: list[FunctionStub] = []

        for py_name, c_func in exports.items():
            parsed = parsed_funcs.get(c_func)
            if parsed is None:
                continue
            parsed.py_name = py_name

            # determine confidence
            if parsed.raises and parsed.raises != {"Exception"}:
                confidence = Confidence.EXACT
            elif parsed.has_arg_parsing or parsed.has_clinic:
                confidence = Confidence.LIKELY
            else:
                confidence = Confidence.CONSERVATIVE

            # build qualified name
            qualname = f"{module_name}.{py_name}"

            stub = FunctionStub(
                qualname=qualname,
                raises=frozenset(parsed.raises),
                confidence=confidence,
            )
            stubs.append(stub)

        return stubs


def find_c_modules(cpython_root: Path) -> list[tuple[Path, str]]:
    """
    find all c extension modules in cpython source tree.

    arguments:
        `cpython_root: Path`
            root directory of cpython source

    returns: `list[tuple[Path, str]]`
            list of (c_file_path, module_name) tuples
    """
    modules_dir = cpython_root / "Modules"
    if not modules_dir.exists():
        return []

    results: list[tuple[Path, str]] = []

    # common module file patterns
    for c_file in modules_dir.glob("*.c"):
        module_name = _infer_module_name(c_file)
        if module_name:
            results.append((c_file, module_name))

    # subdirectory modules (e.g., _sqlite/)
    for subdir in modules_dir.iterdir():
        if subdir.is_dir() and subdir.name.startswith("_"):
            for c_file in subdir.glob("*.c"):
                module_name = subdir.name
                results.append((c_file, module_name))

    return results


def _infer_module_name(c_file: Path) -> str | None:
    """
    infer module name from c file name.

    arguments:
        `c_file: Path`
            path to .c file

    returns: `str | None`
        inferred module name, or none if not a module
    """
    stem = c_file.stem

    # skip non-module files
    skip_patterns = {"config", "main", "getpath", "getbuildinfo"}
    if stem in skip_patterns:
        return None

    # _foomodule.c -> _foo
    if stem.endswith("module"):
        return stem[:-6]

    # _foo.c -> _foo
    if stem.startswith("_"):
        return stem

    # foomodule.c -> foo
    if stem.endswith("module"):
        return stem[:-6]

    return stem
