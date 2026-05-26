"""Helper utilities for exec-json.

Provides JSON extraction from mixed text and a hand-written JSON schema
validator (no external dependencies).
"""

from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def extract_json(text: str) -> tuple[Any, str | None]:
    """Extract the first valid JSON value from *text*.

    Scans *text* for the first ``{`` (object) or ``[`` (array), then
    extracts the balanced bracket substring respecting string escapes and
    nesting.  Attempts ``json.loads`` on the candidate; if parsing fails
    returns ``(None, error_message)``.

    Args:
        text: Arbitrary output that may contain JSON embedded in prose.

    Returns:
        ``(parsed_value, None)`` on success, ``(None, error_string)`` on
        failure.
    """
    if not text:
        return None, "No output to extract JSON from"

    # Locate the first bracket.
    start = -1
    brace_char: str | None = None
    for idx, ch in enumerate(text):
        if ch in ("{", "["):
            start = idx
            brace_char = ch
            break

    if start == -1:
        return None, "No JSON object or array found in output"

    closing = "}" if brace_char == "{" else "]"
    counter = 1
    in_quotes = False
    i = start

    # Use a while-loop so we can manually advance the index when skipping
    # escaped characters inside strings.
    while i < len(text) - 1:
        i += 1
        ch = text[i]

        if in_quotes:
            if ch == "\\":
                # Skip the next character entirely (escaped quote, backslash, etc.)
                if i + 1 < len(text):
                    i += 1
                continue
            if ch == '"':
                in_quotes = False
            continue

        if ch == '"':
            in_quotes = True
        elif ch == brace_char:  # type: ignore[comparison-overlap]
            counter += 1
        elif ch == closing:
            counter -= 1
            if counter == 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate), None
                except json.JSONDecodeError as exc:
                    return None, f"Invalid JSON: {exc}"

    return None, "Unbalanced brackets – could not extract complete JSON"


# ---------------------------------------------------------------------------
# Hand-written JSON schema validator
# ---------------------------------------------------------------------------

# Mapping of Python types to JSON Schema type names.
_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
    type(None): "null",
}


def _type_name(value: Any) -> str:
    """Return the JSON Schema type name for a Python value."""
    return _TYPE_MAP.get(type(value), "unknown")


def _validate_value(
    data: Any,
    schema: Any,
    path: str,
    errors: list[str],
) -> None:
    """Recursively validate *data* against *schema*, appending to *errors*.

    Args:
        data: The value to validate.
        schema: The JSON schema fragment (subset of JSON Schema).
        path: Dot-separated path for error messages (e.g. ``"root.items"``).
        errors: Accumulator list for human-readable error strings.
    """
    # --- type ---
    schema_type = schema.get("type")
    if schema_type is not None:
        actual = _type_name(data)
        if isinstance(schema_type, list):
            if actual not in schema_type:
                errors.append(
                    f"{path}: expected type in {schema_type!r}, got {actual!r}"
                )
                return  # further checks are meaningless
        else:
            if actual != schema_type:
                errors.append(
                    f"{path}: expected type {schema_type!r}, got {actual!r}"
                )
                return

    # --- enum ---
    enum_values = schema.get("enum")
    if enum_values is not None and data not in enum_values:
        errors.append(
            f"{path}: expected one of {enum_values!r}, got {data!r}"
        )
        return

    # --- object ---
    if schema_type == "object" or (isinstance(schema_type, list) and "object" in schema_type):
        if not isinstance(data, dict):
            return  # type error already reported

        # required
        required = schema.get("required", [])
        for field in required:
            if field not in data:
                errors.append(f"{path}: missing required field {field!r}")

        # properties
        properties = schema.get("properties", {})
        for key, sub_schema in properties.items():
            if key in data:
                _validate_value(
                    data[key], sub_schema, f"{path}.{key}", errors
                )

    # --- array ---
    if schema_type == "array" or (isinstance(schema_type, list) and "array" in schema_type):
        if not isinstance(data, list):
            return
        items_schema = schema.get("items")
        if items_schema is not None:
            for i, item in enumerate(data):
                _validate_value(item, items_schema, f"{path}[{i}]", errors)

    # --- minimum / maximum (number / integer) ---
    if schema_type in ("number", "integer") or (
        isinstance(schema_type, list) and any(t in ("number", "integer") for t in schema_type)
    ):
        if isinstance(data, (int, float)):
            min_ = schema.get("minimum")
            max_ = schema.get("maximum")
            if min_ is not None and data < min_:
                errors.append(f"{path}: value {data} is less than minimum {min_}")
            if max_ is not None and data > max_:
                errors.append(f"{path}: value {data} is greater than maximum {max_}")

    # --- minLength / maxLength (string) ---
    if schema_type == "string" or (isinstance(schema_type, list) and "string" in schema_type):
        if isinstance(data, str):
            min_len = schema.get("minLength")
            max_len = schema.get("maxLength")
            if min_len is not None and len(data) < min_len:
                errors.append(
                    f"{path}: string length {len(data)} is less than "
                    f"minLength {min_len}"
                )
            if max_len is not None and len(data) > max_len:
                errors.append(
                    f"{path}: string length {len(data)} exceeds "
                    f"maxLength {max_len}"
                )

    # --- minItems / maxItems (array) ---
    if schema_type == "array" or (isinstance(schema_type, list) and "array" in schema_type):
        if isinstance(data, list):
            min_items = schema.get("minItems")
            max_items = schema.get("maxItems")
            if min_items is not None and len(data) < min_items:
                errors.append(
                    f"{path}: array length {len(data)} is less than "
                    f"minItems {min_items}"
                )
            if max_items is not None and len(data) > max_items:
                errors.append(
                    f"{path}: array length {len(data)} exceeds "
                    f"maxItems {max_items}"
                )


def validate_schema(data: Any, schema: dict) -> tuple[bool, list[str]]:
    """Validate *data* against a JSON Schema subset.

    Supported schema keywords:

    * ``type`` (string or list of strings)
    * ``enum``
    * ``required``, ``properties`` (recursive)
    * ``items`` (per-element validation)
    * ``minimum`` / ``maximum`` (number/integer)
    * ``minLength`` / ``maxLength`` (string)
    * ``minItems`` / ``maxItems`` (array)

    Args:
        data: The JSON-deserialised value to validate.
        schema: A dict describing the expected shape (JSON Schema subset).

    Returns:
        ``(True, [])`` if valid, ``(False, list_of_error_strings)`` otherwise.
    """
    errors: list[str] = []
    _validate_value(data, schema, "root", errors)
    return len(errors) == 0, errors
