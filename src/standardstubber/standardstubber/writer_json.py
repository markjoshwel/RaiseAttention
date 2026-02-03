"""
json stub file writer for pyras v2 format.

provides efficient json generation for .pyras stub files v2.0.
the v2 format uses nested structure for better organisation and per-exception confidence.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .models import Confidence, StubMetadata

logger = logging.getLogger(__name__)

# test module patterns to skip
test_module_prefixes = ("_test", "xx", "_xx")


def _is_test_module(module_name: str) -> bool:
    """
    check if module is a test module that should be skipped.

    arguments:
        `module_name: str`
            name of the module to check

    returns: `bool`
        true if module should be skipped
    """
    return module_name.startswith(test_module_prefixes)


def _parse_qualname(qualname: str) -> tuple[str, str, str]:
    """
    parse qualname into (module, class_or_func, method).

    handles various formats:
    - "module.function" -> (module, "", function)
    - "module.class.method" -> (module, class, method)
    - "_module.Class.method" -> (_module, Class, method)

    arguments:
        `qualname: str`
            fully qualified name

    returns: `tuple[str, str, str]`
        (module, class_or_func, method) where method may be empty for module-level functions
    """
    parts = qualname.split(".")

    if len(parts) == 2:
        # module.function
        return (parts[0], "", parts[1])
    elif len(parts) == 3:
        # module.class.method
        return (parts[0], parts[1], parts[2])
    elif len(parts) > 3:
        # deeply nested: module.class.nested.method
        # treat as module.class.rest
        return (parts[0], parts[1], ".".join(parts[2:]))
    else:
        # single part - shouldn't happen for stdlib
        return (qualname, "", "")


def write_stub_file_json_v2(
    output_path: Path,
    metadata: StubMetadata,
    raw_stubs: list[tuple[str, frozenset[str], str, str]],
    skip_test_modules: bool = True,
) -> int:
    """
    write .pyras file in v2.0 json format with nested structure.

    structure:
    {
      "metadata": {...},
      "_io": {
        "Bufferedreader": {
          "peek": {
            "TypeError": "likely",
            "ValueError": "exact"
          }
        }
      }
    }

    arguments:
        `output_path: Path`
            path to write the .pyras file
        `metadata: StubMetadata`
            file metadata (format_version will be set to "2.0")
        `raw_stubs: list[tuple[str, frozenset[str], str, str]]`
            list of (qualname, raises, confidence, notes) tuples
        `skip_test_modules: bool`
            whether to skip test modules (default true)

    returns: `int`
        number of unique stubs written
    """
    # build nested structure: module -> class -> method -> exception -> confidence
    # can also be list for compactness (all default confidence)
    nested: dict[str, Any] = {}

    for qualname, raises, confidence_str, _ in raw_stubs:
        confidence = confidence_str if confidence_str else Confidence.LIKELY.value

        module, class_name, method = _parse_qualname(qualname)

        # skip test modules if enabled
        if skip_test_modules and _is_test_module(module):
            continue

        # ensure module exists
        if module not in nested:
            nested[module] = {}

        # handle module-level functions (no class)
        if not class_name:
            # use empty string as class key for module-level functions
            if "" not in nested[module]:
                nested[module][""] = {}
            if method not in nested[module][""]:
                nested[module][""][method] = {}

            # add each exception with its confidence
            for exc in raises:
                # only store non-default confidence (not "likely")
                if confidence != Confidence.LIKELY.value:
                    nested[module][""][method][exc] = confidence
                else:
                    # default confidence - just mark as present with empty value
                    nested[module][""][method][exc] = ""
        else:
            # class method
            if class_name not in nested[module]:
                nested[module][class_name] = {}
            if method not in nested[module][class_name]:
                nested[module][class_name][method] = {}

            for exc in raises:
                if confidence != Confidence.LIKELY.value:
                    nested[module][class_name][method][exc] = confidence
                else:
                    nested[module][class_name][method][exc] = ""

    # clean up: remove empty confidence values for compactness
    for module in nested:
        for class_name in nested[module]:
            for method in nested[module][class_name]:
                # convert {"exc": ""} to just ["exc"] list for default confidence
                exc_dict = nested[module][class_name][method]
                default_conf_exceptions = [exc for exc, conf in exc_dict.items() if not conf]
                non_default_conf_exceptions = {exc: conf for exc, conf in exc_dict.items() if conf}

                # rebuild: list for default, dict for non-default
                if default_conf_exceptions and non_default_conf_exceptions:
                    # mixed - keep as dict, but default ones get "likely" explicitly
                    nested[module][class_name][method] = {
                        exc: Confidence.LIKELY.value for exc in default_conf_exceptions
                    }
                    nested[module][class_name][method].update(non_default_conf_exceptions)
                elif default_conf_exceptions:
                    # all default - use list for compactness
                    nested[module][class_name][method] = sorted(default_conf_exceptions)
                else:
                    # all non-default - use dict
                    nested[module][class_name][method] = non_default_conf_exceptions

    # remove empty class entries
    for module in list(nested.keys()):
        for class_name in list(nested[module].keys()):
            if not nested[module][class_name]:
                del nested[module][class_name]
        if not nested[module]:
            del nested[module]

    # prepare output structure
    output: dict[str, Any] = {
        "metadata": {
            "name": metadata.name,
            "version": metadata.version,
            "format_version": "2.0",
            "generator": metadata.generator or "standardstubber@0.2.0",
        }
    }

    if metadata.package:
        output["metadata"]["package"] = metadata.package
    if metadata.generated_at:
        output["metadata"]["generated_at"] = metadata.generated_at.isoformat()

    # add all module data (sorted for determinism)
    for module in sorted(nested.keys()):
        output[module] = {}
        for class_name in sorted(nested[module].keys()):
            if class_name:  # normal class
                output[module][class_name] = {}
                for method in sorted(nested[module][class_name].keys()):
                    output[module][class_name][method] = nested[module][class_name][method]
            else:  # module-level functions - merge into module directly
                for method in sorted(nested[module][class_name].keys()):
                    output[module][method] = nested[module][class_name][method]

    # write json file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, sort_keys=False, ensure_ascii=False)

    num_written = sum(len(methods) for module in nested.values() for methods in module.values())
    logger.info("wrote %d unique stubs to %s (v2.0 json)", num_written, output_path)
    return num_written
