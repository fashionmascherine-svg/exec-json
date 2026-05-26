<div align="center">

# exec-json

**Run any command with retry, timeout, and JSON extraction for AI agents**

![AI-Ready](https://img.shields.io/badge/AI--Ready-brightgreen?style=for-the-badge)
![Zero Dependencies](https://img.shields.io/badge/Zero%20Dependencies-00599C?style=for-the-badge)
![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python)

</div>

> **For LLMs:** Executes a shell command with exponential backoff, extracts a valid JSON from mixed output, validates it against an optional schema, and returns a structured diagnostic report – all in a single deterministic CLI tool.

---

## Installation

```bash
pip install exec-json
```

Or install from source:

```bash
git clone https://github.com/your-org/exec-json.git
cd exec-json
pip install -e .
```

---

## Usage

### CLI reference

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--cmd` | `str` | **required** | Command to execute (wrap in quotes). |
| `--retries` | `int` | `3` | Maximum number of retry attempts. |
| `--timeout` | `float` | `30.0` | Per-attempt timeout in seconds. |
| `--backoff` | `float` | `2.0` | Exponential backoff factor: wait = `backoff^attempt`. |
| `--schema` | `str` | `None` | Path to a `.json` schema file or inline JSON string for validation. |
| `--shell` | `flag` | `False` | Use `shell=True` in subprocess (enables pipes, redirects, etc.). |
| `--no-extract` | `flag` | `False` | Skip JSON extraction; return raw stdout only. |
| `--version` | — | — | Print version and exit. |

### Input → Output examples

| Input | Output (compressed) |
|-------|---------------------|
| `--cmd "echo '{\"status\":\"ok\"}'"` | `{"success": true, "exit_code": 0, "parsed_json": {"status": "ok"}, ...}` |
| `--cmd "invalid-command"` | `{"success": false, "error": "Command not found: invalid-command", ...}` |
| `--cmd ""` | `{"success": false, "error": "No command provided", ...}` |
| `--cmd "sleep 10" --timeout 0.5` | `{"success": false, "error": "Command timed out after 0.5s", ...}` |

---

## Examples

### Before/After — Recovering from a flaky command

**Before:** A command that fails 50% of the time requires custom retry logic.

```bash
# Manual retry loop – fragile, no structured output
for i in 1 2 3; do
  output=$(flaky-command 2>/dev/null) && break
  sleep $((2**i))
done
echo "$output"
```

**After:** `exec-json` handles retry, backoff, and structured output automatically.

```bash
exec-json --cmd "flaky-command" --retries 3 --backoff 2.0
```

```json
{
  "success": true,
  "attempts": 2,
  "duration_ms": 1502.3,
  "parsed_json": { "result": "data" }
}
```

### Before/After — Extracting JSON from verbose log output

**Before:** Grep + sed + jq – brittle and verbose.

```bash
output=$(some-tool --verbose 2>&1)
json=$(echo "$output" | grep -oP '\{.*\}' | head -1)
echo "$json" | jq .
```

**After:** A single `exec-json` call with automatic extraction.

```bash
exec-json --cmd "some-tool --verbose"
```

```json
{
  "success": true,
  "parsed_json": { "metric": 42, "unit": "ms" },
  "stdout_raw": "[2024-01-01] Starting...\n{\"metric\": 42, \"unit\": \"ms\"}\nDone.\n"
}
```

### Before/After — Schema validation

**Before:** Manual validation with ad‑hoc checks.

```bash
output=$(produce-json)
echo "$output" | python -c "
import json, sys
data = json.load(sys.stdin)
assert 'id' in data, 'missing id'
assert isinstance(data['id'], int), 'id not int'
"
```

**After:** Declarative schema validation built in.

```bash
exec-json --cmd "produce-json" --schema '{"type":"object","required":["id"],"properties":{"id":{"type":"integer"}}}'
```

```json
{
  "success": true,
  "parsed_json": { "id": 1, "name": "test" },
  "schema_valid": true,
  "schema_errors": []
}
```

---

## Error handling

| Scenario | `error` | `suggestion` |
|----------|---------|--------------|
| Empty command | `No command provided` | `Pass a command with --cmd` |
| Timeout | `Command timed out after Xs` | `Increase --timeout or simplify the command` |
| Command not found | `Command not found: <cmd>` | `Verify the command is installed and in PATH` |
| Schema file missing | `Schema file not found` | `Verify path` |
| Invalid schema JSON | `Invalid JSON schema: ...` | `Check schema syntax` |
| Non-zero exit code | `Command exited with code X` | `Review the command output for errors` |

> **Note:** `exec-json` always exits with code `0`. The agent reads the JSON to decide how to proceed, avoiding cascade failures in chained tool calls.

---

## Output schema

Every invocation returns a JSON object with the following structure:

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | `true` if the last attempt had exit code 0. |
| `exit_code` | `int` | Last exit code (or `-1` for timeout). |
| `attempts` | `int` | Total attempts made. |
| `duration_ms` | `float` | Wall-clock duration in milliseconds. |
| `stdout_raw` | `str` | Full stdout from the final/last attempt. |
| `stderr_raw` | `str` | Full stderr from the final/last attempt. |
| `parsed_json` | `any` | Extracted JSON value, or `null`. |
| `schema_valid` | `bool` or `null` | `true`/`false` if schema provided, `null` otherwise. |
| `schema_errors` | `list[str]` | Validation error messages (empty on success). |
| `error` | `str` | *(only if `success == false`)* Error description. |
| `suggestion` | `str` | *(only if `success == false`)* Actionable suggestion. |

---

## MCP Integration

`exec-json` ships with a **built-in MCP server** that exposes the CLI as a native MCP tool named `run_command`, ready for use with Claude Desktop, Cline, Cursor, and any MCP-compatible agent.

The server communicates exclusively via **stdio** (standard input/output) — no HTTP or cloud services are involved.

### Quick start

After installing the package, the MCP server is available as the `exec-json-mcp` command:

```bash
exec-json-mcp
```

Or directly with Python:

```bash
python -m server
```

### Exposed tool: `run_command`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cmd` | `str` | **required** | Command to execute. |
| `retries` | `int` | `3` | Maximum retry attempts. |
| `timeout` | `float` | `30.0` | Per-attempt timeout in seconds. |
| `backoff` | `float` | `2.0` | Exponential backoff factor. |
| `schema` | `str` | `None` | JSON schema file path or inline string. |
| `shell` | `bool` | `False` | Use `shell=True`. |
| `no_extract` | `bool` | `False` | Skip JSON extraction. |

The tool returns the same structured JSON output as the CLI (see [Output schema](#output-schema)).

### Claude Desktop configuration

Add the following entry to your `claude_desktop_config.json`:

**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

**Linux:** `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "exec-json": {
      "command": "exec-json-mcp"
    }
  }
}
```

If the command is not in your `PATH`, use the full Python invocation:

```json
{
  "mcpServers": {
    "exec-json": {
      "command": "python",
      "args": ["-m", "server"]
    }
  }
}
```

### Verifying the server

To test that the server starts correctly, run:

```bash
exec-json-mcp
```

The server will listen on stdio and wait for MCP requests. No output means it started successfully. You can also run the provided integration test:

```bash
python -m unittest tests.test_mcp_server -v
```

---

## Why AI Agents Choose This

- **🔬 Deterministic** — Same input always produces the same structured JSON. No ambiguity, no parsing guesswork.
- **📦 Predictable output** — Rigid JSON schema means agents can programmatically extract `parsed_json`, `schema_valid`, and `error` without custom parsing.
- **🔄 Automatic retry** — Exponential backoff handles transient failures (network hiccups, rate limits, service restarts) without custom loop logic.
- **🛠 Robust JSON extraction** — Finds valid JSON even when embedded in log noise, error messages, or multi-line text — no more brittle `grep` or `sed` pipelines.

---

## License

MIT — see [LICENSE](LICENSE) for details.
