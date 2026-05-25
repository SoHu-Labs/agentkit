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
)
from agentkit.llm._litellm import (
    _build_completion_kwargs,
    _get_go_api_key,
    _get_personal_deepseek_key,
)


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


class TestGoApiKey:
    def test_env_var(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OPENCODE_API_KEY", "sk-env-go")
        assert _get_go_api_key() == "sk-env-go"

    def test_opencode_block(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
        auth = tmp_path / "auth.json"
        auth.write_text(json.dumps({"opencode": {"key": "sk-opencode"}}))
        monkeypatch.setattr("agentkit.llm._litellm._AUTH_PATH", auth)
        assert _get_go_api_key() == "sk-opencode"

    def test_opencode_go_block(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
        auth = tmp_path / "auth.json"
        auth.write_text(json.dumps({"opencode-go": {"key": "sk-go"}}))
        monkeypatch.setattr("agentkit.llm._litellm._AUTH_PATH", auth)
        assert _get_go_api_key() == "sk-go"

    def test_zen_block(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
        auth = tmp_path / "auth.json"
        auth.write_text(json.dumps({"zen": {"key": "sk-zen"}}))
        monkeypatch.setattr("agentkit.llm._litellm._AUTH_PATH", auth)
        assert _get_go_api_key() == "sk-zen"

    def test_returns_none_when_no_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
        monkeypatch.setattr(
            "agentkit.llm._litellm._AUTH_PATH", tmp_path / "nonexistent.json"
        )
        assert _get_go_api_key() is None

    def test_ignores_deepseek_block(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
        auth = tmp_path / "auth.json"
        auth.write_text(json.dumps({"deepseek": {"key": "sk-personal"}}))
        monkeypatch.setattr("agentkit.llm._litellm._AUTH_PATH", auth)
        assert _get_go_api_key() is None


class TestPersonalDeepSeekKey:
    def test_deepseek_block(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        auth = tmp_path / "auth.json"
        auth.write_text(json.dumps({"deepseek": {"key": "sk-personal"}}))
        monkeypatch.setattr("agentkit.llm._litellm._AUTH_PATH", auth)
        assert _get_personal_deepseek_key() == "sk-personal"

    def test_deepseek_env_var(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-personal")
        monkeypatch.setattr(
            "agentkit.llm._litellm._AUTH_PATH", tmp_path / "nonexistent.json"
        )
        assert _get_personal_deepseek_key() == "sk-env-personal"

    def test_returns_none_when_no_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.setattr(
            "agentkit.llm._litellm._AUTH_PATH", tmp_path / "nonexistent.json"
        )
        assert _get_personal_deepseek_key() is None

    def test_ignores_opencode_block(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        auth = tmp_path / "auth.json"
        auth.write_text(json.dumps({"opencode": {"key": "sk-go"}}))
        monkeypatch.setattr("agentkit.llm._litellm._AUTH_PATH", auth)
        assert _get_personal_deepseek_key() is None


class TestCompleteMocked:
    def test_complete_returns_text(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OPENCODE_API_KEY", "sk-test")
        with patch("agentkit.llm._litellm.litellm.completion") as mock:
            mock.return_value.choices = [type("c", (), {"message": type("m", (), {"content": "hello"})()})()]
            mock.return_value.usage = type("u", (), {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})()
            result = complete(
                [{"role": "user", "content": "hi"}],
                alias="fast",
                aliases={"fast": "test/model"},
            )
            assert result == "hello"

    def test_complete_log_fn_called(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OPENCODE_API_KEY", "sk-test")
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

    def test_complete_log_fn_called_on_error(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OPENCODE_API_KEY", "sk-test")
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

    def test_complete_with_tools_returns_raw(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OPENCODE_API_KEY", "sk-test")
        with patch("agentkit.llm._litellm.litellm.completion") as mock:
            mock.return_value = "raw-response"
            resp = complete_with_tools(
                [{"role": "user", "content": "x"}],
                tools=[{"type": "function", "function": {"name": "test"}}],
                alias="fast",
                aliases={"fast": "test/model"},
            )
            assert resp == "raw-response"

    def test_complete_falls_back_on_go_api_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        auth = tmp_path / "auth.json"
        auth.write_text(
            json.dumps(
                {
                    "opencode-go": {"key": "sk-go-sub"},
                    "deepseek": {"key": "sk-personal-fallback"},
                }
            )
        )
        monkeypatch.setattr("agentkit.llm._litellm._AUTH_PATH", auth)

        call_kwargs: list[dict] = []

        def fail_then_succeed(**kwargs: Any) -> Any:
            call_kwargs.append(dict(kwargs))
            if len(call_kwargs) == 1:
                raise RuntimeError("Go API unavailable")
            resp = type("r", (), {"choices": [type("c", (), {"message": type("m", (), {"content": "fallback-ok"})()})()], "usage": None})()
            return resp

        with patch("agentkit.llm._litellm.litellm.completion", side_effect=fail_then_succeed):
            result = complete([{"role": "user", "content": "hi"}], alias="fast")
            assert result == "fallback-ok"

        assert len(call_kwargs) == 2
        # First call: Go API with subscription key
        assert call_kwargs[0]["api_key"] == "sk-go-sub"
        assert "go/v1" in call_kwargs[0]["api_base"]
        # Second call: direct DeepSeek with personal key
        assert call_kwargs[1]["api_key"] == "sk-personal-fallback"
        assert "api.deepseek.com/v1" in call_kwargs[1]["api_base"]


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

    def test_json_mode(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OPENCODE_API_KEY", "sk-test")
        kwargs = _build_completion_kwargs(
            model="test/model",
            alias="fast",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=100,
            temperature=0.5,
            json_mode=True,
        )
        assert kwargs["response_format"] == {"type": "json_object"}

    def test_go_key_sets_api_base(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OPENCODE_API_KEY", "sk-go")
        kwargs = _build_completion_kwargs(
            model="deepseek/deepseek-v4-flash",
            alias="fast",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=100,
            temperature=0.5,
        )
        assert kwargs["api_key"] == "sk-go"
        assert "go/v1" in kwargs["api_base"]

    def test_personal_key_no_api_base(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        auth = tmp_path / "auth.json"
        auth.write_text(json.dumps({"deepseek": {"key": "sk-personal"}}))
        monkeypatch.setattr("agentkit.llm._litellm._AUTH_PATH", auth)
        kwargs = _build_completion_kwargs(
            model="deepseek/deepseek-v4-flash",
            alias="fast",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=100,
            temperature=0.5,
        )
        assert kwargs["api_key"] == "sk-personal"
        assert "api.deepseek.com/v1" in kwargs["api_base"]

    def test_raises_when_no_key(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.setattr("agentkit.llm._litellm._AUTH_PATH", tmp_path / "nonexistent.json")
        with pytest.raises(Exception):
            _build_completion_kwargs(
                model="deepseek/deepseek-v4-flash",
                alias="fast",
                messages=[{"role": "user", "content": "x"}],
                max_tokens=100,
                temperature=0.5,
            )


class TestResponseCost:
    def test_returns_float(self):
        with patch("agentkit.llm._litellm.litellm.completion_cost", return_value=0.05):
            assert response_cost_usd(None) == 0.05

    def test_returns_zero_on_error(self):
        with patch("agentkit.llm._litellm.litellm.completion_cost", side_effect=Exception("nope")):
            assert response_cost_usd(None) == 0.0


class TestPublicAuthReaders:
    def test_public_names_are_the_private_impls(self):
        from agentkit.llm import get_go_api_key, get_personal_deepseek_key
        from agentkit.llm._litellm import _get_go_api_key, _get_personal_deepseek_key
        assert get_go_api_key is _get_go_api_key
        assert get_personal_deepseek_key is _get_personal_deepseek_key
