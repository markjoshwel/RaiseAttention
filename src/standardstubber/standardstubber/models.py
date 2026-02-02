"""
data models for .pyras stub files.

defines the structure of python raiseattention stub files (.pyras),
which contain exception metadata for native/unanalysable functions.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Final, NamedTuple


class Confidence(Enum):
    """
    confidence level for exception signature extraction.

    attributes:
        `EXACT`
            proven from source code analysis (found explicit PyErr_SetString)
        `LIKELY`
            reasonable inference (argument parsing implies TypeError)
        `CONSERVATIVE`
            unknown, erring on safety (complex control flow)
        `MANUAL`
            hand-curated by human expert
    """

    EXACT = "exact"
    LIKELY = "likely"
    CONSERVATIVE = "conservative"
    MANUAL = "manual"


# pyras format version
FORMAT_VERSION: Final[str] = "1.0"


@dataclass(frozen=True, slots=True)
class StubMetadata:
    """
    metadata section of a .pyras stub file.

    attributes:
        `name: str`
            what this stub file describes (e.g., "stdlib", "pydantic-core")
        `version: str`
            pep 440 version specifier (e.g., ">=3.10,<3.14")
        `format_version: str`
            pyras format version
        `generator: str | None`
            tool that generated this file
        `generated_at: datetime | None`
            when this file was generated
        `package: str | None`
            import name for third-party packages (may differ from name)
    """

    name: str
    version: str
    format_version: str = FORMAT_VERSION
    generator: str | None = None
    generated_at: datetime | None = None
    package: str | None = None

    def to_toml(self) -> str:
        """
        serialise metadata to toml format.

        returns: `str`
            toml representation of metadata section
        """
        lines: list[str] = ["[metadata]"]
        lines.append(f'name = "{self.name}"')
        lines.append(f'version = "{self.version}"')
        lines.append(f'format_version = "{self.format_version}"')
        if self.generator:
            lines.append(f'generator = "{self.generator}"')
        if self.generated_at:
            lines.append(f'generated_at = "{self.generated_at.isoformat()}"')
        if self.package:
            lines.append(f'package = "{self.package}"')
        return "\n".join(lines)


@dataclass(slots=True)
class FunctionStub:
    """
    exception stub for a single function.

    attributes:
        `qualname: str`
            fully qualified name (e.g., "json.loads", "json.JSONDecoder.decode")
        `raises: frozenset[str]`
            exception types this function may raise
        `confidence: Confidence`
            how confident we are in this signature
        `notes: str`
            additional notes about the signature
    """

    qualname: str
    raises: frozenset[str]
    confidence: Confidence = Confidence.EXACT
    notes: str = ""

    def to_toml(self) -> str:
        """
        serialise function stub to toml format.

        returns: `str`
            toml representation of function stub
        """
        lines: list[str] = [f'["{self.qualname}"]']
        # sort raises for deterministic output
        raises_list = sorted(self.raises)
        lines.append(f"raises = {raises_list}")
        if self.confidence != Confidence.EXACT:
            lines.append(f'confidence = "{self.confidence.value}"')
        if self.notes:
            # escape quotes in notes
            escaped_notes = self.notes.replace('"', '\\"')
            lines.append(f'notes = "{escaped_notes}"')
        return "\n".join(lines)


@dataclass
class StubFile:
    """
    complete .pyras stub file.

    attributes:
        `metadata: StubMetadata`
            file metadata
        `stubs: list[FunctionStub]`
            function exception stubs
    """

    metadata: StubMetadata
    stubs: list[FunctionStub] = field(default_factory=list)

    def to_toml(self) -> str:
        """
        serialise entire stub file to toml format.

        returns: `str`
            complete toml representation
        """
        sections: list[str] = [self.metadata.to_toml(), ""]

        # group stubs by module for readability
        by_module: dict[str, list[FunctionStub]] = {}
        for stub in self.stubs:
            # extract module from qualname (e.g., "json" from "json.loads")
            parts = stub.qualname.split(".")
            module = parts[0] if len(parts) > 1 else ""
            by_module.setdefault(module, []).append(stub)

        for module in sorted(by_module.keys()):
            module_stubs = sorted(by_module[module], key=lambda s: s.qualname)
            for stub in module_stubs:
                sections.append(stub.to_toml())
                sections.append("")

        return "\n".join(sections)

    def write(self, path: Path) -> None:
        """
        write stub file to disk.

        arguments:
            `path: Path`
                path to write to (should have .pyras extension)
        """
        path.write_text(self.to_toml(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> StubFile:
        """
        load stub file from disk.

        arguments:
            `path: Path`
                path to .pyras file

        returns: `StubFile`
            parsed stub file

        raises:
            `FileNotFoundError`
                if file does not exist
            `tomllib.TOMLDecodeError`
                if file is not valid toml
            `KeyError`
                if required fields are missing
        """
        with open(path, "rb") as f:
            data = tomllib.load(f)

        # parse metadata
        meta_data = data["metadata"]
        generated_at: datetime | None = None
        if "generated_at" in meta_data:
            generated_at = datetime.fromisoformat(str(meta_data["generated_at"]))

        metadata = StubMetadata(
            name=str(meta_data["name"]),
            version=str(meta_data["version"]),
            format_version=str(meta_data.get("format_version", FORMAT_VERSION)),
            generator=str(meta_data["generator"]) if "generator" in meta_data else None,
            generated_at=generated_at,
            package=str(meta_data["package"]) if "package" in meta_data else None,
        )

        # parse function stubs
        stubs: list[FunctionStub] = []
        for key, value in data.items():
            if key == "metadata":
                continue

            # key is the qualname (without quotes from toml)
            qualname = key
            raises_raw: list[object] = value.get("raises", [])
            raises = frozenset(str(r) for r in raises_raw)
            confidence_str = str(value.get("confidence", "exact"))
            confidence = Confidence(confidence_str)
            notes = str(value.get("notes", ""))

            stubs.append(
                FunctionStub(
                    qualname=qualname,
                    raises=raises,
                    confidence=confidence,
                    notes=notes,
                )
            )

        return cls(metadata=metadata, stubs=stubs)


class StubLookupResult(NamedTuple):
    """
    result of looking up a function in stub files.

    attributes:
        `raises: frozenset[str]`
            exception types the function may raise
        `confidence: Confidence`
            confidence level of the signature
        `source: Path | None`
            path to the stub file (none if from builtin)
    """

    raises: frozenset[str]
    confidence: Confidence
    source: Path | None = None
