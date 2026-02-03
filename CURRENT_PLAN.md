# Current Plan: Complete Exception Detection for builtins.open

## Context

RaiseAttention is a static exception flow analyser for Python. When analysing code like:

```python
_ = open("README.md", "r", encoding="utf-8").read()
```

We want to report **all** exceptions that `open()` can raise, not just the ones detectable from C source analysis.

## What We've Done

### Session 1: CLI Improvements
- Added "N issues found" summary output (like basedpyright)
- Added `--no-cache` CLI flag
- Fixed module-level exception detection (code outside functions)

### Session 2: Builtins Module Support

1. **Fixed stub resolver bug** (`stub_resolver.py`)
   - `_exact_match()` was incorrectly rejecting exception dicts like `{"TypeError": "exact"}`
   - Added `_is_exception_dict()` helper to distinguish from class dicts

2. **Added builtins to standardstubber** (`analyser.py`)
   - Extended `find_c_modules()` to scan `Python/bltinmodule.c`
   - Regenerated `python-3.12.pyras` with 47 builtin functions

3. **Added introspection-based resolution** (`external_analyser.py`)
   - `_get_builtin_canonical_module()` uses `func.__module__` to find canonical module
   - `open.__module__` returns `'_io'`, so `open` → `_io.open` automatically
   - No hacky redirect maps to maintain

### Session 3: Python Source Analysis - COMPLETED ✅

#### Goal
Show ALL exceptions for `open()` by **proper means** - analysing Python source code from CPython tarballs, not hacky mapping dicts.

#### Implementation

1. **Added `find_python_modules()` to `analyser.py`** (lines 1518-1607)
   - Scans `Lib/*.py` and `Lib/**/*.py` in CPython source
   - Filters out test modules, idlelib, tkinter, etc.
   - Returns `list[tuple[Path, module_name]]`

2. **Created `python_analyser.py`** - NEW FILE containing:
   - `PYTHON_TO_C_MAPPING` - Maps reference implementations to C modules (`_pyio` → `_io`)
   - `OS_SYSCALL_EXCEPTIONS` - Known exception signatures for `os.open()`, `os.stat()`, etc.
   - `PythonFunctionInfo` dataclass - Tracks function-level exception info
   - `ExceptionVisitor` class - AST visitor that extracts `raise` statements and function calls
   - `PythonAnalyser` class - Main analyser with:
     - `analyse_module()` - Analyses single Python file
     - `_compute_transitive_raises()` - Fixpoint iteration for call graph propagation
     - **Class instantiation detection** - `ClassName()` → `ClassName.__init__` exceptions
     - `analyse_all()` - Batch analysis returning raw stub tuples

3. **Updated `cli.py`** to integrate Python analysis:
   - Phase 1: C source analysis (parallel with ProcessPoolExecutor)
   - Phase 2: Python source analysis (sequential, fast AST parsing)
   - Stub merging using `_merge_stubs()` function:
     - Union all exception types from both sources
     - Use `exact` confidence if either source reports exact
     - Combine notes from both sources

4. **Regenerated `python-3.12.pyras` stubs**:
   - **Before:** 1652 C-only stubs
   - **After:** 6165 merged stubs (C + Python analysis)

#### Final Output

```
$ uv run raiseattention check examples/read.py --no-cache
examples\read.py:1:4: error: call to 'open' may raise unhandled exception(s): ValueError, TypeError, PermissionError, IsADirectoryError, FileNotFoundError, NotADirectoryError, LookupError, OSError, FileExistsError
1 issue found
```

All OS-level exceptions are now detected:
- `FileNotFoundError` - file doesn't exist
- `PermissionError` - no access
- `IsADirectoryError` - tried to open a directory
- `NotADirectoryError` - path component isn't a directory
- `FileExistsError` - exclusive create mode but file exists
- `OSError` - generic I/O error
- `TypeError` - wrong argument types
- `ValueError` - invalid mode string
- `LookupError` - unknown encoding

#### Architecture

**Where:** In **standardstubber**, not raiseattention.

Rationale:
- standardstubber already extracts CPython tarballs and analyses them
- It generates `.pyras` files at build time (not runtime)
- The stubs ship with raiseattention
- This keeps the architecture clean: standardstubber → stubs → raiseattention

#### Files Modified

| File | Action | Status |
|------|--------|--------|
| `src/standardstubber/standardstubber/python_analyser.py` | CREATE | ✅ Done |
| `src/standardstubber/standardstubber/analyser.py` | MODIFY | ✅ Done |
| `src/standardstubber/standardstubber/cli.py` | MODIFY | ✅ Done |
| `src/raiseattention/stubs/stdlib/python-3.12.pyras` | REGENERATE | ✅ Done |

## Test Results

All 178 tests pass:
```
tests\test_analyser.py .........................
tests\test_analyzer_synthetic.py ........s............
tests\test_ast_visitor.py ....................
tests\test_cache.py ............
tests\test_cli.py ................
tests\test_config.py ............
tests\test_env_detector.py ................
tests\test_external_analyser.py ..............................
tests\test_lsp_server.py ...........................
======================= 178 passed, 1 skipped in 4.71s ========================
```

## References

- CPython `Lib/_pyio.py`: https://github.com/python/cpython/blob/main/Lib/_pyio.py
- Python docs on `open()`: https://docs.python.org/3/library/functions.html#open
- Current stubs: `src/raiseattention/stubs/stdlib/python-3.12.pyras`
