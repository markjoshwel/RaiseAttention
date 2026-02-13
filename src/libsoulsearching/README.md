# libsoulsearching

python virtual environment finder for most mainstream setups,
after multiple projects of mine needed to dig through a venv

## installation

```text
pip install libsoulsearching
```

## quickstart

```python
from libsoulsearching import find_venv, find_all_venvs, ToolType

# find the first/best venv
info = find_venv("/path/to/project")
if info:
    print(f"found {info.tool.value} venv at {info.venv_path}")

# find all venvs
all_venvs = find_all_venvs("/path/to/project")
for venv in all_venvs:
    print(f"{venv.tool.value}: {venv.venv_path}")

# find specific tool only
poetry_venv = find_venv("/path/to/project", tool=ToolType.POETRY)
```

## supported tools

- **poetry**  
  `poetry.lock`, `pyproject.toml` with poetry config

- **pipenv**  
  `pipfile.lock`

- **pdm**  
  `pdm.lock`, `.pdm.toml`

- **uv**  
  `uv.lock`, `.venv`

- **rye**  
  `rye.lock`, `.python-version`

- **hatch**  
  `pyproject.toml` with `[tool.hatch.envs]`

- **venv**  
  `.venv/pyvenv.cfg`

- **pyenv**  
  `.python-version`

## cli usage

```text
# find first venv
venvfinder /path/to/project

# list all venvs
venvfinder /path/to/project --all

# find specific tool
venvfinder /path/to/project --tool poetry

# json output
venvfinder /path/to/project --json
```

## api reference

- `libsoulsearching.find_venv()`  
  find a virtual environment in the given project directory

- `libsoulsearching.find_all_venvs()`  
  find all virtual environments in the given project directory

- `libsoulsearching.ToolType`  
  enumeration of supported python environment management tools

- `libsoulsearching.VenvInfo`  
  information about a detected python virtual environment

### def libsoulsearching.find_venv()

find a virtual environment in the given project directory

- signature:

  ```python
  def find_venv(
      project_root: str | Path,
      tool: ToolType | None = None,
  ) -> VenvInfo | None: ...
  ```

- arguments:
  - `project_root: str | Path`  
    path to the project directory
  - `tool: ToolType | None`  
    specific tool to detect. if none, uses priority order

- returns: `VenvInfo | None`  
  venvinfo if a venv is found, none otherwise

### def libsoulsearching.find_all_venvs()

find all virtual environments in the given project directory

returns all detected venvs in priority order, including potentially
invalid ones (is_valid=false) if the tool's marker files exist but
the actual venv is missing

- signature:

  ```python
  def find_all_venvs(project_root: str | Path) -> list[VenvInfo]: ...
  ```

- arguments:
  - `project_root: str | Path`  
    path to the project directory

- returns: `list[VenvInfo]`  
  list of venvinfo objects (may be empty)

### class libsoulsearching.ToolType

enumeration of supported python environment management tools

- attributes:
  - `POETRY: str`  
    poetry package manager
  - `PIPENV: str`  
    pipenv package manager
  - `PDM: str`  
    pdm package manager
  - `UV: str`  
    uv package manager
  - `RYE: str`  
    rye package manager
  - `HATCH: str`  
    hatch package manager
  - `VENV: str`  
    standard venv module
  - `PYENV: str`  
    pyenv version manager
  - `ENV_VAR: str`  
    virtual environment from environment variable

### class libsoulsearching.VenvInfo

information about a detected python virtual environment

- attributes:
  - `tool: ToolType`  
    the detected tool type
  - `venv_path: Path | None`  
    path to the virtual environment directory
  - `python_executable: Path | None`  
    path to the python executable
  - `python_version: str | None`  
    python version string (e.g., "3.10.5")
  - `is_valid: bool`  
    whether the detected environment exists and is valid

## licence

libsoulsearching is unencumbered, free-as-in-freedom, and is dual-licenced under
The Unlicense or the BSD Zero Clause License. (SPDX: `Unlicense OR 0BSD`)

you are free to use the software as you wish, without any restrictions or
obligations, subject only to the warranty disclaimers in the licence text
of your choosing.
