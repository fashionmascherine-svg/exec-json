#!/usr/bin/env python3
"""MCP server for exec-json.

Exposes the ``exec-json`` CLI as a Model Context Protocol (MCP) tool
named ``run_command``, communicating via stdio for local AI agents
(Claude Desktop, Cline, Cursor, etc.).

Usage (after installing the package)::

    exec-json-mcp

Or directly with Python::

    python -m server

The server registers a single tool:

- **run_command** — mirrors the CLI arguments (``cmd``, ``retries``,
  ``timeout``, ``backoff``, ``schema``, ``shell``, ``no_extract``) and
  returns the same structured JSON that ``exec-json`` produces.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "exec-json",
    instructions=(
        "Executes a shell command with exponential backoff, extracts a valid "
        "JSON from mixed output, validates it against an optional schema, and "
        "returns a structured diagnostic report."
    ),
)


# ---------------------------------------------------------------------------
# Tool: run_command
# ---------------------------------------------------------------------------


@mcp.tool(
    name="run_command",
    description=(
        "Run a shell command with retry, timeout, JSON extraction, and "
        "optional schema validation. Returns a structured JSON diagnostic "
        "report."
    ),
)
def run_command(
    cmd: str,
    retries: int = 3,
    timeout: float = 30.0,
    backoff: float = 2.0,
    schema: str | None = None,
    shell: bool = False,
    no_extract: bool = False,
) -> dict[str, Any]:
    """Execute a command and return the structured JSON result.

    Args:
        cmd: The command to execute (required).
        retries: Maximum number of retry attempts (default 3).
        timeout: Per-attempt timeout in seconds (default 30).
        backoff: Exponential backoff base (default 2.0).
        schema: Path to a ``.json`` schema file or inline JSON string.
        shell: Whether to use ``shell=True`` (default False).
        no_extract: Skip JSON extraction (default False).

    Returns:
        A dict with the same structure as the ``exec-json`` CLI output.
    """
    # Build the argument list for the subprocess call.
    args: list[str] = [
        sys.executable,
        "-m",
        "exec_json",
        "--cmd",
        cmd,
        "--retries",
        str(retries),
        "--timeout",
        str(timeout),
        "--backoff",
        str(backoff),
    ]

    if schema is not None:
        args.extend(["--schema", schema])

    if shell:
        args.append("--shell")

    if no_extract:
        args.append("--no-extract")

    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout + 10.0,  # allow a little overhead for the subprocess
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "exit_code": -1,
            "attempts": 1,
            "duration_ms": timeout * 1000,
            "stdout_raw": "",
            "stderr_raw": "",
            "parsed_json": None,
            "schema_valid": None,
            "schema_errors": [],
            "error": f"MCP tool timed out after {timeout}s",
            "suggestion": "Increase --timeout or simplify the command",
        }
    except Exception as exc:  # pylint: disable=broad-except
        return {
            "success": False,
            "exit_code": -1,
            "attempts": 1,
            "duration_ms": 0.0,
            "stdout_raw": "",
            "stderr_raw": str(exc),
            "parsed_json": None,
            "schema_valid": None,
            "schema_errors": [],
            "error": f"MCP internal error: {exc}",
            "suggestion": "Check the command syntax and environment",
        }

    # Parse the JSON output from the subprocess.
    if proc.returncode != 0:
        # Even if the subprocess failed, it should have printed valid JSON
        # (the CLI always exits 0).  Try to parse it anyway.
        pass

    try:
        result: dict[str, Any] = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        result = {
            "success": False,
            "exit_code": proc.returncode,
            "attempts": 1,
            "duration_ms": 0.0,
            "stdout_raw": proc.stdout,
            "stderr_raw": proc.stderr,
            "parsed_json": None,
            "schema_valid": None,
            "schema_errors": [],
            "error": "MCP: failed to parse exec-json output",
            "suggestion": "Check that exec-json is installed correctly",
        }

    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the MCP stdio server.

    This is registered as the ``exec-json-mcp`` console script entry point.
    """
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
