"""examples of using raiseattention with file i/o operations.

this module demonstrates how raiseattention detects unhandled exceptions
in real-world file handling scenarios.
"""

from __future__ import annotations


# =============================================================================
# example 1: basic file reading with unhandled exceptions
# =============================================================================


def read_config_simple(filepath: str) -> dict:
    """read configuration from a file.

    raiseattention will flag: unhandled FileNotFoundError, PermissionError, IsADirectoryError
    """
    with open(filepath, "r") as f:  # line 10 - can raise FileNotFoundError, PermissionError
        content = f.read()  # line 11 - can raise IOError, OSError
    return {"content": content}


# =============================================================================
# example 2: proper exception handling
# =============================================================================


def read_config_safe(filepath: str) -> dict | None:
    """read configuration with proper exception handling.

    raiseattention will detect: all exceptions handled, no diagnostics
    """
    try:
        with open(filepath, "r") as f:
            content = f.read()
        return {"content": content}
    except FileNotFoundError:
        print(f"config file not found: {filepath}")
        return None
    except PermissionError:
        print(f"permission denied: {filepath}")
        return None
    except IsADirectoryError:
        print(f"path is a directory: {filepath}")
        return None


# =============================================================================
# example 3: processing multiple files
# =============================================================================


def process_files(file_list: list[str]) -> list[dict]:
    """process multiple files - some exceptions handled, some not.

    raiseattention will flag: json.JSONDecodeError from json.load is unhandled
    """
    import json

    results = []
    for filepath in file_list:
        try:
            with open(filepath, "r") as f:
                data = json.load(f)  # line 50 - can raise JSONDecodeError (NOT caught!)
                results.append(data)
        except FileNotFoundError:
            print(f"skipping missing file: {filepath}")
    return results


# =============================================================================
# example 4: complex file operations with partial handling
# =============================================================================


def backup_and_write(data: str, target_path: str) -> bool:
    """backup existing file before writing.

    raiseattention will flag:
    - shutil.copy2 can raise PermissionError, OSError (unhandled)
    - open() can raise PermissionError (unhandled in write mode)
    """
    import shutil
    import os

    # backup existing file
    if os.path.exists(target_path):
        backup_path = target_path + ".backup"
        shutil.copy2(target_path, backup_path)  # line 75 - unhandled exceptions!

    # write new data
    with open(target_path, "w") as f:  # line 79 - unhandled PermissionError
        f.write(data)

    return True


# =============================================================================
# example 5: file operations in library code (external functions)
# =============================================================================


def process_user_data(input_file: str, output_file: str) -> None:
    """process user data from input to output.

    since parse_user_data is not defined in this file, raiseattention
    will warn about potential unhandled exceptions from the external call.
    """
    # calling external function - exceptions unknown
    data = parse_user_data(
        input_file
    )  # line 93 - external function, potential unhandled exceptions

    # writing to file - unhandled exceptions
    with open(output_file, "w") as f:  # line 96 - unhandled PermissionError, IOError
        f.write(format_data(data))


def parse_user_data(filepath: str) -> dict:
    """parse user data from file.

    raises: json.JSONDecodeError, FileNotFoundError, PermissionError
    """
    import json

    with open(filepath) as f:
        return json.load(f)


def format_data(data: dict) -> str:
    """format data for output."""
    return str(data)


# =============================================================================
# example 6: csv processing with mixed handling
# =============================================================================


def process_csv(csv_path: str) -> list[dict]:
    """process csv file.

    raiseattention will flag:
    - csv.reader can raise various errors (unhandled)
    - row access can raise IndexError (unhandled)
    """
    import csv

    rows = []
    try:
        with open(csv_path, newline="") as f:  # handled by outer try
            reader = csv.reader(f)
            for row in reader:  # line 128 - csv errors not caught!
                if len(row) > 0:
                    rows.append({"data": row[0]})  # safe
                else:
                    rows.append({"data": row[1]})  # line 132 - unhandled IndexError!
    except FileNotFoundError:
        print(f"csv not found: {csv_path}")
    return rows


# =============================================================================
# example 7: async file operations
# =============================================================================


async def async_read_file(filepath: str) -> str:
    """async file reading using aiofiles.

    raiseattention will flag: unhandled exceptions from open and read
    """
    import aiofiles

    async with aiofiles.open(filepath, "r") as f:  # line 147 - unhandled FileNotFoundError
        content = await f.read()  # line 148 - unhandled IOError
    return content


async def async_read_file_safe(filepath: str) -> str | None:
    """async file reading with proper handling.

    raiseattention will detect: all exceptions handled
    """
    import aiofiles

    try:
        async with aiofiles.open(filepath, "r") as f:
            return await f.read()
    except FileNotFoundError:
        print(f"file not found: {filepath}")
        return None
    except PermissionError:
        print(f"permission denied: {filepath}")
        return None


# =============================================================================
# example 8: using pathlib with exception handling
# =============================================================================


def read_with_pathlib(data_dir: str, filename: str) -> str:
    """read file using pathlib.

    raiseattention will flag: unhandled exceptions from read_text
    """
    from pathlib import Path

    file_path = Path(data_dir) / filename
    return file_path.read_text()  # line 180 - unhandled FileNotFoundError, PermissionError


def read_with_pathlib_safe(data_dir: str, filename: str) -> str | None:
    """read file using pathlib with handling.

    raiseattention will detect: exceptions handled
    """
    from pathlib import Path

    file_path = Path(data_dir) / filename
    try:
        return file_path.read_text()
    except FileNotFoundError:
        print(f"file not found: {file_path}")
        return None
    except PermissionError:
        print(f"permission denied: {file_path}")
        return None


# =============================================================================
# example 9: temporary file handling
# =============================================================================


def process_with_temp(data: str) -> str:
    """process data using temporary file.

    raiseattention will flag: unhandled exceptions from tempfile operations
    """
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(
        mode="w", delete=False
    ) as tmp:  # line 209 - unhandled exceptions
        tmp.write(data)
        tmp_path = tmp.name

    try:
        result = process_file(tmp_path)  # external function
    finally:
        os.unlink(tmp_path)  # line 217 - unhandled OSError

    return result


def process_file(path: str) -> str:
    """process a file."""
    with open(path) as f:
        return f.read().upper()


# =============================================================================
# example 10: comprehensive file processor (production-ready pattern)
# =============================================================================


class FileProcessor:
    """robust file processor with comprehensive exception handling.

    raiseattention will verify all exception paths are handled.
    """

    def __init__(self, backup_dir: str) -> None:
        self.backup_dir = backup_dir

    def process_and_backup(self, input_path: str, output_path: str) -> dict:
        """process file with full error handling.

        all exceptions are handled or documented.
        """
        import json
        from pathlib import Path

        try:
            # read input
            data = self._read_input(input_path)

            # process
            result = self._transform(data)

            # backup existing output if present
            self._backup_if_exists(output_path)

            # write output
            self._write_output(output_path, result)

            return {"success": True, "records": len(result)}

        except FileNotFoundError as e:
            return {"success": False, "error": f"file not found: {e}"}
        except PermissionError as e:
            return {"success": False, "error": f"permission denied: {e}"}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"invalid json: {e}"}
        except OSError as e:
            return {"success": False, "error": f"os error: {e}"}

    def _read_input(self, path: str) -> dict:
        """read and parse input file."""
        import json

        with open(path, "r") as f:
            return json.load(f)

    def _transform(self, data: dict) -> list[dict]:
        """transform data."""
        return [{"processed": True, "data": data}]

    def _backup_if_exists(self, path: str) -> None:
        """backup file if it exists."""
        from pathlib import Path
        import shutil

        target = Path(path)
        if target.exists():
            backup_path = Path(self.backup_dir) / f"{target.name}.backup"
            try:
                shutil.copy2(path, backup_path)
            except (PermissionError, OSError) as e:
                print(f"warning: could not backup: {e}")

    def _write_output(self, path: str, data: list[dict]) -> None:
        """write output file."""
        import json

        with open(path, "w") as f:
            json.dump(data, f, indent=2)
