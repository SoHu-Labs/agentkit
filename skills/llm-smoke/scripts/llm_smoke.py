#!/usr/bin/env python3
"""Smoke-test agentkit LLM auth + connectivity."""
from __future__ import annotations

import sys

from agentkit.llm import (
    complete,
    get_go_api_key,
    get_personal_deepseek_key,
    resolve_model,
)


def main() -> int:
    go = get_go_api_key()
    personal = get_personal_deepseek_key()
    if go:
        print(f"key source: opencode-go (...{go[-4:]})")
    elif personal:
        print(f"key source: personal deepseek (...{personal[-4:]})")
    else:
        print("key source: NONE FOUND — set OPENCODE_API_KEY/DEEPSEEK_API_KEY or auth.json")
        return 1

    alias = sys.argv[1] if len(sys.argv) > 1 else "fast"
    print(f"alias: {alias} -> model: {resolve_model(alias)}")

    rec: dict = {}
    text = complete(
        [{"role": "user", "content": "Reply with the single word: pong"}],
        alias=alias,
        max_tokens=8,
        log_fn=rec.update,
    )
    print(f"response: {text!r}")
    print(f"cost_usd: {rec.get('cost_usd')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
