---
name: llm-smoke
description: Verify agentkit LLM auth + connectivity end to end. Use when an LLM call fails with an auth error, after changing API keys or ~/.local/share/opencode/auth.json, or when setting up a new machine. Reports which key source resolved, the model, the response, and the cost.
---

# agentkit LLM smoke test

Run the helper to confirm the opencode-go-key → DeepSeek fallback is wired and a
completion succeeds.

## Steps
1. `python skills/llm-smoke/scripts/llm_smoke.py [alias]` (default alias: `fast`).
2. Read the output:
   - `key source:` tells you whether the opencode subscription key or the
     personal DeepSeek key resolved. `NONE FOUND` means set `OPENCODE_API_KEY` or
     `DEEPSEEK_API_KEY`, or add a key under the `opencode`/`deepseek` block in
     `~/.local/share/opencode/auth.json`.
   - `response:` should be a short non-empty string.
   - `cost_usd:` is the litellm-estimated cost.
3. If it fails, the printed exception is the real auth/connectivity error.
