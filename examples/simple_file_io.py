"""simple file i/o example to test raiseattention detection.

this demonstrates that raiseattention does NOT detect exceptions from
built-in functions like open(), but DOES detect explicit raise statements.
"""

from __future__ import annotations


# =============================================================================
# example 1: simple file reading (built-in open)
# =============================================================================


def read_simple(filepath: str) -> str:
    """read file using built-in open().

    note: raiseattention does NOT detect FileNotFoundError, PermissionError, etc.
    from built-in open() because it doesn't have signatures for built-ins.
    """
    with open(filepath, "r") as f:
        return f.read()


# =============================================================================
# example 2: explicit validation before opening
# =============================================================================


def read_with_validation(filepath: str) -> str:
    """read file with explicit validation.

    raiseattention WILL detect the ValueError from validate_path()
    """
    validate_path(filepath)

    with open(filepath, "r") as f:
        return f.read()


def validate_path(filepath: str) -> None:
    """validate file path."""
    if not filepath:
        raise ValueError("filepath cannot be empty")
    if not filepath.endswith(".txt"):
        raise ValueError("only .txt files supported")


# =============================================================================
# example 3: calling a function that does file io and validation
# =============================================================================


def process_config(config_path: str) -> dict:
    """process config file.

    raiseattention will flag: unhandled ValueError from load_and_parse
    """
    config = load_and_parse(config_path)
    return {"processed": True, "config": config}


def load_and_parse(path: str) -> dict:
    """load and parse config.

    raises: ValueError if path invalid
    """
    if not path:
        raise ValueError("path required")

    # open() exceptions are NOT detected
    with open(path) as f:
        content = f.read()

    return {"content": content}


# =============================================================================
# example 4: proper handling
# =============================================================================


def process_config_safe(config_path: str) -> dict | None:
    """process config with proper exception handling.

    no diagnostics - all explicit exceptions are handled.
    """
    try:
        config = load_and_parse(config_path)
        return {"processed": True, "config": config}
    except ValueError as e:
        print(f"error: {e}")
        return None


# =============================================================================
# example 5: json file operations
# =============================================================================


def load_json_file(path: str) -> dict:
    """load json from file.

    note: json.load() exceptions are NOT detected (built-in).
    but ValueError from validate_json_path IS detected.
    """
    import json

    validate_json_path(path)

    with open(path) as f:
        return json.load(f)


def validate_json_path(path: str) -> None:
    """validate json file path."""
    if not path.endswith(".json"):
        raise ValueError("file must be .json")
