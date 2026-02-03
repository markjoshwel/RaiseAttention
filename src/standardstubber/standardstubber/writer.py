"""
incremental toml stub file writer.

provides efficient, streaming toml generation for .pyras stub files
without the deduplication and memory issues of the old approach.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Final

from .models import Confidence, StubMetadata

logger = logging.getLogger(__name__)

# escape characters for toml strings
ESCAPE_CHARS: Final[dict[str, str]] = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\r": "\\r",
}


def _escape_toml_string(s: str) -> str:
    """
    escape a string for toml output.

    arguments:
        `s: str`
            string to escape

    returns: `str`
        escaped string
    """
    result = []
    for char in s:
        if char in ESCAPE_CHARS:
            result.append(ESCAPE_CHARS[char])
        else:
            result.append(char)
    return "".join(result)


def _write_metadata_section(file_handle: Any, metadata: StubMetadata) -> None:
    """
    write the metadata section to the file.

    arguments:
        `file_handle: Any`
            writable file handle
        `metadata: StubMetadata`
            metadata to write
    """
    file_handle.write("[metadata]\n")
    file_handle.write(f'name = "{_escape_toml_string(metadata.name)}"\n')
    file_handle.write(f'version = "{_escape_toml_string(metadata.version)}"\n')
    file_handle.write(f'format_version = "{metadata.format_version}"\n')
    if metadata.generator:
        file_handle.write(f'generator = "{_escape_toml_string(metadata.generator)}"\n')
    if metadata.generated_at:
        file_handle.write(f'generated_at = "{metadata.generated_at.isoformat()}"\n')
    if metadata.package:
        file_handle.write(f'package = "{_escape_toml_string(metadata.package)}"\n')
    file_handle.write("\n")


def write_stub_file_incremental(
    output_path: Path,
    metadata: StubMetadata,
    raw_stubs: list[tuple[str, frozenset[str], str, str]],
) -> int:
    """
    write .pyras file using incremental approach with explicit deduplication.

    this function collects raw stub data (qualname, raises, confidence, notes),
    deduplicates by qualname, groups by module, sorts deterministically,
    and writes directly to the output file.

    arguments:
        `output_path: Path`
            path to write the .pyras file
        `metadata: StubMetadata`
            file metadata
        `raw_stubs: list[tuple[str, frozenset[str], str, str]]`
            list of (qualname, raises, confidence, notes) tuples

    returns: `int`
        number of unique stubs written
    """
    # step 1: deduplicate by qualname, merging raises sets
    # use a dict to track: qualname -> (raises_set, confidence, notes)
    merged: dict[str, tuple[set[str], Confidence, str]] = {}

    for qualname, raises_frozen, confidence_str, notes in raw_stubs:
        confidence = Confidence(confidence_str) if confidence_str else Confidence.EXACT
        raises = set(raises_frozen)

        if qualname in merged:
            existing_raises, existing_conf, existing_notes = merged[qualname]
            # merge raises sets
            existing_raises.update(raises)
            # pick more conservative confidence
            confidence_order = [
                Confidence.CONSERVATIVE,
                Confidence.LIKELY,
                Confidence.EXACT,
                Confidence.MANUAL,
            ]
            existing_idx = confidence_order.index(existing_conf)
            new_idx = confidence_order.index(confidence)
            final_conf = existing_conf if existing_idx < new_idx else confidence
            # merge notes (prefer existing if it has content)
            final_notes = existing_notes if existing_notes else notes
            merged[qualname] = (existing_raises, final_conf, final_notes)
        else:
            merged[qualname] = (raises, confidence, notes)

    # step 2: group by module
    by_module: dict[str, list[tuple[str, set[str], Confidence, str]]] = {}
    for qualname, (raises, confidence, notes) in merged.items():
        parts = qualname.split(".")
        module = parts[0] if len(parts) > 1 else ""
        if module not in by_module:
            by_module[module] = []
        by_module[module].append((qualname, raises, confidence, notes))

    # step 3: sort each module's stubs by qualname for deterministic output
    for module in by_module:
        by_module[module].sort(key=lambda x: x[0])

    # step 4: write to file
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        _write_metadata_section(f, metadata)

        # write modules in sorted order for readability
        for module in sorted(by_module.keys()):
            stubs = by_module[module]
            for qualname, raises, confidence, notes in stubs:
                f.write(f'["{qualname}"]\n')

                # sort raises for deterministic output
                raises_list = sorted(raises)
                f.write(f"raises = {raises_list}\n")

                if confidence != Confidence.EXACT:
                    f.write(f'confidence = "{confidence.value}"\n')

                if notes:
                    escaped_notes = _escape_toml_string(notes)
                    f.write(f'notes = "{escaped_notes}"\n')

                f.write("\n")

    num_written = len(merged)
    logger.info("wrote %d unique stubs to %s", num_written, output_path)
    return num_written
