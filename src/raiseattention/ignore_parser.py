"""parser for raiseattention ignore comments.

this module parses pyright-style ignore comments from python source code
to allow line-specific suppression of exception diagnostics.

formats (all case-insensitive):
    # raiseattention: ignore[ExceptionType1, ExceptionType2]
    # RaiseAttention: ignore[ExceptionType1, ExceptionType2]
    # ra: ignore[ExceptionType1, ExceptionType2]
    # RA: ignore[ExceptionType1, ExceptionType2]

rules:
    - must be on the same line as the statement (after the statement)
    - must include brackets with exception types
    - plain "# raiseattention: ignore" without brackets is invalid
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# pattern for valid ignore comments: # raiseattention: ignore[ExceptionType1, ExceptionType2]
# supports: raiseattention, RaiseAttention, ra, RA (case insensitive)
# captures exception types inside the brackets
_VALID_IGNORE_PATTERN = re.compile(
    r"#\s*(?:raiseattention|[rR][aA])\s*:\s*ignore\s*\[\s*([^\]]+)\s*\]",
    re.IGNORECASE,
)

# pattern for invalid ignore comments (missing brackets)
# supports: raiseattention, RaiseAttention, ra, RA (case insensitive)
_INVALID_IGNORE_PATTERN = re.compile(
    r"#\s*(?:raiseattention|[rR][aA])\s*:\s*ignore\s*(?!\s*\[)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class IgnoreDirective:
    """
    a parsed ignore directive.

    attributes:
        `line: int`
            line number where the directive appears (1-indexed)
        `exception_types: frozenset[str]`
            exception types to ignore on this line
        `raw: str`
            the raw comment text
    """

    line: int
    exception_types: frozenset[str]
    raw: str


@dataclass(frozen=True, slots=True)
class InvalidIgnoreDirective:
    """
    an invalid ignore directive (missing brackets).

    attributes:
        `line: int`
            line number where the invalid directive appears (1-indexed)
        `raw: str`
            the raw comment text
    """

    line: int
    raw: str


@dataclass
class IgnoreParseResult:
    """
    result of parsing ignore comments from a file.

    attributes:
        `directives: dict[int, IgnoreDirective]`
            mapping of line numbers to ignore directives
        `invalid: list[InvalidIgnoreDirective]`
            list of invalid directives (missing brackets)
    """

    directives: dict[int, IgnoreDirective]
    invalid: list[InvalidIgnoreDirective]

    def should_ignore(self, line: int, exception_type: str) -> bool:
        """
        check if an exception should be ignored on a given line.

        arguments:
            `line: int`
                line number (1-indexed)
            `exception_type: str`
                the exception type to check

        returns: `bool`
                true if the exception should be ignored
        """
        directive = self.directives.get(line)
        if directive is None:
            return False

        # for external exception classes like 'module.submodule.ExceptionClassName',
        # only check the class name part
        exc_name = exception_type.split(".")[-1]
        return exc_name in directive.exception_types


def parse_ignore_comments(source: str) -> IgnoreParseResult:
    """
    parse raiseattention ignore comments from source code.

    arguments:
        `source: str`
            python source code to parse

    returns: `IgnoreParseResult`
            parsed directives and any invalid directives
    """
    directives: dict[int, IgnoreDirective] = {}
    invalid: list[InvalidIgnoreDirective] = []

    lines = source.split("\n")

    for line_num, line in enumerate(lines, start=1):
        # check for invalid format (missing brackets)
        if _INVALID_IGNORE_PATTERN.search(line):
            # make sure it's not actually valid (valid pattern also matches invalid)
            if not _VALID_IGNORE_PATTERN.search(line):
                invalid.append(
                    InvalidIgnoreDirective(
                        line=line_num,
                        raw=line.strip(),
                    )
                )
                continue

        # check for valid format
        match = _VALID_IGNORE_PATTERN.search(line)
        if match:
            # parse exception types from inside brackets
            types_str = match.group(1)
            exception_types = frozenset(t.strip() for t in types_str.split(",") if t.strip())

            directives[line_num] = IgnoreDirective(
                line=line_num,
                exception_types=exception_types,
                raw=line.strip(),
            )

    return IgnoreParseResult(directives=directives, invalid=invalid)


def parse_ignore_comments_from_file(file_path: str | Path) -> IgnoreParseResult:
    """
    parse raiseattention ignore comments from a file.

    arguments:
        `file_path: str | Path`
            path to the python file

    returns: `IgnoreParseResult`
            parsed directives and any invalid directives

    raises:
        `FileNotFoundError`
            if the file does not exist
        `OSError`
            if the file cannot be read
    """
    file_path = Path(file_path)
    source = file_path.read_text(encoding="utf-8")
    return parse_ignore_comments(source)
