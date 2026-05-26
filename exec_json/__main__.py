#!/usr/bin/env python3
"""CLI entry point for exec-json.

Parses command-line arguments and delegates to :func:`exec_json.core.execute`.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from exec_json import __version__
from exec_json.core import execute


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Parsed namespace with command, retries, timeout, backoff, schema,
        shell, and no_extract.
    """
    parser = argparse.ArgumentParser(
        prog="exec-json",
        description=(
            "Execute a command with retry, timeout, and automatic JSON "
            "extraction from mixed output. Returns a structured JSON report "
            "suitable for AI agent consumption."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--cmd",
        required=True,
        type=str,
        help="Command to execute (wrap in quotes).",
    )
    parser.add_argument(
        "--retries",
        default=3,
        type=int,
        help="Maximum number of retry attempts (default: 3).",
    )
    parser.add_argument(
        "--timeout",
        default=30.0,
        type=float,
        help="Timeout per attempt in seconds (default: 30).",
    )
    parser.add_argument(
        "--backoff",
        default=2.0,
        type=float,
        help="Exponential backoff factor: wait = backoff**attempt (default: 2.0).",
    )
    parser.add_argument(
        "--schema",
        default=None,
        type=str,
        help=(
            "Path to a JSON schema file or inline JSON string for validation."
        ),
    )
    parser.add_argument(
        "--shell",
        action="store_true",
        default=False,
        help="Use shell=True when executing the command.",
    )
    parser.add_argument(
        "--no-extract",
        action="store_true",
        default=False,
        help="Skip JSON extraction; return raw stdout only.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point.

    Parses arguments, calls :func:`~exec_json.core.execute`, and prints
    the resulting JSON to stdout. Always exits with code 0.

    Args:
        argv: Optional argument list (for testing).
    """
    args = _parse_args(argv)

    result: dict[str, Any] = execute(
        cmd=args.cmd,
        retries=args.retries,
        timeout=args.timeout,
        backoff=args.backoff,
        schema=args.schema,
        shell=args.shell,
        no_extract=args.no_extract,
    )

    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
