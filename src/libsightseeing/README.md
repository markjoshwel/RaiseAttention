# libsightseeing

a shared library for file finding and source resolution with gitignore support.
i needed a simple way to find files while respecting .gitignore without pulling
in heavy dependencies.

## installation

```text
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

- **respects .gitignore**  
  automatically excludes gitignored files

- **glob patterns**  
  supports include/exclude patterns

- **simple one-liner**  
  `find_files()` for quick usage

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
