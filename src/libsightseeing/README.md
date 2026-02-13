# libsightseeing

a shared library for file finding and source resolution with gitignore support.
i built this because i needed a simple way to find files while respecting
.gitignore without pulling in heavy dependencies.

## installation

```text
pip install libsightseeing
```

**nix users, rejoice:** available via the RaiseAttention workspace

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

et voilà! — file finding without the fuss.

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

- **respects .gitignore** — automatically excludes gitignored files
- **glob patterns** — supports include/exclude patterns
- **simple one-liner** — `find_files()` for quick usage
- **configurable resolver** — `SourceResolver` for advanced cases
- **lightweight** — only depends on pathspec

## licence

libsightseeing is free and unencumbered software released into the public domain.
for more information, please refer to <https://unlicense.org/> or go ham with the
zero-clause bsd licence — your choice.

see [LICENCING](../../LICENCING) for details.
