from agentkit.llm._mlx import MlxLlm, MODEL_VARIANTS, DEFAULT_MODEL_PATH
from agentkit.llm._logging import SqliteCallLogger


def __getattr__(name: str):
    if name in ("DEFAULT_MODEL_ALIASES", "complete", "complete_with_tools",
                 "resolve_model", "response_cost_usd",
                 "get_go_api_key", "get_personal_deepseek_key"):
        from agentkit.llm._litellm import (
            DEFAULT_MODEL_ALIASES,
            complete,
            complete_with_tools,
            resolve_model,
            response_cost_usd,
            get_go_api_key,
            get_personal_deepseek_key,
        )
        return globals().get(name) or locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "MlxLlm",
    "MODEL_VARIANTS",
    "DEFAULT_MODEL_PATH",
    "SqliteCallLogger",
]
