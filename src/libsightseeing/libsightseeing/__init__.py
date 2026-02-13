"""
libsightseeing - a shared library for file finding and source resolution.

a library for finding files in repositories while respecting .gitignore files
and supporting include/exclude patterns.

functions:
    `find_files` - one-liner api for finding files
    `find_project_root` - find project root by walking up directory tree

classes:
    `SourceResolver` - configurable file resolver with gitignore support

usage:
    ```python
    from libsightseeing import find_files, find_project_root, SourceResolver

    # find project root
    root = find_project_root("~/Works/example/sub/dir")
    if root:
        print(f"found project at: {root}")  # ~/Works/example

    # simple file finding
    files = find_files(".", include=["*.py"])

    # advanced usage
    resolver = SourceResolver(
        root=".",
        include=["src/**/*.py"],
        exclude=["tests"],
        respect_gitignore=True,
    )
    files = resolver.resolve()
    ```
"""

from __future__ import annotations

from pathlib import Path

from .core import SourceResolver, find_project_root

__version__ = "0.2.0"
__all__ = ["find_files", "find_project_root", "SourceResolver"]


def find_files(
    root: str | Path = ".",
    *,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    respect_gitignore: bool = True,
) -> tuple[Path, ...]:
    """
    find files in a directory with gitignore support.

    a convenience function that creates a SourceResolver with the given
    parameters and returns the resolved files.

    arguments:
        `root: str | Path`
            the root directory to search in (default: current directory)
        `include: list[str] | None`
            glob patterns for files to include
        `exclude: list[str] | None`
            glob patterns for files to exclude
        `respect_gitignore: bool`
            whether to respect .gitignore files (default: True)

    returns: `tuple[Path, ...]`
        tuple of resolved file paths

    usage:
        ```python
        # find all python files
        files = find_files(".", include=["*.py"])

        # find files excluding tests
        files = find_files("src", exclude=["tests"])

        # include gitignored files
        files = find_files(".", include=["*.py"], respect_gitignore=False)
        ```
    """
    # call constructor directly, conditionally passing exclude
    # this preserves the default exclude patterns from SourceResolver when not specified
    if exclude is not None:
        resolver = SourceResolver(
            root=Path(root),
            include=include or [],
            exclude=exclude,
            respect_gitignore=respect_gitignore,
        )
    else:
        resolver = SourceResolver(
            root=Path(root),
            include=include or [],
            respect_gitignore=respect_gitignore,
        )
    return resolver.resolve()
