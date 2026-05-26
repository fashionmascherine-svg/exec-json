"""Minimal integration test for the exec-json MCP server.

Starts the server as a subprocess, sends an MCP ``initialize`` request
followed by a ``tools/call`` request, and verifies the structured response.
"""

from __future__ import annotations

import json
import sys
import subprocess
import time
import unittest
from pathlib import Path

# Ensure the package is importable from the parent directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestMcpServer(unittest.TestCase):
    """Verify that the MCP stdio server starts and responds correctly."""

    def _start_server(self) -> subprocess.Popen:
        """Start the MCP server as a subprocess."""
        proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "server.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return proc

    def _send_json(self, proc: subprocess.Popen, data: dict) -> None:
        """Write a JSON-RPC message to the server's stdin."""
        line = json.dumps(data) + "\n"
        proc.stdin.write(line)  # type: ignore[union-attr]
        proc.stdin.flush()  # type: ignore[union-attr]

    def _read_json(self, proc: subprocess.Popen, timeout: float = 5.0) -> dict:
        """Read a single JSON-RPC response from the server's stdout."""
        deadline = time.monotonic() + timeout
        buffer = ""
        while time.monotonic() < deadline:
            # Read whatever is available (non-blocking-ish via short sleep).
            char = proc.stdout.read(1)  # type: ignore[union-attr]
            if char:
                buffer += char
                if char == "\n":
                    # Try to parse the line as JSON.
                    stripped = buffer.strip()
                    if stripped:
                        try:
                            return json.loads(stripped)
                        except json.JSONDecodeError:
                            pass
                    buffer = ""
            else:
                time.sleep(0.05)
        raise TimeoutError(f"No JSON response received within {timeout}s")

    def test_initialize_and_tools_list(self) -> None:
        """Server should respond to initialize and expose the run_command tool."""
        proc = self._start_server()
        try:
            # 1. Initialize
            self._send_json(proc, {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            })
            resp = self._read_json(proc)
            self.assertEqual(resp.get("id"), 1)
            self.assertIn("result", resp)

            # 2. Send initialized notification
            self._send_json(proc, {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            })

            # 3. List tools
            self._send_json(proc, {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
            })
            resp2 = self._read_json(proc)
            self.assertEqual(resp2.get("id"), 2)
            tools = resp2.get("result", {}).get("tools", [])
            tool_names = [t["name"] for t in tools]
            self.assertIn("run_command", tool_names)

        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def test_run_command_tool_success(self) -> None:
        """Call run_command and verify it returns structured JSON."""
        proc = self._start_server()
        try:
            # Initialize
            self._send_json(proc, {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            })
            self._read_json(proc)
            self._send_json(proc, {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            })
            time.sleep(0.2)

            # Call run_command
            self._send_json(proc, {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "run_command",
                    "arguments": {
                        "cmd": "echo '{\"status\":\"ok\"}'",
                        "retries": 0,
                        "timeout": 10.0,
                    },
                },
            })
            resp = self._read_json(proc)
            self.assertEqual(resp.get("id"), 2)
            content = resp.get("result", {}).get("content", [])
            # The response content is a list of content items, each with "text"
            self.assertTrue(len(content) > 0)
            text = content[0].get("text", "")
            parsed = json.loads(text)
            self.assertTrue(parsed["success"])
            self.assertEqual(parsed["parsed_json"], {"status": "ok"})

        finally:
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
