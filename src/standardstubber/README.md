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
│   ├── writer_json.py       # json v2.0 file writer
│   └── writer.py            # incremental toml v1.0 file writer (legacy)
├── typings/                 # type stubs for libclang
│   └── clang/
│       └── cindex.pyi       # type annotations for clang bindings
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

## the .pyras file format (v2.0)

`.pyras` (python raiseattention stub) files are **JSON-based** exception metadata stubs for
native/unanalysable python functions. v2.0 replaces the old TOML format with a nested JSON
structure that supports per-exception confidence levels and efficient parsing.

### design goals

- **fast parsing:** JSON format (parsed with stdlib `json` module)
- **nested structure:** module → class → method → exception → confidence
- **version-aware:** PEP 440 specifiers for matching python/package versions
- **per-exception confidence:** each exception can have its own trust level
- **fuzzy matching:** resolver handles class name mismatches (e.g., `mmap.mmap` vs `mmap.Mmap_object`)

### file structure

```json
{
  "metadata": {
    "name": "stdlib",
    "version": ">=3.12,<3.13",
    "format_version": "2.0",
    "generator": "standardstubber@0.1.0"
  },
  "_io": {
    "BufferedReader": {
      "peek": {
        "TypeError": "exact"
      },
      "read": {
        "BufferError": "exact",
        "ValueError": "likely"
      }
    }
  },
  "json": {
    "loads": [
      "TypeError",
      "json.JSONDecodeError"
    ]
  }
}
```

### complete example

```json
{
  "metadata": {
    "name": "stdlib",
    "version": ">=3.12,<3.13",
    "format_version": "2.0",
    "generator": "standardstubber@0.2.0",
    "generated_at": "2026-02-03T10:30:00"
  },
  "_abc": {
    "Abcmodule": {
      "_abc_init": {
        "TypeError": "exact"
      },
      "_abc_instancecheck": [
        "TypeError"
      ],
      "get_cache_token": {
        "Exception": "conservative"
      }
    }
  },
  "_io": {
    "Bufferedreader": {
      "peek": {
        "TypeError": "exact"
      },
      "read": [
        "BufferError",
        "ValueError"
      ]
    }
  },
  "mmap": {
    "Mmap_object": {
      "read": {
        "BufferError": "exact"
      },
      "readline": [
        "BufferError"
      ]
    }
  }
}
```

### metadata section

the `"metadata"` object is required and must appear first:

| field | required | type | description |
|-------|----------|------|-------------|
| `name` | **yes** | string | package name: `"stdlib"`, `"pydantic-core"`, `"numpy"` |
| `version` | **yes** | string | PEP 440 version specifier |
| `format_version` | no | string | format version: `"2.0"` |
| `generator` | no | string | tool version: `"standardstubber@0.2.0"` |
| `generated_at` | no | string | ISO8601 timestamp |
| `package` | no | string | import name for third-party packages |

**version specifiers:**

```json
{
  "metadata": {
    "name": "stdlib",
    "version": ">=3.12,<3.13"
  }
}
```

### nested structure

the json structure follows the hierarchy: `module` → `class` → `method` → `exception` → `confidence`

**module-level functions:**
use empty string `""` as class key, merged into module directly in output:

```json
{
  "json": {
    "loads": [
      "TypeError",
      "json.JSONDecodeError"
    ]
  }
}
```

**class methods:**
nested under class name key:

```json
{
  "_io": {
    "Bufferedreader": {
      "peek": {
        "TypeError": "exact"
      }
    }
  }
}
```

### exception data formats

two formats are supported for exception data:

1. **list format** (compact, all default confidence):
   ```json
   "loads": ["TypeError", "ValueError"]
   ```
   all exceptions use default confidence (`"likely"`)

2. **dict format** (explicit per-exception confidence):
   ```json
   "peek": {
     "TypeError": "exact",
     "ValueError": "likely"
   }
   ```
   each exception has its own confidence level

### confidence levels

confidence is **optional** and defaults to `"likely"` when omitted. the levels form a hierarchy:

| level | rank | meaning | when to use |
|-------|------|---------|-------------|
| `conservative` | 0 (lowest) | unknown, erring on safety | complex control flow, unanalysed callee |
| `likely` | 1 | reasonable inference | argument parsing implies TypeError, complex branches |
| `exact` | 2 | proven from source | found explicit `PyErr_SetString` with known type |
| `manual` | 3 (highest) | hand-curated by expert | expert knowledge or documentation-based |

**merging behaviour:** when deduplicating, the more conservative confidence is kept.
the order is: `conservative` < `likely` < `exact` < `manual`.

### exception type formats

- built-ins: `"ValueError"`, `"TypeError"`, `"OSError"`, `"MemoryError"`
- module-specific: `"json.JSONDecodeError"`, `"zlib.error"`, `"pickle.PickleError"`
- conservative fallback: `["Exception"]` or `{"Exception": "conservative"}`

### output conventions

standardstubber produces `.pyras` v2.0 files with these conventions:

1. **sorted by module** - alphabetical order
2. **sorted by class** within each module
3. **sorted by method** within each class
4. **compact format** - list for all-default confidence, dict for mixed/explicit
5. **test modules filtered** - `_test*`, `xx*`, `_xx*` modules excluded

### usage in raiseattention

```python
from stub_resolver import create_stub_resolver

resolver = create_stub_resolver(python_version="3.12")

# exact match
result = resolver.get_raises("mmap.Mmap_object.readline")
print(result.raises)  # frozenset({'BufferError'})
print(result.confidence)  # 'exact'

# fuzzy match (handles class name mismatches)
result = resolver.get_raises("mmap.mmap.readline")  # finds Mmap_object.readline
print(result.raises)  # same as above

# per-exception confidence
print(result.per_exception_confidence)
# {'BufferError': 'exact'}
```

## architecture

### key components

1. **analyser.py** - c source analysis using libclang:
   - `CPythonAnalyser` class parses cpython c modules
   - identifies `PyMethodDef` arrays to find exported functions
   - extracts `PyErr_*` function calls to determine exception types
   - detects argument clinic usage (implies `TypeError`/`ValueError`)
   - performs call graph propagation for transitive exception tracking
   - **filters test modules** (`_test*`, `xx*`, `_xx*`) at discovery phase

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
   - **default confidence changed to "likely"** (was "exact")

4. **resolver.py** - stub resolution at check-time:
   - `StubResolver` searches multiple stub sources by priority
   - version-aware resolution using `packaging` library
   - **JSON parsing** (much faster than TOML)
   - **fuzzy matching** for class name mismatches
   - caching for performance

5. **writer_json.py** - JSON v2.0 writer:
   - `write_stub_file_json_v2()` for efficient file generation
   - **per-exception confidence** support
   - **nested structure** (module → class → method → exception)
   - deterministic sorting for reproducible output
   - **test module filtering** (excludes `_test*`, `xx*`, `_xx*`)

6. **writer.py** - TOML v1.0 writer (legacy):
   - `write_stub_file_incremental()` for old format
   - maintained for backward compatibility if needed

### v2.0 improvements

**json format benefits:**
- **faster parsing** - stdlib `json` vs `tomllib`
- **nested structure** - better organisation
- **per-exception confidence** - granular trust levels
- **smaller file size** - compact list format for default confidence
- **no test modules** - automatically filtered during generation

**fuzzy matching:**
- resolves class name mismatches (e.g., `mmap.mmap` → `mmap.Mmap_object`)
- handles underscore prefix variations (`io` ↔ `_io`)
- scans all classes in module for method name matches

**default confidence "likely":**
- more honest about uncertainty in static analysis
- "exact" only when proven from explicit `PyErr_SetString`

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

**pattern 3: pyerr_setfromerrno**

```c
if (result < 0) {
    PyErr_SetFromErrno(PyExc_OSError);
    return NULL;
}
```
→ records `OSError` with confidence "exact"

**pattern 4: argument parsing**

```c
if (!PyArg_ParseTuple(args, "s#:method", &buffer, &length)) {
    return NULL;
}
```
→ records `TypeError` with confidence "likely"

**pattern 5: error propagation**

```c
PyObject *result = PyObject_CallFunction(func, "O", arg);
if (result == NULL) {
    return NULL;  // propagates whatever exception 'func' raised
}
```
→ propagates exceptions transitively through call graph

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
from standardstubber import CPythonAnalyser
from standardstubber.models import StubMetadata
from standardstubber.writer_json import write_stub_file_json_v2
from pathlib import Path

# analyse cpython source
analyser = CPythonAnalyser(cpython_root=Path("/path/to/cpython"))
c_file = Path("/path/to/cpython/Modules/_json.c")
stubs = analyser.analyse_module_file(c_file, "_json")

# convert to raw tuples for v2.0
raw_stubs = [
    (stub.qualname, stub.raises, stub.confidence.value, stub.notes)
    for stub in stubs
]

# write v2.0 json file
metadata = StubMetadata(
    name="stdlib",
    version=">=3.12,<3.13",
    generator="standardstubber@0.2.0",
)
write_stub_file_json_v2(
    Path("stdlib-3.12.pyras"),
    metadata,
    raw_stubs,
    skip_test_modules=True,
)
```

### resolving stubs at check-time

```python
from stub_resolver import create_stub_resolver

resolver = create_stub_resolver(
    project_root=Path("/path/to/project"),
    python_version="3.12",
)

# look up exception signature
result = resolver.get_raises("json.loads")
if result:
    print(f"raises: {result.raises}")
    print(f"confidence: {result.confidence}")
    print(f"per-exception: {result.per_exception_confidence}")
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
uv run basedpyright standardstubber/  # from standardstubber/ directory
```

### generating all stdlib stubs

```text
python generate_all.py --jobs 16 --verbose
```

this will:
1. extract each cpython tarball in `resources/`
2. analyse all c modules with parallel workers (excluding test modules)
3. generate v2.0 JSON `.pyras` files in `../raiseattention/stubs/stdlib/`

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

6. **class name mapping** - we use C struct names (e.g., `Mmap_object`) rather
   than Python class names (e.g., `mmap`). the resolver uses fuzzy matching to
   handle this.

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
