# RaiseAttention

> [!WARNING]
> this project is vibe coded, as a test of Kimi K2.5. it isn't battle tested,
> so issues may arise. if you're willing to run into potential bugs, feel free to use it!

a static exception flow analyser for python that identifies unhandled exceptions in your
codebase—even the ones you think are handled.

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

install from source:

```text
pip install git+https://github.com/markjoshwel/RaiseAttention.git
```

**nix users, rejoice:** `nix run github:markjoshwel/RaiseAttention`

### cli

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

the lsp server will give you errors when you're calling a function that may raise an
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
- **docstring heuristics** — checks `__doc__` for "raises" keywords when static analysis
  isn't possible
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
```

### cli flags

- `--local` — analyse only first-party code (skip external modules)
- `--strict` — enable strict mode (flags undocumented exceptions)
- `--debug` — enable debug logging
- `--no-warn-native` — suppress `PossibleNativeException` warnings
- `--json` — output diagnostics as json
- `--absolute` — use absolute paths in output
- `--full-module-path` — show full module path for exceptions

## licence

RaiseAttention is free and unencumbered software released into the public domain.
for more information, please refer to the [UNLICENCE](/UNLICENCE) or <https://unlicense.org>.
