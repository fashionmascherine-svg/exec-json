"""Unit tests for exec-json.

Covers extraction, validation, execution logic, and CLI integration.
Uses only the standard library (unittest, json, subprocess).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

# Ensure the package is importable from the parent directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exec_json.core import execute
from exec_json.utils import extract_json, validate_schema


# ======================================================================
# Tests for utils.extract_json
# ======================================================================

class TestExtractJson(unittest.TestCase):
    """Test the JSON extraction logic."""

    def test_extract_simple_object(self) -> None:
        """Extract a plain JSON object from pure JSON text."""
        text = '{"name": "test", "value": 42}'
        result, error = extract_json(text)
        self.assertIsNone(error)
        self.assertEqual(result, {"name": "test", "value": 42})

    def test_extract_array(self) -> None:
        """Extract a JSON array."""
        text = '[1, 2, 3]'
        result, error = extract_json(text)
        self.assertIsNone(error)
        self.assertEqual(result, [1, 2, 3])

    def test_extract_json_embedded_in_text(self) -> None:
        """Extract JSON embedded in surrounding text/log output."""
        text = (
            "2024-01-01 INFO Starting process...\n"
            'Processing result: {"status": "ok", "count": 5}\n'
            "Done.\n"
        )
        result, error = extract_json(text)
        self.assertIsNone(error)
        self.assertEqual(result, {"status": "ok", "count": 5})

    def test_extract_nested_json(self) -> None:
        """Extract deeply nested JSON with strings containing braces."""
        text = """{
            "level1": {
                "level2": [
                    {"name": "item1", "data": "{}"},
                    {"name": "item2", "data": "[]"}
                ],
                "escaped": "quoted \\" brace { here",
                "empty_obj": {}
            }
        }"""
        result, error = extract_json(text)
        self.assertIsNone(error)
        self.assertIsInstance(result, dict)
        self.assertIn("level1", result)
        self.assertEqual(
            result["level1"]["level2"][0]["data"], "{}"
        )

    def test_extract_no_braces(self) -> None:
        """Return None when text has no JSON brackets."""
        text = "just some plain text without json"
        result, error = extract_json(text)
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertIn("No JSON", error)

    def test_extract_unbalanced_brackets(self) -> None:
        """Return None for unbalanced brackets."""
        text = '{"key": "value"'
        result, error = extract_json(text)
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertIn("Unbalanced", error)

    def test_extract_empty_string(self) -> None:
        """Return None for empty input."""
        result, error = extract_json("")
        self.assertIsNone(result)
        self.assertIsNotNone(error)

    def test_extract_two_jsons_only_first(self) -> None:
        """Only the first JSON should be extracted."""
        text = '{"first": 1} some text {"second": 2}'
        result, error = extract_json(text)
        self.assertIsNone(error)
        self.assertEqual(result, {"first": 1})

    def test_extract_with_escaped_quotes(self) -> None:
        """Handle escaped quotes inside JSON strings."""
        text = '{"message": "He said \\"hello\\""}'
        result, error = extract_json(text)
        self.assertIsNone(error)
        self.assertEqual(result["message"], 'He said "hello"')


# ======================================================================
# Tests for utils.validate_schema
# ======================================================================

class TestValidateSchema(unittest.TestCase):
    """Test the hand-written JSON schema validator."""

    def test_validate_type_string(self) -> None:
        """Validate a string value against type: 'string'."""
        valid, errors = validate_schema("hello", {"type": "string"})
        self.assertTrue(valid)
        self.assertEqual(errors, [])

    def test_validate_type_integer(self) -> None:
        """Validate an integer value against type: 'integer'."""
        valid, errors = validate_schema(42, {"type": "integer"})
        self.assertTrue(valid)
        self.assertEqual(errors, [])

    def test_validate_type_wrong(self) -> None:
        """Report error when the type does not match."""
        valid, errors = validate_schema("hello", {"type": "integer"})
        self.assertFalse(valid)
        self.assertTrue(any("integer" in e for e in errors))

    def test_validate_required_fields(self) -> None:
        """Report missing required fields on an object."""
        schema = {
            "type": "object",
            "required": ["name", "version"],
            "properties": {
                "name": {"type": "string"},
                "version": {"type": "integer"},
            },
        }
        data = {"name": "test"}
        valid, errors = validate_schema(data, schema)
        self.assertFalse(valid)
        self.assertTrue(any("version" in e for e in errors))

    def test_validate_properties_nested(self) -> None:
        """Validate nested object properties."""
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                    },
                },
            },
        }
        data = {"user": {"id": 1, "name": "Alice"}}
        valid, errors = validate_schema(data, schema)
        self.assertTrue(valid)
        self.assertEqual(errors, [])

    def test_validate_array_items(self) -> None:
        """Validate items in an array."""
        schema = {
            "type": "array",
            "items": {"type": "integer"},
        }
        data = [1, 2, 3]
        valid, errors = validate_schema(data, schema)
        self.assertTrue(valid)
        self.assertEqual(errors, [])

    def test_validate_array_item_type_mismatch(self) -> None:
        """Report type mismatch in array items."""
        schema = {
            "type": "array",
            "items": {"type": "integer"},
        }
        data = [1, "two", 3]
        valid, errors = validate_schema(data, schema)
        self.assertFalse(valid)
        # Should have at least one error about the string element.
        self.assertTrue(any("string" in e for e in errors))

    def test_validate_enum(self) -> None:
        """Validate enum values."""
        schema = {"type": "string", "enum": ["red", "green", "blue"]}
        valid, errors = validate_schema("red", schema)
        self.assertTrue(valid)
        valid, errors = validate_schema("yellow", schema)
        self.assertFalse(valid)

    def test_validate_minimum_maximum(self) -> None:
        """Validate numeric boundaries."""
        schema = {"type": "integer", "minimum": 1, "maximum": 10}
        self.assertTrue(validate_schema(5, schema)[0])
        self.assertFalse(validate_schema(0, schema)[0])
        self.assertFalse(validate_schema(11, schema)[0])

    def test_validate_min_length_max_length(self) -> None:
        """Validate string length boundaries."""
        schema = {"type": "string", "minLength": 2, "maxLength": 5}
        self.assertTrue(validate_schema("abc", schema)[0])
        self.assertFalse(validate_schema("a", schema)[0])
        self.assertFalse(validate_schema("abcdef", schema)[0])

    def test_validate_min_items_max_items(self) -> None:
        """Validate array length boundaries."""
        schema = {"type": "array", "minItems": 1, "maxItems": 3}
        self.assertTrue(validate_schema([1], schema)[0])
        self.assertTrue(validate_schema([1, 2, 3], schema)[0])
        self.assertFalse(validate_schema([], schema)[0])
        self.assertFalse(validate_schema([1, 2, 3, 4], schema)[0])


# ======================================================================
# Tests for core.execute
# ======================================================================

class TestExecute(unittest.TestCase):
    """Test the core :func:`execute` function with real subprocess calls."""

    # ------------------------------------------------------------------
    #  Helper
    # ------------------------------------------------------------------
    def _python_cmd(self, code: str) -> str:
        """Wrap Python code in a command string that prints JSON.

        Args:
            code: Python expression that evaluates to a JSON-serialisable value.

        Returns:
            A shell command string.
        """
        return f'{sys.executable} -c "import json; print(json.dumps({code}))"'

    @staticmethod
    def _failing_cmd(exit_code: int = 1) -> str:
        """Return a command that always fails."""
        return f"{sys.executable} -c 'import sys; sys.exit({exit_code})'"

    # ------------------------------------------------------------------
    #  Tests
    # ------------------------------------------------------------------
    def test_success_simple(self) -> None:
        """A command that succeeds and outputs JSON."""
        script = "import json; print(json.dumps({'key': 'value'}))\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_path = f.name
        try:
            cmd = f"{sys.executable} {script_path}"
            result = execute(cmd, retries=0)
            self.assertTrue(result["success"])
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(result["parsed_json"], {"key": "value"})
        finally:
            os.unlink(script_path)

    def test_success_with_json_in_text(self) -> None:
        """Extract JSON from multi-line text output."""
        script = (
            "import sys\n"
            'sys.stdout.write("Processing...\\n")\n'
            'import json\n'
            'sys.stdout.write(json.dumps({"status": "ok"}) + "\\n")\n'
            'sys.stdout.write("Done.\\n")\n'
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_path = f.name
        try:
            cmd = f"{sys.executable} {script_path}"
            result = execute(cmd, retries=0)
            self.assertTrue(result["success"])
            self.assertEqual(result["parsed_json"], {"status": "ok"})
        finally:
            os.unlink(script_path)

    def test_retry_eventual_success(self) -> None:
        """Command fails first time, then succeeds on retry."""
        # Create a script that fails on first invocation but succeeds after.
        script = (
            "import os, sys\n"
            "flag_file = sys.argv[1]\n"
            "if os.path.exists(flag_file):\n"
            "    print('{\"status\": \"ok\"}')\n"
            "    sys.exit(0)\n"
            "else:\n"
            "    # Create flag so next invocation succeeds\n"
            "    open(flag_file, 'w').close()\n"
            "    sys.exit(1)\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_path = f.name

        flag_file = tempfile.mktemp(suffix=".flag")
        try:
            cmd = f"{sys.executable} {script_path} {flag_file}"
            result = execute(cmd, retries=2, backoff=0.1)
            self.assertTrue(result["success"])
            self.assertEqual(result["parsed_json"], {"status": "ok"})
            self.assertGreater(result["attempts"], 1)
        finally:
            os.unlink(script_path)
            if os.path.exists(flag_file):
                os.unlink(flag_file)

    def test_max_retries_exhausted(self) -> None:
        """Command fails every time, all retries exhausted."""
        cmd = self._failing_cmd(1)
        result = execute(cmd, retries=2, backoff=0.1)
        self.assertFalse(result["success"])
        self.assertNotEqual(result["exit_code"], 0)
        self.assertEqual(result["attempts"], 3)  # initial + 2 retries

    def test_timeout(self) -> None:
        """Command that times out."""
        cmd = f"{sys.executable} -c 'import time; time.sleep(10)'"
        result = execute(cmd, retries=0, timeout=0.5)
        self.assertFalse(result["success"])
        self.assertIn("timed out", result["error"].lower())

    def test_empty_command(self) -> None:
        """Empty command returns structured error."""
        result = execute("", retries=0)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "No command provided")

    def test_command_not_found(self) -> None:
        """Non-existent command returns structured error."""
        result = execute("nonexistent_command_xyz123", retries=0)
        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"].lower())

    def test_schema_validation_pass(self) -> None:
        """JSON passes schema validation."""
        script = "import json; print(json.dumps({'name': 'test', 'count': 42}))\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_path = f.name
        try:
            cmd = f"{sys.executable} {script_path}"
            result = execute(
                cmd,
                retries=0,
                schema='{"type": "object", "required": ["name", "count"]}',
            )
            self.assertTrue(result["schema_valid"])
            self.assertEqual(result["schema_errors"], [])
        finally:
            os.unlink(script_path)

    def test_schema_validation_fail(self) -> None:
        """JSON fails schema validation (missing required field)."""
        script = "import json; print(json.dumps({'name': 'test'}))\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_path = f.name
        try:
            cmd = f"{sys.executable} {script_path}"
            result = execute(
                cmd,
                retries=0,
                schema='{"type": "object", "required": ["name", "count"]}',
            )
            self.assertFalse(result["schema_valid"])
            self.assertTrue(len(result["schema_errors"]) > 0)
        finally:
            os.unlink(script_path)

    def test_schema_file_not_found(self) -> None:
        """Nonexistent schema file returns error."""
        script = "import json; print(json.dumps({'key': 'value'}))\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_path = f.name
        try:
            cmd = f"{sys.executable} {script_path}"
            result = execute(
                cmd,
                retries=0,
                schema="/nonexistent/path/schema.json",
            )
            self.assertFalse(result["success"])
            self.assertIn("Schema file not found", result["error"])
        finally:
            os.unlink(script_path)

    def test_schema_invalid_json(self) -> None:
        """Malformed schema string returns error."""
        script = "import json; print(json.dumps({'key': 'value'}))\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_path = f.name
        try:
            cmd = f"{sys.executable} {script_path}"
            result = execute(
                cmd,
                retries=0,
                schema="{invalid json!!!",
            )
            self.assertFalse(result["success"])
            self.assertIn("Invalid JSON schema", result["error"])
        finally:
            os.unlink(script_path)

    def test_no_extract_flag(self) -> None:
        """With --no-extract, parsed_json is None but stdout_raw is present."""
        script = "import json; print(json.dumps({'key': 'value'}))\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_path = f.name
        try:
            cmd = f"{sys.executable} {script_path}"
            result = execute(cmd, retries=0, no_extract=True)
            self.assertTrue(result["success"])
            self.assertIsNone(result["parsed_json"])
            self.assertIn("key", result["stdout_raw"])
        finally:
            os.unlink(script_path)

    def test_shell_true(self) -> None:
        """Shell=True works with shell builtins (echo)."""
        result = execute(
            'echo \'{"hello": "world"}\'', retries=0, shell=True
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["parsed_json"], {"hello": "world"})

    def test_stdout_without_json(self) -> None:
        """When stdout has no JSON, parsed_json is None."""
        script = "print('just text')\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_path = f.name
        try:
            cmd = f"{sys.executable} {script_path}"
            result = execute(cmd, retries=0)
            self.assertTrue(result["success"])
            self.assertIsNone(result["parsed_json"])
        finally:
            os.unlink(script_path)

    def test_stderr_captured(self) -> None:
        """Stderr is captured even on success."""
        script = (
            "import sys\n"
            'sys.stderr.write("warning: something\\n")\n'
            'import json\n'
            'sys.stdout.write(json.dumps({"ok": True}) + "\\n")\n'
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_path = f.name
        try:
            cmd = f"{sys.executable} {script_path}"
            result = execute(cmd, retries=0)
            self.assertTrue(result["success"])
            self.assertIn("warning", result["stderr_raw"])
        finally:
            os.unlink(script_path)

    def test_duration_ms_is_positive(self) -> None:
        """duration_ms should be positive after execution."""
        script = "import json; print(json.dumps({'a': 1}))\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_path = f.name
        try:
            cmd = f"{sys.executable} {script_path}"
            result = execute(cmd, retries=0)
            self.assertGreater(result["duration_ms"], 0)
        finally:
            os.unlink(script_path)

    def test_retry_with_backoff_positive(self) -> None:
        """Retry with backoff: duration should be at least the sleep time."""
        cmd = self._failing_cmd(1)
        start = time.monotonic()
        result = execute(cmd, retries=1, backoff=0.5)
        elapsed = time.monotonic() - start
        self.assertFalse(result["success"])
        # The wait should be at least backoff**0 = 0.5 for the first retry.
        self.assertGreaterEqual(elapsed, 0.4)  # allow a little slack

    def test_output_schema_structure(self) -> None:
        """Verify result dict contains all expected keys."""
        script = "import json; print(json.dumps({'x': 1}))\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_path = f.name
        try:
            cmd = f"{sys.executable} {script_path}"
            result = execute(cmd, retries=0)
            expected_keys = {
                "success", "exit_code", "attempts", "duration_ms",
                "stdout_raw", "stderr_raw", "parsed_json", "schema_valid",
                "schema_errors",
            }
            self.assertTrue(expected_keys.issubset(result.keys()))
        finally:
            os.unlink(script_path)


# ======================================================================
# Tests for CLI integration (through __main__.py)
# ======================================================================

class TestMainCli(unittest.TestCase):
    """Test the CLI entry point via subprocess."""

    def test_cli_help(self) -> None:
        """--help should exit with 0 and contain usage info."""
        proc = subprocess.run(
            [sys.executable, "-m", "exec_json", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("usage", proc.stdout.lower())

    def test_cli_version(self) -> None:
        """--version should print the version string."""
        proc = subprocess.run(
            [sys.executable, "-m", "exec_json", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("1.0.0", proc.stdout)

    def test_cli_success(self) -> None:
        """CLI produces valid JSON output on success."""
        script = "import json; print(json.dumps({'a': 1}))\n"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_path = f.name
        try:
            cmd = f"{sys.executable} {script_path}"
            proc = subprocess.run(
                [sys.executable, "-m", "exec_json", "--cmd", cmd, "--retries", "0"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 0)
            output = json.loads(proc.stdout)
            self.assertTrue(output["success"])
            self.assertEqual(output["parsed_json"], {"a": 1})
        finally:
            os.unlink(script_path)

    def test_cli_error_always_exit_zero(self) -> None:
        """Even on failure, CLI exits with code 0."""
        proc = subprocess.run(
            [
                sys.executable, "-m", "exec_json",
                "--cmd", "",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0)
        output = json.loads(proc.stdout)
        self.assertFalse(output["success"])


# ======================================================================
# Entry point
# ======================================================================
if __name__ == "__main__":
    unittest.main()
