"""Core execution logic for exec-json.

Provides the :func:`execute` function that runs a command with retry logic,
extracts the first valid JSON from stdout, validates it against an optional
schema, and returns a structured diagnostic dict.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from exec_json.utils import extract_json, validate_schema


def _load_schema(schema_arg: str | None) -> dict[str, Any] | None:
    """Load a JSON schema from a file path or inline JSON string.

    Args:
        schema_arg: A file path ending with ``.json``, or an inline JSON
            string.  ``None`` means no schema.

    Returns:
        The parsed schema dict, or ``None``.

    Raises:
        FileNotFoundError: If *schema_arg* looks like a path but does not
            exist.
        json.JSONDecodeError: If the schema content is not valid JSON.
    """
    if schema_arg is None:
        return None

    # Treat as file if it looks like a path (contains path separators or
    # ends with .json, or the file actually exists).
    is_path: bool = (
        "/" in schema_arg
        or "\\" in schema_arg
        or schema_arg.endswith(".json")
        or os.path.isfile(schema_arg)
    )

    if is_path:
        path = Path(schema_arg)
        if not path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_arg}")
        return json.loads(path.read_text(encoding="utf-8"))
    else:
        return json.loads(schema_arg)


def execute(
    cmd: str,
    retries: int = 3,
    timeout: float = 30.0,
    backoff: float = 2.0,
    schema: str | None = None,
    shell: bool = False,
    no_extract: bool = False,
) -> dict[str, Any]:
    """Execute *cmd* with retry logic and optional JSON extraction/validation.

    Implements the deterministic algorithm:

    1. If *cmd* is empty, immediately return an error result.
    2. For ``i`` in ``0..retries``:
       - Run the command via ``subprocess.run``.
       - If exit code is 0 and it's not the last attempt, break (success).
       - Otherwise wait ``backoff ** i`` seconds and retry.
    3. Collect stdout and stderr of the final (or first successful) attempt.
    4. If ``no_extract`` is False, attempt JSON extraction from stdout.
    5. If a *schema* is provided, validate the extracted JSON.
    6. Build and return the result dict.

    Args:
        cmd: The shell command to execute (required).
        retries: Maximum number of retry attempts (default 3).
        timeout: Per-attempt timeout in seconds (default 30).
        backoff: Exponential backoff base — wait = ``backoff ** attempt``
            seconds (default 2.0).
        schema: Path to a ``.json`` schema file or inline JSON schema string.
        shell: Whether to use ``shell=True`` in ``subprocess``.
        no_extract: If True, skip JSON extraction entirely.

    Returns:
        A dict following the rigid output schema:

        .. code-block:: json

            {
              "success": true|false,
              "exit_code": 0,
              "attempts": 2,
              "duration_ms": 1234,
              "stdout_raw": "...",
              "stderr_raw": "...",
              "parsed_json": null|{...},
              "schema_valid": true|false|null,
              "schema_errors": [...],
              "error": "...",        // only if success == false
              "suggestion": "..."    // only if success == false
            }
    """
    start_time: float = time.monotonic()

    # ------------------------------------------------------------------
    # 1. Empty command guard
    # ------------------------------------------------------------------
    if not cmd or not cmd.strip():
        return _error_result(
            exit_code=1,
            attempts=0,
            duration_ms=0.0,
            stdout_raw="",
            stderr_raw="",
            error="No command provided",
            suggestion="Pass a command with --cmd",
        )

    # ------------------------------------------------------------------
    # 2. Load schema (early exit on invalid schema)
    # ------------------------------------------------------------------
    parsed_schema: dict[str, Any] | None = None
    if schema is not None:
        try:
            parsed_schema = _load_schema(schema)
        except FileNotFoundError:
            return _error_result(
                exit_code=1,
                attempts=0,
                duration_ms=(time.monotonic() - start_time) * 1000,
                stdout_raw="",
                stderr_raw="",
                error="Schema file not found",
                suggestion=f"Verify path: {schema}",
            )
        except json.JSONDecodeError as exc:
            return _error_result(
                exit_code=1,
                attempts=0,
                duration_ms=(time.monotonic() - start_time) * 1000,
                stdout_raw="",
                stderr_raw="",
                error=f"Invalid JSON schema: {exc}",
                suggestion="Check schema syntax",
            )

    # ------------------------------------------------------------------
    # 3. Execution loop with retry
    # ------------------------------------------------------------------
    last_stdout: str = ""
    last_stderr: str = ""
    last_exit_code: int = -1
    attempt_count: int = 0
    success: bool = False

    # Pre-process command: if shell=False, split the string into a list
    # of arguments so subprocess.run can find the executable correctly.
    if shell:
        cmd_args: str | list[str] = cmd
    else:
        try:
            cmd_args = shlex.split(cmd)
        except ValueError as exc:
            return _error_result(
                exit_code=1,
                attempts=0,
                duration_ms=(time.monotonic() - start_time) * 1000,
                stdout_raw="",
                stderr_raw="",
                error=f"Invalid command syntax: {exc}",
                suggestion="Check the command for unbalanced quotes or special characters",
            )

    for i in range(retries + 1):
        attempt_count = i + 1
        try:
            proc = subprocess.run(
                cmd_args,  # type: ignore[arg-type]
                capture_output=True,
                text=True,
                timeout=timeout if timeout > 0 else None,
                shell=shell,
            )
            last_stdout = proc.stdout
            last_stderr = proc.stderr
            last_exit_code = proc.returncode

            if proc.returncode == 0 and i < retries:
                success = True
                break  # early success (not the last allowed attempt)

            if proc.returncode == 0:
                success = True
                # Last attempt succeeded – that's fine.
                break

        except subprocess.TimeoutExpired as exc:
            last_stdout = exc.stdout if exc.stdout else ""
            last_stderr = exc.stderr if exc.stderr else ""
            last_exit_code = -1
            # If we still have retries left, continue; otherwise break.
            if i >= retries:
                success = False
                break
            continue

        except (FileNotFoundError, OSError):
            return _error_result(
                exit_code=127,
                attempts=attempt_count,
                duration_ms=(time.monotonic() - start_time) * 1000,
                stdout_raw="",
                stderr_raw="",
                error=f"Command not found: {cmd}",
                suggestion="Verify the command is installed and in PATH",
            )

        except Exception as exc:  # pylint: disable=broad-except
            return _error_result(
                exit_code=1,
                attempts=attempt_count,
                duration_ms=(time.monotonic() - start_time) * 1000,
                stdout_raw="",
                stderr_raw=str(exc),
                error=f"Unexpected error: {exc}",
                suggestion="Check the command syntax and environment",
            )

        # If we got here and exit_code != 0 and it's not the last attempt,
        # wait and retry.
        if last_exit_code != 0 and i < retries:
            sleep_sec: float = backoff**i
            time.sleep(sleep_sec)

    elapsed_ms: float = (time.monotonic() - start_time) * 1000

    # ------------------------------------------------------------------
    # 4. JSON extraction
    # ------------------------------------------------------------------
    parsed_json: Any = None
    if not no_extract and last_stdout:
        parsed_json, _ = extract_json(last_stdout)

    # ------------------------------------------------------------------
    # 5. Schema validation
    # ------------------------------------------------------------------
    schema_valid: bool | None = None
    schema_errors: list[str] = []

    if parsed_schema is not None and parsed_json is not None:
        ok, errs = validate_schema(parsed_json, parsed_schema)
        schema_valid = ok
        schema_errors = errs
    elif parsed_schema is not None and parsed_json is None:
        # Nothing to validate – schema_valid stays None for "no data",
        # but we can still report it as null.
        schema_valid = None
        schema_errors = ["No parsed JSON to validate"]

    # ------------------------------------------------------------------
    # 6. Build result
    # ------------------------------------------------------------------
    if success:
        result: dict[str, Any] = {
            "success": True,
            "exit_code": last_exit_code,
            "attempts": attempt_count,
            "duration_ms": round(elapsed_ms, 1),
            "stdout_raw": last_stdout,
            "stderr_raw": last_stderr,
            "parsed_json": parsed_json,
            "schema_valid": schema_valid,
            "schema_errors": schema_errors,
        }
    else:
        # Determine error message for non-zero exit or timeout.
        if last_exit_code == -1:
            # Timeout case
            error_msg = f"Command timed out after {timeout}s"
            suggestion_msg = "Increase --timeout or simplify the command"
        elif last_exit_code == 127:
            # Already handled above, but just in case.
            error_msg = f"Command not found: {cmd}"
            suggestion_msg = "Verify the command is installed and in PATH"
        else:
            error_msg = (
                f"Command exited with code {last_exit_code}"
            )
            suggestion_msg = "Review the command output for errors"

        result = {
            "success": False,
            "exit_code": last_exit_code,
            "attempts": attempt_count,
            "duration_ms": round(elapsed_ms, 1),
            "stdout_raw": last_stdout,
            "stderr_raw": last_stderr,
            "parsed_json": parsed_json,
            "schema_valid": schema_valid,
            "schema_errors": schema_errors,
            "error": error_msg,
            "suggestion": suggestion_msg,
        }

    return result


def _error_result(
    exit_code: int,
    attempts: int,
    duration_ms: float,
    stdout_raw: str,
    stderr_raw: str,
    error: str,
    suggestion: str,
) -> dict[str, Any]:
    """Build an error result dict with uniform structure.

    Args:
        exit_code: Process exit code (or synthetic).
        attempts: Number of attempts made.
        duration_ms: Wall-clock duration in milliseconds.
        stdout_raw: Captured stdout.
        stderr_raw: Captured stderr.
        error: Human-readable error description.
        suggestion: Actionable suggestion for the caller.

    Returns:
        Dict following the rigid output schema with ``success: false``.
    """
    return {
        "success": False,
        "exit_code": exit_code,
        "attempts": attempts,
        "duration_ms": round(duration_ms, 1),
        "stdout_raw": stdout_raw,
        "stderr_raw": stderr_raw,
        "parsed_json": None,
        "schema_valid": None,
        "schema_errors": [],
        "error": error,
        "suggestion": suggestion,
    }
