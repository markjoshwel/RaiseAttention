"""
gitignore handling module for libsightseeing.

handles parsing and matching of .gitignore files using pathspec.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathspec import GitIgnoreSpec


class GitignoreMatcher:
    """
    matcher for .gitignore rules.

    collects and applies .gitignore rules from the root directory
    and all subdirectories during file traversal.

    attributes:
        `root: Path`
            the root directory to match against
        `specs: list[tuple[Path, GitIgnoreSpec]]`
            list of (directory, spec) tuples

    usage:
        ```python
        matcher = GitignoreMatcher(Path("."))
        if matcher.is_ignored(Path("./file.txt")):
            print("file is ignored")
        ```
    """

    def __init__(self, root: Path) -> None:
        """
        initialise the gitignore matcher.

        arguments:
            `root: Path`
                the root directory to search for .gitignore files
        """
        self.root = root.resolve()
        self.specs: list[tuple[Path, GitIgnoreSpec]] = []
        self._collect_gitignore_rules()

    def _collect_gitignore_rules(self) -> None:
        """
        collect all .gitignore rules from root and subdirectories.

        finds all .gitignore files and parses their rules using pathspec.
        """
        from pathspec import GitIgnoreSpec

        # find all .gitignore files
        for gitignore_file in self.root.rglob(".gitignore"):
            if not gitignore_file.is_file():
                continue

            try:
                content = gitignore_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            # parse patterns from content
            patterns = []
            for line in content.splitlines():
                line = line.rstrip("\n")
                # skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                patterns.append(line)

            if patterns:
                spec = GitIgnoreSpec.from_lines(patterns)
                self.specs.append((gitignore_file.parent, spec))

    def is_ignored(self, file_path: Path) -> bool:
        """
        check if a file is ignored by any .gitignore rule.

        arguments:
            `file_path: Path`
                the file path to check

        returns: `bool`
            True if the file is ignored, False otherwise
        """
        resolved_path = file_path.resolve()

        # check if any parent directory is ignored first
        parent = resolved_path.parent
        while parent != parent.parent and self.root in parent.parents or parent == self.root:
            if self._is_path_ignored(parent):
                return True
            if parent == self.root:
                break
            parent = parent.parent

        # check the file itself
        return self._is_path_ignored(resolved_path)

    def _is_path_ignored(self, path: Path) -> bool:
        """
        check if a path is ignored by gitignore rules.

        arguments:
            `path: Path`
                the path to check

        returns: `bool`
            True if the path is ignored, False otherwise
        """
        matched = False

        for ignore_dir, spec in self.specs:
            # only apply rules from directories that contain the path
            if not str(path).startswith(str(ignore_dir)):
                continue

            # get relative path from the gitignore directory
            try:
                rel_path = path.relative_to(ignore_dir)
            except ValueError:
                continue

            # check if path matches any pattern
            if spec.match_file(str(rel_path)):
                matched = True

        return matched
