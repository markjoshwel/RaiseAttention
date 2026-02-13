# libsightseeing

a shared library for file finding and source resolution with gitignore support,
after i needed a simple way to find files while respecting .gitignore

## installation

```text
pip install libsightseeing
```

## usage

### finding project root

```python
from libsightseeing import find_project_root

# find project root from current directory
root = find_project_root()
if root:
    print(f"found project at: {root}")

# find from a subdirectory
root = find_project_root("~/Works/example/sub/dir")
if root:
    print(f"found project at: {root}")  # ~/Works/example

# use with custom markers
root = find_project_root(
    ".",
    markers=[".git", "pyproject.toml", "package.json"]
)
```

### finding files

```python
from libsightseeing import find_files

# find all python files
files = find_files(".", include=["*.py"])

# find files excluding tests
files = find_files("src", exclude=["tests"])

# include gitignored files
files = find_files(".", include=["*.py"], respect_gitignore=False)
```

### combining both

```python
from libsightseeing import find_project_root, find_files

# find project root first, then find files there
root = find_project_root(".")
if root:
    files = find_files(root, include=["*.py"])
```

### advanced api

```python
from libsightseeing import SourceResolver

resolver = SourceResolver(
    root=".",
    include=["src/**/*.py"],
    exclude=["tests"],
    respect_gitignore=True,
)
files = resolver.resolve()
```

## features

- **find project root**  
  walk up the tree looking for .git, pyproject.toml, package.json, cargo.toml, etc.

- **respects .gitignore**  
  automatically excludes gitignored files

- **glob patterns**  
  supports include/exclude patterns

- **simple one-liner**  
  `find_files()` and `find_project_root()` for quick usage

- **configurable resolver**  
  `SourceResolver` for advanced cases

- **lightweight**  
  only depends on pathspec

## licence

libsightseeing is unencumbered, free-as-in-freedom, and is dual-licenced under
The Unlicense or the BSD Zero Clause License. (SPDX: `Unlicense OR 0BSD`)

you are free to use the software as you wish, without any restrictions or
obligations, subject only to the warranty disclaimers in the licence text
of your choosing.
