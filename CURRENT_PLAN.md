# Current Plan: Enhance RaiseAttention with Wrapper/HOF Traversal, Native Code Detection, and Debug Logging

**Status:** Complete ✅  
**Created:** 2025-01-XX  
**Last Updated:** 2025-02-02

---

## Summary

Enhance the exception flow analysis in RaiseAttention with four key features:

1. **Wrapper/HOF/Callable traversal** — Track exceptions through decorators, higher-order functions (map/filter/sorted), generic wrappers, and callable argument passing
2. **Native code detection** — Report `PossibleNativeException` for C extensions and unparseable stdlib/third-party functions (opt-out with `--no-warn-native`)
3. **Docstring heuristics** — Check `__doc__` for "raise"/"raises" keywords when we can't statically analyse a function
4. **Debug logging** — Add structured logging throughout the analysis pipeline for debugging

---

## Implementation Order

- [ ] **Feature 4: Debug logging** (do first — helps debug other features)
- [ ] **Feature 2: Native code detection** (`PossibleNativeException`)
- [ ] **Feature 3: Docstring heuristics**
- [ ] **Feature 1: Wrapper/HOF/Callable traversal** (most complex, benefits from debug logging)
- [ ] **Comprehensive tests** with synthetic code samples

---

## Feature 1: Wrapper/HOF/Callable Traversal

### Goal

Enable the analyser to track exceptions through ALL wrapper patterns — decorators, higher-order functions, generic wrappers, and any situation where callables are passed around.

### Files to Modify

- `src/raiseattention/ast_visitor.py` — Detect wrapper patterns in AST
- `src/raiseattention/external_analyser.py` — Follow callables passed to higher-order functions
- `src/raiseattention/analyser.py` — Handle wrapper resolution in signature computation

### Implementation Details

#### 1.1 Decorator Detection

**In `ast_visitor.py`:**

- Add `decorators: list[str]` field to `FunctionInfo` dataclass
- In `_process_function()`, capture decorators from `node.decorator_list`
- Track decorators that wrap functions: `@functools.wraps`, `@contextlib.contextmanager`, `@functools.lru_cache`, `@functools.cache`, custom decorators

#### 1.2 Callable Argument Detection

**In `ast_visitor.py`:**

- Add `callable_args: list[str]` field to `CallInfo` dataclass
- In `visit_Call()`, detect callable arguments:
  - Function names passed as positional args
  - Function names passed as keyword args (e.g., `key=func`)
  - Lambda expressions (track as `<lambda>`)

```python
def _extract_callable_args(self, call: ast.Call) -> list[str]:
    """extract function names passed as arguments to a call."""
    callables = []
    for arg in call.args:
        if isinstance(arg, ast.Name):
            callables.append(arg.id)
        elif isinstance(arg, ast.Attribute):
            callables.append(self._get_attribute_string(arg))
        elif isinstance(arg, ast.Lambda):
            callables.append("<lambda>")
    for kw in call.keywords:
        if isinstance(kw.value, ast.Name):
            callables.append(kw.value.id)
        elif isinstance(kw.value, ast.Attribute):
            callables.append(self._get_attribute_string(kw.value))
    return callables
```

#### 1.3 Higher-Order Function Recognition

**In `external_analyser.py`:**

Create a registry of known HOFs that invoke their callable arguments:

```python
# HOFs where the first positional arg is a callable that gets invoked
_CALLABLE_INVOKING_HOFS: Final[frozenset[str]] = frozenset({
    # builtins
    "map", "filter", "sorted", "min", "max", "reduce",
    # functools
    "functools.reduce", "functools.partial",
    # itertools
    "itertools.filterfalse", "itertools.takewhile", "itertools.dropwhile",
    "itertools.starmap", "itertools.groupby",
    # concurrent
    "concurrent.futures.ThreadPoolExecutor.submit",
    "concurrent.futures.ProcessPoolExecutor.submit",
    "asyncio.create_task", "asyncio.ensure_future",
})

# HOFs where 'key' kwarg is a callable
_KEY_CALLABLE_HOFS: Final[frozenset[str]] = frozenset({
    "sorted", "min", "max", "itertools.groupby",
    "heapq.nlargest", "heapq.nsmallest",
})
```

#### 1.4 Wrapper Resolution in Signature Computation

**In `analyser.py` — modify `get_function_signature()`:**

- Include exceptions from callable arguments passed to known HOFs
- Follow the callable argument's signature recursively

#### 1.5 Lambda Expression Handling

**In `ast_visitor.py`:**

- When encountering a lambda passed as argument, analyse its body for potential exceptions
- Track lambdas as anonymous functions that can contribute exceptions

---

## Feature 2: Native Code Detection (`PossibleNativeException`)

### Goal

When encountering C extensions or functions that cannot be statically analysed, report `PossibleNativeException` as a placeholder. Opt-out available via `--no-warn-native`.

### Files to Modify

- `src/raiseattention/external_analyser.py` — Main logic for detecting and reporting native code
- `src/raiseattention/analyser.py` — Integrate native code detection into signature computation
- `src/raiseattention/config.py` — Add `warn_native` configuration option
- `src/raiseattention/cli.py` — Add `--no-warn-native` flag

### Implementation Details

#### 2.1 Sentinel Exception

**In `external_analyser.py`:**

```python
POSSIBLE_NATIVE_EXCEPTION: Final[str] = "PossibleNativeException"
```

#### 2.2 Configuration

**In `config.py` — add to `AnalysisConfig`:**

```python
warn_native: bool = True  # Warn about possible native code exceptions
```

#### 2.3 CLI Flag (argparse)

**In `cli.py`:**

```python
parser.add_argument(
    "--no-warn-native",
    action="store_true",
    help="disable warnings about possible native code exceptions",
)

# In handler:
config.analysis.warn_native = not args.no_warn_native
```

#### 2.4 Detection Logic

**In `external_analyser.py` — modify `get_function_exceptions()`:**

- Check if module is a C extension → return `PossibleNativeException`
- Check if `spec.origin == "built-in"` → return `PossibleNativeException`
- If no static exceptions found for external function, check docstring and possibly return `PossibleNativeException`

---

## Feature 3: Docstring Heuristics

### Goal

When we can't statically analyse a function, check its `__doc__` for "raise" or "raises" keywords as a hint.

### Files to Modify

- `src/raiseattention/external_analyser.py` — Add docstring inspection logic

### Implementation Details

```python
def _check_docstring_for_raises(self, module_name: str, function_name: str) -> bool:
    """
    check if a function's docstring mentions raising exceptions.
    
    this is a heuristic for functions we can't statically analyse.
    """
    try:
        module = importlib.import_module(module_name)
        obj = module
        # Handle dotted function names (e.g., "JSONDecoder.decode")
        for part in function_name.split("."):
            obj = getattr(obj, part, None)
            if obj is None:
                return False
        
        if obj is not None and hasattr(obj, "__doc__") and obj.__doc__:
            doc_lower = obj.__doc__.lower()
            return "raise" in doc_lower or "raises" in doc_lower
    except (ImportError, AttributeError, TypeError):
        pass
    return False
```

---

## Feature 4: Debug Logging

### Goal

Add structured debug logging throughout the analysis pipeline for easier debugging.

### Files to Modify

- `src/raiseattention/analyser.py` — Core analysis logging
- `src/raiseattention/external_analyser.py` — External module resolution logging
- `src/raiseattention/ast_visitor.py` — AST traversal logging
- `src/raiseattention/cli.py` — Add `--debug` flag to enable debug logging

### Implementation Details

#### 4.1 Logger Setup

**In each module:**

```python
import logging

logger = logging.getLogger(__name__)
```

#### 4.2 CLI Flag (argparse)

**In `cli.py`:**

```python
parser.add_argument(
    "--debug",
    action="store_true",
    help="enable debug logging",
)

# In handler:
if args.debug:
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(name)s] %(message)s",
    )
```

#### 4.3 Key Debug Points

**In `analyser.py`:**
- `logger.debug(f"analysing file: {file_path}")` 
- `logger.debug(f"computing signature for: {qualified_name}")`
- `logger.debug(f"direct raises in '{func_name}': {direct_exceptions}")`
- `logger.debug(f"call to '{called_func_name}' at line {call_location[0]}")`
- `logger.debug(f"called function may raise: {called_exceptions}")`
- `logger.debug(f"exceptions handled by try-block: {handled_types}")`
- `logger.debug(f"unhandled exceptions at call site: {unhandled_exceptions}")`
- `logger.debug(f"final signature for '{func_name}': {result}")`

**In `external_analyser.py`:**
- `logger.debug(f"resolving module: {module_name}")`
- `logger.debug(f"module location: path={location.file_path}, stdlib={location.is_stdlib}, c_ext={location.is_c_extension}")`
- `logger.debug(f"following import: {function_name} -> {import_path}")`
- `logger.debug(f"detected native code in: {module_name}")`
- `logger.debug(f"checking docstring for: {module_name}.{function_name}")`
- `logger.debug(f"cache hit for: {module_name}")`

**In `ast_visitor.py`:**
- `logger.debug(f"visiting function: {qualified_name}")`
- `logger.debug(f"function has decorators: {decorators}")`
- `logger.debug(f"found raise statement: {exc_type} at line {node.lineno}")`
- `logger.debug(f"found call to '{func_name}' at line {node.lineno}")`
- `logger.debug(f"call has callable args: {callable_args}")`
- `logger.debug(f"entering try-block at line {node.lineno}")`

---

## Test Plan

### New Synthetic Code Samples

Add to `tests/fixtures/code_samples.py`:

1. `create_decorator_wrapper_file()` — Decorator wrapper patterns
2. `create_hof_callable_file()` — Higher-order function patterns
3. `create_callable_passing_file()` — Callable passing patterns
4. `create_native_code_test_file()` — Native/C extension code usage

### New Test Cases

#### In `tests/test_analyser.py` — TestWrapperTraversal class (~12 tests):

- `test_decorated_function_exceptions_propagate`
- `test_lru_cache_decorated_exceptions_propagate`
- `test_context_manager_exceptions_propagate`
- `test_map_with_risky_callable`
- `test_filter_with_risky_predicate`
- `test_sorted_with_risky_key`
- `test_reduce_with_risky_function`
- `test_callable_passed_to_executor`
- `test_callable_in_class_callback`
- `test_safe_map_no_flag`
- `test_nested_hof_calls`
- `test_lambda_with_risky_body`

#### In `tests/test_analyser.py` — TestDebugLogging class (~2 tests):

- `test_debug_logging_enabled`
- `test_debug_logging_shows_signature_computation`

#### In `tests/test_external_analyser.py` — TestNativeCodeDetection class (~5 tests):

- `test_c_extension_returns_possible_native_exception`
- `test_builtin_returns_possible_native_exception`
- `test_no_warn_native_suppresses_warning`
- `test_docstring_with_raises_triggers_warning`
- `test_docstring_without_raises_no_false_positive`

#### In `tests/test_ast_visitor.py` — TestCallableArgDetection class (~4 tests):

- `test_detects_function_passed_to_map`
- `test_detects_lambda_passed_to_filter`
- `test_detects_key_kwarg_callable`
- `test_detects_decorators`

---

## Files to Modify Summary

| File | Changes |
|------|---------|
| `src/raiseattention/analyser.py` | Debug logging, HOF signature resolution, native code integration |
| `src/raiseattention/external_analyser.py` | Debug logging, `PossibleNativeException`, docstring heuristics, HOF registry |
| `src/raiseattention/ast_visitor.py` | Debug logging, decorator detection, callable argument detection |
| `src/raiseattention/config.py` | Add `warn_native: bool = True` to `AnalysisConfig` |
| `src/raiseattention/cli.py` | Add `--debug` and `--no-warn-native` flags |
| `tests/fixtures/code_samples.py` | Add 4 new synthetic code generators |
| `tests/test_analyser.py` | Add ~14 new test cases |
| `tests/test_external_analyser.py` | Add ~5 new test cases |
| `tests/test_ast_visitor.py` | Add ~4 new test cases |

---

## Design Decisions

1. **HOF False Positives**: Conservative approach — only flag exceptions from callable args when passed to *known* HOFs in the registry. Custom functions that accept callables will only be tracked if we can see they invoke the callable in their body.

2. **Performance**: Use `frozenset` for HOF registry (O(1) lookups), avoid redundant AST traversals, cache docstring lookup results, keep callable argument extraction in the same visitor pass.

3. **Callable Tracking**: Leverage existing `get_function_signature()` recursion to follow callable arguments the same way we follow regular function calls.

---

## Progress Tracking

### Feature 4: Debug Logging
- [x] Add logger to `analyser.py`
- [x] Add logger to `external_analyser.py`
- [x] Add logger to `ast_visitor.py`
- [x] Add `--debug` flag to `cli.py`
- [x] Add debug log statements throughout

### Feature 2: Native Code Detection
- [x] Add `POSSIBLE_NATIVE_EXCEPTION` constant
- [x] Add `warn_native` to config
- [x] Add `--no-warn-native` to CLI
- [x] Implement native code detection in `get_function_exceptions()`
- [x] Add tests

### Feature 3: Docstring Heuristics
- [x] Implement `_check_docstring_for_raises()`
- [x] Integrate with native code detection
- [x] Add tests

### Feature 1: Wrapper/HOF/Callable Traversal
- [x] Add `decorators` field to `FunctionInfo`
- [x] Add `callable_args` field to `CallInfo`
- [x] Implement `_extract_callable_args()`
- [x] Add HOF registry
- [x] Update `get_function_signature()` to follow callable args
- [x] Handle lambda expressions (gracefully skipped)
- [x] Add synthetic code samples
- [x] Add tests

### Final
- [x] Run full test suite (178 passed, 1 skipped)
- [x] Update AGENTS.md if needed
- [x] Update CURRENT_PLAN.md to mark completed items

