"""
python source analyser for exception extraction.

analyses python source files to find raise statements and build
function-level exception signatures. used alongside the c analyser
to provide complete stdlib exception coverage.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from .models import Confidence, FunctionStub

logger = logging.getLogger(__name__)


# mapping from python reference implementations to c module names
# when analysing _pyio.py, we generate stubs for _io as well
PYTHON_TO_C_MAPPING: Final[dict[str, str]] = {
    "_pyio": "_io",
    "_pydecimal": "_decimal",
    "_pydatetime": "_datetime",
}

# known os syscall exception signatures
# these are documented by cpython and represent errno -> exception mappings
OS_SYSCALL_EXCEPTIONS: Final[dict[str, frozenset[str]]] = {
    # file operations
    "os.open": frozenset(
        {
            "FileNotFoundError",
            "PermissionError",
            "FileExistsError",
            "IsADirectoryError",
            "NotADirectoryError",
            "OSError",
        }
    ),
    "os.close": frozenset({"OSError"}),
    "os.read": frozenset({"OSError", "BlockingIOError"}),
    "os.write": frozenset({"OSError", "BlockingIOError"}),
    "os.stat": frozenset({"FileNotFoundError", "PermissionError", "OSError"}),
    "os.lstat": frozenset({"FileNotFoundError", "PermissionError", "OSError"}),
    "os.fstat": frozenset({"OSError"}),
    "os.lseek": frozenset({"OSError"}),
    "os.truncate": frozenset({"FileNotFoundError", "PermissionError", "OSError"}),
    "os.ftruncate": frozenset({"OSError"}),
    "os.remove": frozenset(
        {
            "FileNotFoundError",
            "PermissionError",
            "IsADirectoryError",
            "OSError",
        }
    ),
    "os.unlink": frozenset(
        {
            "FileNotFoundError",
            "PermissionError",
            "IsADirectoryError",
            "OSError",
        }
    ),
    "os.rename": frozenset(
        {
            "FileNotFoundError",
            "FileExistsError",
            "PermissionError",
            "IsADirectoryError",
            "NotADirectoryError",
            "OSError",
        }
    ),
    "os.mkdir": frozenset(
        {
            "FileExistsError",
            "PermissionError",
            "FileNotFoundError",
            "OSError",
        }
    ),
    "os.makedirs": frozenset(
        {
            "FileExistsError",
            "PermissionError",
            "FileNotFoundError",
            "OSError",
        }
    ),
    "os.rmdir": frozenset(
        {
            "FileNotFoundError",
            "PermissionError",
            "OSError",
        }
    ),
    "os.listdir": frozenset(
        {
            "FileNotFoundError",
            "PermissionError",
            "NotADirectoryError",
            "OSError",
        }
    ),
    "os.scandir": frozenset(
        {
            "FileNotFoundError",
            "PermissionError",
            "NotADirectoryError",
            "OSError",
        }
    ),
    "os.chdir": frozenset(
        {
            "FileNotFoundError",
            "PermissionError",
            "NotADirectoryError",
            "OSError",
        }
    ),
    "os.getcwd": frozenset({"OSError"}),
    "os.chmod": frozenset({"FileNotFoundError", "PermissionError", "OSError"}),
    "os.chown": frozenset({"FileNotFoundError", "PermissionError", "OSError"}),
    "os.link": frozenset(
        {
            "FileNotFoundError",
            "FileExistsError",
            "PermissionError",
            "OSError",
        }
    ),
    "os.symlink": frozenset(
        {
            "FileExistsError",
            "PermissionError",
            "OSError",
        }
    ),
    "os.readlink": frozenset(
        {
            "FileNotFoundError",
            "PermissionError",
            "OSError",
        }
    ),
    "os.access": frozenset({"OSError"}),
    # path operations that may raise
    "os.path.exists": frozenset({"OSError"}),
    "os.path.isfile": frozenset({"OSError"}),
    "os.path.isdir": frozenset({"OSError"}),
    "os.path.getsize": frozenset({"FileNotFoundError", "OSError"}),
    "os.path.getmtime": frozenset({"FileNotFoundError", "OSError"}),
    "os.path.getatime": frozenset({"FileNotFoundError", "OSError"}),
    "os.path.getctime": frozenset({"FileNotFoundError", "OSError"}),
    # os.fspath can raise TypeError
    "os.fspath": frozenset({"TypeError"}),
}


@dataclass
class PythonFunctionInfo:
    """
    information about a python function for exception analysis.

    attributes:
        `name: str`
            function name (without class prefix)
        `qualname: str`
            qualified name (e.g., "FileIO.__init__")
        `local_raises: set[str]`
            exceptions explicitly raised in this function
        `calls: set[str]`
            function calls made (for propagation)
        `propagated_raises: set[str]`
            exceptions from called functions (computed by fixpoint)
    """

    name: str
    qualname: str
    local_raises: set[str] = field(default_factory=set)
    calls: set[str] = field(default_factory=set)
    propagated_raises: set[str] = field(default_factory=set)


class ExceptionVisitor(ast.NodeVisitor):
    """
    ast visitor that extracts exception information from python source.

    tracks:
    - `raise ExceptionType` statements
    - `raise ExceptionType(...)` statements
    - bare `raise` statements (re-raise)
    - function calls for propagation
    """

    def __init__(self) -> None:
        self.functions: dict[str, PythonFunctionInfo] = {}
        self._current_class: str | None = None
        self._current_function: str | None = None
        self._current_qualname: str | None = None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """visit a class definition."""
        old_class = self._current_class
        self._current_class = node.name
        self.generic_visit(node)
        self._current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """visit a function definition."""
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """visit an async function definition."""
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """common handler for function definitions."""
        old_function = self._current_function
        old_qualname = self._current_qualname

        self._current_function = node.name
        if self._current_class:
            self._current_qualname = f"{self._current_class}.{node.name}"
        else:
            self._current_qualname = node.name

        # create function info
        func_info = PythonFunctionInfo(
            name=node.name,
            qualname=self._current_qualname,
        )
        self.functions[self._current_qualname] = func_info

        # visit body
        self.generic_visit(node)

        self._current_function = old_function
        self._current_qualname = old_qualname

    def visit_Raise(self, node: ast.Raise) -> None:
        """visit a raise statement."""
        if self._current_qualname is None:
            # module-level raise - ignore for now
            return

        func_info = self.functions.get(self._current_qualname)
        if func_info is None:
            return

        exc_type = self._get_exception_type(node.exc)
        if exc_type:
            func_info.local_raises.add(exc_type)

    def visit_Call(self, node: ast.Call) -> None:
        """visit a function call."""
        if self._current_qualname is None:
            return

        func_info = self.functions.get(self._current_qualname)
        if func_info is None:
            self.generic_visit(node)
            return

        # get called function name
        call_name = self._get_call_name(node)
        if call_name:
            func_info.calls.add(call_name)

        self.generic_visit(node)

    def _get_exception_type(self, exc: ast.expr | None) -> str | None:
        """
        extract exception type name from raise expression.

        arguments:
            `exc: ast.expr | None`
                the exception expression (None for bare raise)

        returns: `str | None`
            exception type name, or none for bare raise
        """
        if exc is None:
            # bare raise - we can't statically determine the type
            return None

        # raise ExceptionType
        if isinstance(exc, ast.Name):
            return exc.id

        # raise ExceptionType(...)
        if isinstance(exc, ast.Call):
            if isinstance(exc.func, ast.Name):
                return exc.func.id
            if isinstance(exc.func, ast.Attribute):
                # module.ExceptionType(...)
                return self._get_attribute_name(exc.func)

        # raise module.ExceptionType
        if isinstance(exc, ast.Attribute):
            return self._get_attribute_name(exc)

        return None

    def _get_attribute_name(self, node: ast.Attribute) -> str:
        """get full attribute name (e.g., 'os.error')."""
        parts: list[str] = [node.attr]
        current: ast.expr = node.value
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))

    def _get_call_name(self, node: ast.Call) -> str | None:
        """
        get called function name.

        arguments:
            `node: ast.Call`
                the call node

        returns: `str | None`
            function name or none if can't determine
        """
        if isinstance(node.func, ast.Name):
            return node.func.id

        if isinstance(node.func, ast.Attribute):
            return self._get_attribute_name(node.func)

        return None


class PythonAnalyser:
    """
    analyses python source files for exception signatures.

    uses ast to parse source and extract raise statements,
    then computes transitive exception propagation through
    the call graph.
    """

    def __init__(self) -> None:
        self._module_cache: dict[str, dict[str, PythonFunctionInfo]] = {}

    def analyse_module(self, path: Path, module_name: str) -> list[FunctionStub]:
        """
        analyse a single python module for exceptions.

        arguments:
            `path: Path`
                path to .py file
            `module_name: str`
                module name (e.g., "_pyio")

        returns: `list[FunctionStub]`
            function stubs with exception signatures
        """
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.warning("failed to read %s: %s", path, e)
            return []

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as e:
            logger.warning("failed to parse %s: %s", path, e)
            return []

        # extract function information
        visitor = ExceptionVisitor()
        visitor.visit(tree)

        # cache for cross-module lookups
        self._module_cache[module_name] = visitor.functions

        # compute transitive raises
        self._compute_transitive_raises(visitor.functions, module_name)

        # generate stubs
        stubs: list[FunctionStub] = []
        for func_info in visitor.functions.values():
            effective_raises = func_info.local_raises | func_info.propagated_raises

            if not effective_raises:
                continue

            qualname = f"{module_name}.{func_info.qualname}"
            stub = FunctionStub(
                qualname=qualname,
                raises=frozenset(effective_raises),
                confidence=Confidence.EXACT,
                notes="from python source analysis",
            )
            stubs.append(stub)

        # also generate stubs for c module mapping
        if module_name in PYTHON_TO_C_MAPPING:
            c_module = PYTHON_TO_C_MAPPING[module_name]
            for stub in list(stubs):
                c_qualname = stub.qualname.replace(f"{module_name}.", f"{c_module}.", 1)
                c_stub = FunctionStub(
                    qualname=c_qualname,
                    raises=stub.raises,
                    confidence=stub.confidence,
                    notes=f"from {module_name} python source",
                )
                stubs.append(c_stub)

        return stubs

    def _compute_transitive_raises(
        self,
        functions: dict[str, PythonFunctionInfo],
        _module_name: str,
    ) -> None:
        """
        compute transitive exception propagation.

        follows function calls and propagates exceptions from callees
        to callers using fixpoint iteration.

        arguments:
            `functions: dict[str, PythonFunctionInfo]`
                function map from visitor
            `_module_name: str`
                current module name (reserved for future cross-module lookups)
        """
        changed = True
        iterations = 0
        max_iterations = 100

        while changed and iterations < max_iterations:
            changed = False
            iterations += 1

            for func_info in functions.values():
                before = len(func_info.propagated_raises)

                for call_name in func_info.calls:
                    # check os syscall exceptions first
                    if call_name in OS_SYSCALL_EXCEPTIONS:
                        func_info.propagated_raises |= OS_SYSCALL_EXCEPTIONS[call_name]
                        continue

                    # check for os.* prefixed calls
                    if call_name.startswith("os."):
                        full_name = call_name
                        if full_name in OS_SYSCALL_EXCEPTIONS:
                            func_info.propagated_raises |= OS_SYSCALL_EXCEPTIONS[full_name]
                            continue

                    # check local functions
                    callee = functions.get(call_name)
                    if callee:
                        func_info.propagated_raises |= callee.local_raises
                        func_info.propagated_raises |= callee.propagated_raises
                        continue

                    # check for class instantiation (ClassName -> ClassName.__init__)
                    init_name = f"{call_name}.__init__"
                    callee = functions.get(init_name)
                    if callee:
                        func_info.propagated_raises |= callee.local_raises
                        func_info.propagated_raises |= callee.propagated_raises
                        continue

                    # check for self.method or cls.method calls
                    if "." in call_name:
                        parts = call_name.split(".")
                        if parts[0] in ("self", "cls") and len(parts) == 2:
                            method_name = parts[1]
                            # look for method in same class
                            for qname, callee in functions.items():
                                if qname.endswith(f".{method_name}"):
                                    func_info.propagated_raises |= callee.local_raises
                                    func_info.propagated_raises |= callee.propagated_raises

                if len(func_info.propagated_raises) != before:
                    changed = True

    def analyse_all(
        self,
        modules: list[tuple[Path, str]],
    ) -> list[tuple[str, frozenset[str], str, str]]:
        """
        analyse multiple python modules.

        arguments:
            `modules: list[tuple[Path, str]]`
                list of (path, module_name) tuples

        returns: `list[tuple[str, frozenset[str], str, str]]`
            raw stub tuples (qualname, raises, confidence, notes)
        """
        all_stubs: list[tuple[str, frozenset[str], str, str]] = []

        for path, module_name in modules:
            stubs = self.analyse_module(path, module_name)
            for stub in stubs:
                all_stubs.append(
                    (
                        stub.qualname,
                        stub.raises,
                        stub.confidence.value,
                        stub.notes,
                    )
                )

        return all_stubs
