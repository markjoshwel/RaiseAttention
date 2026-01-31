"""
abstract syntax tree visitor for exception detection.

this module provides ast traversal capabilities to identify raise statements,
function calls, and exception handling patterns in python source code.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from typing_extensions import override

if TYPE_CHECKING:
    pass


@dataclass
class ExceptionInfo:
    """
    information about an exception that may be raised.

    Attributes
    ----------
        `exception_type: str`
            the fully qualified name of the exception type
        `location: tuple[int, int]`
            line and column where the exception is raised
        `message: str | None`
            optional message associated with the raise
        `is_re_raise: bool`
            whether this is a bare 'raise' (re-raising current exception)
    """

    exception_type: str
    location: tuple[int, int]
    message: str | None = None
    is_re_raise: bool = False


@dataclass
class FunctionInfo:
    """
    information about a function and its exception signature.

    Attributes
    ----------
        `name: str`
            function name
        `qualified_name: str`
            fully qualified name including module and class
        `location: tuple[int, int]`
            line and column of function definition
        `raises: list[ExceptionInfo]`
            exceptions raised directly in this function
        `calls: list[str]`
            functions called by this function
        `docstring: str | None`
            function docstring if present
    """

    name: str
    qualified_name: str
    location: tuple[int, int]
    raises: list[ExceptionInfo] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    docstring: str | None = None


@dataclass
class TryExceptInfo:
    """
    information about a try-except block.

    Attributes
    ----------
        `location: tuple[int, int]`
            line and column of the try statement
        `handled_types: list[str]`
            exception types being caught
        `has_bare_except: bool`
            whether a bare 'except:' is present
        `has_except_exception: bool`
            whether 'except Exception:' is present
        `reraises: bool`
            whether the except block re-raises
    """

    location: tuple[int, int]
    handled_types: list[str] = field(default_factory=list)
    has_bare_except: bool = False
    has_except_exception: bool = False
    reraises: bool = False


class ExceptionVisitor(ast.NodeVisitor):
    """
    ast visitor that collects exception-related information.

    traverses the ast to find:
    - raise statements
    - function definitions and their exception signatures
    - try-except blocks
    - function calls that may raise exceptions

    Attributes
    ----------
        `functions: dict[str, FunctionInfo]`
            mapping of qualified function names to their info
        `current_function: FunctionInfo | None`
            currently visiting function
        `try_except_blocks: list[TryExceptInfo]`
            all try-except blocks found
        `imports: dict[str, str]`
            mapping of imported names to their full paths
    """

    module_name: str
    functions: dict[str, FunctionInfo]
    current_function: FunctionInfo | None
    try_except_blocks: list[TryExceptInfo]
    imports: dict[str, str]
    _class_stack: list[str]

    def __init__(self, module_name: str = "") -> None:
        """
        Initialise the exception visitor.

        arguments:
            `module_name: str`
                name of the module being analysed
        """
        self.module_name = module_name
        self.functions = {}
        self.current_function = None
        self.try_except_blocks = []
        self.imports = {}
        self._class_stack = []

    @override
    def visit_Import(self, node: ast.Import) -> None:
        """Visit import statements to track imported modules."""
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.imports[name] = alias.name
        self.generic_visit(node)

    @override
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Visit from-import statements to track imported names."""
        module = node.module or ""
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            if module:
                self.imports[name] = f"{module}.{alias.name}"
            else:
                self.imports[name] = alias.name
        self.generic_visit(node)

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definitions to track qualified names."""
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def _process_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """
        Process function definitions to collect exception information.

        arguments:
            `node: ast.FunctionDef | ast.AsyncFunctionDef`
                the function definition node
        """
        # build qualified name
        class_prefix = ".".join(self._class_stack)
        if class_prefix:
            qualified_name = f"{self.module_name}.{class_prefix}.{node.name}"
        else:
            qualified_name = f"{self.module_name}.{node.name}" if self.module_name else node.name

        # extract docstring
        docstring = ast.get_docstring(node)

        # create function info
        func_info = FunctionInfo(
            name=node.name,
            qualified_name=qualified_name,
            location=(node.lineno, node.col_offset),
            docstring=docstring,
        )

        # store and set as current
        self.functions[qualified_name] = func_info
        previous_function = self.current_function
        self.current_function = func_info

        # visit function body
        self.generic_visit(node)

        # restore previous function
        self.current_function = previous_function

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definitions."""
        self._process_function(node)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definitions."""
        self._process_function(node)

    @override
    def visit_Raise(self, node: ast.Raise) -> None:
        """
        Visit raise statements to collect exception information.

        arguments:
            `node: ast.Raise`
                the raise statement node
        """
        if node.exc is None:
            # bare 'raise' - re-raising current exception
            exc_info = ExceptionInfo(
                exception_type="",
                location=(node.lineno, node.col_offset),
                is_re_raise=True,
            )
        else:
            # get exception type
            exc_type = self._get_exception_type(node.exc)

            # try to get message
            message: str | None = None
            if (
                isinstance(node.exc, ast.Call)
                and node.exc.args
                and isinstance(node.exc.args[0], ast.Constant)
            ):
                message = str(node.exc.args[0].value)

            exc_info = ExceptionInfo(
                exception_type=exc_type,
                location=(node.lineno, node.col_offset),
                message=message,
                is_re_raise=False,
            )

        # add to current function if inside one
        if self.current_function:
            self.current_function.raises.append(exc_info)

        self.generic_visit(node)

    @override
    def visit_Try(self, node: ast.Try) -> None:
        """
        Visit try-except blocks to collect exception handling information.

        arguments:
            `node: ast.Try`
                the try statement node
        """
        try_info = TryExceptInfo(
            location=(node.lineno, node.col_offset),
        )

        for handler in node.handlers:
            if handler.type is None:
                # bare except:
                try_info.has_bare_except = True
            else:
                exc_type = self._get_exception_type(handler.type)
                try_info.handled_types.append(exc_type)

                # check for 'except Exception:'
                if exc_type == "Exception":
                    try_info.has_except_exception = True

            # check if handler re-raises
            for stmt in handler.body:
                if isinstance(stmt, ast.Raise) and stmt.exc is None:
                    try_info.reraises = True
                    break

        self.try_except_blocks.append(try_info)

        # continue visiting
        self.generic_visit(node)

    @override
    def visit_Call(self, node: ast.Call) -> None:
        """
        Visit function calls to track what functions are called.

        arguments:
            `node: ast.Call`
                the call expression node
        """
        if self.current_function:
            func_name = self._get_call_name(node.func)
            if func_name:
                self.current_function.calls.append(func_name)

        self.generic_visit(node)

    def _get_exception_type(self, node: ast.expr) -> str:
        """
        Get the string representation of an exception type from an ast node.

        arguments:
            `node: ast.expr`
                the ast expression node

        returns: `str`
            string representation of the exception type
        """
        if isinstance(node, ast.Name):
            # direct exception name (e.g., ValueError)
            if node.id in self.imports:
                return self.imports[node.id]
            return node.id
        elif isinstance(node, ast.Attribute):
            # qualified name (e.g., requests.RequestException)
            return self._get_attribute_string(node)
        elif isinstance(node, ast.Call):
            # exception instantiation (e.g., ValueError("message"))
            return self._get_exception_type(node.func)
        elif isinstance(node, ast.Subscript):
            # generic type (e.g., list[str])
            return self._get_exception_type(node.value)
        else:
            return ""

    def _get_attribute_string(self, node: ast.Attribute) -> str:
        """
        Convert an attribute access to a string.

        arguments:
            `node: ast.Attribute`
                the attribute node

        returns: `str`
            dot-separated attribute path
        """
        parts = []
        current: ast.expr = node

        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value

        if isinstance(current, ast.Name):
            parts.append(current.id)

        return ".".join(reversed(parts))

    def _get_call_name(self, node: ast.expr) -> str | None:
        """
        Get the name of a called function.

        arguments:
            `node: ast.expr`
                the function expression node

        returns: `str | None`
            function name or none if cannot be determined
        """
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_string(node)
        return None


def parse_file(file_path: str | Path) -> ExceptionVisitor:
    """
    Parse a python file and return an exception visitor with collected info.

    arguments:
        `file_path: str | Path`
            path to the python file to parse

    returns: `ExceptionVisitor`
        visitor containing all exception information

    Raises
    ------
        `SyntaxError`
            if the file contains invalid python syntax
        `FileNotFoundError`
            if the file does not exist
        `OSError`
            if the file cannot be read
    """
    file_path = Path(file_path)

    # read file content
    source = file_path.read_text(encoding="utf-8")

    # parse ast
    tree = ast.parse(source, filename=str(file_path))

    # determine module name from file path
    module_name = file_path.stem

    # visit ast
    visitor = ExceptionVisitor(module_name=module_name)
    visitor.visit(tree)

    return visitor


def parse_source(source: str, module_name: str = "<string>") -> ExceptionVisitor:
    """
    Parse python source code and return an exception visitor.

    arguments:
        `source: str`
            python source code to parse
        `module_name: str`
            name to use for the module

    returns: `ExceptionVisitor`
        visitor containing all exception information

    Raises
    ------
        `SyntaxError`
            if the source contains invalid python syntax
    """
    tree = ast.parse(source, filename=module_name)

    visitor = ExceptionVisitor(module_name=module_name)
    visitor.visit(tree)

    return visitor
