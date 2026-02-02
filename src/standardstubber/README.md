# standardstubber

CPython standard library exception stub generator for RaiseAttention.

## Overview

This package extracts exception signatures from CPython's C extension modules
and generates `.pyras` stub files. These stubs enable RaiseAttention to track
exceptions from native code that cannot be statically analysed.

## Usage

```bash
# Generate stubs from a CPython source tarball
standardstubber --cpython Python-3.12.12.tar.xz --version ">=3.12,<3.13" -o stdlib-3.12.pyras

# Generate stubs from an extracted source tree
standardstubber --cpython /path/to/cpython --version ">=3.12,<3.13" -o stdlib-3.12.pyras
```

## .pyras File Format

The `.pyras` (Python RaiseAttention Stub) format is a TOML-based file containing
exception metadata for functions:

```toml
[metadata]
name = "stdlib"
version = ">=3.12,<3.13"
format_version = "1.0"
generator = "standardstubber@0.1.0"

["json.loads"]
raises = ["TypeError", "json.JSONDecodeError"]
confidence = "exact"

["zlib.compress"]
raises = ["TypeError", "OverflowError", "zlib.error"]
confidence = "exact"
```

## Development

This package is part of the RaiseAttention workspace. Install with:

```bash
uv pip install -e src/standardstubber
```
