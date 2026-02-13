"""
pattern matching module for libsightseeing.

handles include/exclude glob pattern matching for files.
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path


class PatternMatcher:
    """
    matcher for include/exclude glob patterns.

    matches file paths against include and exclude glob patterns.
    if no include patterns are specified, all files are considered included.

    attributes:
        `include: list[str]`
            glob patterns for files to include
        `exclude: list[str]`
            glob patterns for files to exclude

    usage:
        ```python
        matcher = PatternMatcher(
            include=["*.py", "src/**/*.py"],
            exclude=["tests", ".venv"]
        )
        if matcher.matches(Path("./src/main.py"), Path(".")):
            print("file matches patterns")
        ```
    """

    include: list[str]
    exclude: list[str]

    def __init__(self, include: list[str], exclude: list[str]) -> None:
        """
        initialise the pattern matcher.

        arguments:
            `include: list[str]`
                glob patterns for files to include
            `exclude: list[str]`
                glob patterns for files to exclude
        """
        self.include = include
        self.exclude = exclude

    def matches(self, file_path: Path, root: Path) -> bool:
        """
        check if a file matches the include/exclude patterns.

        a file matches if:
        1. it matches at least one include pattern (or no include patterns specified)
        2. it does not match any exclude pattern

        arguments:
            `file_path: Path`
                the file path to check
            `root: Path`
                the root directory for relative path calculation

        returns: `bool`
            True if the file matches, False otherwise
        """
        # get relative path from root for matching
        try:
            rel_path = file_path.relative_to(root)
        except ValueError:
            # file is not under root, use absolute path
            rel_path = file_path

        # normalize path separators for cross-platform matching
        rel_path_str = str(rel_path).replace("\\", "/")
        file_name = file_path.name

        # check exclude patterns first
        for pattern in self.exclude:
            if self._match_pattern(rel_path_str, file_name, pattern):
                return False
            # also check if any parent directory matches the exclude pattern
            # (e.g., .venv should match .venv/script.py)
            if "/" in rel_path_str:
                path_parts = rel_path_str.split("/")
                for i in range(len(path_parts) - 1):  # -1 to not include the filename
                    parent_path = "/".join(path_parts[: i + 1])
                    if fnmatch(parent_path, pattern):
                        return False

        # check include patterns
        if not self.include:
            # no include patterns means include all
            return True

        for pattern in self.include:
            if self._match_pattern(rel_path_str, file_name, pattern):
                return True

        # didn't match any include pattern
        return False

    def _match_pattern(self, rel_path: str, file_name: str, pattern: str) -> bool:
        """
        match a path against a glob pattern.

        arguments:
            `rel_path: str`
                relative path from root
            `file_name: str`
                just the filename
            `pattern: str`
                glob pattern to match against

        returns: `bool`
            True if the path matches the pattern
        """
        # match against full relative path
        if fnmatch(rel_path, pattern):
            return True

        # match against filename only (for patterns like "*.py")
        if fnmatch(file_name, pattern):
            return True

        # match against path components (for directory patterns)
        if "/" in pattern:
            # handle ** patterns
            if "**" in pattern:
                parts = rel_path.split("/")
                pattern_parts = pattern.split("/")

                # handle patterns like "src/**/*.py"
                if "**" in pattern_parts:
                    # split pattern around **
                    idx = pattern_parts.index("**")
                    prefix = "/".join(pattern_parts[:idx])  # e.g., "src"
                    suffix = "/".join(pattern_parts[idx + 1 :])  # e.g., "*.py"

                    # check if path starts with prefix
                    if prefix and not rel_path.startswith(prefix + "/"):
                        return False

                    # check if any suffix of the path matches the suffix pattern
                    for i in range(len(parts)):
                        path_suffix = "/".join(parts[i:])
                        if fnmatch(path_suffix, suffix):
                            return True

                # simple ** matching - check if pattern matches as suffix
                if pattern.startswith("**/"):
                    suffix_pattern = pattern[3:]
                    if fnmatch(rel_path, suffix_pattern):
                        return True
                    # check each suffix
                    for i in range(len(parts)):
                        path_suffix = "/".join(parts[i:])
                        if fnmatch(path_suffix, suffix_pattern):
                            return True

        return False
