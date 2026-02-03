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
