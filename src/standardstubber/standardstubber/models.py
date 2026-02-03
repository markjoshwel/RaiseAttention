"""
data models for .pyras stub files.

defines the structure of python raiseattention stub files (.pyras),
which contain exception metadata for native/unanalysable functions.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import datetime
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

        # deduplicate stubs by qualname, merging raises sets
        merged: dict[str, FunctionStub] = {}
        for stub in self.stubs:
            if stub.qualname in merged:
                existing = merged[stub.qualname]
                # merge raises sets
                combined_raises = existing.raises | stub.raises
                # pick more conservative confidence
                confidence = self._more_conservative(existing.confidence, stub.confidence)
                # merge notes
                notes = existing.notes or stub.notes
                merged[stub.qualname] = FunctionStub(
                    qualname=stub.qualname,
                    raises=combined_raises,
                    confidence=confidence,
                    notes=notes,
                )
            else:
                merged[stub.qualname] = stub

        # group stubs by module for readability
        by_module: dict[str, list[FunctionStub]] = {}
        for stub in merged.values():
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

    @staticmethod
    def _more_conservative(a: Confidence, b: Confidence) -> Confidence:
        """return the more conservative of two confidence levels."""
        order = [Confidence.CONSERVATIVE, Confidence.LIKELY, Confidence.EXACT, Confidence.MANUAL]
        return a if order.index(a) < order.index(b) else b

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


# === call graph analysis types ===


@dataclass
class FunctionSummary:
    """
    summary of a c function for call graph analysis.

    used to build intra-module call graphs and compute transitive
    exception propagation.

    attributes:
        `name: str`
            c function name (e.g., "py_scanstring")
        `module: str`
            module name (e.g., "_json")
        `local_raises: set[str]`
            exceptions raised directly in this function
        `propagated_raises: set[str]`
            exceptions propagated from callees (computed by fixpoint)
        `outgoing_calls: set[str]`
            names of all direct callees in same translation unit
        `propagate_callees: set[str]`
            subset of outgoing_calls where errors are propagated
            (i.e., `if (res == NULL) return NULL` patterns)
        `confidence: Confidence`
            confidence level for this function's analysis
        `has_arg_parsing: bool`
            whether function uses PyArg_Parse*
        `has_clinic: bool`
            whether function uses argument clinic
        `notes: str`
            additional notes about the analysis
    """

    name: str
    module: str = ""
    local_raises: set[str] = field(default_factory=set)
    propagated_raises: set[str] = field(default_factory=set)
    outgoing_calls: set[str] = field(default_factory=set)
    propagate_callees: set[str] = field(default_factory=set)
    confidence: Confidence = Confidence.EXACT
    has_arg_parsing: bool = False
    has_clinic: bool = False
    has_explicit_raise: bool = False
    notes: str = ""

    def effective_raises(self) -> set[str]:
        """
        compute effective raises set (local + propagated).

        returns: `set[str]`
            all exception types this function may raise
        """
        return self.local_raises | self.propagated_raises


@dataclass
class ModuleGraph:
    """
    call graph for a single c module (translation unit).

    contains function summaries and export mappings for computing
    transitive exception propagation.

    attributes:
        `module_name: str`
            python module name (e.g., "_json")
        `functions: dict[str, FunctionSummary]`
            c function name -> summary
        `exports: dict[str, str]`
            python name -> c function name (from PyMethodDef)
    """

    module_name: str
    functions: dict[str, FunctionSummary] = field(default_factory=dict)
    exports: dict[str, str] = field(default_factory=dict)

    def compute_transitive_raises(self) -> None:
        """
        compute transitive exception propagation via fixpoint iteration.

        updates `propagated_raises` for all functions by following
        `propagate_callees` edges until no changes occur.
        """
        changed = True
        iterations = 0
        max_iterations = 1000  # prevent infinite loops

        while changed and iterations < max_iterations:
            changed = False
            iterations += 1

            for func in self.functions.values():
                before = len(func.propagated_raises)

                # add raises from propagated callees
                for callee_name in func.propagate_callees:
                    callee = self.functions.get(callee_name)
                    if callee is None:
                        continue

                    # propagate both local and already-propagated raises
                    func.propagated_raises |= callee.local_raises
                    func.propagated_raises |= callee.propagated_raises

                if len(func.propagated_raises) != before:
                    changed = True

    def get_exported_stubs(self) -> list[FunctionStub]:
        """
        generate function stubs for all exported functions.

        must call `compute_transitive_raises()` first.

        returns: `list[FunctionStub]`
            stubs for python-visible functions
        """
        stubs: list[FunctionStub] = []

        for py_name, c_name in sorted(self.exports.items()):
            func = self.functions.get(c_name)
            if func is None:
                continue

            effective = func.effective_raises()

            # determine confidence based on analysis quality
            confidence = self._compute_confidence(func, effective)

            # build qualified name
            qualname = f"{self.module_name}.{py_name}"

            stub = FunctionStub(
                qualname=qualname,
                raises=frozenset(effective),
                confidence=confidence,
                notes=func.notes,
            )
            stubs.append(stub)

        return stubs

    def _compute_confidence(self, func: FunctionSummary, effective: set[str]) -> Confidence:
        """
        determine confidence level for a function based on analysis.

        arguments:
            `func: FunctionSummary`
                function to evaluate
            `effective: set[str]`
                effective raises set

        returns: `Confidence`
            appropriate confidence level
        """
        # no exceptions found - conservative fallback
        if not effective or effective == {"Exception"}:
            return Confidence.CONSERVATIVE

        # explicit local raises found
        if func.has_explicit_raise:
            return Confidence.EXACT

        # only propagated exceptions (no local sites)
        if not func.local_raises and func.propagated_raises:
            # check if any callee has conservative confidence
            for callee_name in func.propagate_callees:
                callee = self.functions.get(callee_name)
                if callee and callee.confidence == Confidence.CONSERVATIVE:
                    return Confidence.LIKELY
            return Confidence.LIKELY

        # has argument parsing - inferred TypeError
        if func.has_arg_parsing or func.has_clinic:
            return Confidence.LIKELY

        # fallback - default to likely since we can't be certain
        return Confidence.LIKELY
