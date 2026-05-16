"""Tests for agentkit.core."""
from pathlib import Path
from unittest.mock import patch

import pytest

from agentkit.core import repo_root, AgentError, LLMFailureWithTranscript


class TestRepoRoot:
    def test_env_var_takes_priority(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("REPO_ROOT", str(tmp_path))
        assert repo_root() == tmp_path.resolve()

    def test_finds_pyproject_toml_from_cwd(self, tmp_path: Path):
        marker = tmp_path / "pyproject.toml"
        marker.touch()
        result = repo_root(start=tmp_path)
        assert result == tmp_path

    def test_raises_file_not_found_when_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("REPO_ROOT", raising=False)
        with pytest.raises(FileNotFoundError):
            repo_root(start=tmp_path, marker="nonexistent.toml")

    def test_custom_env_var(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MY_PROJECT_ROOT", str(tmp_path))
        result = repo_root(env_var="MY_PROJECT_ROOT")
        assert result == tmp_path.resolve()


class TestErrors:
    def test_agent_error_is_exception(self):
        with pytest.raises(AgentError):
            raise AgentError("something went wrong")

    def test_llm_failure_carries_state(self):
        transcript = [{"role": "user", "content": "hello"}]
        err = LLMFailureWithTranscript(
            "LLM failed",
            transcript=transcript,
            cost_usd=0.05,
            rounds=3,
        )
        assert err.transcript == transcript
        assert err.cost_usd == 0.05
        assert err.rounds == 3
        assert isinstance(err, AgentError)

    def test_llm_failure_defaults(self):
        err = LLMFailureWithTranscript("oops", transcript=[])
        assert err.cost_usd == 0.0
        assert err.rounds == 0
