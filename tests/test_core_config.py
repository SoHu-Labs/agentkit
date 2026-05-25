"""Tests for agentkit.core config primitives."""
from __future__ import annotations

import pytest

from agentkit.core import (
    ConfigError,
    env_bool,
    env_int,
    env_path,
    env_str,
    expand_path,
    load_yaml_mapping,
)


def test_load_yaml_mapping_ok(tmp_path):
    p = tmp_path / "c.yaml"; p.write_text("a: 1\nb: two\n")
    assert load_yaml_mapping(p) == {"a": 1, "b": "two"}


def test_load_yaml_mapping_missing_file(tmp_path):
    with pytest.raises(ConfigError):
        load_yaml_mapping(tmp_path / "nope.yaml")


def test_load_yaml_mapping_empty_returns_dict(tmp_path):
    p = tmp_path / "c.yaml"; p.write_text("")
    assert load_yaml_mapping(p) == {}


def test_load_yaml_mapping_non_mapping(tmp_path):
    p = tmp_path / "c.yaml"; p.write_text("- 1\n- 2\n")
    with pytest.raises(ConfigError):
        load_yaml_mapping(p)


def test_load_yaml_mapping_custom_error_cls(tmp_path):
    class MyErr(Exception):
        ...
    with pytest.raises(MyErr):
        load_yaml_mapping(tmp_path / "nope.yaml", error_cls=MyErr)


def test_env_str(monkeypatch):
    monkeypatch.delenv("X", raising=False)
    assert env_str("X", "def") == "def"
    monkeypatch.setenv("X", "  v  ")
    assert env_str("X") == "v"


def test_env_str_required(monkeypatch):
    monkeypatch.delenv("X", raising=False)
    with pytest.raises(ConfigError):
        env_str("X", required=True)


def test_env_int_and_bad(monkeypatch):
    monkeypatch.setenv("N", "5")
    assert env_int("N") == 5
    monkeypatch.setenv("N", "x")
    with pytest.raises(ConfigError):
        env_int("N")


def test_env_bool(monkeypatch):
    monkeypatch.setenv("B", "yes"); assert env_bool("B") is True
    monkeypatch.setenv("B", "off"); assert env_bool("B") is False
    monkeypatch.delenv("B", raising=False); assert env_bool("B", True) is True


def test_expand_path(tmp_path):
    assert expand_path("", tmp_path) == tmp_path
    assert expand_path(None, tmp_path) == tmp_path
    abs_p = tmp_path / "a"
    assert expand_path(str(abs_p), tmp_path) == abs_p.resolve()


def test_env_path(monkeypatch, tmp_path):
    monkeypatch.delenv("P", raising=False)
    assert env_path("P", tmp_path) == tmp_path
    monkeypatch.setenv("P", str(tmp_path / "z"))
    assert env_path("P", tmp_path) == (tmp_path / "z").resolve()
