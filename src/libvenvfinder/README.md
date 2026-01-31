# libvenvfinder

universal python virtual environment finder

## Installation

```bash
pip install libvenvfinder
```

## Quick Start

```python
from libvenvfinder import find_venv, find_all_venvs, ToolType

# Find the first/best venv
info = find_venv("/path/to/project")
if info:
    print(f"Found {info.tool.value} venv at {info.venv_path}")

# Find all venvs
all_venvs = find_all_venvs("/path/to/project")
for venv in all_venvs:
    print(f"{venv.tool.value}: {venv.venv_path}")

# Find specific tool only
poetry_venv = find_venv("/path/to/project", tool=ToolType.POETRY)
```

## Supported Tools

- **Poetry** - `poetry.lock`, `pyproject.toml` with poetry config
- **Pipenv** - `Pipfile.lock`
- **PDM** - `pdm.lock`, `.pdm.toml`
- **uv** - `uv.lock`, `.venv`
- **Rye** - `rye.lock`, `.python-version`
- **Hatch** - `pyproject.toml` with `[tool.hatch.envs]`
- **venv** - `.venv/pyvenv.cfg`
- **pyenv** - `.python-version`

## CLI Usage

```bash
# Find first venv
venvfinder /path/to/project

# List all venvs
venvfinder /path/to/project --all

# Find specific tool
venvfinder /path/to/project --tool poetry

# JSON output
venvfinder /path/to/project --json
```

## API Reference

### `find_venv(project_root: str | Path, tool: ToolType | None = None) -> VenvInfo | None`

Find a virtual environment in the given project directory.

**Parameters:**
- `project_root`: Path to the project directory
- `tool`: Specific tool to detect (optional). If None, uses priority order.

**Returns:** `VenvInfo` if found, `None` otherwise

### `find_all_venvs(project_root: str | Path) -> list[VenvInfo]`

Find all virtual environments in the given project directory.

**Returns:** List of `VenvInfo` objects in priority order

### `VenvInfo`

Dataclass containing venv information:

- `tool: ToolType` - The detected tool (poetry, pdm, uv, etc.)
- `venv_path: Path | None` - Path to venv directory
- `python_executable: Path | None` - Path to python binary
- `python_version: str | None` - Python version string (e.g., "3.10.5")
- `is_valid: bool` - Whether the venv exists and is usable

### `ToolType` (Enum)

- `POETRY`, `PIPENV`, `PDM`, `UV`, `RYE`, `HATCH`, `VENV`, `PYENV`

## License

MIT
