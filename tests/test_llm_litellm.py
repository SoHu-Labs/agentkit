"""Tests for agentkit.llm.litellm — alias resolution + auth fallback (no live API)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from agentkit.llm import (
    DEFAULT_MODEL_ALIASES,
    complete,
    complete_with_tools,
    resolve_model,
    response_cost_usd,
    _resolve_deepseek_auth,
)
from agentkit.llm._litellm import _build_completion_kwargs


class TestResolveModel:
    def test_default_aliases(self):
        assert resolve_model("fast") == "deepseek/deepseek-v4-flash"
        assert resolve_model("smart") == "deepseek/deepseek-v4-pro"

    def test_custom_aliases(self):
        aliases = {"fast": "custom/model"}
        assert resolve_model("fast", aliases=aliases) == "custom/model"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FAST_MODEL", "env/model")
        assert resolve_model("fast") == "env/model"

    def test_unknown_alias_passthrough(self):
        assert resolve_model("nonexistent") == "nonexistent"


class TestDeepSeekAuth:
    def test_env_var_first(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("OPENCODE_API_KEY", "sk-env-first")
        key, source = _resolve_deepseek_auth()
        assert key == "sk-env-first"
        assert "env var" in source.lower()

    def test_opencode_block_in_auth_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        auth = tmp_path / "auth.json"
        auth.write_text(json.dumps({"opencode": {"key": "sk-opencode"}}))
        monkeypatch.setattr("agentkit.llm._litellm._AUTH_PATH", auth)
        monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
        key, source = _resolve_deepseek_auth()
        assert key == "sk-opencode"
        assert "opencode subscription" in source.lower()

    def test_deepseek_block_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        auth = tmp_path / "auth.json"
        auth.write_text(json.dumps({"deepseek": {"key": "sk-personal"}}))
        monkeypatch.setattr("agentkit.llm._litellm._AUTH_PATH", auth)
        monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        key, source = _resolve_deepseek_auth()
        assert key == "sk-personal"
        assert "personal" in source.lower()

    def test_deepseek_env_var_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-env")
        monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
        monkeypatch.setattr("agentkit.llm._litellm._AUTH_PATH", tmp_path / "nonexistent.json")
        key, source = _resolve_deepseek_auth()
        assert key == "sk-deepseek-env"

    def test_raises_when_no_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.setattr("agentkit.llm._litellm._AUTH_PATH", tmp_path / "nonexistent.json")
        with pytest.raises(Exception):  # LLMError inherits from AgentError
            _resolve_deepseek_auth()


class TestCompleteMocked:
    def test_complete_returns_text(self):
        with patch("agentkit.llm._litellm.litellm.completion") as mock:
            mock.return_value.choices = [type("c", (), {"message": type("m", (), {"content": "hello"})()})()]
            mock.return_value.usage = type("u", (), {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})()
            result = complete(
                [{"role": "user", "content": "hi"}],
                alias="fast",
                aliases={"fast": "test/model"},
            )
            assert result == "hello"

    def test_complete_log_fn_called(self):
        records = []

        with patch("agentkit.llm._litellm.litellm.completion") as mock:
            mock.return_value.choices = [type("c", (), {"message": type("m", (), {"content": "ok"})()})()]
            mock.return_value.usage = type("u", (), {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})()
            with patch("agentkit.llm._litellm.litellm.completion_cost", return_value=0.01):
                complete(
                    [{"role": "user", "content": "x"}],
                    alias="fast",
                    aliases={"fast": "test/model"},
                    log_fn=records.append,
                )

        assert len(records) == 1
        assert records[0]["alias"] == "fast"
        assert records[0]["model"] == "test/model"
        assert records[0]["input_tokens"] == 1
        assert records[0]["output_tokens"] == 1
        assert records[0]["error"] is None

    def test_complete_log_fn_called_on_error(self):
        records = []

        with patch("agentkit.llm._litellm.litellm.completion", side_effect=RuntimeError("boom")):
            try:
                complete(
                    [{"role": "user", "content": "x"}],
                    alias="fast",
                    aliases={"fast": "test/model"},
                    log_fn=records.append,
                )
            except Exception:
                pass

        assert len(records) == 1
        assert records[0]["error"] == "boom"
        assert records[0]["cost_usd"] == 0.0

    def test_complete_with_tools_returns_raw(self):
        with patch("agentkit.llm._litellm.litellm.completion") as mock:
            mock.return_value = "raw-response"
            resp = complete_with_tools(
                [{"role": "user", "content": "x"}],
                tools=[{"type": "function", "function": {"name": "test"}}],
                alias="fast",
                aliases={"fast": "test/model"},
            )
            assert resp == "raw-response"


class TestBuildCompletionKwargs:
    def test_lm_studio_override(self):
        kwargs = _build_completion_kwargs(
            model="openai/local-model",
            alias="local",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=100,
            temperature=0.5,
        )
        assert kwargs["api_base"] == "http://localhost:1234/v1"

    def test_json_mode(self):
        kwargs = _build_completion_kwargs(
            model="test/model",
            alias="fast",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=100,
            temperature=0.5,
            json_mode=True,
        )
        assert kwargs["response_format"] == {"type": "json_object"}


class TestResponseCost:
    def test_returns_float(self):
        with patch("agentkit.llm._litellm.litellm.completion_cost", return_value=0.05):
            assert response_cost_usd(None) == 0.05

    def test_returns_zero_on_error(self):
        with patch("agentkit.llm._litellm.litellm.completion_cost", side_effect=Exception("nope")):
            assert response_cost_usd(None) == 0.0
