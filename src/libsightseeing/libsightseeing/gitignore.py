"""
gitignore handling module for libsightseeing.

handles parsing and matching of .gitignore files, inspired by
sota staircase SideStepper but simplified for libsightseeing's needs.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gitignore_parser import IgnoreRule


class GitignoreMatcher:
    """
    matcher for .gitignore rules.

    collects and applies .gitignore rules from the root directory
    and all subdirectories during file traversal.

    attributes:
        `root: Path`
            the root directory to match against
        `rules: list[tuple[Path, list[IgnoreRule]]]`
            list of (directory, rules) tuples

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
        self.rules: list[tuple[Path, list[IgnoreRule]]] = []
        self._collect_gitignore_rules()

    def _collect_gitignore_rules(self) -> None:
        """
        collect all .gitignore rules from root and subdirectories.

        finds all .gitignore files and parses their rules.
        """
        from gitignore_parser import rule_from_pattern

        # find all .gitignore files
        for gitignore_file in self.root.rglob(".gitignore"):
            if not gitignore_file.is_file():
                continue

            rules: list[IgnoreRule] = []
            try:
                content = gitignore_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            for line_no, line in enumerate(content.splitlines()):
                line = line.rstrip("\n")
                # skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                rule = rule_from_pattern(
                    pattern=line,
                    base_path=gitignore_file.parent,
                    source=(gitignore_file, line_no),
                )
                if rule is not None:
                    rules.append(rule)

            if rules:
                self.rules.append((gitignore_file.parent, rules))

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

        for ignore_dir, rules in self.rules:
            # only apply rules from directories that contain the path
            if not str(path).startswith(str(ignore_dir)):
                continue

            for rule in rules:
                if rule.match(path):
                    # negation rules un-ignore
                    if rule.negation:
                        matched = False
                    else:
                        matched = True

        return matched
