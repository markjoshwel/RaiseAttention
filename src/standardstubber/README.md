# standardstubber

> **note**
> standardstubber is at 0.1.0 and is primarily used internally within the raiseattention
> workspace. it is functional but not yet extensively battle-tested for external use.

a cpython standard library exception stub generator that extracts exception signatures
from cpython's c extension modules and generates `.pyras` stub files for raiseattention.

## overview

cpython's standard library includes many c extension modules (`_json.c`, `zlibmodule.c`,
`_ssl.c`, etc.) that signal exceptions by calling `PyErr_SetString()` or similar to set
cpython's error indicator, then returning an error sentinel (`NULL`, `-1`, etc.).

from python's perspective, this appears as a normal exception at the call site,
but static analysis of python source cannot see into c implementations. standardstubber
pre-computes exception metadata from the c source, enabling raiseattention to track
exceptions from native code through python call chains.

## project structure

```
standardstubber/
├── standardstubber/         # main package
│   ├── __init__.py          # public api exports
│   ├── cli.py               # command-line interface
│   ├── analyser.py          # c source analysis using libclang
│   ├── models.py            # data models for .pyras files
│   ├── patterns.py          # error propagation pattern detection
│   ├── resolver.py          # stub file resolution at check-time
│   └── writer.py            # incremental toml file writer
├── resources/               # analysis specifications
│   ├── cpython-analysis.md  # detailed cpython analysis guide
│   └── Python-*.tar.xz      # cpython source tarballs (for generation)
├── generate_all.py          # batch stub generator for multiple versions
├── pyproject.toml           # package configuration
└── README.md                # this file
```

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

generate all stdlib stubs for multiple python versions (used for creating the shipped stubs):

```text
python generate_all.py --jobs 16 --verbose
```

## the .pyras file format

`.pyras` (python raiseattention stub) files are TOML-based exception metadata stubs for
native/unanalysable python functions. they enable raiseattention to track exceptions
through c extension modules that cannot be statically analysed from python source alone.

### design goals

- **human-readable:** deterministic sorting, optional comments supported
- **machine-parseable:** standard TOML format (parsed with `tomllib`)
- **version-aware:** PEP 440 specifiers for matching python/package versions
- **confidence-rated:** tiered trust levels (`conservative` < `likely` < `exact` < `manual`)

### file structure

```
[metadata]                    # required header (exactly one)
name = "..."
version = "..."

["module.function"]           # function stub sections (one per function)
raises = [...]
confidence = "..."
```

### complete example

```toml
[metadata]
name = "stdlib"
version = ">=3.12,<3.13"
format_version = "1.0"
generator = "standardstubber@0.1.0"
generated_at = "2026-02-03T10:30:00"

["builtins.open"]
raises = ["OSError", "TypeError", "ValueError"]
confidence = "exact"

["json.loads"]
raises = ["TypeError", "json.JSONDecodeError"]
confidence = "exact"

["json.JSONDecoder.decode"]
raises = ["json.JSONDecodeError"]
confidence = "exact"

["_json.encode_basestring_ascii"]
raises = ["ValueError", "TypeError"]
confidence = "exact"

["zlib.compress"]
raises = ["TypeError", "OverflowError", "zlib.error"]
confidence = "exact"

["_pickle.Pickler.dump"]
raises = ["Exception"]
confidence = "conservative"
```

### metadata section `[metadata]` (required)

must appear first. contains file-level metadata.

| field | required | type | description |
|-------|----------|------|-------------|
| `name` | **yes** | string | package name: `"stdlib"`, `"pydantic-core"`, `"numpy"` |
| `version` | **yes** | string | PEP 440 version specifier |
| `format_version` | no | string | format version: `"1.0"` (default) |
| `generator` | no | string | tool that created the file: `"standardstubber@0.1.0"` |
| `generated_at` | no | string | ISO8601 timestamp: `"2026-02-03T10:30:00"` |
| `package` | no | string | import name (for third-party, when different from distribution name) |

**version specifiers:**

```toml
# for stdlib (CPython versions)
version = ">=3.12,<3.13"     # CPython 3.12.x only
version = ">=3.10,<3.14"     # CPython 3.10, 3.11, 3.12, 3.13
version = "==3.12.*"         # only 3.12.x patches

# for third-party packages
name = "pydantic-core"
package = "pydantic_core"    # import name
version = ">=2.0,<3.0"       # pydantic-core 2.x series
```

### function stub sections `["qualname"]`

each function gets its own TOML table with the fully qualified name as the key.

| field | required | type | description |
|-------|----------|------|-------------|
| `qualname` (table name) | **yes** | string | fully qualified name: `"json.loads"` |
| `raises` | **yes** | list[string] | exception types the function may raise |
| `confidence` | no | string | trust level (see below) |

**qualname format:**

```toml
# module-level functions
["json.loads"]
["zlib.compress"]
["_json.encode_basestring_ascii"]

# class methods (dot notation)
["json.JSONDecoder.decode"]
["pickle.Pickler.dump"]

# nested modules
["xml.etree.ElementTree.parse"]
```

**exception type formats:**
- built-ins: `"ValueError"`, `"TypeError"`, `"OSError"`, `"MemoryError"`
- module-specific: `"json.JSONDecodeError"`, `"zlib.error"`, `"pickle.PickleError"`
- conservative fallback: `["Exception"]`

### confidence levels

confidence is **optional** and defaults to `exact` when omitted. the levels form a hierarchy:

| level | rank | meaning | when to use |
|-------|------|---------|-------------|
| `conservative` | 0 (lowest) | unknown, erring on safety | complex control flow, unanalysed callee |
| `likely` | 1 | reasonable inference | argument parsing implies TypeError, complex branches |
| `exact` | 2 | proven from source | found explicit `PyErr_SetString` with known type |
| `manual` | 3 (highest) | hand-curated by expert | expert knowledge or documentation-based |

**merging behaviour:** when deduplicating stubs with the same qualname, the more conservative
confidence is kept. the order is: `conservative` < `likely` < `exact` < `manual`.

### raises list

the `raises` field is an array of exception type names:

```toml
["module.function"]
raises = ["ValueError", "TypeError", "OSError"]
```

**exception type formats:**
- built-in exceptions: `"ValueError"`, `"TypeError"`, `"OSError"`
- module-specific exceptions: `"json.JSONDecodeError"`, `"zlib.error"`
- nested exceptions: `"xml.etree.ElementTree.ParseError"`
- conservative fallback: `["Exception"]` when specific types cannot be determined

**deterministic ordering:**
standardstubber sorts exception types alphabetically for consistent, diff-friendly output.

### output conventions

standardstubber produces `.pyras` files with these conventions:

1. **sorted by module** - all functions from `_json` together, then `_pickle`, etc.
2. **sorted by qualname** within each module
3. **deterministic exception ordering** - alphabetically sorted
4. **blank lines between stubs** for readability
5. **optional fields omitted** when empty (no `confidence = "exact"` when it's the default)

### usage in raiseattention

```python
from packaging.specifiers import SpecifierSet
from packaging.version import Version
from pathlib import Path
import tomllib

# load and parse a .pyras file
with open("stubs/stdlib/python-3.12.pyras", "rb") as f:
    data = tomllib.load(f)

# check metadata
metadata = data["metadata"]
specifier = SpecifierSet(metadata["version"])
target = Version("3.12.1")
if target in specifier:
    # version matches, use this stub file
    pass

# look up a function
func_data = data.get("json.loads")
if func_data:
    raises = func_data.get("raises", [])  # ["TypeError", "json.JSONDecodeError"]
    confidence = func_data.get("confidence", "exact")
```

## architecture

### key components

1. **analyser.py** - c source analysis using libclang:
   - `CPythonAnalyser` class parses cpython c modules
   - identifies `PyMethodDef` arrays to find exported functions
   - extracts `PyErr_*` function calls to determine exception types
   - detects argument clinic usage (implies `TypeError`/`ValueError`)
   - performs call graph propagation for transitive exception tracking

2. **patterns.py** - error propagation pattern detection:
   - detects common cpython error handling idioms
   - identifies goto-based cleanup patterns
   - detects null-check error propagation
   - recognises error clearing vs. propagation

3. **models.py** - data models:
   - `Confidence` enum for analysis confidence levels
   - `FunctionStub` - exception stub for a single function
   - `StubFile` - complete .pyras file with metadata
   - `ModuleGraph` - call graph for intra-module propagation
   - `FunctionSummary` - analysis summary for call graph analysis

4. **resolver.py** - stub resolution at check-time:
   - `StubResolver` searches multiple stub sources by priority
   - version-aware resolution using `packaging` library
   - caching for performance
   - project-local override support

5. **writer.py** - incremental TOML writer:
   - `write_stub_file_incremental()` for efficient file generation
   - explicit deduplication by qualname
   - deterministic sorting for reproducible output
   - proper TOML string escaping

### how it works

```python
from standardstubber import CPythonAnalyser

# create analyser for cpython source tree
analyser = CPythonAnalyser(cpython_root=Path("/path/to/cpython"))

# parse and analyse a c module
tu = analyser.parse_module(Path("/path/to/cpython/Modules/_json.c"))

# find exported functions (PyMethodDef arrays)
exports = analyser.find_exported_functions(tu)
# exports: {"loads": "py_loads", "dumps": "py_dumps", ...}

# analyse with propagation
graph = analyser.analyse_module_with_propagation(c_file, "_json")

# get final stubs with transitive exceptions
stubs = graph.get_exported_stubs()
```

### exception extraction patterns

**pattern 1: direct pyerr_setstring**

```c
if (error_condition) {
    PyErr_SetString(PyExc_ValueError, "message");
    return NULL;
}
```
→ records `ValueError`

**pattern 2: pyerr_format**

```c
PyErr_Format(PyExc_TypeError, "expected %.100s", expected);
return NULL;
```
→ records `TypeError`

**pattern 3: pyerr_setfromerrno**

```c
if (result < 0) {
    PyErr_SetFromErrno(PyExc_OSError);
    return NULL;
}
```
→ records `OSError`

**pattern 4: argument parsing**

```c
if (!PyArg_ParseTuple(args, "s#:method", &buffer, &length)) {
    return NULL;
}
```
→ records `TypeError`

**pattern 5: error propagation**

```c
PyObject *result = PyObject_CallFunction(func, "O", arg);
if (result == NULL) {
    return NULL;  // propagates whatever exception 'func' raised
}
```
→ marks as "may raise Exception" or analyses callee transitively

### call graph propagation

standardstubber builds intra-module call graphs to compute transitive exception
propagation:

1. **first pass**: analyse each function to find local exception sources
   - direct `PyErr_*` calls
   - argument parsing
   - calls to functions in the same translation unit

2. **second pass**: propagate exceptions through the call graph via fixpoint iteration
   - if function a calls function b and propagates errors
   - and function b raises `ValueError`
   - then function a also raises `ValueError`

this is essential for accuracy because cpython modules often have deep call chains:
```c
// _json.c example chain
py_scanstring()      // may raise ValueError (explicit)
  → scanstring_str() // propagates from scanstring
    -> match_number() // propagates from scanstring
      -> parse_number() // may also raise
```

## installation

install from the raiseattention workspace:

```text
uv pip install -e src/standardstubber
```

or with development dependencies:

```text
uv pip install -e "src/standardstubber[dev]"
```

**nix users, rejoice:** this package is part of the raiseattention workspace which
provides a nix development shell with all dependencies.

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
  --no-propagation      disable call graph propagation analysis (faster but
                        less accurate)
  --jobs JOBS, -j JOBS  number of parallel jobs (default: cpu count)
  --profile             output timing breakdown per phase (deprecated, use -v)
```

## programmatic api

### basic usage

```python
from standardstubber import (
    CPythonAnalyser,
    StubResolver,
    create_default_resolver,
    FunctionStub,
    StubFile,
)

# analyse cpython source
analyser = CPythonAnalyser(cpython_root=Path("/path/to/cpython"))
c_file = Path("/path/to/cpython/Modules/_json.c")
graph = analyser.analyse_module_with_propagation(c_file, "_json")
stubs = graph.get_exported_stubs()

# write stub file
metadata = StubMetadata(
    name="stdlib",
    version=">=3.12,<3.13",
    generator="standardstubber@0.1.0",
)
stub_file = StubFile(metadata=metadata, stubs=stubs)
stub_file.write(Path("stdlib-3.12.pyras"))
```

### resolving stubs at check-time

```python
from standardstubber import StubResolver, create_default_resolver
from packaging.version import Version

# create resolver with default sources
resolver = create_default_resolver(
    project_root=Path("/path/to/project"),
    python_version="3.12",
)

# look up exception signature
result = resolver.get_raises("json.loads")
if result:
    print(f"raises: {result.raises}")
    print(f"confidence: {result.confidence}")
    print(f"source: {result.source}")
```

## development

### running tests

```text
cd src/standardstubber
uv run pytest tests/ -v
```

### linting and type checking

```text
uv run ruff check standardstubber/
uv run ruff format standardstubber/
uv run mypy standardstubber/
```

### generating all stdlib stubs

```text
python generate_all.py --jobs 16 --verbose
```

this will:
1. extract each cpython tarball in `resources/`
2. analyse all c modules with parallel workers
3. generate `.pyras` files in `../raiseattention/stubs/stdlib/`

## dependencies

### required

- `libclang>=18.1.1` - c parser for analysing cpython source
- `packaging>=24.0` - pep 440 version specifier handling
- `typing-extensions>=4.6.0` - type hints backport

### development

- `pytest>=8.0.0` - testing framework

## known limitations

1. **c extensions only** - standardstubber only analyses c extension modules, not
   pure python code (raiseattention handles that separately)

2. **platform-specific code** - `#ifdef` branches for different platforms may not
   all be analysed (libclang sees one platform at a time)

3. **dynamic exception types** - if a function calls `PyErr_SetObject()` with a
   dynamically-determined exception type, we fall back to `Exception`

4. **cross-module calls** - calls to functions in other modules are treated as
   "may raise Exception" (conservative fallback)

5. **macro-based errors** - some cpython error handling uses complex macros that
   may not be fully analysed

## docstring format

all python code uses the meadow docstring format (mdf):

- **lowercase** all docstrings and comments
- **british english** spelling (analyse, behaviour, colour)
- plaintext-first with backtick-quoted type annotations

see `resources/MDF.md` in the raiseattention workspace for the full specification.

## code style

- python 3.11+ minimum
- type hints everywhere
- `pathlib.Path` over `os.path`
- f-strings for string formatting
- maximum line length: 100 characters
- british spelling throughout

## licence

standardstubber is part of raiseattention and follows the same licencing.
see the main raiseattention `UNLICENCE` file for details.

## see also

- `resources/cpython-analysis.md` - detailed cpython analysis guide
- raiseattention's `external_analyser.py` - uses these stubs at check-time
- cpython developer's guide: <https://devguide.python.org/>
- libclang documentation: <https://libclang.readthedocs.io/>
