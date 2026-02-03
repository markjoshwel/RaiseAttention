"""type stubs for clang.cindex to appease basedpyright."""

from __future__ import annotations

from typing import Any, Generator

class Cursor:
    """clang cursor representing an ast node."""

    kind: CursorKind
    spelling: str
    type: Type
    location: SourceLocation
    hash: int
    result_type: Type

    def get_children(self) -> list[Cursor]: ...
    def walk_preorder(self) -> Generator[Cursor, Any, None]: ...
    def get_tokens(self) -> Generator[Token, Any, None]: ...
    def is_definition(self) -> bool: ...
    def get_arguments(self) -> list[Cursor]: ...

class CursorKind:
    """kind of clang cursor."""

    # declarations
    FUNCTION_DECL: CursorKind
    VAR_DECL: CursorKind

    # expressions
    CALL_EXPR: CursorKind
    DECL_REF_EXPR: CursorKind
    INIT_LIST_EXPR: CursorKind
    CSTYLE_CAST_EXPR: CursorKind
    PAREN_EXPR: CursorKind
    UNARY_OPERATOR: CursorKind
    BINARY_OPERATOR: CursorKind
    UNEXPOSED_EXPR: CursorKind

    # statements
    IF_STMT: CursorKind
    RETURN_STMT: CursorKind
    LABEL_STMT: CursorKind
    GOTO_STMT: CursorKind

    # literals
    STRING_LITERAL: CursorKind
    INTEGER_LITERAL: CursorKind
    GNU_NULL_EXPR: CursorKind

    # types
    TYPE_REF: CursorKind

class Type:
    """clang type."""

    kind: TypeKind
    spelling: str

    def get_canonical(self) -> Type: ...

class TypeKind:
    """kind of clang type."""

    POINTER: TypeKind
    TYPEDEF: TypeKind

class SourceLocation:
    """source location in a file."""

    file: File | None
    line: int
    column: int

class File:
    """source file."""

    name: str

class Token:
    """clang token."""

    spelling: str

class TranslationUnit:
    """translation unit (parsed file)."""

    cursor: Cursor
    PARSE_DETAILED_PROCESSING_RECORD: int

    def get_children(self) -> list[Cursor]: ...

class Index:
    """clang index."""

    @classmethod
    def create(cls) -> Index: ...
    def parse(
        self,
        path: str,
        args: list[str] | None = None,
        unsaved_files: list[tuple[str, str]] | None = None,
        options: int = 0,
    ) -> TranslationUnit: ...
