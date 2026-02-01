# libsightseeing

a shared library for file finding and source resolution with gitignore support.

## overview

libsightseeing provides a simple api for finding files in repositories while
respecting .gitignore files and supporting include/exclude patterns.

## installation

```bash
pip install libsightseeing
```

## usage

### simple api

```python
from libsightseeing import find_files

# find all python files
files = find_files(".", include=["*.py"])

# find files excluding tests
files = find_files("src", exclude=["tests"])

# include gitignored files
files = find_files(".", include=["*.py"], respect_gitignore=False)
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

- respects .gitignore files automatically
- supports glob patterns for include/exclude
- simple one-liner api
- configurable resolver for advanced use cases
- only depends on gitignore-parser

## licence

mit
