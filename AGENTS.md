# agents.md

conventions and guidelines for working on the raiseattention project.

## project overview

raiseattention is a static exception flow analyser for python that identifies
unhandled exceptions in python codebases. it provides:

- cli tool for analysing projects
- lsp server for real-time editor integration
- multi-tier caching for performance
- virtual environment auto-detection (via libsoulsearching)
- **robust exception flow tracking** through transitive call chains
- **intelligent try-except detection** at call sites
- **external module analysis** for stdlib and third-party packages
- **higher-order function traversal** for map/filter/sorted and callable args
- **native code detection** with `PossibleNativeException` warnings
- **docstring heuristics** for functions that can't be statically analysed
- **debug logging** throughout the analysis pipeline

## workspace structure

this project uses uv workspaces to manage multiple packages:

```
raiseattention/
├── src/
│   ├── raiseattention/       # main exception analyser
│   │   ├── __init__.py
│   │   ├── analyser.py       # core analysis engine (rewritten with proper exception tracking)
│   │   ├── ast_visitor.py    # ast traversal (tracks calls with try-except context)
│   │   ├── cache.py          # caching system
│   │   ├── cli.py            # command-line interface
│   │   ├── config.py         # configuration loading
│   │   ├── env_detector.py   # venv detection (re-exports libsoulsearching)
│   │   ├── external_analyser.py  # stdlib/third-party module analysis
│   │   └── lsp_server.py     # lsp server implementation
│   │
│   ├── libsoulsearching/        # standalone venv detection library
│   │   ├── libsoulsearching/
│   │   │   ├── __init__.py   # public api: find_venv, find_all_venvs, ToolType, VenvInfo
│   │   │   ├── cli.py        # venvfinder executable
│   │   │   ├── core.py       # main detection orchestration
│   │   │   ├── models.py     # dataclasses and enums
│   │   │   └── detectors/    # individual tool detectors
│   │   │       ├── poetry.py
│   │   │       ├── pipenv.py
│   │   │       ├── pdm.py
│   │   │       ├── uv.py
│   │   │       ├── rye.py
│   │   │       ├── hatch.py
│   │   │       ├── venv.py
│   │   │       ├── pyenv.py
│   │   │       └── utils.py
│   │   ├── pyproject.toml    # standalone package config
│   │   └── README.md
│   │
│   └── libsightseeing/       # file finding library with gitignore support
│       ├── libsightseeing/
│       │   ├── __init__.py   # public api: find_files, SourceResolver
│       │   ├── core.py       # SourceResolver class
│       │   ├── gitignore.py  # GitignoreMatcher for .gitignore handling
│       │   └── patterns.py   # include/exclude pattern matching
│       ├── tests/
│       │   └── test_core.py  # 15 comprehensive tests
│       ├── pyproject.toml    # standalone package config
│       └── README.md
│
│   └── standardstubber/        # cpython stub generator for native exceptions
│       ├── standardstubber/
│       │   ├── __init__.py   # public api exports
│       │   ├── cli.py        # command-line interface
│       │   ├── analyser.py   # c source analysis using libclang
│       │   ├── models.py     # data models for .pyras v2.0 files
│       │   ├── patterns.py   # error propagation pattern detection
│       │   ├── resolver.py   # stub file resolution
│       │   ├── writer_json.py # json v2.0 file writer
│       │   └── writer.py     # legacy toml v1.0 writer
│       ├── typings/          # type stubs for libclang
│       ├── resources/        # cpython source tarballs
│       ├── pyproject.toml    # standalone package config
│       └── README.md
│
├── tests/                    # comprehensive test suite (178 tests, 82% coverage)
│   ├── __init__.py
│   ├── fixtures/            # synthetic codebases for testing
│   │   ├── __init__.py
│   │   └── code_samples.py  # synthetic exception scenarios
│   ├── test_analyser.py
│   ├── test_analyzer_synthetic.py  # 35 synthetic exception tests
│   ├── test_ast_visitor.py
│   ├── test_cache.py
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_env_detector.py
│   ├── test_external_analyser.py  # 24 external module analysis tests
│   └── test_lsp_server.py   # 18 comprehensive lsp tests
│
├── resources/                # documentation and specs
│   ├── MDF.md               # meadow docstring format
│   ├── PROMPT.md            # project specification
│   └── VENV_DETECTION.md    # venv detection spec
│
├── pyproject.toml           # workspace root configuration
├── README.md                # project readme
└── AGENTS.md               # this file
```

## docstring format: meadow docstring format (mdf)

all python code must use the meadow docstring format as defined in
`resources/MDF.md`. key characteristics:

- **lowercase** all docstrings and comments
- **british english** spelling (e.g., "analyse", "behaviour", "colour")
- plaintext-first with backtick-quoted type annotations

### mdf structure

```python
def example_function(arg1: str, arg2: int | None = None) -> bool:
    """
    short one-line preamble describing the function.
    
    optional longer description in the body section.
    can span multiple lines.
    
    arguments:
        `arg1: str`
            description of the first argument
        `arg2: int | None`
            description with default value
    
    raises:
        `ValueError`
            when arg1 is empty
    
    returns: `bool`
        description of return value
    
    usage:
        ```python
        result = example_function("test", 42)
        ```
    """
    pass
```

### mdf sections (in order)

1. **preamble** (required) - one-line description
2. **body** (optional) - longer description
3. **arguments/attributes/parameters** (if applicable)
4. **functions/methods** (for module/class docstrings)
5. **returns** (if applicable)
6. **raises** (if applicable)
7. **usage** (optional) - code examples in markdown code blocks

### type annotation format

- use backticks around type annotations: `` `str` ``, `` `int | None` ``
- use modern python 3.10+ syntax: `| None` instead of `Optional[]`
- use `list[]`, `dict[]`, `tuple[]` instead of `typing.List`, etc.

## code style

### general

- python 3.10+ minimum
- use type hints everywhere
- prefer `pathlib.Path` over `os.path`
- use `.joinpath()` instead of `/` operator for path joining
- use f-strings for string formatting
- maximum line length: 100 characters

### imports

- use `from __future__ import annotations` in all files
- group imports: stdlib, third-party, local
- sort imports alphabetically within groups

### naming

- `snake_case` for functions, variables, methods
- `PascalCase` for classes
- `UPPER_CASE` for constants
- `private_prefix` with underscore for internal functions

### error handling

- use specific exception types
- avoid bare `except:` clauses
- use `try/except/else/finally` appropriately
- document all raised exceptions in docstrings

## british english

use british spelling throughout:

| american | british |
|----------|---------|
| analyze | analyse |
| behavior | behaviour |
| color | colour |
| center | centre |
| program | programme (when referring to tv/theatre) |
| disk | disc |
| check | cheque (financial), check (verify) |

## testing

- use pytest for all tests
- test files: `test_*.py` in `tests/` directory
- use fixtures from `conftest.py` where appropriate
- aim for >80% code coverage
- use descriptive test method names
- **use synthetic codebases in `tests/fixtures/` for comprehensive exception testing**

### current status (2026-02-02)

**libsoulsearching:** 95% coverage, all tests passing
- 22 unit tests (core api, cli)
- 42 edge case tests (hatch/pdm/pyenv detectors)
- 6 real integration tests with actual tools
- ci passing (14 jobs)

**raiseattention:** ✅ production ready
- **178 tests, all passing, 82% coverage**
- **exception analyser completely rewritten** with proper flow tracking:
  - transitive exception tracking through call chains
  - try-except context detection at call sites
  - exception hierarchy support (built-in exceptions)
  - async/await exception handling
  - **external module analysis** for stdlib and third-party packages
  - **fully qualified exception types** (e.g., `copy.Error`, `tomlantic.TOMLValidationError`)
  - **cwd-relative paths** for human-readable output
  - **higher-order function traversal** (map, filter, sorted, min, max, reduce, etc.)
  - **native code detection** with `PossibleNativeException` for C extensions
  - **docstring heuristics** for functions that can't be statically analysed
  - **debug logging** with `--debug` CLI flag
- **comprehensive test coverage**:
  - 35 synthetic analyser tests (unhandled/caught/edge cases)
  - 24 external analyser tests (stdlib/third-party tracking)
  - 18 comprehensive LSP server tests
  - 12 synthetic code generators for testing scenarios
  - 9 HOF exception propagation tests
  - 6 native code detection tests
  - 5 callable argument detection tests
  - 3 debug logging tests
- **ci passing** - all integration tests working

### synthetic codebases for testing

the `tests/fixtures/code_samples.py` module provides synthetic code generators:

```python
from tests.fixtures import (
    create_unhandled_exception_file,   # code that should be flagged
    create_handled_exception_file,     # code that should not be flagged  
    create_complex_nesting_file,       # multi-level call chains
    create_exception_chaining_file,    # raise ... from ... scenarios
    create_custom_exceptions_file,     # user-defined exception classes
    create_mixed_scenario_file,        # both handled and unhandled
    create_async_exceptions_file,      # async/await scenarios
    create_synthetic_codebase,         # complete test codebase
    create_decorator_wrapper_file,     # decorator wrapper patterns
    create_hof_callable_file,          # higher-order function patterns
    create_callable_passing_file,      # callable passing patterns
    create_native_code_test_file,      # native/C extension code usage
)
```

### test structure

```python
def test_descriptive_name() -> None:
    """test what this test verifies."""
    # arrange
    input_data = ...
    
    # act
    result = function_under_test(input_data)
    
    # assert
    assert result == expected_value
```

## exception analyser architecture

the exception analyser has been redesigned for robust flow tracking:

### key components

1. **ast_visitor.py** - enhanced ast traversal:
   - `CallInfo` dataclass tracks function calls with location and try-except context
   - `TryExceptInfo` tracks exception handling blocks with line ranges
   - tracks which calls are inside which try-except blocks
   - handles async/await expressions

2. **analyser.py** - core analysis engine:
   - two-pass diagnostic computation
   - **first pass**: finds unhandled exceptions at call sites
   - **second pass** (strict mode): flags functions with undocumented exceptions
   - exception hierarchy resolution (e.g., catching `Exception` handles `ValueError`)
   - **fully qualified exception types**: reports `tomlantic.TOMLValidationError` instead of just `TOMLValidationError`
   - recursion detection for circular call graphs
   - integrates with external_analyser for stdlib/third-party lookups

3. **external_analyser.py** - stdlib and third-party module analysis:
   - analyses external python source files for exception signatures
   - uses dfs with memoisation for transitive exception tracking
   - follows imports and re-exports (e.g., `tomllib.load` → `tomllib._parser.load`)
   - skips c extensions (`.so`/`.pyd`) as they cannot be statically analysed
   - per-module caching to avoid redundant parsing
   - integrates with libsoulsearching to locate site-packages

### how it works

```python
# example detection - local code
def risky():
    raise ValueError("error")

def caller():
    risky()  # diagnostic: unhandled ValueError at this line

def safe_caller():
    try:
        risky()  # no diagnostic - handled by except ValueError
    except ValueError:
        pass

# example detection - external/stdlib code
import json

def parse_data(data: str) -> dict:
    return json.loads(data)  # diagnostic: unhandled JSONDecodeError, TypeError
```

### external module analysis

the analyser can detect exceptions from stdlib and third-party packages:

```python
import tomllib
import json

def load_config(path: str) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)  # detects: TypeError, TOMLDecodeError (via suffixed_err)

def parse_json(data: str) -> dict:
    return json.loads(data)  # detects: JSONDecodeError, TypeError
```

the external analyser:
1. resolves imports to find actual module files
2. follows re-exports (e.g., `tomllib.load` → `tomllib._parser.load`)
3. uses dfs to compute transitive exception signatures
4. **qualifies exception types with module name** (e.g., `copy.Error` instead of just `Error`)
5. caches results to avoid redundant parsing

**c extension stub generation:**
for c extension modules that cannot be statically analysed, the external analyser
uses pre-computed `.pyras` stub files generated by **standardstubber**. these stubs
contain exception signatures extracted from cpython's c source code and are stored
in `src/raiseattention/stubs/stdlib/`. see the [standardstubber README](src/standardstubber/README.md)
for details on the `.pyras` v2.0 format and stub generation process.

## libsoulsearching

libsoulsearching is a standalone library for detecting python virtual environments.
it is published separately to pypi and can be used independently.

### using libsoulsearching programmatically

```python
from libsoulsearching import find_venv, find_all_venvs, ToolType

# find first/best venv
info = find_venv("/path/to/project")
if info:
    print(f"found {info.tool.value} venv at {info.venv_path}")

# find all venvs
all_venvs = find_all_venvs("/path/to/project")
for venv in all_envs:
    print(f"{venv.tool.value}: {venv.venv_path}")

# find specific tool only
poetry_venv = find_venv("/path/to/project", tool=ToolType.POETRY)
```

### cli usage

```bash
# find first venv
venvfinder /path/to/project

# list all venvs
venvfinder /path/to/project --all

# find specific tool
venvfinder /path/to/project --tool poetry

# json output
venvfinder /path/to/project --json
```

### supported tools

- poetry (poetry.lock, .venv)
- pipenv (pipfile.lock)
- pdm (pdm.lock, .pdm.toml)
- uv (uv.lock, .venv)
- rye (rye.lock, .python-version)
- hatch (pyproject.toml with [tool.hatch.envs])
- venv (.venv/pyvenv.cfg)
- pyenv (.python-version)

### testing libsoulsearching

libsoulsearching has its own test suite in `src/libsoulsearching/tests/`:

```bash
# run libsoulsearching tests
cd src/libsoulsearching
uv run pytest tests/ -v

# run with coverage
uv run pytest tests/ --cov=libsoulsearching --cov-report=term-missing
```

**test structure:**
- `test_core.py` - api tests for `find_venv()` and `find_all_venvs()`
- `test_cli.py` - command-line interface tests  
- `test_integration_real.py` - real integration tests with actual tools
- `conftest.py` - shared fixtures and test configuration

**current coverage: ~95%**
- well-covered: core api, cli, all detectors
- pdm: 100% (edge cases: missing config, invalid toml, path resolution)
- pyenv: 100% (edge cases: version parsing, pyenv_root handling, tilde expansion)
- hatch: 96% (edge cases: toml parsing, custom paths, oserror handling)
- subprocess error handling covered by nix integration tests

**test files:**
- `test_core.py` - api tests for `find_venv()` and `find_all_venvs()`
- `test_cli.py` - command-line interface tests
- `test_integration_real.py` - real integration tests with actual tools
- `test_detectors_edge_cases.py` - edge case tests for hatch/pdm/pyenv detectors
- `conftest.py` - shared fixtures and test configuration

**testing notes:**
- tests clear `VIRTUAL_ENV` env var automatically (see `conftest.py`)
- mock projects created with fixtures (poetry_project, uv_project, etc.)
- platform-specific code (windows/unix) tested via mocking

### nix integration tests

real integration tests are provided via nix that actually invoke poetry, pipenv,
pdm, uv, rye, and hatch to create projects and verify detection works.

**requirements:** nix with flakes enabled, linux (tested on nixos)

**run via nix develop:**
```bash
# enter integration shell with all tools
nix develop .#integration

# run real integration tests (creates actual projects)
uv run pytest src/libsoulsearching/tests/test_integration_real.py -v
```

**run via nix flake check:**
```bash
# run unit tests
nix flake check .#unit-tests

# run integration tests
nix flake check .#integration-tests
```

**nixos rye workaround:**
rye bundles dynamically-linked binaries that expect fhs paths. on nixos, the
integration shell automatically patches these binaries using `patchelf` to use
nixos's dynamic linker. this happens automatically when entering the shell.

see: `flake.nix` integration shell `shellhook` for implementation details.

## dependencies

### required

- `pygls>=1.3.0` - lsp server framework
- `lsprotocol>=2023.0.0` - lsp types
- `libsoulsearching` - venv detection (workspace member)
- `typing-extensions>=4.6.0` - type hints backport

### development

- `pytest>=8.0.0` - testing framework
- `pytest-cov>=4.0.0` - coverage reporting
- `pytest-asyncio>=0.23.0` - async test support
- `mypy>=1.8.0` - type checking
- `ruff>=0.3.0` - linting and formatting

## commands

### installation

```bash
# install entire workspace with uv
uv sync

# install with dev dependencies
uv sync --extra dev

# install in editable mode
uv pip install -e ".[dev]"

# install just libsoulsearching
uv pip install -e src/libsoulsearching

# install just libsightseeing
uv pip install -e src/libsightseeing
```

## libsightseeing

libsightseeing is a standalone library for file finding and source resolution with gitignore support.
it is used by raiseattention for finding python files to analyse.

### using libsightseeing programmatically

```python
from libsightseeing import find_files, SourceResolver

# simple one-liner
files = find_files(".", include=["*.py"])

# advanced usage with resolver
resolver = SourceResolver(
    root=".",
    include=["src/**/*.py"],
    exclude=["tests"],
    respect_gitignore=True,
)
files = resolver.resolve()
```

### features

- respects .gitignore files automatically
- supports glob patterns for include/exclude
- default excludes `.venv` directory
- cross-platform path handling
- only depends on gitignore-parser

### testing libsightseeing

libsightseeing has its own test suite in `src/libsightseeing/tests/`:

```bash
# run libsightseeing tests
cd src/libsightseeing
uv run pytest tests/ -v

# run with coverage
uv run pytest tests/ --cov=libsightseeing --cov-report=term-missing
```

**test structure:**
- `test_core.py` - 15 comprehensive tests covering:
  - basic file finding
  - exclude patterns (including .venv)
  - gitignore respect
  - pattern matching with globs
  - nested directories

## standardstubber

standardstubber is a cpython standard library exception stub generator that extracts
exception signatures from c extension modules and generates `.pyras` v2.0 stub files.
it is used internally to create the pre-computed exception metadata for raiseattention's
external analyser.

### using standardstubber

```bash
# generate stubs from a cpython source tarball
uv run standardstubber --cpython Python-3.12.12.tar.xz --version ">=3.12,<3.13" -o stdlib-3.12.pyras

# generate all stdlib stubs for multiple versions
python src/standardstubber/generate_all.py --jobs 16 --verbose
```

### key features

- **libclang-based analysis** - parses cpython c source to find exception signatures
- **call graph propagation** - computes transitive exceptions through function calls
- **json v2.0 format** - nested structure with per-exception confidence levels
- **fuzzy matching** - resolver handles class name mismatches (e.g., `mmap.mmap` vs `mmap.Mmap_object`)
- **test module filtering** - automatically excludes `_test*`, `xx*`, `_xx*` modules

### .pyras v2.0 format

the v2.0 format uses json with a nested structure:

```json
{
  "metadata": {
    "name": "stdlib",
    "version": ">=3.12,<3.13",
    "format_version": "2.0"
  },
  "_io": {
    "BufferedReader": {
      "peek": {
        "TypeError": "exact"
      }
    }
  }
}
```

see the [standardstubber README](src/standardstubber/README.md) for full format documentation.

### testing standardstubber

standardstubber has its own test suite and type stubs in `src/standardstubber/`:

```bash
# run standardstubber tests
cd src/standardstubber
uv run pytest tests/ -v

# run linters
uv run ruff check standardstubber/
uv run mypy standardstubber/
uv run basedpyright standardstubber/  # from standardstubber/ directory
```

### testing

```bash
# run all tests
uv run pytest

# run with coverage
uv run pytest --cov=src/raiseattention --cov-report=html

# run specific test file
uv run pytest tests/test_analyser.py

# run synthetic exception tests
uv run pytest tests/test_analyzer_synthetic.py -v

# run lsp server tests
uv run pytest tests/test_lsp_server.py -v

# run libsoulsearching tests only
uv run --directory src/libsoulsearching pytest
```

### linting and type checking

```bash
# run ruff linter
uv run ruff check src tests

# run ruff formatter
uv run ruff format src tests

# run basedpyright type checker on all packages
uv run basedpyright src/raiseattention src/libsoulsearching src/libsightseeing

# run mypy type checker on all packages
uv run mypy src/raiseattention src/libsoulsearching src/libsightseeing

# run type checker on specific package
uv run mypy src/libsoulsearching
```

### running the tools

```bash
# analyse current directory
uv run raiseattention check .

# analyse specific file
uv run raiseattention check src/main.py

# analyse with json output
uv run raiseattention check --json .

# analyse only local/first-party code (skip external modules)
uv run raiseattention check --local .

# enable strict mode
uv run raiseattention check --strict .

# use absolute paths in output
uv run raiseattention check --absolute .

# show full module path for exceptions (e.g., 'tomlantic.tomlantic.TOMLValidationError')
uv run raiseattention check --full-module-path .

# enable debug logging (shows analysis steps)
uv run raiseattention check --debug .

# disable native code warnings (suppresses PossibleNativeException)
uv run raiseattention check --no-warn-native .

# start lsp server
uv run raiseattention lsp

# check cache status
uv run raiseattention cache status

# find venvs with venvfinder
uv run venvfinder .
uv run venvfinder . --all
uv run venvfinder . --tool poetry --json
```

### nix development

```bash
# enter development shell
nix develop

# enter integration shell (includes all venv tools)
nix develop .#integration

# run unit tests via nix
nix flake check .#unit-tests

# run integration tests via nix
nix flake check .#integration-tests

# build packages
nix build .#libsoulsearching
nix build .#raiseattention
```

## continuous integration

github actions workflow runs on every push to main and pull requests.

### nix-based jobs (fully reproducible)

- `check-flake` - validates flake.nix evaluates correctly
- `check-flake` - validates flake.nix evaluates correctly
- `all-unit-tests-nix` - runs all unit tests via `nix run .#unit-tests`
- `soulsearching-integration-tests-nix` - runs soulsearching real integration tests on linux
- `integration-tests-nix-macos` - runs integration tests on macos
- `nix-lint-and-typecheck` - runs ruff, basedpyright, and mypy on all three packages via `nix run .#lint`
- `nix-build-packages` - builds all three packages (libsoulsearching, libsightseeing, raiseattention) via `nix build`

### compatibility matrix

- `compat` - tests across python 3.11-3.13 on ubuntu/windows/macos
- uses uv directly (not nix) to verify broad compatibility

### running ci locally

```bash
# run unit tests
nix run .#unit-tests

# run integration tests
nix run .#integration-tests

# run linters (ruff, basedpyright, and mypy on all three packages)
nix run .#lint

# build packages (libsoulsearching, libsightseeing, raiseattention)
nix build .#libsoulsearching
nix build .#libsightseeing
nix build .#raiseattention

# validate flake
nix flake check
```

## git workflow

1. create feature branches from main
2. write tests for new functionality
3. ensure all tests pass before committing
4. use conventional commit messages
5. keep commits focused and atomic

### commit message format

```
type(scope): description

optional longer description

- bullet points for details
- more details
```

types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## configuration

configuration is loaded from (in order of precedence):

1. default values
2. `pyproject.toml` `[tool.raiseattention]` section
3. `.raiseattention.toml` file
4. environment variables (prefix: `RAISEATTENTION_`)

## performance considerations

- use caching for expensive operations
- implement debouncing for lsp requests
- lazy-load heavy dependencies
- use generators for large collections
- exception signatures are cached to avoid recomputation

## security

- never log or expose secrets
- validate all file paths
- use subprocess with timeouts
- sanitize user input

## known limitations

1. **c extension modules** - the analyser cannot statically analyse c extensions (e.g., `_json`, `_csv`, modules with `.so`/`.pyd` files). instead, it reports `PossibleNativeException` as a warning. use `--no-warn-native` to suppress these warnings.

2. **custom exception hierarchies** - the analyser understands built-in exception hierarchies (e.g., `ValueError` → `Exception`) but not custom class inheritance without parsing class definitions. marked as skipped test.

3. **dynamic imports and calls** - the analyser cannot track exceptions through dynamic imports (`importlib.import_module`) or dynamic function calls (`getattr(obj, method_name)()`).

4. **lambda expressions in HOFs** - when lambda expressions are passed to higher-order functions like `map`, `filter`, or `sorted`, the analyser cannot currently analyse the lambda body for potential exceptions. named functions passed to HOFs are fully tracked.

## local-only mode

to analyse only first-party code without external module analysis:

```bash
# cli flag
raiseattention check --local .

# or in pyproject.toml
[tool.raiseattention.analysis]
local_only = true
```

## questions?

refer to:
- `resources/PROMPT.md` - full project specification
- `resources/MDF.md` - docstring format specification
- `resources/VENV_DETECTION.md` - venv detection specification
- `src/libsoulsearching/README.md` - libsoulsearching documentation
