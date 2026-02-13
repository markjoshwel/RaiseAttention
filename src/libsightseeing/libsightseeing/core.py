"""
core module for libsightseeing.

contains the SourceResolver class for finding files with gitignore support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Generator
from typing import Final

from .gitignore import GitignoreMatcher
from .patterns import PatternMatcher

# default exclude patterns - only .venv as per requirements
DEFAULT_EXCLUDE: Final[list[str]] = [".venv"]

# default project markers to look for when finding project root
DEFAULT_PROJECT_MARKERS: Final[list[str]] = [
    # version control
    ".git",
    ".hg",
    ".svn",
    # python
    "pyproject.toml",
    "poetry.lock",
    "Pipfile",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    # rust
    "Cargo.toml",
    "Cargo.lock",
    # node.js/bun/deno
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "bun.lock",
    "deno.json",
    "deno.jsonc",
    # go
    "go.mod",
    "go.sum",
    # java
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    # php
    "composer.json",
    "composer.lock",
    # ruby
    "Gemfile",
    "Gemfile.lock",
    # c/c++
    "CMakeLists.txt",
    "Makefile",
    # zig
    "build.zig",
    # swift
    "Package.swift",
    # dart/flutter
    "pubspec.yaml",
    # elixir
    "mix.exs",
    # haskell
    "stack.yaml",
    "package.yaml",
    # docker
    "Dockerfile",
    "docker-compose.yml",
    # general
    "README.md",
    "LICENSE",
    ".editorconfig",
]


@dataclass
class SourceResolver:
    """
    configurable file resolver with gitignore support.

    resolves source files from a root directory, respecting .gitignore files
    and supporting include/exclude patterns.

    attributes:
        `root: Path`
            the root directory to search in
        `include: list[str]`
            glob patterns for files to include
        `exclude: list[str]`
            glob patterns for files to exclude
        `respect_gitignore: bool`
            whether to respect .gitignore files

    usage:
        ```python
        resolver = SourceResolver(
            root=Path("."),
            include=["src/**/*.py"],
            exclude=["tests"],
            respect_gitignore=True,
        )
        files = resolver.resolve()
        ```
    """

    root: Path
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=lambda: DEFAULT_EXCLUDE.copy())
    respect_gitignore: bool = True

    def __post_init__(self) -> None:
        """ensure root is a Path object."""
        self.root = Path(self.root).resolve()

    def resolve(self) -> tuple[Path, ...]:
        """
        resolve all files matching the configured patterns.

        walks the directory tree from root, collecting files that:
        1. match include patterns (if specified)
        2. do not match exclude patterns
        3. are not ignored by .gitignore (if respect_gitignore is True)

        returns: `tuple[Path, ...]`
            tuple of resolved file paths, sorted alphabetically
        """
        files: list[Path] = []
        gitignore_matcher: GitignoreMatcher | None = None

        if self.respect_gitignore:
            gitignore_matcher = GitignoreMatcher(self.root)

        pattern_matcher = PatternMatcher(self.include, self.exclude)

        for file_path in self._iter_files():
            # check if file matches patterns
            if not pattern_matcher.matches(file_path, self.root):
                continue

            # check if file is gitignored
            if gitignore_matcher is not None and gitignore_matcher.is_ignored(file_path):
                continue

            files.append(file_path)

        return tuple(sorted(files))

    def _iter_files(self) -> Generator[Path, None, None]:
        """
        iterate over all files in the root directory.

        yields: Path
            file paths (not directories)
        """
        if not self.root.exists():
            return

        for path in self.root.rglob("*"):
            if path.is_file():
                yield path


def find_project_root(
    start_path: str | Path = ".",
    markers: list[str] | None = None,
    max_depth: int = 100,
) -> Path | None:
    """
    find the nearest project root by walking up the directory tree.

    walks up from the start path looking for common project marker files
    or directories (.git, pyproject.toml, package.json, etc.).

    arguments:
        `start_path: str | Path`
            the starting directory (default: current directory)
        `markers: list[str] | None`
            list of marker files/directories to look for.
            defaults to common markers for various languages.
        `max_depth: int`
            maximum number of parent directories to traverse (default: 100)

    returns: `Path | None`
        path to the project root if found, None otherwise

    usage:
        ```python
        # find project root from current directory
        root = find_project_root()
        if root:
            print(f"found project at: {root}")

        # find from specific path with custom markers
        root = find_project_root(
            "~/Works/example/sub/dir",
            markers=[".git", "pyproject.toml"]
        )

        # use with libsightseeing
        root = find_project_root(".")
        if root:
            files = find_files(root, include=["*.py"])
        ```
    """
    start = Path(start_path).expanduser().resolve()

    # if start is a file, begin from its parent directory
    if start.is_file():
        start = start.parent

    # use default markers if none provided
    search_markers = markers if markers is not None else DEFAULT_PROJECT_MARKERS

    current = start
    depth = 0

    while current != current.parent and depth < max_depth:
        # check for any marker in current directory
        for marker in search_markers:
            marker_path = current / marker
            if marker_path.exists():
                return current

        # move up to parent
        current = current.parent
        depth += 1

    return None
