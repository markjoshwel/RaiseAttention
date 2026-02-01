"""practical examples of raiseattention detecting unhandled exceptions.

this demonstrates what raiseattention actually detects - exceptions from:
1. explicit raise statements in your code
2. function calls to other functions in your codebase that raise exceptions
"""

from __future__ import annotations

import json
from pathlib import Path


# =============================================================================
# example 1: calling a function that raises (transitive detection)
# =============================================================================


def load_user_data(user_id: int) -> dict:
    """load user data from database.

    raiseattention will flag: calling validate_user_id may raise ValueError
    """
    # calling a function that raises - this line will be flagged
    validate_user_id(user_id)

    # this line is safe (returns normally)
    return {"user_id": user_id, "name": "test"}


def validate_user_id(user_id: int) -> None:
    """validate user id."""
    if user_id <= 0:
        raise ValueError("user_id must be positive")
    if user_id > 999999:
        raise ValueError("user_id too large")


# =============================================================================
# example 2: proper exception handling
# =============================================================================


def load_user_data_safe(user_id: int) -> dict | None:
    """load user data with proper exception handling.

    raiseattention will detect: all exceptions handled, no diagnostics
    """
    try:
        validate_user_id(user_id)
        return {"user_id": user_id, "name": "test"}
    except ValueError as e:
        print(f"validation failed: {e}")
        return None


# =============================================================================
# example 3: partial handling (catches one, misses another)
# =============================================================================


def load_user_data_partial(user_id: int) -> dict | None:
    """load user data with incomplete handling.

    raiseattention will flag: ValueError from validate_user_id not handled
    """
    validate_user_id(user_id)  # line 50 - unhandled ValueError

    try:
        result = fetch_from_cache(user_id)
    except KeyError:
        result = None

    if result is None:
        result = fetch_from_database(user_id)

    return result


def fetch_from_cache(user_id: int) -> dict:
    """fetch from cache."""
    cache = {1: {"name": "alice"}}
    if user_id not in cache:
        raise KeyError(f"user {user_id} not in cache")
    return cache[user_id]


def fetch_from_database(user_id: int) -> dict:
    """fetch from database - no exceptions raised."""
    return {"user_id": user_id, "name": "from_db"}


# =============================================================================
# example 4: multi-level call chain
# =============================================================================


def process_user_request(request_data: dict) -> dict:
    """process a user request through multiple levels.

    raiseattention will flag: validation errors propagate through the chain
    """
    # level 3: calling level 2
    user = extract_user(request_data)  # line 87 - unhandled exceptions

    # process user
    return {"processed": True, "user": user}


def extract_user(request_data: dict) -> dict:
    """extract user from request - level 2."""
    user_id = request_data.get("user_id")

    # level 2: calling level 1
    validate_user_data(user_id)  # line 97 - calls validator

    return {"user_id": user_id}


def validate_user_data(user_id: int | None) -> None:
    """validate user data - level 1."""
    if user_id is None:
        raise TypeError("user_id is required")
    if not isinstance(user_id, int):
        raise TypeError("user_id must be an integer")


# =============================================================================
# example 5: exception hierarchy (catching parent catches children)
# =============================================================================


def process_with_parent_catch(data: str) -> dict:
    """process with exception hierarchy handling.

    raiseattention will detect: ValueError caught by Exception handler
    """
    try:
        parse_integer(data)  # may raise ValueError
        return {"success": True}
    except Exception:  # catches ValueError (subclass of Exception)
        return {"success": False}


def parse_integer(data: str) -> int:
    """parse string to integer."""
    if not data.isdigit():
        raise ValueError(f"not a number: {data}")
    return int(data)


# =============================================================================
# example 6: different exception types, partial handling
# =============================================================================


def process_mixed_exceptions(username: str, age: str) -> dict:
    """process with multiple exception types.

    raiseattention will flag: TypeError from validate_username not caught
    """
    # validates username - may raise TypeError
    validate_username(username)  # line 139 - unhandled TypeError

    # validates age - may raise ValueError
    try:
        validate_age(age)
    except ValueError:
        print("invalid age, using default")
        age = "25"

    return {"username": username, "age": int(age)}


def validate_username(username: str) -> None:
    """validate username."""
    if not isinstance(username, str):
        raise TypeError("username must be a string")
    if len(username) < 3:
        raise ValueError("username too short")


def validate_age(age: str) -> None:
    """validate age."""
    if not age.isdigit():
        raise ValueError("age must be numeric")
    age_int = int(age)
    if age_int < 0 or age_int > 150:
        raise ValueError("age out of range")


# =============================================================================
# example 7: re-raising and exception chaining
# =============================================================================


def process_with_chaining(data: dict) -> dict:
    """process with exception chaining.

    raiseattention will flag: original ValidationError may escape
    """
    try:
        return validate_data_structure(data)
    except ValidationErrorChained as e:
        # wrap in ProcessingError but original exception is available
        raise ProcessingError(f"failed to process") from e


class ValidationErrorChained(Exception):
    """validation failed for chaining example."""

    pass


class ProcessingError(Exception):
    """processing failed."""

    pass


def validate_data_structure(data: dict) -> dict:
    """validate data structure."""
    if "required_field" not in data:
        raise ValidationErrorChained("missing required_field")
    return data


# =============================================================================
# example 8: library wrapper pattern
# =============================================================================


class ConfigLoader:
    """configuration loader with proper exception handling.

    all public methods handle exceptions or document what they raise.
    """

    def load_config(self, path: str) -> dict | None:
        """load configuration file.

        all exceptions are caught and converted to return values.
        """
        try:
            return self._parse_config_file(path)
        except ConfigError as e:
            print(f"config error: {e}")
            return None

    def _parse_config_file(self, path: str) -> dict:
        """parse config file - may raise ConfigError."""
        import json

        try:
            with open(path) as f:
                content = f.read()
        except FileNotFoundError:
            raise ConfigError(f"config file not found: {path}")
        except PermissionError:
            raise ConfigError(f"cannot read config: {path}")

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ConfigError(f"invalid json: {e}")


class ConfigError(Exception):
    """configuration error."""

    pass


# =============================================================================
# example 9: async functions
# =============================================================================


async def fetch_user_async(user_id: int) -> dict | None:
    """fetch user asynchronously.

    raiseattention will flag: unhandled ValidationError
    """
    # validate user id
    validate_user_id(user_id)  # line 245 - unhandled ValueError

    # fetch from api
    return await mock_api_call(user_id)


async def fetch_user_async_safe(user_id: int) -> dict | None:
    """fetch user with proper handling."""
    try:
        validate_user_id(user_id)
        return await mock_api_call(user_id)
    except ValueError as e:
        print(f"invalid user_id: {e}")
        return None


async def mock_api_call(user_id: int) -> dict:
    """mock api call."""
    return {"user_id": user_id}


# =============================================================================
# example 10: complete production example
# =============================================================================


class UserService:
    """production-ready user service with full exception handling.

    raiseattention will verify all exception paths are handled.
    """

    def create_user(self, username: str, email: str, age: int) -> dict:
        """create a new user with validation.

        all validation exceptions are caught and returned as error response.
        """
        try:
            # validate all inputs
            self._validate_username(username)
            self._validate_email(email)
            self._validate_age(age)

            # create user
            user = {
                "username": username,
                "email": email,
                "age": age,
            }

            return {"success": True, "user": user}

        except (ValidationError, TypeError, ValueError) as e:
            return {"success": False, "error": str(e)}

    def _validate_username(self, username: str) -> None:
        """validate username."""
        if not isinstance(username, str):
            raise TypeError("username must be string")
        if len(username) < 3:
            raise ValidationError("username must be at least 3 characters")
        if not username.isalnum():
            raise ValidationError("username must be alphanumeric")

    def _validate_email(self, email: str) -> None:
        """validate email."""
        if not isinstance(email, str):
            raise TypeError("email must be string")
        if "@" not in email:
            raise ValidationError("invalid email format")

    def _validate_age(self, age: int) -> None:
        """validate age."""
        if not isinstance(age, int):
            raise TypeError("age must be integer")
        if age < 13:
            raise ValidationError("must be at least 13 years old")
        if age > 120:
            raise ValidationError("invalid age")


class ValidationError(Exception):
    """validation error."""

    pass
