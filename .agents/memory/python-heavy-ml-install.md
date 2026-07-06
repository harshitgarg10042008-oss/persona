---
name: Python heavy ML dependency installs
description: How to reliably install large ML packages (torch, mediapipe, transformers, whisper) for a Python project with no pre-existing pyproject.toml
---

The `installLanguagePackages` code-execution callback threw an opaque `Failed to install packages:` error with no detail when the project had no `pyproject.toml` yet, and continued failing even after retries.

**Why:** The Python package tooling on Replit expects a uv-managed project (`pyproject.toml` + `UV_PROJECT_ENVIRONMENT=.pythonlibs`). A bare repo cloned from GitHub with only a `requirements.txt` doesn't have this, so the installer tool's project detection silently breaks.

**How to apply:** If `installLanguagePackages` fails immediately with no useful error message on a freshly imported repo:
1. Run `uv init --no-readme --no-workspace` in the project root to create a minimal `pyproject.toml`, then delete the placeholder `main.py` it generates.
2. Add dependencies directly to `pyproject.toml` and run `uv sync` (as a detached background process via `setsid nohup ... &`, since large packages like torch can take minutes and the interactive bash tool has a ~2 min timeout).
3. Packages install into `.pythonlibs/` (per `UV_PROJECT_ENVIRONMENT` env var), not `.venv/`. Add `.pythonlibs/` and `uv.lock` to `.gitignore`.
4. Long-running Django management commands (migrate, check) can also exceed the bash tool's default timeout on first run due to heavy imports (torch/transformers) — redirect output to a file and use `timeout N ... > file 2>&1` rather than piping directly, and re-read the file afterward if the tool call itself reports a spurious non-zero/-1 exit.
