# raiseattention usage examples

this directory contains practical examples demonstrating how raiseattention detects unhandled exceptions in python code.

## what raiseattention detects

raiseattention detects unhandled exceptions from:

1. **explicit raise statements** in functions you define
2. **function calls** to other functions in your codebase that raise exceptions
3. **transitive propagation** - exceptions that bubble up through multiple call levels

## quick start

### command line usage

```bash
# analyse a single file
uv run raiseattention check examples/working_examples.py

# analyse entire project
uv run raiseattention check .

# output as json for ci/cd integration
uv run raiseattention check --format=json src/

# save report to file
uv run raiseattention check --format=json --output=report.json src/
```

### example output

```
B:\RaiseAttention\examples\working_examples.py:25:4: error: call to 'validate_user_id' may raise unhandled exception(s): ValueError
B:\RaiseAttention\examples\working_examples.py:67:4: error: call to 'validate_user_id' may raise unhandled exception(s): ValueError
```

## common patterns

### pattern 1: calling a validator

**before (raisesattention flags this):**
```python
def load_user_data(user_id: int) -> dict:
    validate_user_id(user_id)  # flagged: may raise ValueError
    return {"user_id": user_id}

def validate_user_id(user_id: int) -> None:
    if user_id <= 0:
        raise ValueError("user_id must be positive")
```

**after (properly handled):**
```python
def load_user_data(user_id: int) -> dict | None:
    try:
        validate_user_id(user_id)
        return {"user_id": user_id}
    except ValueError as e:
        print(f"validation failed: {e}")
        return None
```

### pattern 2: multi-level call chains

**the analyzer tracks exceptions through multiple levels:**

```python
# level 3 (called by user code)
def process_user_request(request_data: dict) -> dict:
    user = extract_user(request_data)  # flagged: may raise TypeError
    return {"processed": True, "user": user}

# level 2 (middle layer)
def extract_user(request_data: dict) -> dict:
    user_id = request_data.get("user_id")
    validate_user_data(user_id)  # propagates exceptions up
    return {"user_id": user_id}

# level 1 (validation)
def validate_user_data(user_id: int | None) -> None:
    if user_id is None:
        raise TypeError("user_id is required")  # exception origin
```

raiseattention will flag the call at **line 3** because:
1. `validate_user_data` raises `TypeError`
2. `extract_user` calls `validate_user_data` without handling it
3. `process_user_request` calls `extract_user` without handling it
4. therefore `process_user_request` may raise `TypeError`

### pattern 3: exception hierarchy

**catching a parent exception handles child exceptions:**

```python
def process_data(data: str) -> dict:
    try:
        parse_number(data)  # may raise ValueError (subclass of Exception)
        return {"success": True}
    except Exception:  # catches ValueError
        return {"success": False}

def parse_number(data: str) -> int:
    if not data.isdigit():
        raise ValueError(f"not a number: {data}")
    return int(data)
```

raiseattention knows that `ValueError` is a subclass of `Exception`, so it **won't flag** this code.

### pattern 4: partial handling

**when you handle some exceptions but not others:**

```python
def process_user(username: str, age: str) -> dict:
    # only catches ValueError, misses TypeError
    try:
        validate_username(username)
    except ValueError:
        username = "default"
    
    # this line will be flagged - TypeError not caught!
    validate_username(username)  # may raise TypeError
    
    return {"username": username, "age": age}

def validate_username(username: str) -> None:
    if not isinstance(username, str):
        raise TypeError("must be string")
    if len(username) < 3:
        raise ValueError("too short")
```

## lsp server (editor integration)

start the lsp server for real-time diagnostics in your editor:

```bash
uv run raiseattention lsp
```

### editor configuration

**vscode:**
```json
{
  "python.analysis.extraPaths": ["src"],
  "python.linting.enabled": true
}
```

**neovim (with lspconfig):**
```lua
require'lspconfig'.raiseattention.setup{
  cmd = {'uv', 'run', 'raiseattention', 'lsp'},
  filetypes = {'python'},
}
```

## ci/cd integration

### github actions

```yaml
name: exception-check
on: [push, pull_request]

jobs:
  check-exceptions:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      
      - name: check for unhandled exceptions
        run: |
          uv run raiseattention check --format=json . > exceptions.json
          if [ $(jq '.summary.issues_found' exceptions.json) -gt 0 ]; then
            echo "found unhandled exceptions:"
            cat exceptions.json | jq '.diagnostics[]'
            exit 1
          fi
```

### pre-commit hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: raiseattention
        name: check for unhandled exceptions
        entry: uv run raiseattention check
        language: system
        files: \.py$
        pass_filenames: true
```

## configuration

### pyproject.toml

```toml
[tool.raiseattention]
strict_mode = false
allow_bare_except = false

exclude = [
    "**/tests/**",
    "**/migrations/**",
]

ignore_exceptions = [
    "KeyboardInterrupt",
    "SystemExit",
]

[tool.raiseattention.cache]
enabled = true
max_file_entries = 10000

[tool.raiseattention.lsp]
debounce_ms = 500
max_diagnostics_per_file = 100
```

### environment variables

```bash
# strict mode
export RAISEATTENTION_STRICT_MODE=true

# debounce interval for lsp
export RAISEATTENTION_DEBOUNCE_MS=750
```

## best practices

### 1. handle exceptions at the right level

handle exceptions as close to the user-facing code as possible:

```python
# good: handle at api level
@app.route("/users", methods=["POST"])
def create_user():
    try:
        user_service.create_user(request.json)
        return {"success": True}
    except ValidationError as e:
        return {"success": False, "error": str(e)}, 400

# less good: handle deep in service layer
class UserService:
    def create_user(self, data):
        try:
            validate_data(data)
        except ValidationError:
            return None  # caller doesn't know why it failed
```

### 2. use specific exception types

```python
# good: specific exceptions
class ValidationError(Exception):
    pass

class NotFoundError(Exception):
    pass

# use them
raise ValidationError("invalid email")
raise NotFoundError(f"user {user_id} not found")
```

### 3. document expected exceptions

```python
def load_config(path: str) -> dict:
    """load configuration from file.
    
    raises:
        ConfigError: if file not found or invalid
    """
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise ConfigError(f"failed to load config: {e}")
```

### 4. wrap external library exceptions

```python
def fetch_from_api(endpoint: str) -> dict:
    """fetch data from external api.
    
    wraps requests exceptions in our own exception type.
    """
    import requests
    
    try:
        response = requests.get(endpoint)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise ApiError(f"api request failed: {e}")
```

## limitations

1. **built-in function signatures** - raiseattention doesn't know what exceptions built-in functions like `open()`, `json.load()`, or `csv.reader()` can raise. it only tracks exceptions through:
   - explicit `raise` statements in your code
   - function calls to other functions in your codebase

2. **external libraries** - exceptions from third-party libraries are only detected if you add exception signatures to the dependency cache or wrap them in your own functions.

3. **custom exception hierarchies** - raiseattention understands built-in exception hierarchies (e.g., `ValueError` → `Exception`), but not custom class inheritance without parsing class definitions.

## troubleshooting

### no diagnostics found

if raiseattention finds no issues but you expect it to:

1. check that functions have explicit `raise` statements
2. verify the functions are called (not just defined)
3. ensure you're analyzing the right files (check `exclude` patterns)

### too many diagnostics

if raiseattention is too noisy:

1. add specific exception types to `ignore_exceptions`
2. exclude test files or generated code
3. use `strict_mode = false` to reduce documentation warnings

## examples in this directory

- `working_examples.py` - demonstrates what raiseattention can detect (25 functions, 6 unhandled exception issues)
- `file_io_examples.py` - shows patterns for file operations (note: raiseattention doesn't track built-in exceptions)

run the analyzer on these files to see the output:

```bash
uv run raiseattention check examples/working_examples.py
```
