"""
cpython c source analyser using libclang.

extracts exception signatures from cpython's c extension modules
by parsing c source code and identifying PyErr_* function calls.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

# configure libclang path before importing clang
# on windows, libclang.dll is bundled with the python package
if sys.platform == "win32":
    from clang.cindex import Config
    import clang.native

    libclang_path = Path(clang.native.__file__).parent / "libclang.dll"
    if libclang_path.exists():
        Config.set_library_file(str(libclang_path))

try:
    from clang.cindex import (
        Cursor,
        CursorKind,
        Index,
        TranslationUnit,
        TypeKind,
    )
except ImportError as e:
    error_msg = """
error: libclang not found.

standardstubber requires libclang to parse cpython c source code.

on windows:
1. download llvm from https://github.com/llvm/llvm-project/releases
2. install it (e.g., to c:\\program files\\llvm)
3. add the bin directory to your path, or
4. set the libclang_path environment variable:
   $env:libclang_path = "c:\\program files\\llvm\\bin\\libclang.dll"

on linux/macos:
   sudo apt install libclang-dev  # debian/ubuntu
   sudo dnf install clang-devel   # fedora
   brew install llvm              # macos

original error: {}
""".format(e)
    print(error_msg, file=sys.stderr)
    sys.exit(1)

from .models import Confidence, FunctionStub, FunctionSummary, ModuleGraph
from .patterns import (
    PatternDetector,
    PYOBJECT_CALL_FUNCS,
    ERROR_CLEAR_FUNCS,
)

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


# pyerr functions that raise any exception (propagation)
PYERR_RAISE_ANY: Final[frozenset[str]] = frozenset(
    {
        "PyErr_Restore",
        "PyErr_SetRaisedException",
        "_PyErr_SetRaisedException",
    }
)


# regex to match argument clinic annotations for type constructors
# matches patterns like:
#   int.__new__ as long_new
#   float.__new__ as float_new
#   list.__init__
#   str.__new__ as unicode_new
# the c function name is optional (may be omitted if it follows clinic naming)
_CLINIC_CONSTRUCTOR_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(\w+)\.(__new__|__init__)(?:\s+as\s+(\w+))?$",
    re.MULTILINE,
)


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
        `outgoing_calls: set[str]`
            names of all direct callees in same translation unit
        `propagate_callees: set[str]`
            callees whose errors are propagated via null check patterns
    """

    c_name: str
    py_name: str = ""
    raises: set[str] = field(default_factory=set)
    has_arg_parsing: bool = False
    has_clinic: bool = False
    has_explicit_raise: bool = False
    outgoing_calls: set[str] = field(default_factory=set)
    propagate_callees: set[str] = field(default_factory=set)


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
    # caches for performance
    _file_content_cache: dict[str, str | None] = field(default_factory=dict, repr=False)
    _clinic_cache: dict[tuple[str, int], bool] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        """initialise clang index."""
        self._index = Index.create()

    def get_file_content(self, file_path: Path) -> str | None:
        """
        get file content with caching.

        arguments:
            `file_path: Path`
                path to file

        returns: `str | None`
            file content, or none on error
        """
        key = str(file_path)
        if key in self._file_content_cache:
            return self._file_content_cache[key]

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            self._file_content_cache[key] = content
            return content
        except OSError:
            self._file_content_cache[key] = None
            return None

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

        python names are qualified with class names when detected from the
        variable name (e.g., `FileIO_methods` → methods are `FileIO.method`).

        also extracts type constructors (__new__/__init__) from argument clinic
        annotations.

        arguments:
            `tu: TranslationUnit`
                parsed translation unit

        returns: `dict[str, str]`
            mapping from qualified python names to c function names
        """
        exports: dict[str, str] = {}

        # first, find type constructors from argument clinic annotations
        # this extracts int.__new__, float.__new__, str.__new__, etc.
        file_path = Path(tu.spelling)
        file_content = self.get_file_content(file_path)
        if file_content:
            clinic_constructors = self._find_clinic_constructors(file_content)
            exports.update(clinic_constructors)

        # iterate over top-level cursors only (much faster than walk_preorder)
        for cursor in tu.cursor.get_children():
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
                        # parse the array initialiser with class prefix extraction
                        var_name = cursor.spelling
                        class_prefix = self._infer_class_from_methods_array(var_name)
                        exports.update(self._parse_method_def_array(cursor, class_prefix))

        # also search by variable name patterns (fallback)
        if not exports:
            for cursor in tu.cursor.get_children():
                if cursor.kind == CursorKind.VAR_DECL:
                    name = cursor.spelling.lower()
                    if name.endswith("_methods") or name.endswith("methods"):
                        logger.debug(
                            "found methods array by name: %s (type=%s)",
                            cursor.spelling,
                            cursor.type.spelling,
                        )
                        var_name = cursor.spelling
                        class_prefix = self._infer_class_from_methods_array(var_name)
                        exports.update(self._parse_method_def_array(cursor, class_prefix))

        self._method_defs.update(exports)
        return exports

    def _find_clinic_constructors(self, file_content: str) -> dict[str, str]:
        """
        find type constructor mappings from argument clinic annotations.

        parses clinic input blocks in c source files to find type constructor
        declarations like:
            /*[clinic input]
            @classmethod
            int.__new__ as long_new
                x: object(c_default="NULL") = 0
            [clinic start generated code]*/

        these map python type names (e.g., "int", "float", "str") to their
        c constructor functions. the __new__/__init__ suffixes are stripped
        since we want to map the type callable itself.

        arguments:
            `file_content: str`
                content of the c source file

        returns: `dict[str, str]`
            mapping from type names (e.g., "int") to c function names
        """
        constructors: dict[str, str] = {}

        # find all clinic input blocks
        # pattern: /*[clinic input] ... [clinic start generated code]*/
        clinic_blocks: list[str] = re.findall(
            r"/\*\[clinic input\](.*?)\[clinic start generated code\]\*/",
            file_content,
            re.DOTALL,
        )

        for block in clinic_blocks:
            # look for constructor declarations in each block
            for line in block.split("\n"):
                stripped_line = line.strip()
                match = _CLINIC_CONSTRUCTOR_PATTERN.match(stripped_line)
                if match:
                    type_name = match.group(1)  # e.g., "int", "float"
                    method = match.group(2)  # "__new__" or "__init__"
                    c_func = match.group(3)  # e.g., "long_new" (may be None)

                    # use just the type name, not type.__new__ or type.__init__
                    # since calling int(...) invokes the constructor
                    # if both __new__ and __init__ exist, prefer __new__ (first occurrence)
                    if type_name in constructors:
                        logger.debug(
                            "skipping duplicate constructor for %s (%s)",
                            type_name,
                            method,
                        )
                        continue

                    if c_func:
                        # explicit mapping: int.__new__ as long_new
                        constructors[type_name] = c_func
                        logger.debug(
                            "found clinic constructor: %s -> %s (from %s)",
                            type_name,
                            c_func,
                            method,
                        )
                    else:
                        # implicit mapping: list.__init__ -> list___init__
                        # clinic convention: type_dunder_method -> type___method__
                        implicit_func = f"{type_name}___{method.strip('_')}__"
                        constructors[type_name] = implicit_func
                        logger.debug(
                            "found clinic constructor (implicit): %s -> %s (from %s)",
                            type_name,
                            implicit_func,
                            method,
                        )

        return constructors

    def _infer_class_from_methods_array(self, var_name: str) -> str:
        """
        infer class name from PyMethodDef array variable name.

        uses heuristics based on CPython naming conventions:
        - class method arrays: PascalCase (e.g., FileIO_methods, BufferedWriter_methods)
          OR compound lowercase (e.g., bufferedreader_methods, textiowrapper_methods)
        - module method arrays: simple lowercase (e.g., json_methods, module_methods)

        arguments:
            `var_name: str`
                variable name (e.g., "FileIO_methods", "bufferedwriter_methods")

        returns: `str`
            class prefix to prepend to method names, or empty string for module-level
        """
        name = var_name

        # strip common suffixes
        for suffix in ("_methods", "_Methods", "Methods", "methods"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        else:
            # no methods suffix found - treat as module-level
            return ""

        # skip explicit module-level patterns
        module_level_patterns = {
            "module",
            "mod",
            "",
            # common short module names that use _methods arrays
            "builtin",  # bltinmodule.c uses builtin_methods for module-level builtins
            "json",
            "socket",
            "gc",
            "time",
            "signal",
            "select",
            "posix",
            "nt",
            "os",
            "sys",
            "array",
            "zlib",
            "mmap",
            "math",
            "cmath",
            "abc",
            "pwd",
            "grp",
            "spwd",
            "fcntl",
            "nis",
            "binascii",
            "audioop",
            "atexit",
            "resource",
            "syslog",
            "termios",
            "unicodedata",
            "itertools",
            "overlapped",
            "pyexpat",
            "readline",
            "faulthandler",
        }
        name_lower = name.lower()
        if name_lower in module_level_patterns:
            return ""

        # strip common prefixes (Py, _Py, _)
        for prefix in ("Py", "_Py", "_"):
            if name.startswith(prefix) and len(name) > len(prefix):
                name = name[len(prefix) :]
                break

        # empty after stripping? module-level
        if not name:
            return ""

        # PascalCase heuristic: class names start with uppercase
        # e.g., FileIO, BufferedWriter, Compressor
        if name[0].isupper():
            return name

        # for lowercase names, use length-based heuristic:
        # compound words (bufferedreader, textiowrapper, iobase) are longer
        # simple module names (json, socket) are short
        # threshold: 6+ chars suggests a class name (iobase, fileio, bytesio)
        if len(name) >= 6:
            # convert to PascalCase for class name
            return name.capitalize()

        # short lowercase name - likely module-level
        return ""

    def _parse_method_def_array(self, var_cursor: Cursor, class_prefix: str = "") -> dict[str, str]:
        """
        parse a PyMethodDef array initialiser.

        arguments:
            `var_cursor: Cursor`
                variable declaration cursor
            `class_prefix: str`
                class name to prepend to method names (empty for module-level)

        returns: `dict[str, str]`
            mapping from qualified python names to c function names
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
                                # qualify with class prefix if present
                                if class_prefix:
                                    qualified_name = f"{class_prefix}.{py_name}"
                                else:
                                    qualified_name = py_name
                                methods[qualified_name] = c_func

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
            spelling = str(cursor.spelling)
            if spelling.startswith('"') and spelling.endswith('"'):
                return spelling[1:-1]
            return spelling

        # try to extract from tokens (most reliable method)
        try:
            tokens = list(cursor.get_tokens())
            for token in tokens:
                spelling = str(token.spelling)
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
            return str(cursor.spelling)

        # UNEXPOSED_EXPR may have the function name in its spelling
        if cursor.kind == CursorKind.UNEXPOSED_EXPR:
            # if this UNEXPOSED_EXPR has a meaningful spelling, it's the func name
            if cursor.spelling and not cursor.spelling.startswith('"'):
                # check if it looks like a function/variable name
                # (has underscores or starts with a letter)
                spelling = str(cursor.spelling)
                if spelling[0].isalpha():
                    return spelling

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
        check if function uses argument clinic (with cached file content and memoization).

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

        file_path = str(location.file)
        func_line = location.line

        # check memoization cache
        cache_key = (file_path, func_line)
        if cache_key in self._clinic_cache:
            return self._clinic_cache[cache_key]

        try:
            if file_content is None:
                source_file = Path(file_path)
                file_content = self.get_file_content(source_file)
                if file_content is None:
                    self._clinic_cache[cache_key] = False
                    return False

            # look for clinic markers near function
            lines = file_content.split("\n")

            # check 50 lines before function for clinic markers
            start = max(0, func_line - 50)
            end = min(len(lines), func_line)
            region = "\n".join(lines[start:end])

            result = "[clinic start generated code]" in region
            self._clinic_cache[cache_key] = result
            return result

        except OSError:
            self._clinic_cache[cache_key] = False
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
        for cursor in tu.cursor.get_children():
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
                result.has_explicit_raise = True

        # check for PyErr_NoMemory, PyErr_SetFromErrno, etc.
        elif call_name in PYERR_SPECIFIC:
            result.raises.add(PYERR_SPECIFIC[call_name])
            result.has_explicit_raise = True

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
            spelling = str(cursor.spelling)
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
        return bool(return_type.kind == TypeKind.POINTER)

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

    def analyse_module_with_propagation(self, c_file: Path, module_name: str) -> ModuleGraph:
        """
        analyse a c module file with call graph propagation.

        builds a call graph for all functions in the module and computes
        transitive exception propagation via fixpoint iteration.

        arguments:
            `c_file: Path`
                path to .c file
            `module_name: str`
                python module name (e.g., "_json")

        returns: `ModuleGraph`
            module graph with transitive exception information
        """
        logger.info("analysing with propagation: %s", c_file)

        graph = ModuleGraph(module_name=module_name)

        import time

        t_start = time.perf_counter()

        try:
            tu = self.parse_module(c_file)
        except (FileNotFoundError, RuntimeError) as e:
            logger.warning("failed to parse %s: %s", c_file, e)
            return graph

        t_parse = time.perf_counter()

        # find exported functions
        exports = self.find_exported_functions(tu)
        graph.exports = exports

        t_exports = time.perf_counter()

        if not exports:
            return graph

        # read file content once for clinic detection (uses cache)
        file_content = self.get_file_content(c_file)

        # create shared pattern detector for caching across all functions in this TU
        pattern_detector = PatternDetector()

        # collect all function definitions in the translation unit
        all_func_cursors: dict[str, Cursor] = {}
        for cursor in tu.cursor.get_children():
            if cursor.kind == CursorKind.FUNCTION_DECL and cursor.is_definition():
                all_func_cursors[cursor.spelling] = cursor

        t_collect = time.perf_counter()

        # analyse each function, building call graph (shared detector for caching)
        for func_name, func_cursor in all_func_cursors.items():
            summary = self._analyse_function_with_calls(
                func_cursor, file_content, module_name, all_func_cursors, pattern_detector
            )
            graph.functions[func_name] = summary

        t_analyse = time.perf_counter()

        # compute transitive exception propagation
        graph.compute_transitive_raises()

        t_end = time.perf_counter()

        if logger.isEnabledFor(logging.INFO):
            logger.info(
                "timing: parse=%.3fs exports=%.3fs collect=%.3fs analyse=%.3fs total=%.3fs",
                t_parse - t_start,
                t_exports - t_parse,
                t_collect - t_exports,
                t_analyse - t_collect,
                t_end - t_start,
            )

        return graph

    def _analyse_function_with_calls(
        self,
        func_cursor: Cursor,
        file_content: str | None,
        module_name: str,
        all_funcs: dict[str, Cursor],
        pattern_detector: PatternDetector | None = None,
    ) -> FunctionSummary:
        """
        analyse a function cursor with call graph information.

        uses single-pass ast collection for performance and
        detects multiple propagation patterns including goto-based.

        arguments:
            `func_cursor: Cursor`
                function definition cursor
            `file_content: str | None`
                cached file content for clinic detection
            `module_name: str`
                python module name
            `all_funcs: dict[str, Cursor]`
                all function definitions in the translation unit
            `pattern_detector: PatternDetector | None`
                shared pattern detector for caching

        returns: `FunctionSummary`
            analysis result with call graph information
        """
        func_name = func_cursor.spelling
        summary = FunctionSummary(name=func_name, module=module_name)

        if pattern_detector is None:
            pattern_detector = PatternDetector()

        # check source for argument clinic markers
        summary.has_clinic = self._check_argument_clinic_cached(func_cursor, file_content)
        if summary.has_clinic:
            summary.local_raises.add("TypeError")

        # === single-pass collection ===
        # collect labels, calls, gotos, and if statements in one pass
        all_labels: dict[str, Cursor] = {}
        all_calls: list[Cursor] = []
        # map line number -> list of goto labels (for fast lookup)
        goto_map: dict[int, list[str]] = {}
        error_clear_locations: set[int] = set()  # lines where errors are cleared

        for child in func_cursor.walk_preorder():
            kind = child.kind
            if kind == CursorKind.LABEL_STMT:
                all_labels[child.spelling] = child
            elif kind == CursorKind.CALL_EXPR:
                all_calls.append(child)
                # detect error clearing
                if child.spelling in ERROR_CLEAR_FUNCS:
                    error_clear_locations.add(child.location.line)
            elif kind == CursorKind.GOTO_STMT:
                # build map of line -> goto labels
                line = child.location.line
                # for goto statements, child usually has no children but refers to label
                # libclang: get_tokens/spelling is reliable for goto label name
                tokens = list(child.get_tokens())
                if len(tokens) >= 2 and tokens[0].spelling == "goto":
                    label_name = tokens[1].spelling.rstrip(";")
                    if line not in goto_map:
                        goto_map[line] = []
                    goto_map[line].append(label_name)

        # === analyse calls ===
        call_sites: list[tuple[Cursor, str]] = []  # (call_cursor, callee_name) for TU calls
        pyobject_call_propagates = False

        for call_cursor in all_calls:
            call_name = call_cursor.spelling
            call_line = call_cursor.location.line

            # track outgoing calls to functions in the same TU
            if call_name in all_funcs:
                summary.outgoing_calls.add(call_name)
                call_sites.append((call_cursor, call_name))

            # analyse for direct exception setting
            self._analyse_call_for_summary(call_cursor, summary)

            # detect PyObject_Call* that propagates any exception
            if call_name in PYOBJECT_CALL_FUNCS:
                # check if error is handled after this call
                if not self._is_error_cleared_after(call_line, error_clear_locations):
                    pyobject_call_propagates = True

            # detect PyErr_Restore/SetRaisedException
            if call_name in PYERR_RAISE_ANY:
                summary.local_raises.add("Exception")

        # if PyObject_Call propagates without clear, mark as may raise any
        if pyobject_call_propagates:
            summary.local_raises.add("Exception")

        # === detect propagation patterns ===
        for call_cursor, callee_name in call_sites:
            # check original null-check pattern
            if self._is_propagation_site(call_cursor, func_cursor):
                summary.propagate_callees.add(callee_name)
                continue

            # check goto-based propagation pattern (O(1) lookup)
            goto_site = pattern_detector.detect_goto_error_fast(
                call_cursor.location.line, callee_name, goto_map
            )
            if goto_site is not None and goto_site.propagates:
                summary.propagate_callees.add(callee_name)

        # argument clinic heuristic: if function foo calls foo_impl,
        # add foo_impl to propagate_callees since clinic wrappers
        # always propagate errors from their implementation functions
        func_name = func_cursor.spelling
        impl_name = f"{func_name}_impl"
        if impl_name in summary.outgoing_calls:
            summary.propagate_callees.add(impl_name)
            logger.debug(
                "clinic heuristic: %s propagates from %s",
                func_name,
                impl_name,
            )

        # if function can return null but no exceptions found, be conservative
        if not summary.local_raises and self._can_return_null(func_cursor):
            summary.local_raises.add("Exception")

        return summary

    def _is_error_cleared_after(self, call_line: int, error_clear_locations: set[int]) -> bool:
        """
        check if an error is cleared after a specific line.

        arguments:
            `call_line: int`
                line of the call
            `error_clear_locations: set[int]`
                lines where PyErr_Clear etc are called

        returns: `bool`
            true if error is cleared after this call
        """
        # simple heuristic: check if there's a clear within 10 lines after
        for clear_line in error_clear_locations:
            if call_line < clear_line <= call_line + 10:
                return True
        return False

    def _analyse_call_for_summary(self, call_cursor: Cursor, summary: FunctionSummary) -> None:
        """
        analyse a call expression for exception-setting behaviour.

        arguments:
            `call_cursor: Cursor`
                call expression cursor
            `summary: FunctionSummary`
                summary to update
        """
        call_name = call_cursor.spelling

        # check for PyErr_SetString, PyErr_Format, etc.
        if call_name in PYERR_SETTERS:
            exc_type = self._extract_exception_type(call_cursor)
            if exc_type:
                summary.local_raises.add(exc_type)
                summary.has_explicit_raise = True

        # check for PyErr_NoMemory, PyErr_SetFromErrno, etc.
        elif call_name in PYERR_SPECIFIC:
            summary.local_raises.add(PYERR_SPECIFIC[call_name])
            summary.has_explicit_raise = True

        # check for PyArg_Parse*
        elif call_name.startswith("PyArg_Parse"):
            summary.has_arg_parsing = True
            summary.local_raises.add("TypeError")

        # check for _PyArg_* functions (internal argument parsing)
        elif call_name.startswith("_PyArg_"):
            summary.has_arg_parsing = True
            summary.local_raises.add("TypeError")

    def _is_propagation_site(self, call_cursor: Cursor, func_cursor: Cursor) -> bool:
        """
        detect if a call site propagates errors to the caller.

        looks for patterns like:
        - `if (callee() == NULL) return NULL;`
        - `if (callee() < 0) return -1;`
        - `PyObject *res = callee(); if (res == NULL) return NULL;`

        arguments:
            `call_cursor: Cursor`
                call expression cursor
            `func_cursor: Cursor`
                containing function cursor

        returns: `bool`
            true if this call site propagates errors
        """
        # get the parent of the call expression
        parent = self._find_parent(call_cursor, func_cursor)
        if parent is None:
            return False

        # pattern 1: call directly in if condition
        # if (callee() == NULL) or if (!callee())
        if parent.kind == CursorKind.BINARY_OPERATOR:
            grandparent = self._find_parent(parent, func_cursor)
            if grandparent and grandparent.kind == CursorKind.IF_STMT:
                return self._check_if_propagates_error(grandparent)

        # pattern 2: call assigned to variable, then checked
        # PyObject *res = callee();
        if parent.kind in (CursorKind.VAR_DECL, CursorKind.BINARY_OPERATOR):
            var_name = self._get_assigned_variable(parent)
            if var_name:
                # look for subsequent if statement checking this variable
                return self._check_variable_propagation(var_name, call_cursor, func_cursor)

        # pattern 3: call directly used as condition
        # if (callee())
        if parent.kind == CursorKind.IF_STMT:
            return self._check_if_propagates_error(parent)

        # pattern 4: call inside unary not
        # if (!callee())
        if parent.kind == CursorKind.UNARY_OPERATOR:
            grandparent = self._find_parent(parent, func_cursor)
            if grandparent and grandparent.kind == CursorKind.IF_STMT:
                return self._check_if_propagates_error(grandparent)

        return False

    def _find_parent(self, target: Cursor, func_cursor: Cursor) -> Cursor | None:
        """
        find the parent of a cursor within a function.

        arguments:
            `target: Cursor`
                cursor to find parent of
            `func_cursor: Cursor`
                containing function cursor

        returns: `Cursor | None`
            parent cursor, or none if not found
        """
        target_hash = target.hash

        def search(cursor: Cursor) -> Cursor | None:
            for child in cursor.get_children():
                if child.hash == target_hash:
                    return cursor
                result = search(child)
                if result is not None:
                    return result
            return None

        return search(func_cursor)

    def _get_assigned_variable(self, cursor: Cursor) -> str | None:
        """
        get the variable name from an assignment or declaration.

        arguments:
            `cursor: Cursor`
                assignment or declaration cursor

        returns: `str | None`
            variable name, or none if not found
        """
        if cursor.kind == CursorKind.VAR_DECL:
            return str(cursor.spelling)

        if cursor.kind == CursorKind.BINARY_OPERATOR:
            # look for assignment operator (=)
            children = list(cursor.get_children())
            if len(children) >= 2:
                first = children[0]
                if first.kind == CursorKind.DECL_REF_EXPR:
                    return str(first.spelling)

        return None

    def _check_if_propagates_error(self, if_cursor: Cursor) -> bool:
        """
        check if an if statement propagates an error.

        looks for `return NULL;` or `return -1;` in the then branch,
        without PyErr_Clear or new PyErr_* calls.

        arguments:
            `if_cursor: Cursor`
                if statement cursor

        returns: `bool`
            true if this if statement propagates errors
        """
        children = list(if_cursor.get_children())
        if len(children) < 2:
            return False

        # children[0] is condition, children[1] is then branch
        then_branch = children[1]

        has_return_error = False
        has_error_handling = False

        for child in then_branch.walk_preorder():
            # check for return statement
            if child.kind == CursorKind.RETURN_STMT:
                if self._returns_error_sentinel(child):
                    has_return_error = True

            # check for PyErr_Clear or new PyErr_* calls
            if child.kind == CursorKind.CALL_EXPR:
                call_name = child.spelling
                if call_name == "PyErr_Clear":
                    has_error_handling = True
                elif call_name in PYERR_SETTERS or call_name in PYERR_SPECIFIC:
                    # new exception being set - not propagation
                    has_error_handling = True

        return has_return_error and not has_error_handling

    def _returns_error_sentinel(self, return_cursor: Cursor) -> bool:
        """
        check if a return statement returns an error sentinel.

        looks for `return NULL;`, `return -1;`, or similar patterns.

        arguments:
            `return_cursor: Cursor`
                return statement cursor

        returns: `bool`
            true if this returns an error sentinel
        """
        children = list(return_cursor.get_children())
        if not children:
            return False

        return_expr = children[0]

        # check for NULL
        if return_expr.kind == CursorKind.GNU_NULL_EXPR:
            return True

        # check for integer literal -1 or 0
        if return_expr.kind == CursorKind.INTEGER_LITERAL:
            try:
                tokens = list(return_expr.get_tokens())
                if tokens:
                    val = tokens[0].spelling
                    if val in ("-1", "0"):
                        return True
            except Exception:
                pass

        # check for unary minus with integer literal
        if return_expr.kind == CursorKind.UNARY_OPERATOR:
            inner = list(return_expr.get_children())
            if inner and inner[0].kind == CursorKind.INTEGER_LITERAL:
                try:
                    tokens = list(inner[0].get_tokens())
                    if tokens and tokens[0].spelling == "1":
                        return True
                except Exception:
                    pass

        # check for NULL cast: (void *)0 or ((void *)0)
        if return_expr.kind in (CursorKind.CSTYLE_CAST_EXPR, CursorKind.PAREN_EXPR):
            for child in return_expr.walk_preorder():
                if child.kind == CursorKind.INTEGER_LITERAL:
                    try:
                        tokens = list(child.get_tokens())
                        if tokens and tokens[0].spelling == "0":
                            return True
                    except Exception:
                        pass
                if child.kind == CursorKind.GNU_NULL_EXPR:
                    return True

        return False

    def _check_variable_propagation(
        self, var_name: str, call_cursor: Cursor, func_cursor: Cursor
    ) -> bool:
        """
        check if a variable is checked for error and propagates.

        looks for patterns like:
        ```c
        PyObject *res = callee();
        if (res == NULL)
            return NULL;
        ```

        arguments:
            `var_name: str`
                variable name to check
            `call_cursor: Cursor`
                the call expression cursor
            `func_cursor: Cursor`
                containing function cursor

        returns: `bool`
            true if variable is checked and error propagated
        """
        call_line = call_cursor.location.line

        # look for if statements after the call
        for child in func_cursor.walk_preorder():
            if child.kind != CursorKind.IF_STMT:
                continue

            # must be after the call
            if child.location.line <= call_line:
                continue

            # check if the condition references our variable
            condition_children = list(child.get_children())
            if not condition_children:
                continue

            condition = condition_children[0]

            # look for variable reference in condition
            if self._condition_checks_variable(condition, var_name):
                if self._check_if_propagates_error(child):
                    return True

        return False

    def _condition_checks_variable(self, condition: Cursor, var_name: str) -> bool:
        """
        check if a condition references a specific variable.

        arguments:
            `condition: Cursor`
                condition expression cursor
            `var_name: str`
                variable name to look for

        returns: `bool`
            true if variable is referenced in condition
        """
        for child in condition.walk_preorder():
            if child.kind == CursorKind.DECL_REF_EXPR:
                if child.spelling == var_name:
                    return True
        return False


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

    # test module prefixes to exclude (they're only used by the test suite, not production code)
    test_prefixes = ("_test", "xx", "_xx")

    # common module file patterns
    for c_file in modules_dir.glob("*.c"):
        module_name = _infer_module_name(c_file)
        if module_name and not module_name.startswith(test_prefixes):
            results.append((c_file, module_name))

    # subdirectory modules (e.g., _sqlite/)
    for subdir in modules_dir.iterdir():
        if subdir.is_dir() and subdir.name.startswith("_"):
            # skip test module directories
            if subdir.name.startswith(test_prefixes):
                continue
            for c_file in subdir.glob("*.c"):
                module_name = subdir.name
                results.append((c_file, module_name))

    # special handling for Python/ directory (builtins module)
    # bltinmodule.c contains built-in functions like open(), print(), len(), etc.
    python_dir = cpython_root / "Python"
    if python_dir.exists():
        bltinmodule = python_dir / "bltinmodule.c"
        if bltinmodule.exists():
            results.append((bltinmodule, "builtins"))

    # special handling for Objects/ directory (built-in type constructors)
    # these define types like int, float, str, list, etc. that are exposed
    # via the builtins module
    objects_dir = cpython_root / "Objects"
    if objects_dir.exists():
        # only include files that define type objects (end with "object.c")
        # these contain __new__/__init__ implementations for built-in types
        for c_file in objects_dir.glob("*object.c"):
            # skip generic object.c which doesn't define a user-visible type
            if c_file.stem == "object":
                continue
            # all type objects are exposed via builtins module
            results.append((c_file, "builtins"))

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


def find_python_modules(cpython_root: Path) -> list[tuple[Path, str]]:
    """
    find python stdlib modules in cpython source tree.

    scans the Lib/ directory for .py files, filtering out test modules
    and other non-stdlib directories.

    arguments:
        `cpython_root: Path`
            root directory of cpython source

    returns: `list[tuple[Path, str]]`
        list of (py_file_path, module_name) tuples
    """
    lib_dir = cpython_root / "Lib"
    if not lib_dir.exists():
        return []

    results: list[tuple[Path, str]] = []

    # directories to skip entirely (tests, gui, legacy, etc.)
    skip_dirs: frozenset[str] = frozenset(
        {
            "test",
            "tests",
            "idlelib",
            "tkinter",
            "turtledemo",
            "lib2to3",
            "ensurepip",
            "venv",
            "site-packages",
            "__pycache__",
            "pydoc_data",
            "msilib",  # windows-only, deprecated
        }
    )

    # file prefixes to skip
    skip_prefixes = ("test_", "_test")

    for py_file in lib_dir.rglob("*.py"):
        # skip files in excluded directories
        if any(part in skip_dirs for part in py_file.relative_to(lib_dir).parts):
            continue

        # skip test files
        if py_file.name.startswith(skip_prefixes):
            continue

        # skip __main__.py files (entry points, not modules)
        if py_file.name == "__main__.py":
            continue

        # infer module name from path
        module_name = _infer_python_module_name(py_file, lib_dir)
        if module_name:
            results.append((py_file, module_name))

    return results


def _infer_python_module_name(py_file: Path, lib_dir: Path) -> str | None:
    """
    infer module name from python file path.

    arguments:
        `py_file: Path`
            path to .py file
        `lib_dir: Path`
            path to Lib/ directory

    returns: `str | None`
        inferred module name (e.g., "json.decoder"), or none if invalid
    """
    rel_path = py_file.relative_to(lib_dir)
    parts = list(rel_path.parts)

    # handle package __init__.py
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
        if not parts:
            return None
        return ".".join(parts)

    # remove .py extension from last part
    parts[-1] = parts[-1][:-3]

    return ".".join(parts)
