# Contributing to exec-json

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing to `exec-json`.

## Code of Conduct

Please be respectful and constructive in all interactions. We strive to maintain a welcoming community for all contributors.

## Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-org/exec-json.git
   cd exec-json
   ```

2. **Create a virtual environment (recommended):**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   # or
   .venv\Scripts\activate     # Windows
   ```

3. **Install in editable mode:**
   ```bash
   pip install -e .
   ```

## Running Tests

All tests use the standard `unittest` framework — no external dependencies required.

```bash
# Run all tests
python -m unittest tests.test_core -v

# Run a specific test class
python -m unittest tests.test_core.TestExtractJson -v

# Run a specific test method
python -m unittest tests.test_core.TestExecute.test_timeout -v
```

## Code Style

- **Language:** All code, comments, and docstrings **must be in English**.
- **Python version:** 3.8+ compatible (no f-string debug expressions, no 3.10+ syntax).
- **Imports:** Standard library only — no external dependencies.
- **Docstrings:** Google style for all public functions and methods.
- **Type hints:** Required for all function signatures (use `from __future__ import annotations`).
- **Line length:** Aim for 88 characters (compatible with `black` defaults).

## Pull Request Process

1. Ensure all existing tests pass before submitting.
2. Add tests for any new functionality (we aim for at least 15 tests).
3. Update the `README.md` if the CLI interface or output schema changes.
4. Update the `plans/exec-json-plan.md` if the architecture changes.
5. Keep the diff focused — one feature/fix per PR.

## Project Structure

```
exec_json/
├── exec_json/
│   ├── __init__.py          # Package metadata and version
│   ├── __main__.py          # CLI entry point (argparse)
│   ├── core.py              # Core execution logic
│   └── utils.py             # JSON extraction and schema validation utilities
├── tests/
│   └── test_core.py         # Unit tests (unittest)
├── plans/
│   └── exec-json-plan.md    # Architecture and development plan
├── .gitignore
├── CONTRIBUTING.md
├── pyproject.toml
└── README.md
```

## Design Principles

- **Zero dependencies** — the tool must work with only the Python standard library.
- **Deterministic output** — same input always produces the same structured JSON.
- **Robust extraction** — JSON can be embedded in noisy text, log output, or error messages.
- **Always exit 0** — the calling agent reads the JSON to decide how to proceed, preventing cascade failures.
- **Backward compatibility** — never change the output schema without a major version bump.

## Reporting Issues

When reporting a bug, include:

- The exact `exec-json` command you ran.
- The full output (redact sensitive information).
- Expected vs. actual behavior.
- Python version (`python --version`).
- Operating system.

---

**Thank you for helping make `exec-json` better!** 🚀
