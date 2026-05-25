"""YAML configuration loading."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from agentkit.core._errors import ConfigError


def load_yaml_mapping(
    path: Path,
    *,
    allow_empty: bool = True,
    error_cls: type[Exception] = ConfigError,
) -> dict[str, Any]:
    """Load a YAML file that must contain a mapping (dict).

    Raises *error_cls* if the file is missing, empty (unless *allow_empty*),
    or not a mapping. Pass *error_cls* to keep a consumer's own error type.
    Requires PyYAML (``pip install 'agentkit[config]'``).
    """
    import yaml  # lazy: keeps `import agentkit.core` dependency-free

    if not path.is_file():
        raise error_cls(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        if allow_empty:
            return {}
        raise error_cls(f"Config file is empty: {path}")
    if not isinstance(data, dict):
        raise error_cls(f"Config root must be a mapping: {path}")
    return data
