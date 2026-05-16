"""Cloud LLM abstraction via litellm with provider aliases and DeepSeek auth fallback.

For local MLX models see ``agentkit.llm.mlx``.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

import litellm

from agentkit.core import LLMError

# ---------------------------------------------------------------------------
# Default model aliases (overridable per project)
# ---------------------------------------------------------------------------

DEFAULT_MODEL_ALIASES: dict[str, str] = {
    "fast": "deepseek/deepseek-v4-flash",
    "smart": "deepseek/deepseek-v4-pro",
    "local": "openai/local-model",
    "local_smart": "openai/local-model",
    "cheap": "openai/minimax-m2.5",
}

# Aliases routed through OpenCode Go API (OpenAI-compatible endpoint)
_GO_API_ALIASES = frozenset({"fast", "smart", "cheap"})

# LM Studio defaults for local aliases
_LM_STUDIO_BASE_URL = os.environ.get("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
_LOCAL_MODEL_DEFAULT = "mlx-community/Qwen3.5-4B-MLX-4bit"

# ---------------------------------------------------------------------------
# Auth resolution
# ---------------------------------------------------------------------------

_AUTH_PATH = Path.home() / ".local" / "share" / "opencode" / "auth.json"


def _read_auth_json() -> dict:
    if not _AUTH_PATH.is_file():
        return {}
    try:
        return json.loads(_AUTH_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _resolve_deepseek_auth() -> tuple[str, str]:
    """Return ``(api_key, source_description)`` for DeepSeek.

    Priority:
    1. ``OPENCODE_API_KEY`` env var — explicit override
    2. auth.json → ``opencode``, ``opencode-go``, ``zen``, ``opencode-zen`` blocks — opencode subscription
    3. auth.json → ``deepseek`` block — personal API key
    4. ``DEEPSEEK_API_KEY`` env var — explicit override

    The subscription key is used via the OpenCode Go API endpoint.
    """
    key = os.environ.get("OPENCODE_API_KEY", "").strip()
    if key:
        return key, "OPENCODE_API_KEY env var"

    data = _read_auth_json()
    for block in ("opencode", "opencode-go", "zen", "opencode-zen"):
        entry = data.get(block)
        if isinstance(entry, dict):
            k = entry.get("key") or entry.get("apiKey")
            if isinstance(k, str) and k.strip():
                print("DeepSeek auth: using opencode subscription")
                return k.strip(), f"opencode subscription (auth.json → {block})"

    entry = data.get("deepseek")
    if isinstance(entry, dict):
        k = entry.get("key")
        if isinstance(k, str) and k.strip():
            print("DeepSeek auth: using personal API key")
            return k.strip(), "personal API key (auth.json → deepseek)"

    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        print("DeepSeek auth: using DEEPSEEK_API_KEY env var")
        return key, "DEEPSEEK_API_KEY env var"

    raise LLMError(
        "No DeepSeek API key found. Add it under 'opencode' or 'deepseek' blocks in "
        "~/.local/share/opencode/auth.json, or set DEEPSEEK_API_KEY / OPENCODE_API_KEY env var."
    )


# ---------------------------------------------------------------------------
# Model alias resolution
# ---------------------------------------------------------------------------

def resolve_model(
    alias: str,
    *,
    aliases: dict[str, str] | None = None,
) -> str:
    """Resolve a model alias to a provider model ID.

    Environment variable ``{ALIAS.upper()}_MODEL`` overrides the alias lookup.
    If *aliases* is provided it is used instead of ``DEFAULT_MODEL_ALIASES``.
    """
    alias_map = aliases or DEFAULT_MODEL_ALIASES
    env_key = f"{alias.upper()}_MODEL"
    env_val = os.environ.get(env_key, "").strip()
    if env_val:
        return env_val
    return alias_map.get(alias, alias)


# ---------------------------------------------------------------------------
# Core completion
# ---------------------------------------------------------------------------

LogFn = Callable[[dict[str, Any]], None]


def complete(
    messages: list[dict[str, Any]],
    alias: str = "smart",
    *,
    max_tokens: int = 2000,
    temperature: float = 0.3,
    json_mode: bool = False,
    aliases: dict[str, str] | None = None,
    log_fn: LogFn | None = None,
    **extra_kwargs: Any,
) -> str:
    """Send a chat completion request via litellm. Returns the response text.

    DeepSeek auth is resolved automatically with fallback: opencode subscription
    key first, then personal API key. The source is printed to stdout.

    Args:
        messages: Chat messages in OpenAI format.
        alias: Model alias (``fast``, ``smart``, ``cheap``, ``local``, etc.).
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature (0.0–1.0).
        json_mode: If True, request JSON object response format.
        aliases: Override ``DEFAULT_MODEL_ALIASES`` per project.
        log_fn: Optional callback ``log_fn(record)`` called after completion.
        **extra_kwargs: Passed directly to ``litellm.completion()``.

    Returns:
        Generated text string.

    Raises:
        AgentError.LLMError: On any litellm or auth failure.
    """
    model = resolve_model(alias, aliases=aliases)
    t0 = time.perf_counter()
    error_msg: str | None = None

    try:
        kwargs = _build_completion_kwargs(
            model=model,
            alias=alias,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=json_mode,
            **extra_kwargs,
        )
        resp = litellm.completion(**kwargs)
    except Exception as e:
        error_msg = str(e)
        raise LLMError(error_msg) from e
    finally:
        if log_fn:
            duration_ms = (time.perf_counter() - t0) * 1000
            usage: dict[str, int] = {}
            cost = 0.0
            if error_msg is None:
                try:
                    usage = {
                        "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0) or 0,
                        "completion_tokens": getattr(resp.usage, "completion_tokens", 0) or 0,
                        "total_tokens": getattr(resp.usage, "total_tokens", 0) or 0,
                    }
                except Exception:
                    pass
                try:
                    cost = float(litellm.completion_cost(completion_response=resp))
                except Exception:
                    pass
            log_fn(
                {
                    "alias": alias,
                    "model": model,
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                    "cost_usd": cost,
                    "duration_ms": duration_ms,
                    "error": error_msg,
                }
            )

    return str(resp.choices[0].message.content or "")


def complete_with_tools(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    tool_choice: str = "auto",
    alias: str = "smart",
    *,
    max_tokens: int = 2000,
    temperature: float = 0.3,
    aliases: dict[str, str] | None = None,
    log_fn: LogFn | None = None,
    **extra_kwargs: Any,
) -> Any:
    """Send a chat completion request with tool definitions.

    Returns the raw litellm response object. Consumers parse tool calls themselves.

    Args:
        messages: Chat messages in OpenAI format.
        tools: List of OpenAI function tool definitions.
        tool_choice: ``"auto"``, ``"none"``, or a specific tool dict.
        alias: Model alias.
        max_tokens: Maximum tokens to generate.
        temperature: Sampling temperature.
        aliases: Override ``DEFAULT_MODEL_ALIASES``.
        log_fn: Optional callback.
        **extra_kwargs: Passed to ``litellm.completion()``.

    Returns:
        Raw litellm completion response object.
    """
    model = resolve_model(alias, aliases=aliases)

    try:
        kwargs = _build_completion_kwargs(
            model=model,
            alias=alias,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **extra_kwargs,
        )
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice
        return litellm.completion(**kwargs)
    except Exception as e:
        raise LLMError(str(e)) from e


def response_cost_usd(response: Any) -> float:
    """Estimate USD cost of a litellm response."""
    try:
        return float(litellm.completion_cost(completion_response=response))
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_completion_kwargs(
    *,
    model: str,
    alias: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
    json_mode: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        **extra,
    }

    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    # LM Studio local models
    if alias in ("local", "local_smart"):
        kwargs["api_base"] = _LM_STUDIO_BASE_URL
        kwargs["api_key"] = os.environ.get("LM_STUDIO_API_KEY", "lm-studio")
        return kwargs

    # Cloud models via OpenCode Go API
    if alias in _GO_API_ALIASES or "deepseek" in model.lower():
        key, _source = _resolve_deepseek_auth()
        kwargs["api_key"] = key
        kwargs["api_base"] = os.environ.get(
            "OPENCODE_API_BASE", "https://opencode.ai/zen/go/v1"
        )
        return kwargs

    return kwargs
