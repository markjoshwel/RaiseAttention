"""
abstract syntax tree visitor for exception detection.

this module provides ast traversal capabilities to identify raise statements,
function calls, and exception handling patterns in python source code.
it tracks try-except context at call sites to enable proper exception
propagation analysis.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from typing_extensions import override

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# constant for module-level code tracking
MODULE_LEVEL_NAME = "<module>"


@dataclass
class ExceptionInfo:
    """
    information about an exception that may be raised.

    attributes:
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
class TryExceptInfo:
    """
    information about a try-except block.

    attributes:
        `location: tuple[int, int]`
            line and column of the try statement
        `end_location: tuple[int, int]`
            line and column where the try block ends
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
    end_location: tuple[int, int] = field(default_factory=lambda: (0, 0))
    handled_types: list[str] = field(default_factory=list)
    has_bare_except: bool = False
    has_except_exception: bool = False
    reraises: bool = False


@dataclass
class SuppressInfo:
    """
    information about a contextlib.suppress context manager.

    attributes:
        `location: tuple[int, int]`
            line and column of the with statement
        `end_location: tuple[int, int]`
            line and column where the with block ends
        `suppressed_types: list[str]`
            exception types being suppressed
    """

    location: tuple[int, int]
    end_location: tuple[int, int] = field(default_factory=lambda: (0, 0))
    suppressed_types: list[str] = field(default_factory=list)


@dataclass
class CallInfo:
    """
    information about a function call with exception tracking context.

    attributes:
        `func_name: str`
            name of the called function
        `location: tuple[int, int]`
            line and column of the call
        `end_location: tuple[int, int]`
            line and column where the call statement ends
        `is_async: bool`
            whether this is an await expression
        `containing_try_blocks: list[int]`
            indices into try_except_blocks that contain this call
        `containing_suppress_blocks: list[int]`
            indices into suppress_blocks that contain this call
        `callable_args: list[str]`
            names of callables passed as arguments (for HOF tracking)
    """

    func_name: str
    location: tuple[int, int]
    end_location: tuple[int, int]
    is_async: bool = False
    containing_try_blocks: list[int] = field(default_factory=list)
    containing_suppress_blocks: list[int] = field(default_factory=list)
    callable_args: list[str] = field(default_factory=list)


@dataclass
class FunctionInfo:
    """
    information about a function and its exception signature.

    attributes:
        `name: str`
            function name
        `qualified_name: str`
            fully qualified name including module and class
        `location: tuple[int, int]`
            line and column of function definition
        `raises: list[ExceptionInfo]`
            exceptions raised directly in this function
        `calls: list[CallInfo]`
            functions called by this function with context
        `docstring: str | None`
            function docstring if present
        `is_async: bool`
            whether this is an async function
        `decorators: list[str]`
            names of decorators applied to this function
    """

    name: str
    qualified_name: str
    location: tuple[int, int]
    raises: list[ExceptionInfo] = field(default_factory=list)
    calls: list[CallInfo] = field(default_factory=list)
    docstring: str | None = None
    is_async: bool = False
    decorators: list[str] = field(default_factory=list)


class ExceptionVisitor(ast.NodeVisitor):
    """
    ast visitor that collects exception-related information.

    traverses the ast to find:
    - raise statements
    - function definitions and their exception signatures
    - try-except blocks with line ranges
    - contextlib.suppress contexts
    - function calls with their exception handling context

    attributes:
        `functions: dict[str, FunctionInfo]`
            mapping of qualified function names to their info
        `current_function: FunctionInfo | None`
            currently visiting function
        `try_except_blocks: list[TryExceptInfo]`
            all try-except blocks found
        `suppress_blocks: list[SuppressInfo]`
            all contextlib.suppress blocks found
        `imports: dict[str, str]`
            mapping of imported names to their full paths
        `active_try_blocks: list[int]`
            indices of try-except blocks currently in scope
        `active_suppress_blocks: list[int]`
            indices of suppress blocks currently in scope
    """

    module_name: str
    functions: dict[str, FunctionInfo]
    current_function: FunctionInfo | None
    try_except_blocks: list[TryExceptInfo]
    suppress_blocks: list[SuppressInfo]
    imports: dict[str, str]
    _class_stack: list[str]
    active_try_blocks: list[int]
    active_suppress_blocks: list[int]
    _module_level_func: FunctionInfo
    _exception_instances: set[str]

    def __init__(self, module_name: str = "") -> None:
        """
        initialise the exception visitor.

        arguments:
            `module_name: str`
                name of the module being analysed
        """
        self.module_name = module_name
        self.functions = {}
        self.current_function = None
        self.try_except_blocks = []
        self.suppress_blocks = []
        self.imports = {}
        self._class_stack = []
        self.active_try_blocks = []
        self.active_suppress_blocks = []
        self._exception_instances = set()

        # create synthetic function to track module-level code
        qualified_module_name = (
            f"{module_name}.{MODULE_LEVEL_NAME}" if module_name else MODULE_LEVEL_NAME
        )
        self._module_level_func = FunctionInfo(
            name=MODULE_LEVEL_NAME,
            qualified_name=qualified_module_name,
            location=(1, 0),
            docstring=None,
            is_async=False,
        )
        self.functions[qualified_module_name] = self._module_level_func

    @override
    def visit_Import(self, node: ast.Import) -> None:
        """visit import statements to track imported modules."""
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.imports[name] = alias.name
        self.generic_visit(node)

    @override
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """visit from-import statements to track imported names."""
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
        """visit class definitions to track qualified names."""
        self._class_stack.append(node.name)
        self.generic_visit(node)
        _ = self._class_stack.pop()

    def _process_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool = False
    ) -> None:
        """
        process function definitions to collect exception information.

        arguments:
            `node: ast.FunctionDef | ast.AsyncFunctionDef`
                the function definition node
            `is_async: bool`
                whether this is an async function
        """
        # build qualified name
        class_prefix = ".".join(self._class_stack)
        if class_prefix:
            qualified_name = f"{self.module_name}.{class_prefix}.{node.name}"
        else:
            qualified_name = f"{self.module_name}.{node.name}" if self.module_name else node.name

        # extract docstring
        docstring = ast.get_docstring(node)

        # extract decorators
        decorators = [self._get_decorator_name(dec) for dec in node.decorator_list]
        decorators = [d for d in decorators if d]  # filter out empty strings

        logger.debug("visiting function: %s", qualified_name)
        if decorators:
            logger.debug("function has decorators: %s", decorators)

        # create function info
        func_info = FunctionInfo(
            name=node.name,
            qualified_name=qualified_name,
            location=(node.lineno, node.col_offset),
            docstring=docstring,
            is_async=is_async,
            decorators=decorators,
        )

        # store and set as current
        self.functions[qualified_name] = func_info
        previous_function = self.current_function
        self.current_function = func_info

        # save and clear active try blocks
        saved_try_blocks = self.active_try_blocks
        self.active_try_blocks = []

        # visit function body
        self.generic_visit(node)

        # restore state
        self.current_function = previous_function
        self.active_try_blocks = saved_try_blocks

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """visit function definitions."""
        self._process_function(node, is_async=False)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """visit async function definitions."""
        self._process_function(node, is_async=True)

    @override
    def visit_Raise(self, node: ast.Raise) -> None:
        """
        visit raise statements to collect exception information.

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
            logger.debug("found bare raise (re-raise) at line %d", node.lineno)
        elif isinstance(node.exc, ast.Name) and node.exc.id in self._exception_instances:
            # raising a caught exception instance (e.g., 'raise error' where 'error' is from 'except Exception as error:')
            exc_info = ExceptionInfo(
                exception_type="",
                location=(node.lineno, node.col_offset),
                is_re_raise=True,
            )
            logger.debug(
                "found re-raise of exception instance '%s' at line %d", node.exc.id, node.lineno
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
            logger.debug("found raise statement: %s at line %d", exc_type, node.lineno)

        # add to current function or module-level synthetic function
        target_func = self.current_function or self._module_level_func
        target_func.raises.append(exc_info)

        self.generic_visit(node)

    @override
    def visit_Try(self, node: ast.Try) -> None:
        """
        visit try-except blocks to collect exception handling information.

        arguments:
            `node: ast.Try`
                the try statement node
        """
        logger.debug("entering try-block at line %d", node.lineno)

        try_info = TryExceptInfo(
            location=(node.lineno, node.col_offset),
        )

        # find the end line of the try block
        # the try block ends at the start of the first handler
        if node.handlers:
            try_info.end_location = (node.handlers[0].lineno, node.handlers[0].col_offset)
        elif node.orelse:
            try_info.end_location = (node.orelse[0].lineno, node.orelse[0].col_offset)
        elif node.finalbody:
            try_info.end_location = (node.finalbody[0].lineno, node.finalbody[0].col_offset)
        else:
            # fallback: estimate based on last statement in body
            if node.body:
                last_stmt = node.body[-1]
                try_info.end_location = (
                    getattr(last_stmt, "lineno", node.lineno),
                    getattr(last_stmt, "col_offset", node.col_offset),
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

        # add to list and get its index
        block_index = len(self.try_except_blocks)
        self.try_except_blocks.append(try_info)

        # add to active blocks for the try body
        self.active_try_blocks.append(block_index)

        # visit try body with this block active
        for stmt in node.body:
            self.visit(stmt)

        # remove from active blocks
        _ = self.active_try_blocks.pop()

        # visit handlers, else, and finally normally
        for handler in node.handlers:
            self.visit(handler)
        for stmt in node.orelse:
            self.visit(stmt)
        for stmt in node.finalbody:
            self.visit(stmt)

    @override
    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """visit except handlers - do not track try-except context here."""
        # track exception instance name (e.g., 'except ValueError as e:')
        if node.name is not None:
            self._exception_instances.add(node.name)
            logger.debug("tracking exception instance: %s", node.name)

        # except handlers are not inside the try block
        saved_blocks = self.active_try_blocks
        self.active_try_blocks = []
        self.generic_visit(node)
        self.active_try_blocks = saved_blocks

        # remove exception instance when leaving handler
        if node.name is not None:
            self._exception_instances.discard(node.name)

    @override
    def visit_With(self, node: ast.With) -> None:
        """
        visit with statements to detect contextlib.suppress usage.

        arguments:
            `node: ast.With`
                the with statement node
        """
        suppress_block_indices: list[int] = []

        # check each context manager in the with statement
        for item in node.items:
            suppressed_types = self._get_suppressed_exceptions(item.context_expr)
            if suppressed_types:
                # this is a contextlib.suppress context
                suppress_info = SuppressInfo(
                    location=(node.lineno, node.col_offset),
                )

                # find the end of the with block
                if node.body:
                    last_stmt = node.body[-1]
                    suppress_info.end_location = (
                        getattr(last_stmt, "end_lineno", last_stmt.lineno),
                        getattr(last_stmt, "end_col_offset", 0),
                    )

                suppress_info.suppressed_types = suppressed_types

                # add to list and get its index
                block_index = len(self.suppress_blocks)
                self.suppress_blocks.append(suppress_info)
                suppress_block_indices.append(block_index)

                logger.debug(
                    "found contextlib.suppress at line %d for types: %s",
                    node.lineno,
                    suppressed_types,
                )

        # add suppress blocks to active blocks before visiting body
        for block_index in suppress_block_indices:
            self.active_suppress_blocks.append(block_index)

        # visit with body
        for stmt in node.body:
            self.visit(stmt)

        # remove suppress blocks from active after body
        for _ in suppress_block_indices:
            _ = self.active_suppress_blocks.pop()

    def _get_suppressed_exceptions(self, node: ast.expr) -> list[str]:
        """
        check if a with context manager is contextlib.suppress and extract types.

        arguments:
            `node: ast.expr`
                the context expression node (e.g., the part after 'with')

        returns: `list[str]`
            list of suppressed exception types, empty if not a suppress context
        """
        if isinstance(node, ast.Call):
            # check for contextlib.suppress(...) or suppress(...)
            func_name = self._get_call_name(node.func)
            if func_name in ("contextlib.suppress", "suppress"):
                # resolve full name if imported
                if func_name == "suppress" and "suppress" in self.imports:
                    full_name = self.imports["suppress"]
                    if not full_name.endswith("suppress"):
                        # not from contextlib
                        return []

                # extract exception types from arguments
                suppressed_types: list[str] = []
                for arg in node.args:
                    exc_type = self._get_exception_type(arg)
                    if exc_type:
                        suppressed_types.append(exc_type)

                return suppressed_types

        return []

    @override
    def visit_Call(self, node: ast.Call) -> None:
        """
        visit function calls to track what functions are called.

        arguments:
            `node: ast.Call`
                the call expression node
        """
        # use current function or module-level synthetic function
        target_func = self.current_function or self._module_level_func
        func_name = self._get_call_name(node.func)
        if func_name:
            callable_args = self._extract_callable_args(node)
            call_info = CallInfo(
                func_name=func_name,
                location=(node.lineno, node.col_offset),
                end_location=(
                    getattr(node, "end_lineno", node.lineno),
                    getattr(node, "end_col_offset", 0),
                ),
                is_async=False,
                containing_try_blocks=list(self.active_try_blocks),
                containing_suppress_blocks=list(self.active_suppress_blocks),
                callable_args=callable_args,
            )
            target_func.calls.append(call_info)

            logger.debug("found call to '%s' at line %d", func_name, node.lineno)
            if callable_args:
                logger.debug("call has callable args: %s", callable_args)

        self.generic_visit(node)

    @override
    def visit_Await(self, node: ast.Await) -> None:
        """
        visit await expressions to track async function calls.

        arguments:
            `node: ast.Await`
                the await expression node
        """
        # use current function or module-level synthetic function
        target_func = self.current_function or self._module_level_func
        if isinstance(node.value, ast.Call):
            call_node = node.value
            func_name = self._get_call_name(call_node.func)
            if func_name:
                callable_args = self._extract_callable_args(call_node)
                call_info = CallInfo(
                    func_name=func_name,
                    location=(node.lineno, node.col_offset),
                    end_location=(
                        getattr(node, "end_lineno", node.lineno),
                        getattr(node, "end_col_offset", 0),
                    ),
                    is_async=True,
                    containing_try_blocks=list(self.active_try_blocks),
                    containing_suppress_blocks=list(self.active_suppress_blocks),
                    callable_args=callable_args,
                )
                target_func.calls.append(call_info)

                logger.debug("found async call to '%s' at line %d", func_name, node.lineno)
                if callable_args:
                    logger.debug("call has callable args: %s", callable_args)

            # visit the call node's children (args, keywords) without calling visit_Call again
            for arg in call_node.args:
                self.visit(arg)
            for kw in call_node.keywords:
                self.visit(kw)
        else:
            # not a call, just visit children normally
            self.generic_visit(node)

    def _get_exception_type(self, node: ast.expr) -> str:
        """
        get the string representation of an exception type from an ast node.

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
        elif isinstance(node, ast.Tuple):
            # tuple of exception types - return comma-separated list
            types = [self._get_exception_type(elt) for elt in node.elts]
            return ",".join(types)
        else:
            return ""

    def _get_attribute_string(self, node: ast.Attribute) -> str:
        """
        convert an attribute access to a string.

        arguments:
            `node: ast.Attribute`
                the attribute node

        returns: `str`
            dot-separated attribute path
        """
        parts: list[str] = []
        current: ast.expr = node

        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value

        if isinstance(current, ast.Name):
            parts.append(current.id)

        return ".".join(reversed(parts))

    def _get_call_name(self, node: ast.expr) -> str | None:
        """
        get the name of a called function.

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

    def _get_decorator_name(self, node: ast.expr) -> str:
        """
        get the name of a decorator from its ast node.

        arguments:
            `node: ast.expr`
                the decorator expression node

        returns: `str`
            decorator name (empty string if cannot be determined)
        """
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_string(node)
        elif isinstance(node, ast.Call):
            # decorator with arguments, e.g., @lru_cache(maxsize=128)
            return self._get_decorator_name(node.func)
        return ""

    def _extract_callable_args(self, call: ast.Call) -> list[str]:
        """
        extract names of callables passed as arguments to a function call.

        detects function references, method references, and lambdas passed
        as positional or keyword arguments.

        arguments:
            `call: ast.Call`
                the call expression node

        returns: `list[str]`
            names of callable arguments (lambdas represented as '<lambda>')
        """
        callables: list[str] = []

        # check positional arguments
        for arg in call.args:
            if isinstance(arg, ast.Name):
                callables.append(arg.id)
            elif isinstance(arg, ast.Attribute):
                callables.append(self._get_attribute_string(arg))
            elif isinstance(arg, ast.Lambda):
                callables.append("<lambda>")

        # check keyword arguments
        for kw in call.keywords:
            if isinstance(kw.value, ast.Name):
                callables.append(kw.value.id)
            elif isinstance(kw.value, ast.Attribute):
                callables.append(self._get_attribute_string(kw.value))
            elif isinstance(kw.value, ast.Lambda):
                callables.append("<lambda>")

        return callables


def parse_file(file_path: str | Path) -> ExceptionVisitor:
    """
    parse a python file and return an exception visitor with collected info.

    arguments:
        `file_path: str | Path`
            path to the python file to parse

    returns: `ExceptionVisitor`
        visitor containing all exception information

    raises:
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
    parse python source code and return an exception visitor.

    arguments:
        `source: str`
            python source code to parse
        `module_name: str`
            name to use for the module

    returns: `ExceptionVisitor`
        visitor containing all exception information

    raises:
        `SyntaxError`
            if the source contains invalid python syntax
    """
    tree = ast.parse(source, filename=module_name)

    visitor = ExceptionVisitor(module_name=module_name)
    visitor.visit(tree)

    return visitor
