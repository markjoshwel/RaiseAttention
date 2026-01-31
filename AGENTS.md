# agents.md

conventions and guidelines for working on the raiseattention project.

## project overview

raiseattention is a static exception flow analyser for python that identifies
unhandled exceptions in python codebases. it provides:

- cli tool for analysing projects
- lsp server for real-time editor integration
- multi-tier caching for performance
- virtual environment auto-detection (via libvenvfinder)

## workspace structure

this project uses uv workspaces to manage multiple packages:

```
raiseattention/
├── src/
│   ├── raiseattention/       # main exception analyser
│   │   ├── __init__.py
│   │   ├── analyzer.py       # core analysis engine
│   │   ├── ast_visitor.py    # ast traversal
│   │   ├── cache.py          # caching system
│   │   ├── cli.py            # command-line interface
│   │   ├── config.py         # configuration loading
│   │   ├── env_detector.py   # venv detection (re-exports libvenvfinder)
│   │   └── lsp_server.py     # lsp server implementation
│   │
│   └── libvenvfinder/        # standalone venv detection library
│       ├── libvenvfinder/
│       │   ├── __init__.py   # public api: find_venv, find_all_venvs, ToolType, VenvInfo
│       │   ├── cli.py        # venvfinder executable
│       │   ├── core.py       # main detection orchestration
│       │   ├── models.py     # dataclasses and enums
│       │   └── detectors/    # individual tool detectors
│       │       ├── poetry.py
│       │       ├── pipenv.py
│       │       ├── pdm.py
│       │       ├── uv.py
│       │       ├── rye.py
│       │       ├── hatch.py
│       │       ├── venv.py
│       │       ├── pyenv.py
│       │       └── utils.py
│       ├── pyproject.toml    # standalone package config
│       └── README.md
│
├── tests/                    # test suite
│   ├── __init__.py
│   ├── test_analyzer.py
│   ├── test_ast_visitor.py
│   ├── test_cache.py
│   ├── test_cli.py
│   ├── test_config.py
│   └── test_env_detector.py
├── resources/                # documentation and specs
│   ├── MDF.md               # meadow docstring format
│   ├── PROMPT.md            # project specification
│   └── VENV_DETECTION.md    # venv detection spec
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

## libvenvfinder

libvenvfinder is a standalone library for detecting python virtual environments.
it is published separately to pypi and can be used independently.

### using libvenvfinder programmatically

```python
from libvenvfinder import find_venv, find_all_venvs, ToolType

# find first/best venv
info = find_venv("/path/to/project")
if info:
    print(f"found {info.tool.value} venv at {info.venv_path}")

# find all venvs
all_venvs = find_all_venvs("/path/to/project")
for venv in all_venvs:
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

### testing libvenvfinder

libvenvfinder has its own test suite in `src/libvenvfinder/tests/`:

```bash
# run libvenvfinder tests
cd src/libvenvfinder
uv run pytest tests/ -v

# run with coverage
uv run pytest tests/ --cov=libvenvfinder --cov-report=term-missing
```

**test structure:**
- `test_core.py` - api tests for `find_venv()` and `find_all_venvs()`
- `test_cli.py` - command-line interface tests  
- `conftest.py` - shared fixtures and test configuration

**current coverage: ~77%**
- well-covered: core api, cli, venv/uv/rye detectors
- needs work: hatch (32%), pdm (52%), pyenv (47%) - mostly toml parsing paths
- subprocess error handling not fully tested (will be covered by nix integration tests)

**testing notes:**
- tests clear `VIRTUAL_ENV` env var automatically (see `conftest.py`)
- mock projects created with fixtures (poetry_project, uv_project, etc.)
- platform-specific code (windows/unix) tested via mocking

## dependencies

### required

- `pygls>=1.3.0` - lsp server framework
- `lsprotocol>=2023.0.0` - lsp types
- `libvenvfinder` - venv detection (workspace member)
- `typing-extensions>=4.6.0` - type hints backport

### development

- `pytest>=8.0.0` - testing framework
- `pytest-cov>=4.0.0` - coverage reporting
- `mypy>=1.8.0` - type checking
- `ruff>=0.3.0` - linting and formatting

## commands

### installation

```bash
# install entire workspace with uv
uv sync

# install in editable mode
uv pip install -e ".[dev]"

# install just libvenvfinder
uv pip install -e src/libvenvfinder
```

### testing

```bash
# run all tests
uv run pytest

# run with coverage
uv run pytest --cov=src/raiseattention --cov-report=html

# run specific test file
uv run pytest tests/test_analyzer.py

# run libvenvfinder tests only
uv run --directory src/libvenvfinder pytest
```

### linting and type checking

```bash
# run ruff linter
uv run ruff check src tests

# run ruff formatter
uv run ruff format src tests

# run type checker
uv run mypy src

# run type checker on specific package
uv run mypy src/libvenvfinder
```

### running the tools

```bash
# analyse current directory
uv run raiseattention check .

# analyse specific file
uv run raiseattention check src/main.py

# start lsp server
uv run raiseattention lsp

# check cache status
uv run raiseattention cache status

# find venvs with venvfinder
uv run venvfinder .
uv run venvfinder . --all
uv run venvfinder . --tool poetry --json
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

## security

- never log or expose secrets
- validate all file paths
- use subprocess with timeouts
- sanitize user input

## questions?

refer to:
- `resources/PROMPT.md` - full project specification
- `resources/MDF.md` - docstring format specification
- `resources/VENV_DETECTION.md` - venv detection specification
- `src/libvenvfinder/README.md` - libvenvfinder documentation
