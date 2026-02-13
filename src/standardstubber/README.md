# standardstubber

> **note**
> standardstubber is at 2026.2.14+1 and is primarily used internally within the
> RaiseAttention workspace. it is functional but not extensively battle-tested for
> external use.

a cpython standard library exception stub generator that extracts exception signatures
from cpython's c extension modules and generates `.pyras` stub files for RaiseAttention.

## overview

cpython's standard library includes many c extension modules (`_json.c`, `zlibmodule.c`,
`_ssl.c`, etc.) that signal exceptions by calling `PyErr_SetString()` or similar to set
cpython's error indicator, then returning an error sentinel (`NULL`, `-1`, etc.).

from python's perspective, this appears as a normal exception at the call site,
but static analysis of python source cannot see into c implementations. standardstubber
pre-computes exception metadata from the c source, enabling RaiseAttention to track
exceptions from native code through python call chains.

## usage

### quick examples

generate stubs using a tarball from the included resources:

```text
uv run standardstubber --cpython src/standardstubber/resources/Python-3.10.19.tar.xz --version ">=3.10,<3.11" -o src/raiseattention/stubs/stdlib/python-3.10.pyras
```

generate stubs from a downloaded cpython tarball:

```text
uv run standardstubber --cpython ~/Downloads/Python-3.12.12.tar.xz --version ">=3.12,<3.13" -o stdlib-3.12.pyras
```

generate stubs from an already-extracted source tree:

```text
uv run standardstubber --cpython /path/to/cpython --version ">=3.12,<3.13" -o stdlib-3.12.pyras
```

### batch generation

generate all stdlib stubs for multiple python versions:

```text
python generate_all.py --jobs 16 --verbose
```

## the .pyras file format (v2.0)

`.pyras` (python raiseattention stub) files are **JSON-based** exception metadata stubs for
native/unanalysable python functions. v2.0 uses a nested JSON structure that supports
per-exception confidence levels and efficient parsing.

### design goals

- **fast parsing**  
  JSON format (parsed with stdlib `json` module)

- **nested structure**  
  module → class → method → exception → confidence

- **version-aware**  
  PEP 440 specifiers for matching python/package versions

- **per-exception confidence**  
  each exception can have its own trust level

- **fuzzy matching**  
  resolver handles class name mismatches

see the detailed format documentation in the [architecture section](#architecture).

## architecture

### key components

1. **analyser.py**  
   c source analysis using libclang

2. **patterns.py**  
   error propagation pattern detection

3. **models.py**  
   data models for .pyras files

4. **resolver.py**  
   stub resolution at check-time

5. **writer_json.py**  
   JSON v2.0 file writer

### exception extraction patterns

**pattern 1: direct pyerr_setstring**

```c
if (error_condition) {
    PyErr_SetString(PyExc_ValueError, "message");
    return NULL;
}
```

→ records `ValueError` with confidence "exact"

**pattern 2: pyerr_format**

```c
PyErr_Format(PyExc_TypeError, "expected %.100s", expected);
return NULL;
```

→ records `TypeError` with confidence "exact"

**pattern 3: argument parsing**

```c
if (!PyArg_ParseTuple(args, "s#:method", &buffer, &length)) {
    return NULL;
}
```

→ records `TypeError` with confidence "likely"

### call graph propagation

standardstubber builds intra-module call graphs to compute transitive exception
propagation. if function a calls function b and propagates errors, and function b
raises `ValueError`, then function a also raises `ValueError`.

## installation

install from the RaiseAttention workspace:

```text
uv pip install -e src/standardstubber
```

or with development dependencies:

```text
uv pip install -e "src/standardstubber[dev]"
```

## cli reference

```text
standardstubber --help
```

```
usage: standardstubber [-h] --cpython CPYTHON --version VERSION --output OUTPUT
                       [--verbose] [--debug] [--no-propagation] [--jobs JOBS]
                       [--profile]

generate .pyras exception stubs from cpython source

options:
  -h, --help            show this help message and exit
  --cpython CPYTHON     path to cpython source tree or .tar.xz archive
  --version VERSION     pep 440 version specifier (e.g., '>=3.12,<3.13')
  --output OUTPUT, -o OUTPUT
                        output .pyras file path
  --verbose, -v         enable verbose logging
  --debug               enable debug logging
  --no-propagation      disable call graph propagation analysis
  --jobs JOBS, -j JOBS  number of parallel jobs
  --profile             output timing breakdown per phase
```

## dependencies

- `libclang>=18.1.1`  
  c parser for analysing cpython source

- `packaging>=24.0`  
  pep 440 version specifier handling

- `typing-extensions>=4.6.0`  
  type hints backport

## docstring format

all python code uses the meadow docstring format (mdf):

- **lowercase**  
  all docstrings and comments

- **british english**  
  spelling (analyse, behaviour, colour)

- **plaintext-first**  
  with backtick-quoted type annotations

see `resources/MDF.md` in the RaiseAttention workspace for the full specification.

## code style

- python 3.11+ minimum
- type hints everywhere
- `pathlib.Path` over `os.path`
- f-strings for string formatting
- maximum line length: 100 characters
- british spelling throughout

## licence

standardstubber is unencumbered, free-as-in-freedom, and is dual-licenced under
The Unlicense or the BSD Zero Clause License. (SPDX: `Unlicense OR 0BSD`)

you are free to use the software as you wish, without any restrictions or
obligations, subject only to the warranty disclaimers in the licence text
of your choosing.
