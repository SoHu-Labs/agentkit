"""Best-practice environment-variable + path helpers."""
from __future__ import annotations

import os
from pathlib import Path

from agentkit.core._errors import ConfigError

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _raw(key: str) -> str:
    return os.environ.get(key, "").strip()


def env_str(key: str, default: str = "", *, required: bool = False) -> str:
    raw = _raw(key)
    if raw:
        return raw
    if required:
        raise ConfigError(f"Required env var {key!r} is not set")
    return default


def env_int(key: str, default: int = 0, *, required: bool = False) -> int:
    raw = _raw(key)
    if not raw:
        if required:
            raise ConfigError(f"Required env var {key!r} is not set")
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ConfigError(f"Env var {key!r} must be an integer, got {raw!r}") from e


def env_bool(key: str, default: bool = False) -> bool:
    raw = _raw(key).lower()
    if not raw:
        return default
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    raise ConfigError(f"Env var {key!r} must be a boolean, got {raw!r}")


def expand_path(value: str | Path | None, default: Path) -> Path:
    """Resolve *value* (e.g. from YAML) to an absolute path, or *default*.

    Relative paths resolve against the current working directory.
    """
    if value is None or value == "":
        return default
    p = Path(value).expanduser()
    return p.resolve() if p.is_absolute() else (Path.cwd() / p).resolve()


def env_path(key: str, default: Path, *, required: bool = False) -> Path:
    raw = _raw(key)
    if not raw:
        if required:
            raise ConfigError(f"Required env var {key!r} is not set")
        return default
    return Path(raw).expanduser().resolve()
