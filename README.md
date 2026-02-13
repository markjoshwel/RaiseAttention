# RaiseAttention

> [!WARNING]
> this project is vibe coded, as a test of Kimi K2.5. it isn't battle tested,
> so issues may arise. if you're willing to run into potential bugs, feel free to use it!

a static exception flow analyser for python that identifies unhandled exceptions in your
codebase. i built this because i was tired of not knowing what exceptions functions might
raise, especially when calling third-party code.

version 2026.2.14.

- [usage](#usage)
  - [installation](#installation)
  - [cli](#cli)
  - [lsp server](#lsp-server)
- [what does it do?](#what-does-it-do)
- [features](#features)
- [configuration](#configuration)
- [licence](#licence)

## usage

### installation

```text
pip install raiseattention
```

**nix users, rejoice:** `nix run github:markjoshwel/RaiseAttention`

### cli

check version:

```text
raiseattention --version
```

analyse your project:

```text
raiseattention check .
```

analyse a specific file:

```text
raiseattention check src/main.py
```

for json output:

```text
raiseattention check --json .
```

enable debug logging to see what the analyser is doing:

```text
raiseattention check --debug .
```

full cli help:

```text
raiseattention --help
raiseattention check --help
```

### lsp server

start the lsp server for real-time editor integration:

```text
raiseattention lsp
```

the server will give you errors when you're calling a function that may raise an
exception. the laziest way to appease RaiseAttention is to wrap calls in a
`try: ... except Exception:` block—but you probably shouldn't do that lol

## what does it do?

RaiseAttention tracks exception flow through your code. it follows function calls
transitively, so if `a()` calls `b()` which calls `c()` which raises `ValueError`,
RaiseAttention will tell you that calling `a()` may raise `ValueError`.

```python
def risky():
    raise ValueError("something went wrong")

def caller():
    risky()  # RaiseAttention: unhandled ValueError

def safe_caller():
    try:
        risky()  # no warning—handled by except ValueError
    except ValueError:
        pass
```

it also analyses external modules (stdlib and third-party):

```python
import json

def parse_data(data: str) -> dict:
    return json.loads(data)  # RaiseAttention: unhandled JSONDecodeError, TypeError
```

the idea is that you won't have to ~~worry about exceptions anymore~~ live in the dark
when it comes to whether any functions you use may raise exceptions you didn't expect.

## features

- **transitive exception tracking** — follows exceptions through call chains
- **try-except detection** — understands which exceptions are handled at call sites
- **external module analysis** — analyses stdlib and third-party packages
- **higher-order function traversal** — tracks exceptions through `map`, `filter`,
  `sorted`, and other HOFs when you pass callable arguments
- **native code detection** — reports `PossibleNativeException` for C extensions that
  can't be statically analysed (suppress with `--no-warn-native`)
- **c extension stubs** — pre-computed exception signatures for stdlib C modules (6531
  stubs for python 3.12)
- **type constructor analysis** — detects exceptions from `int()`, `float()`, `str()`,
  etc. (e.g., `int("not a number")` raises `ValueError`)
- **smart builtin filtering** — only flags builtins with interesting exceptions, skips
  noisy ones like `len()`, `abs()`, `print()`
- **docstring heuristics** — checks `__doc__` for "raises" keywords when static analysis
  isn't possible
- **exception instance re-raise detection** — `raise error` from `except Exception as error:`
  is treated as re-raise, not a new exception
- **inline ignore comments** — `# raiseattention: ignore[ExceptionType]` for line-specific
  suppression (pyright-style)
- **ra shorthand** — `# ra: ignore[Exception]` works too (all case-insensitive)
- **docstring-based suppression** — exceptions documented in parent docstrings are
  automatically suppressed
- **lsp server** — real-time feedback in your editor
- **debug logging** — see exactly what the analyser is doing with `--debug`

## configuration

configuration is loaded from (in order of precedence):

1. default values
2. `pyproject.toml` `[tool.raiseattention]` section
3. `.raiseattention.toml` file
4. cli flags

example `pyproject.toml`:

```toml
[tool.raiseattention.analysis]
local_only = false    # set to true to skip external module analysis
warn_native = true    # set to false to suppress native code warnings

# control which builtins are analysed
ignore_include = ["str", "print"]  # always ignore these builtins
ignore_exclude = ["open"]          # never ignore this builtin (overrides ignore_include)
```

### inline ignore comments

suppress specific exceptions on a single line:

```python
import json

def parse_data(data: str) -> dict:
    return json.loads(data)  # raiseattention: ignore[JSONDecodeError]
```

multi-line statements work too:

```python
result = some_function(
    arg1,
    arg2,
)  # raiseattention: ignore[ValueError, TypeError]
```

shorthand formats (all case-insensitive):

```python
# raiseattention: ignore[ValueError]
# RaiseAttention: ignore[ValueError]
# ra: ignore[ValueError]
# RA: ignore[ValueError]
```

plain `# raiseattention: ignore` without brackets is invalid and will be reported
as a warning.

### docstring-based suppression

if a line raises an exception, RaiseAttention checks the closest parent function's
docstring. if the docstring contains "raise" or "raises" and the exception class
name, the diagnostic is suppressed:

```python
def parse_config(path: str) -> dict:
    """may raise ValueError if config is invalid."""
    return json.loads(read_file(path))  # no diagnostic - ValueError is documented
```

### cli flags

- `--version` — show version (2026.2.14)
- `--local` — analyse only first-party code (skip external modules)
- `--strict` — enable strict mode (flags undocumented exceptions)
- `--debug` — enable debug logging
- `--no-warn-native` — suppress `PossibleNativeException` warnings
- `--json` — output diagnostics as json
- `--absolute` — use absolute paths in output
- `--full-module-path` — show full module path for exceptions

## workspace packages

this repository contains several packages:

- **raiseattention** (2026.2.14) — main exception analyser
- **libsoulsearching** (0.1.0) — virtual environment detection library
- **libsightseeing** (0.1.0) — file finding with gitignore support
- **standardstubber** (2026.2.14, private) — cpython stub generator

## licence

RaiseAttention is free and unencumbered software released into the public domain.
for more information, please refer to the [UNLICENCE](/UNLICENCE) or <https://unlicense.org>.
