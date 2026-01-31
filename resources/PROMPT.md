# RaiseAttention: Python Exception Flow Analyzer & LSP

> **Disclaimer:** This project is vibe coded, as a test of Kimi K2.5.
>
> This is also basically the prompt used to generate the code, and I one day hope
> to be able to zero-shot prompt for tooling of this caliber.

## Overview

RaiseAttention (RA) is a **static exception flow analyzer** that identifies unhandled exceptions in your Python codebase, even when you think they're handled.

## Core Functionality

### 1. Exception Flow Analysis

**What it does:**
- Statically analyzes Python code to detect all possible exception paths
- Traces exception propagation through function call chains
- Identifies unhandled exceptions, even from external libraries
- Flags functions that may raise exceptions but don't declare or handle them

**Key features:**
- **Whole-program analysis**: Follows exception flows across module boundaries
- **Library introspection**: Analyzes imported dependencies to discover their exception signatures
- **Control flow awareness**: Understands try-except blocks, if-statements guarding raises, and context managers
- **Suppression detection**: Recognizes valid exception suppression patterns (logging, swallowing with justification)

**Example:**

```python
# This looks safe, but RA will flag it
import requests

def fetch_user(user_id: int) -> dict:
    response = requests.get(f"https://api.example.com/users/{user_id}")
    return response.json()  # Can raise: requests.RequestException, JSONDecodeError
    
# RA Error: fetch_user() may raise RequestException, JSONDecodeError but doesn't handle them
```

**To fix:**
```python
def fetch_user(user_id: int) -> dict:
    try:
        response = requests.get(f"https://api.example.com/users/{user_id}")
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch user {user_id}: {e}")
        raise  # Re-raise after logging (RA recognizes this)
    except json.JSONDecodeError:
        return {}  # Handled by returning default
```

### 2. LSP Server Integration

**What it provides:**
- **Real-time diagnostics**: Exception warnings as you type, integrated into your editor
- **Code actions**: Quick fixes to wrap code in try-except blocks
- **Hover information**: Shows which exceptions a function may raise
- **Go-to-definition**: Jump to exception class definitions from raise statements

**LSP Features:**

| Feature | Description | Example |
|---------|-------------|---------|
| **Diagnostics** | Red squiggles for unhandled exceptions | `requests.get()` → ⚠️ May raise RequestException |
| **Code Actions** | Quick fix: "Wrap in try-except" | Right-click → "Add exception handler" |
| **Hover** | Shows exception signature | Hover over function → "Raises: ValueError, KeyError" |
| **Completion** | Suggests exception types in except clauses | `except <Tab>` → Shows relevant exceptions |

**Editor support:**
- VS Code (via LSP client)
- Neovim (via built-in LSP)
- Emacs (via lsp-mode)
- Any editor with LSP support

### 3. Virtual Environment Detection

**Why this matters:**
To accurately analyze your code, RA needs to import and inspect your dependencies. This requires detecting and using the correct Python environment for your project.

**Detection strategy:**
RA uses the [environment detection pseudospec](resources/VENV_DETECTION.md) to automatically discover:

1. **Which tool manages your project** (Poetry, Pipenv, PDM, uv, Rye, Hatch, standard venv, pyenv)
2. **Where the virtual environment is located** (global cache vs. in-project `.venv`)
3. **Which Python executable to use** for running analysis

**Detection priority:**
1. Check for `poetry.lock` → Use Poetry's venv
2. Check for `Pipfile.lock` → Use Pipenv's venv
3. Check for `pdm.lock` → Use PDM's venv
4. Check for `uv.lock` + `.venv` → Use uv's venv
5. Check for `rye.lock` + `.venv` → Use Rye's venv
6. Check for Hatch config → Parse `pyproject.toml`
7. Check for `.venv/pyvenv.cfg` → Standard venv
8. Check for `.python-version` → pyenv/asdf
9. Fallback to `$VIRTUAL_ENV` if activated

**Cross-platform support:**
- macOS/Linux: `~/.cache/pypoetry/virtualenvs/`, `.venv/bin/python`
- Windows: `%APPDATA%\pypoetry\Cache\virtualenvs\`, `.venv\Scripts\python.exe`

**Configuration:**
Users can override detection with:
```toml
# pyproject.toml or .raiseattention.toml
[tool.raiseattention]
python_path = "/path/to/specific/python"  # Override detected Python
venv_path = "/path/to/venv"  # Override detected venv
```

---

## Caching Strategy

**Problem:** Static analysis is expensive. Analyzing a large codebase from scratch on every keystroke is infeasible for LSP responsiveness.

**Solution:** Implement a **multi-tier incremental caching system** that reuses previous analysis results whenever possible.

### Tier 1: File-Level Cache (Fast Path)

**What to cache:**
- Parsed AST (Abstract Syntax Tree) for each file
- Exception signatures for each function/method
- Import graph (which modules import which)
- Hash of file content (SHA-256) for invalidation

**Invalidation triggers:**
- File modification detected via:
  - **mtime** (modification time) - Fast check via filesystem metadata
  - **File size change** - Quick validation
  - **Content hash** - Definitive change detection using SHA-256
  - **Git state** - Invalidate on branch switch, commit, merge, rebase

**Implementation:**
```python
class FileAnalysisCache:
    def get_analysis(self, file_path: str) -> Optional[FileAnalysis]:
        """Return cached analysis if file hasn't changed."""
        entry = self.cache.get(file_path)
        if entry is None:
            return None
        
        # Fast invalidation checks
        current_mtime = os.path.getmtime(file_path)
        current_size = os.path.getsize(file_path)
        
        if entry.mtime != current_mtime or entry.size != current_size:
            return None  # File changed, invalidate
        
        # Definitive check: content hash
        current_hash = self._hash_file(file_path)
        if entry.content_hash != current_hash:
            return None
        
        return entry.analysis
    
    def store_analysis(self, file_path: str, analysis: FileAnalysis):
        """Cache analysis result with metadata."""
        self.cache[file_path] = CacheEntry(
            analysis=analysis,
            mtime=os.path.getmtime(file_path),
            size=os.path.getsize(file_path),
            content_hash=self._hash_file(file_path),
            timestamp=time.time(),
        )
```

**Storage location:**
- Store cache in `.raiseattention/cache/` directory (gitignored)
- Use pickle or JSON for serialization
- Implement LRU eviction (max 10,000 files by default)

**Performance goals:**
- Cache hit: <1ms to retrieve analysis
- Cache miss: Full analysis (500-2000ms for large file)
- Warm cache: 25-50x faster than cold cache

### Tier 2: Dependency Analysis Cache (Medium Path)

**What to cache:**
- Exception signatures of external libraries (e.g., `requests`, `boto3`)
- These rarely change unless dependencies are upgraded
- Store as: `{package_name}@{version}` → exception map

**Invalidation triggers:**
- Dependency version change detected via:
  - `poetry.lock` / `Pipfile.lock` / `pdm.lock` / `uv.lock` hash change
  - `pyproject.toml` / `Pipfile` / `requirements.txt` modification

**Implementation:**
```python
class DependencyCache:
    def get_exceptions(self, package: str, version: str) -> Optional[ExceptionMap]:
        """Get cached exception signatures for a package version."""
        cache_key = f"{package}@{version}"
        return self.cache.get(cache_key)
    
    def store_exceptions(self, package: str, version: str, exceptions: ExceptionMap):
        """Cache exception signatures for a package version."""
        cache_key = f"{package}@{version}"
        self.cache[cache_key] = exceptions
```

**Storage:**
- Global cache in `~/.cache/raiseattention/dependencies/`
- Shared across projects (if they use same package version)
- Never expires (packages are immutable once published)

### Tier 3: Incremental Analysis (Smart Recomputation)

**What to reanalyze:**
When a file changes, only reanalyze:
1. The changed file itself
2. Files that import the changed file (direct dependents)
3. Files that transitively depend on changed symbols (if function signature changed)

**Change impact detection:**
```python
class IncrementalAnalyzer:
    def analyze_change(self, changed_file: str) -> AnalysisResult:
        """Only reanalyze affected files."""
        # 1. Analyze changed file
        new_analysis = self.analyze_file(changed_file)
        old_analysis = self.cache.get_analysis(changed_file)
        
        # 2. Detect what changed (new functions, changed signatures, etc.)
        changes = self._detect_changes(old_analysis, new_analysis)
        
        # 3. Find affected files
        if changes.is_signature_change():
            # Signature changed → reanalyze all dependents
            affected = self.import_graph.get_dependents(changed_file)
        elif changes.is_internal_only():
            # Only internal implementation changed → no propagation
            affected = []
        else:
            # New exports → reanalyze direct importers
            affected = self.import_graph.get_direct_importers(changed_file)
        
        # 4. Reanalyze affected files
        for file in affected:
            self.analyze_file(file)
        
        return AnalysisResult(analyzed=[changed_file] + affected)
```

**Performance goals:**
- Single file change: Reanalyze 1-5 files (not entire codebase)
- LSP responsiveness: <200ms from keystroke to diagnostic

### Tier 4: LSP-Specific Optimizations

**Debouncing:**
- Don't reanalyze on every keystroke
- Debounce interval: 500ms (configurable)
- If user stops typing for 500ms → trigger analysis

**Partial analysis:**
- For hover/completion requests, only analyze the current function scope
- Don't need whole-file analysis for some LSP features

**Background analysis:**
- Run full project analysis in background thread
- Keep main thread responsive for LSP requests
- Update diagnostics asynchronously

**Implementation:**
```python
class LSPServer:
    def __init__(self):
        self.analyzer = IncrementalAnalyzer()
        self.pending_changes = {}
        self.debounce_timer = None
    
    def on_did_change(self, uri: str, changes: List[TextEdit]):
        """File changed in editor."""
        # Store change but don't analyze yet
        self.pending_changes[uri] = changes
        
        # Reset debounce timer
        if self.debounce_timer:
            self.debounce_timer.cancel()
        
        # Analyze after 500ms of inactivity
        self.debounce_timer = Timer(0.5, lambda: self._analyze_pending())
        self.debounce_timer.start()
    
    def _analyze_pending(self):
        """Analyze all pending changes."""
        for uri, changes in self.pending_changes.items():
            result = self.analyzer.analyze_change(uri)
            self.publish_diagnostics(uri, result.diagnostics)
        
        self.pending_changes.clear()
```

### Cache Management

**CLI commands:**
```bash
# Show cache status
raiseattention cache status
# Output: 450 files cached (120 MB), 95% hit rate

# Clear file cache (keep dependency cache)
raiseattention cache clear --files

# Clear all caches
raiseattention cache clear --all

# Prune stale entries (deleted files)
raiseattention cache prune
```

**Configuration:**
```toml
[tool.raiseattention.cache]
enabled = true
max_file_entries = 10000  # LRU eviction threshold
max_memory_mb = 500  # Memory limit
ttl_hours = 24  # Unused entries expire after 24h
```

---

## Exception Handling Philosophy

### What RA Considers "Handled"

**✅ Valid handling patterns:**

1. **Try-except with specific exception:**
   ```python
   try:
       risky_operation()
   except ValueError as e:
       logger.error(f"Invalid value: {e}")
   ```

2. **Try-except-re-raise:**
   ```python
   try:
       risky_operation()
   except Exception as e:
       logger.error(f"Operation failed: {e}")
       raise  # RA recognizes this as handled (logged then propagated)
   ```

3. **Documented propagation:**
   ```python
   def my_function():
       """May raise ValueError, KeyError."""
       risky_operation()  # RA: OK, docstring declares exceptions
   ```

4. **Return None/default on exception:**
   ```python
   try:
       return risky_operation()
   except ValueError:
       return None  # RA: OK, exception converted to None return
   ```

5. **Context manager handling:**
   ```python
   with contextlib.suppress(FileNotFoundError):
       os.remove(file_path)  # RA: OK, exception explicitly suppressed
   ```

**❌ Invalid patterns (RA will flag):**

1. **Bare except without re-raise:**
   ```python
   try:
       risky_operation()
   except Exception:
       pass  # RA Error: Exception swallowed without handling
   ```

2. **Undocumented exception propagation:**
   ```python
   def my_function():
       risky_operation()  # RA Error: May raise ValueError but not declared
   ```

3. **Incomplete exception handling:**
   ```python
   try:
       data = json.loads(response.text)  # Can raise JSONDecodeError
   except requests.RequestException:
       pass  # RA Error: JSONDecodeError not handled
   ```

### Suppression Mechanisms

**1. Inline suppression (for specific lines):**
```python
risky_call()  # raiseattention: ignore[RequestException]
# or
risky_call()  # type: ignore[raiseattention]
```

**2. Function-level suppression:**
```python
@raiseattention.suppress(ValueError, KeyError)
def my_function():
    risky_operation()  # RA won't flag ValueError/KeyError here
```

**3. File-level suppression:**
```python
# raiseattention: ignore-file
# Entire file skipped from analysis
```

**4. Configuration-based suppression:**
```toml
[tool.raiseattention]
# Ignore specific exception types globally
ignore_exceptions = ["KeyboardInterrupt", "SystemExit"]

# Ignore exceptions from specific modules
ignore_modules = ["tests.*", "*.migrations.*"]
```

---

## Usage Patterns

### CLI Mode (CI/CD Integration)

**Basic analysis:**
```bash
# Analyze entire project
raiseattention check .

# Analyze specific files
raiseattention check src/main.py src/utils.py

# Show detailed exception flows
raiseattention check --verbose src/

# Output as JSON (for CI tools)
raiseattention check --format=json --output=report.json
```

**Exit codes:**
- `0` - No unhandled exceptions found
- `1` - Unhandled exceptions found
- `2` - Analysis error (import failure, etc.)

**Example CI integration (GitHub Actions):**
```yaml
- name: Check exception handling
  run: |
    pip install raiseattention
    raiseattention check . || exit 1
```

### LSP Mode (Editor Integration)

**Automatic startup:**
- Editor detects `.raiseattention.toml` or `pyproject.toml` with `[tool.raiseattention]`
- Starts LSP server: `raiseattention lsp --stdio`
- Provides diagnostics, hover, code actions

**VS Code setup:**
```json
{
  "raiseattention.enable": true,
  "raiseattention.severity": "warning",  // or "error"
  "raiseattention.exclude": ["**/tests/**", "**/migrations/**"]
}
```

### Library Mode (Programmatic API)

```python
from raiseattention import Analyzer, AnalysisConfig

# Configure analyzer
config = AnalysisConfig(
    project_root=".",
    venv_path=".venv",  # Auto-detected if None
    cache_enabled=True,
)

# Run analysis
analyzer = Analyzer(config)
result = analyzer.analyze_file("src/main.py")

# Inspect results
for diagnostic in result.diagnostics:
    print(f"{diagnostic.location}: {diagnostic.message}")
    print(f"  Unhandled: {diagnostic.exception_types}")
```

---

## Advanced Features

### 1. Exception Type Inference

RA infers which exceptions a function may raise by:
- Analyzing `raise` statements in function body
- Inspecting called functions' exception signatures
- Reading docstrings (Sphinx/NumPy/Google formats)
- Parsing type stubs (`.pyi` files) for external libraries

**Example:**
```python
def divide(a: int, b: int) -> float:
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b

# RA infers: divide() may raise ValueError
```

### 2. Transitive Exception Propagation

RA tracks exceptions through call chains:

```python
def level_3():
    raise ValueError("Deep error")

def level_2():
    level_3()  # RA: May raise ValueError

def level_1():
    level_2()  # RA: May raise ValueError (transitive)

def main():
    level_1()  # RA Error: Unhandled ValueError from 3 levels deep
```

### 3. Conditional Exception Handling

RA understands control flow:

```python
def process_data(data: Optional[dict]) -> str:
    if data is None:
        return "No data"
    
    # RA knows: data is not None here, so KeyError is possible
    return data["key"]  # RA Error: May raise KeyError
```

### 4. Context Manager Analysis

RA recognizes exception suppression via context managers:

```python
from contextlib import suppress

with suppress(FileNotFoundError):
    os.remove("file.txt")  # RA: OK, FileNotFoundError suppressed

with suppress(ValueError):
    os.remove("file.txt")  # RA Error: FileNotFoundError not suppressed
```

### 5. Async/Await Support

RA handles async exception flows:

```python
async def fetch_data():
    async with aiohttp.ClientSession() as session:
        response = await session.get("https://api.example.com")
        return await response.json()  # RA: May raise aiohttp.ClientError, JSONDecodeError
```

---

## Configuration

### Project-level config (`.raiseattention.toml` or `pyproject.toml`)

```toml
[tool.raiseattention]
# Environment detection
python_path = "auto"  # or explicit path
venv_path = "auto"  # or explicit path

# Analysis settings
strict_mode = false  # If true, require all exceptions to be declared in docstrings
allow_bare_except = false  # If false, flag bare "except:" as error
require_reraise_after_log = true  # Require re-raise after logging

# Exclusions
exclude = [
    "**/tests/**",
    "**/migrations/**",
    "**/__pycache__/**",
]

# Suppression
ignore_exceptions = [
    "KeyboardInterrupt",
    "SystemExit",
]

ignore_modules = [
    "tests.*",
]

# Caching
[tool.raiseattention.cache]
enabled = true
max_file_entries = 10000
max_memory_mb = 500
ttl_hours = 24

# LSP settings
[tool.raiseattention.lsp]
debounce_ms = 500
max_diagnostics_per_file = 100
```

---

## Implementation Requirements

### Core Components

1. **AST Parser** - Parse Python code into AST
   - Use `ast` module (stdlib)
   - Support Python 3.8+ syntax

2. **Exception Analyzer** - Core analysis engine
   - Traverse AST to find `raise` statements
   - Build call graph for transitive analysis
   - Infer exception types from function calls

3. **Type Checker Integration** - Optional integration with mypy/pyright
   - Use existing type information to improve accuracy
   - Leverage type stubs for external libraries

4. **Cache Manager** - Implement multi-tier caching
   - File-level cache with mtime/hash invalidation
   - Dependency cache for external libraries
   - LRU eviction policy

5. **LSP Server** - Language Server Protocol implementation
   - Use `pygls` library (Python LSP framework)
   - Implement textDocument/diagnostic, hover, codeAction
   - Debouncing and incremental updates

6. **Environment Detector** - Detect virtual environment
   - Implement detection pseudospec (see resources/VENV_DETECTION.md)
   - Support Poetry, Pipenv, PDM, uv, Rye, Hatch, venv, pyenv
   - Cross-platform path handling (Windows/macOS/Linux)

### Technology Stack

**Core:**
- Python 3.8+
- `ast` (stdlib) - AST parsing
- `pathlib` (stdlib) - Cross-platform paths
- `hashlib` (stdlib) - Content hashing for cache invalidation

**LSP:**
- `pygls` - LSP server framework
- `lsprotocol` - LSP types and messages

**Optional integrations:**
- `mypy` - Type information (optional)
- `pyright` - Type information (optional)
- `tree-sitter-python` - Alternative parser (optional)

**Dependencies:**
- Minimal dependencies (prefer stdlib)
- All tools optional (graceful degradation if not installed)

### Testing Requirements

**Unit tests:**
- AST parsing edge cases
- Exception inference accuracy
- Cache invalidation logic
- Environment detection across tools

**Integration tests:**
- Full project analysis
- LSP request/response cycles
- CLI command execution

**Performance benchmarks:**
- Cold cache vs. warm cache speedup
- LSP response time (<200ms goal)
- Memory usage under load

---

## Success Criteria

**For developers:**
- "I never have to `git bisect` to find where an uncaught exception was introduced"
- "I know which exceptions to handle before running the code"
- "My editor warns me about exception paths I didn't consider"

**For teams:**
- "CI fails if someone introduces unhandled exceptions"
- "Our production crash rate decreased by 60%"
- "Code reviews focus on logic, not 'did you handle X exception?'"

**For the tool:**
- <5% false positive rate (legitimate code flagged as error)
- <1% false negative rate (real errors missed)
- 95%+ cache hit rate after initial analysis
- <200ms LSP diagnostic latency

---

## Future Enhancements

1. **Machine learning for exception inference** - Learn common exception patterns from codebases
2. **Exception contract generation** - Auto-generate docstrings with exception declarations
3. **IDE refactoring support** - "Extract exception handler" refactoring
4. **Exception flow visualization** - Graph UI showing exception propagation paths
5. **Async exception handling** - Better support for asyncio cancellation and timeouts
6. **Multi-language support** - TypeScript, Java, Rust (similar exception paradigms)

---

## Appendix: Related Work

**Similar tools:**
- Java: Checked exceptions (compile-time enforcement)
- Rust: `Result<T, E>` type (explicit error handling)
- Go: Multiple return values `(value, error)` (explicit but verbose)
- Haskell: `Either` / `Maybe` types (explicit, functional style)

**Python-specific:**
- `mypy` / `pyright` - Type checking but not exception checking
- `pylint` - Style checking, minimal exception analysis
- `ruff` - Fast linter, no exception flow analysis

**RaiseAttention fills the gap:** Static exception analysis for Python with LSP integration and minimal false positives.

---

## Implementation Prompt for LLM

**Goal:** Generate a production-ready Python tool called `raiseattention` that:

1. **Analyzes Python code** to detect unhandled exceptions using AST traversal
2. **Implements an LSP server** for real-time editor diagnostics
3. **Auto-detects virtual environments** using the provided pseudospec (see resources/VENV_DETECTION.md)
4. **Implements multi-tier caching** (file-level + dependency-level + incremental)
5. **Provides CLI and library interfaces** for CI/CD and programmatic usage

**Key technical requirements:**
- Parse Python AST to find `raise` statements and function calls
- Build call graph to track exception propagation transitively
- Implement file content hashing (SHA-256) for cache invalidation
- Detect file changes via mtime, size, and content hash
- Invalidate cache on git state changes (branch switch, commit, merge)
- Use LRU eviction for cache memory management (max 10,000 entries)
- Implement LSP using `pygls` library with debouncing (500ms)
- Detect virtual environments by checking lock files in priority order
- Support cross-platform paths (Windows/macOS/Linux)
- Provide configuration via `pyproject.toml` or `.raiseattention.toml`
- Generate JSON output for CI integration
- Support inline suppression comments (`# raiseattention: ignore`)

**Performance targets:**
- Cold cache: <3s for 1000-file project
- Warm cache: <100ms (25-50x speedup)
- LSP diagnostic latency: <200ms from keystroke
- Cache hit rate: >95% during development

**Dependencies:**
- Core: Python 3.8+, stdlib (`ast`, `pathlib`, `hashlib`, `json`)
- LSP: `pygls`, `lsprotocol`
- Optional: `mypy`, `pyright` (for type information integration)

**Code structure:**
```
raiseattention/
├── analyzer.py          # Core exception analysis engine
├── ast_visitor.py       # AST traversal for exception detection
├── cache.py             # Multi-tier caching implementation
├── env_detector.py      # Virtual environment detection
├── lsp_server.py        # LSP server implementation
├── cli.py               # CLI interface
└── config.py            # Configuration loading
```

**Start by implementing** the environment detector (using provided pseudospec), then the core analyzer, then caching, then LSP server.
