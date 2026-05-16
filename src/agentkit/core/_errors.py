"""Shared exception hierarchy for agent tools."""
from __future__ import annotations

from typing import Any


class AgentError(Exception):
    """Base exception for all agent tool errors."""


class LLMError(AgentError):
    """LLM provider or API call failure."""


class LLMFailureWithTranscript(AgentError):
    """LLM call failed, but partial transcript is available for retry/resume."""

    def __init__(
        self,
        message: str,
        *,
        transcript: list[dict[str, Any]],
        cost_usd: float = 0.0,
        rounds: int = 0,
    ) -> None:
        super().__init__(message)
        self.transcript = transcript
        self.cost_usd = cost_usd
        self.rounds = rounds
