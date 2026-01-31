# Python Virtual Environment Detection & Activation Spec

**Version:** 1.0  
**Date:** 2026-01-31  
**Scope:** Cross-platform environment detection for Poetry, Pipenv, PDM, uv, Rye, Hatch, and standard venv  

---

## 1. Executive Summary

This specification defines a unified approach to detecting and resolving Python virtual environments across popular package management tools. The system must:

1. **Detect** which tool manages the current project
2. **Locate** the associated virtual environment on disk
3. **Query** environment metadata (Python version, location, status)
4. **Support** cross-platform paths (Windows, macOS, Linux)
5. **Provide** programmatic and shell-based interfaces

---

## 2. Tool Detection Matrix

Detection priority order (check in this sequence):

| Priority | Lock File | Config File | Tool | Detection Method |
|----------|-----------|-------------|------|-----------------|
| 1 | `poetry.lock` | `pyproject.toml` | Poetry | `poetry env info -p` |
| 2 | `Pipfile.lock` | `Pipfile` | Pipenv | `pipenv --venv` |
| 3 | `pdm.lock` | `pyproject.toml` | PDM | `pdm info -p` or read `.pdm.toml` |
| 4 | `uv.lock` | `.python-version` | uv | `.venv` directory + `uv.lock` |
| 5 | `rye.lock` | `.python-version` | Rye | `.venv` directory + `rye.lock` |
| 6 | `.hatch` | `pyproject.toml` | Hatch | Parse `[tool.hatch.envs]` in config |
| 7 | `pyvenv.cfg` | — | Standard venv | Check `.venv/pyvenv.cfg` or `.env/pyvenv.cfg` |
| 8 | `.python-version` | — | pyenv/asdf | Check `$PYENV_ROOT/versions/` or `$ASDF_DATA_DIR/versions/` |

---

## 3. Environment Location Resolution

### 3.1 Poetry

**Lock File:** `poetry.lock`  
**Config:** `pyproject.toml` + optional `poetry.toml`  

**Default Location:**
- **macOS/Linux:** `~/.cache/pypoetry/virtualenvs/{project-hash}-py{version}/`
- **Windows:** `%APPDATA%\pypoetry\Cache\virtualenvs\{project-hash}-py{version}\`

**In-Project Location:**  
- If `poetry config virtualenvs.in-project true`: `.venv/`

**Detection Commands:**
```bash
# Get venv path (most reliable)
poetry env info -p

# List all envs with full paths
poetry env list --full-path

# Get venv path + package info (first line is path)
poetry show -v | head -1
```

**Configuration:**
```toml
[tool.poetry]
# Force in-project venv
virtualenvs.in-project = true
# Specify Python version
python = "^3.11"
```

**Environment Variables:**
- `POETRY_VIRTUALENVS_IN_PROJECT` - Set to `1` or `true` to override config

---

### 3.2 Pipenv

**Lock File:** `Pipfile.lock`  
**Config:** `Pipfile`  

**Default Location:**
- **macOS/Linux:** `~/.local/share/virtualenvs/{project-hash}/`
- **Windows:** `%USERPROFILE%\.virtualenvs\{project-hash}\`

**In-Project Location:**  
- If `PIPENV_VENV_IN_PROJECT=1` set: `.venv/`

**Detection Commands:**
```bash
# Get venv path
pipenv --venv

# Activate shell
pipenv shell

# Get Python location
pipenv --py
```

**Configuration:**
```bash
# Set environment variable to use in-project venv
export PIPENV_VENV_IN_PROJECT=1

# Alternative: Custom venv location
export WORKON_HOME=~/.venvs
```

**Environment Variables:**
- `PIPENV_VENV_IN_PROJECT` - `0` or `1`
- `PIPENV_PIPFILE` - Path to custom `Pipfile`
- `PIPENV_IGNORE_PIPFILE` - Use only `.lock` file
- `PIPENV_NOSPIN` - Disable spinner (for automation)
- `PIPENV_YES` - Auto-confirm prompts

---

### 3.3 PDM

**Lock File:** `pdm.lock`  
**Config:** `pyproject.toml` + `.pdm.toml` (project-local)  

**Default Location:**
- Auto-detects: `venv/`, `env/`, `.venv/` in project root
- Falls back to: Currently activated virtualenv
- Stores path in: `.pdm.toml` under `[python]` section as `path`

**Detection Commands:**
```bash
# Get current Python path
pdm info

# List available interpreters
pdm list-interpreters

# Use specific Python (stores in .pdm.toml)
pdm use -f /path/to/python

# Activate in-project venv
pdm venv activate in-project

# Read stored path from config
pdm config -ld python.path
```

**Configuration:**
```toml
# pyproject.toml
[tool.pdm]
python.use-venv = true

# .pdm.toml (auto-generated, don't edit directly)
[python]
path = "/path/to/.venv/bin/python"
```

**Environment Variables:**
- `PDM_IGNORE_SAVED_PYTHON` - Force re-detection of Python
- `PDM_PROJECT_ROOT` - Specify project root

---

### 3.4 uv

**Lock File:** `uv.lock`  
**Config:** `pyproject.toml` + `.python-version`  

**Default Location:** Always `.venv/`

**Detection Commands:**
```bash
# Check current environment
python --version  # If .venv is activated

# uv automatically uses .venv if present
uv pip list

# Get venv path
uv venv --help  # Shows default location
```

**Configuration:**
```
# .python-version file
3.12.5

# or use pyproject.toml
[project]
requires-python = ">=3.12"
```

**Environment Variables:**
- `UV_PYTHON` - Override Python version
- `UV_PROJECT_ENVIRONMENT` - Specify venv location
- `VIRTUAL_ENV` - Set by activation script

---

### 3.5 Rye

**Lock File:** `rye.lock`  
**Config:** `pyproject.toml` + `.python-version`  

**Default Location:** `.venv/`

**Detection Commands:**
```bash
# Get Python version
rye show

# List available toolchains
rye toolchain list

# Pin Python version (updates .python-version)
rye pin 3.12

# Sync environment
rye sync
```

**Configuration:**
```toml
# pyproject.toml
[tool.rye]
managed = true
dev-dependencies = ["pytest", "black"]

# .python-version
3.12.5
```

**Environment Variables:**
- `RYE_HOME` - Rye installation directory
- `RYE_TOOLCHAIN_VERSION` - Override Python version

---

### 3.6 Hatch

**Lock File:** None (uses `pyproject.toml` only)  
**Config:** `pyproject.toml`  

**Default Location:**
- Configured in `[dirs.env]` in `~/.config/hatch/config.toml`
- Default: `{XDG_DATA_HOME}/hatch/env/{type}` or platform-specific
- Can be per-project: `[tool.hatch.envs.<ENV_NAME>]` with `path` option

**Detection Commands:**
```bash
# List environments
hatch env show

# Create environment
hatch env create default

# Remove environment
hatch env remove default
```

**Configuration:**
```toml
# pyproject.toml
[tool.hatch.envs.default]
type = "virtual"
path = ".venv"  # Optional: specify location
python = "3.12"  # Specify Python version
dependencies = ["pytest", "black"]

[tool.hatch.envs.default.env-vars]
PYTHONPATH = "src"
```

**Config File:** `~/.config/hatch/config.toml` (or platform-specific)
```toml
[dirs.env]
virtual = "~/.virtualenvs"  # Global venv location
```

**Environment Variables:**
- `HATCH_PYTHON` - Python executable to use
- `HATCH_ENV_TYPE_VIRTUAL_PATH` - Override venv path

---

### 3.7 Standard venv

**Config:** `pyvenv.cfg`  
**Location:** Anywhere (must be explicitly created/located)

**Detection:**
```bash
# Check pyvenv.cfg inside venv
cat .venv/pyvenv.cfg

# Check environment variable (only if activated)
echo $VIRTUAL_ENV

# Python sys.prefix (works if activated)
python -c "import sys; print(sys.prefix)"
```

**Create:**
```bash
python3 -m venv .venv
source .venv/bin/activate  # Unix
.venv\Scripts\activate.bat  # Windows
```

---

## 4. Cross-Platform Path Handling

### 4.1 Path Separators & Variables

| OS | Path Separator | Home Dir | Activation Script |
|----|---|---|---|
| Linux/macOS | `/` | `~` or `$HOME` | `.venv/bin/activate` |
| Windows | `\` | `%USERPROFILE%` | `.venv\Scripts\activate.bat` or `.venv\Scripts\Activate.ps1` |

### 4.2 Path Expansion Rules

**Input:** `~/.cache/pypoetry/virtualenvs`

**Processing:**
1. Expand `~` to user home (`$HOME` / `%USERPROFILE%`)
2. Expand environment variables: `$VAR` (Unix) or `%VAR%` (Windows)
3. Normalize separators to target OS
4. Resolve symlinks (optional, for clarity)
5. Return absolute path

**Example Implementation:**
```python
import os
from pathlib import Path

def expand_path(path_str: str) -> str:
    """Expand ~ and env variables, normalize separators."""
    # Expand ~ to home
    path = os.path.expanduser(path_str)
    # Expand environment variables
    path = os.path.expandvars(path)
    # Convert to Path object for normalization
    path = Path(path).resolve()
    return str(path)
```

---

## 5. Detection Algorithm

### 5.1 High-Level Flow

```
detect_environment(project_root: str) -> EnvironmentInfo:
    1. Change to project_root
    2. FOR each tool in DETECTION_PRIORITY:
        a. Check if tool marker file exists
        b. IF exists:
            - Determine venv location
            - Validate venv exists
            - Return EnvironmentInfo(tool, path, python_version)
    3. IF no tool found:
        - Check for .python-version (pyenv/asdf)
        - Check for activated venv ($VIRTUAL_ENV)
        - Check for .venv directory
        - Return EnvironmentInfo("unknown", path, None)
    4. ELSE:
        - Return EnvironmentInfo(None, None, None)
```

### 5.2 Pseudocode (Shell)

```bash
#!/bin/bash
# detect_python_env.sh

PROJECT_ROOT="${1:-.}"
cd "$PROJECT_ROOT" || exit 1

# 1. Poetry
if [ -f "poetry.lock" ]; then
    VENV_PATH=$(poetry env info -p 2>/dev/null) || VENV_PATH="<error>"
    TOOL="poetry"
    return 0
fi

# 2. Pipenv
if [ -f "Pipfile.lock" ]; then
    VENV_PATH=$(pipenv --venv 2>/dev/null) || VENV_PATH="<error>"
    TOOL="pipenv"
    return 0
fi

# 3. PDM
if [ -f "pdm.lock" ]; then
    VENV_PATH=$(pdm info 2>/dev/null | grep "Location:" | awk '{print $2}') || VENV_PATH="<error>"
    TOOL="pdm"
    return 0
fi

# 4. uv
if [ -f "uv.lock" ] && [ -d ".venv" ]; then
    VENV_PATH=".venv"
    TOOL="uv"
    return 0
fi

# 5. Rye
if [ -f "rye.lock" ] && [ -d ".venv" ]; then
    VENV_PATH=".venv"
    TOOL="rye"
    return 0
fi

# 6. Hatch
if grep -q '\[tool.hatch.envs' pyproject.toml 2>/dev/null; then
    # Parse hatch config
    VENV_PATH=$(python3 -c "
import tomllib
with open('pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
    envs = data.get('tool', {}).get('hatch', {}).get('envs', {})
    default_env = envs.get('default', {})
    print(default_env.get('path', '.venv'))
")
    TOOL="hatch"
    return 0
fi

# 7. Standard venv
if [ -f ".venv/pyvenv.cfg" ]; then
    VENV_PATH=".venv"
    TOOL="venv"
    return 0
fi

# 8. pyenv/asdf
if [ -f ".python-version" ]; then
    PYTHON_VERSION=$(cat .python-version)
    if [ -n "$PYENV_ROOT" ]; then
        VENV_PATH="$PYENV_ROOT/versions/$PYTHON_VERSION"
    fi
    TOOL="pyenv"
    return 0
fi

# 9. Currently activated env
if [ -n "$VIRTUAL_ENV" ]; then
    VENV_PATH="$VIRTUAL_ENV"
    TOOL="activated"
    return 0
fi

echo "No Python environment detected"
exit 1
```

### 5.3 Pseudocode (Python)

```python
import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, Tuple
from enum import Enum

class ToolType(Enum):
    POETRY = "poetry"
    PIPENV = "pipenv"
    PDM = "pdm"
    UV = "uv"
    RYE = "rye"
    HATCH = "hatch"
    VENV = "venv"
    PYENV = "pyenv"
    UNKNOWN = "unknown"

class EnvironmentInfo:
    def __init__(
        self,
        tool: ToolType,
        venv_path: Optional[str] = None,
        python_version: Optional[str] = None,
        python_executable: Optional[str] = None,
    ):
        self.tool = tool
        self.venv_path = venv_path
        self.python_version = python_version
        self.python_executable = python_executable

def detect_environment(project_root: str = ".") -> EnvironmentInfo:
    """
    Detect Python environment for given project root.
    
    Args:
        project_root: Path to project directory
        
    Returns:
        EnvironmentInfo with detected tool and venv path
    """
    
    project_path = Path(project_root).resolve()
    os.chdir(project_path)
    
    # 1. Poetry
    if (project_path / "poetry.lock").exists():
        return _detect_poetry()
    
    # 2. Pipenv
    if (project_path / "Pipfile.lock").exists():
        return _detect_pipenv()
    
    # 3. PDM
    if (project_path / "pdm.lock").exists():
        return _detect_pdm()
    
    # 4. uv
    if (project_path / "uv.lock").exists() and (project_path / ".venv").is_dir():
        return _detect_uv()
    
    # 5. Rye
    if (project_path / "rye.lock").exists() and (project_path / ".venv").is_dir():
        return _detect_rye()
    
    # 6. Hatch
    if _is_hatch_project(project_path):
        return _detect_hatch()
    
    # 7. Standard venv
    if (project_path / ".venv" / "pyvenv.cfg").exists():
        return _detect_venv()
    
    # 8. pyenv
    if (project_path / ".python-version").exists():
        return _detect_pyenv()
    
    # 9. Currently activated
    if venv := os.environ.get("VIRTUAL_ENV"):
        return EnvironmentInfo(
            tool=ToolType.UNKNOWN,
            venv_path=venv,
        )
    
    return EnvironmentInfo(tool=ToolType.UNKNOWN)

def _detect_poetry() -> EnvironmentInfo:
    """Detect Poetry virtual environment."""
    try:
        result = subprocess.run(
            ["poetry", "env", "info", "-p"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            venv_path = result.stdout.strip()
            return EnvironmentInfo(
                tool=ToolType.POETRY,
                venv_path=venv_path,
                python_executable=str(Path(venv_path) / ("bin" if sys.platform != "win32" else "Scripts") / ("python" if sys.platform != "win32" else "python.exe")),
            )
    except Exception:
        pass
    
    return EnvironmentInfo(tool=ToolType.POETRY, venv_path=None)

def _detect_pipenv() -> EnvironmentInfo:
    """Detect Pipenv virtual environment."""
    try:
        result = subprocess.run(
            ["pipenv", "--venv"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            venv_path = result.stdout.strip()
            return EnvironmentInfo(
                tool=ToolType.PIPENV,
                venv_path=venv_path,
            )
    except Exception:
        pass
    
    return EnvironmentInfo(tool=ToolType.PIPENV, venv_path=None)

def _detect_pdm() -> EnvironmentInfo:
    """Detect PDM virtual environment."""
    # Check .pdm.toml for python.path
    pdm_config = Path(".pdm.toml")
    if pdm_config.exists():
        try:
            import tomllib
            with open(pdm_config, "rb") as f:
                data = tomllib.load(f)
                python_path = data.get("python", {}).get("path")
                if python_path:
                    venv_path = str(Path(python_path).parent.parent)
                    return EnvironmentInfo(
                        tool=ToolType.PDM,
                        venv_path=venv_path,
                        python_executable=python_path,
                    )
        except Exception:
            pass
    
    # Fallback: try pdm command
    try:
        result = subprocess.run(
            ["pdm", "info"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Parse output for "Location:" line
    except Exception:
        pass
    
    return EnvironmentInfo(tool=ToolType.PDM, venv_path=None)

def _detect_uv() -> EnvironmentInfo:
    """Detect uv virtual environment."""
    venv_path = Path(".venv").resolve()
    return EnvironmentInfo(
        tool=ToolType.UV,
        venv_path=str(venv_path),
        python_executable=str(venv_path / ("bin" if sys.platform != "win32" else "Scripts") / ("python" if sys.platform != "win32" else "python.exe")),
    )

def _detect_rye() -> EnvironmentInfo:
    """Detect Rye virtual environment."""
    venv_path = Path(".venv").resolve()
    return EnvironmentInfo(
        tool=ToolType.RYE,
        venv_path=str(venv_path),
    )

def _is_hatch_project(project_path: Path) -> bool:
    """Check if project uses Hatch."""
    pyproject = project_path / "pyproject.toml"
    if not pyproject.exists():
        return False
    try:
        import tomllib
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
            return bool(data.get("tool", {}).get("hatch", {}).get("envs"))
    except Exception:
        return False

def _detect_hatch() -> EnvironmentInfo:
    """Detect Hatch virtual environment."""
    try:
        import tomllib
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
            envs = data.get("tool", {}).get("hatch", {}).get("envs", {})
            default_env = envs.get("default", {})
            venv_path = default_env.get("path", ".venv")
            if not Path(venv_path).is_absolute():
                venv_path = str(Path(venv_path).resolve())
            return EnvironmentInfo(
                tool=ToolType.HATCH,
                venv_path=venv_path,
            )
    except Exception:
        pass
    
    return EnvironmentInfo(tool=ToolType.HATCH, venv_path=None)

def _detect_venv() -> EnvironmentInfo:
    """Detect standard venv."""
    venv_path = Path(".venv").resolve()
    return EnvironmentInfo(
        tool=ToolType.VENV,
        venv_path=str(venv_path),
    )

def _detect_pyenv() -> EnvironmentInfo:
    """Detect pyenv environment."""
    try:
        with open(".python-version", "r") as f:
            version = f.read().strip()
        
        pyenv_root = os.environ.get("PYENV_ROOT", "~/.pyenv")
        pyenv_root = Path(pyenv_root).expanduser()
        venv_path = pyenv_root / "versions" / version
        
        return EnvironmentInfo(
            tool=ToolType.PYENV,
            venv_path=str(venv_path) if venv_path.exists() else None,
            python_version=version,
        )
    except Exception:
        pass
    
    return EnvironmentInfo(tool=ToolType.PYENV)

# Usage
if __name__ == "__main__":
    env_info = detect_environment()
    print(f"Tool: {env_info.tool.value}")
    print(f"Venv Path: {env_info.venv_path}")
    print(f"Python Version: {env_info.python_version}")
    print(f"Python Executable: {env_info.python_executable}")
```

---

## 6. API Interfaces

### 6.1 Shell Command Interface

```bash
# Get environment info as JSON
python detect_env.py --format=json

# Output:
# {
#   "tool": "poetry",
#   "venv_path": "/Users/user/.cache/pypoetry/virtualenvs/myproject-abc123-py3.11",
#   "python_version": "3.11.5",
#   "python_executable": "/Users/user/.cache/pypoetry/virtualenvs/myproject-abc123-py3.11/bin/python",
#   "is_activated": false
# }

# Get environment info as human-readable text
python detect_env.py --format=text

# Output:
# Tool: poetry
# Venv Path: /Users/user/.cache/pypoetry/virtualenvs/myproject-abc123-py3.11
# Python Version: 3.11.5
# Python Executable: /Users/user/.cache/pypoetry/virtualenvs/myproject-abc123-py3.11/bin/python
# Is Activated: false
```

### 6.2 Python Library Interface

```python
from env_detector import detect_environment, EnvironmentInfo, ToolType

# Detect in current project
env = detect_environment()

if env.tool == ToolType.POETRY:
    print(f"Using Poetry: {env.venv_path}")
elif env.tool == ToolType.PIPENV:
    print(f"Using Pipenv: {env.venv_path}")
elif env.tool == ToolType.UNKNOWN:
    print("No recognized environment found")

# Get Python executable
if env.python_executable:
    subprocess.run([env.python_executable, "script.py"])
```

### 6.3 Environment Variable Interface

After detection, set environment variables:

```bash
export DETECTED_TOOL="poetry"
export DETECTED_VENV_PATH="/Users/user/.cache/pypoetry/virtualenvs/myproject-abc123-py3.11"
export DETECTED_PYTHON_EXECUTABLE="/Users/user/.cache/pypoetry/virtualenvs/myproject-abc123-py3.11/bin/python"
```

---

## 7. Error Handling

| Error Scenario | Response |
|---|---|
| No lock file or config found | Return `ToolType.UNKNOWN` with `venv_path=None` |
| Tool command fails (e.g., `poetry env info -p` fails) | Log warning, fallback to file-based detection |
| Venv path doesn't exist on disk | Return path but set `is_valid=False` flag |
| Permission denied accessing venv | Return path but note permission error |
| Circular symlinks in venv path | Use `Path.resolve(strict=False)` and log warning |

---

## 8. Implementation Notes

### 8.1 Timing Considerations
- Poetry `env info -p` can take 0.5-2s (cache lookups)
- Pipenv `--venv` similarly slow (~1-2s)
- PDM and uv are faster (file-based)
- **Recommendation:** Cache detection results per project session

### 8.2 Platform-Specific Behaviors

**Windows:**
- UNC paths: `\\?\C:\path\to\venv`
- Batch script: `.venv\Scripts\activate.bat`
- PowerShell: `.venv\Scripts\Activate.ps1`
- Environment variables: Use `%VAR%` not `$VAR`

**macOS/Linux:**
- Symlinks common in `/usr/local/` - resolve them
- Shell scripts: `.venv/bin/activate`
- Environment variables: Use `$VAR`

### 8.3 Configuration Precedence

For each tool, precedence order:

**Poetry:**
1. `POETRY_VIRTUALENVS_IN_PROJECT` env var
2. `poetry config virtualenvs.in-project` setting
3. Default cache directory

**Pipenv:**
1. `PIPENV_VENV_IN_PROJECT` env var
2. `WORKON_HOME` env var
3. `~/.local/share/virtualenvs/`

**PDM:**
1. `.pdm.toml` `python.path` (auto-stored)
2. Currently activated `$VIRTUAL_ENV`
3. Auto-detected: `.venv/`, `venv/`, `env/` in project

**uv/Rye:**
1. `.python-version` (version spec)
2. Always `.venv/` (location)

**Hatch:**
1. `[tool.hatch.envs.<ENV>.path]` in `pyproject.toml`
2. Configured in `~/.config/hatch/config.toml` `[dirs.env]`
3. Platform-specific default data dir

---

## 9. Testing Requirements

### 9.1 Test Cases

1. **Single-tool projects** - Each tool individually
2. **Multi-file scenarios** - `pyproject.toml` + `poetry.lock` + `uv.lock` (should detect poetry first)
3. **Custom paths** - Hatch with non-standard venv path
4. **Activated environments** - With `$VIRTUAL_ENV` set
5. **Missing/broken venvs** - Lock file present but venv doesn't exist
6. **Cross-platform paths** - Windows UNC paths, macOS symlinks
7. **Nested projects** - Detect correct tool for nested `pyproject.toml` files

### 9.2 Validation Steps

```bash
# Test Poetry
mkdir test_poetry && cd test_poetry
poetry init --no-interaction
poetry add requests
# Verify: poetry env info -p returns valid path

# Test Pipenv
mkdir test_pipenv && cd test_pipenv
pipenv install requests
# Verify: pipenv --venv returns valid path

# Test PDM
mkdir test_pdm && cd test_pdm
pdm init --non-interactive
pdm add requests
# Verify: .pdm.toml contains python.path

# Test uv
mkdir test_uv && cd test_uv
echo "3.12" > .python-version
uv sync
# Verify: .venv exists

# Test Hatch
mkdir test_hatch && cd test_hatch
echo '[tool.hatch]' > pyproject.toml
# Verify: hatch env show lists environments
```

---

## 10. Future Enhancements

1. **Monorepo support** - Detect tool per subdirectory
2. **Container awareness** - Detect if running in Docker/container
3. **Conda/Mamba support** - Add detection for conda environments
4. **Watch mode** - Monitor `.python-version` / `poetry.lock` for changes
5. **IDE integration** - VS Code, PyCharm plugin hooks
6. **Caching layer** - LRU cache for repeated detections
7. **Metrics** - Track detection success rate and timing

---

## 11. References

- Poetry Docs: https://python-poetry.org/docs/managing-environments/
- Pipenv Docs: https://pipenv.pypa.io/
- PDM Docs: https://pdm-project.org/
- uv Docs: https://docs.astral.sh/uv/
- Rye Docs: https://rye.astral.sh/
- Hatch Docs: https://hatch.pypa.io/
- PEP 405: https://www.python.org/dev/peps/pep-0405/ (venv)

---

**Document Version History:**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-31 | Research | Initial spec for 8 major tools, cross-platform support |
