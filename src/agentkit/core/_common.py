"""Repository root detection and shared file utilities."""
from __future__ import annotations

import os
from pathlib import Path


def repo_root(
    *,
    marker: str = "pyproject.toml",
    env_var: str = "REPO_ROOT",
    start: Path | None = None,
) -> Path:
    """Find the repository root directory.

    Resolution order:
    1. ``$REPO_ROOT`` environment variable (or *env_var*)
    2. Walk up from *start* (defaults to CWD) looking for *marker*
    3. Walk up from this file's location looking for *marker*
    4. Raise FileNotFoundError
    """
    env_val = os.environ.get(env_var, "").strip()
    if env_val:
        return Path(env_val).expanduser().resolve()

    search = start.resolve() if start else Path.cwd()
    for ancestor in [search, *search.parents]:
        if (ancestor / marker).is_file():
            return ancestor

    file_dir = Path(__file__).resolve().parent
    for ancestor in [file_dir, *file_dir.parents]:
        if (ancestor / marker).is_file():
            return ancestor

    raise FileNotFoundError(
        f"Could not find {marker} walking up from {search} or {file_dir}. "
        f"Set {env_var} env var or run from within a project repo."
    )
