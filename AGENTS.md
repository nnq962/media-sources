# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project

`media-sources` is a Python 3.10+ project managed with [uv](https://github.com/astral-sh/uv). The project is in its initial state with no external dependencies yet.

## Commands

```bash
# Install dependencies / sync environment
uv sync

# Run the project
uv run python main.py

# Add a dependency
uv add <package>

# Run a script or tool within the venv
uv run <command>
```

There are no tests, linter, or formatter configured yet. When adding them, prefer `pytest` for tests and `ruff` for linting/formatting (common defaults for uv-based projects).
