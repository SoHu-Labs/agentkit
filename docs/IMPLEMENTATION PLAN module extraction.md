# Implementation Plan — Module Extraction

## Progress

| Status | Module | Description |
|--------|--------|-------------|
| ✅ | core/ | repo_root() + AgentError base class (4 consumers, stdlib) |
| ✅ | llm/ | MLX local models + litellm cloud + DeepSeek auth fallback (3 consumers) |
| ✅ | gmail/ | Gmail API client with Protocol-based testability (1 consumer: decisionmaker) |
| ✅ | browser/ | Selenium Brave attach + WebDriver utilities (2 consumers) |
| ✅ | speech/ | MLX Kokoro-82M TTS + Parakeet STT (2 consumers) |

---

## Overview

Extract 5 modules from 5 repos into `agentkit`, a shared library for AI prototyping projects on Apple Silicon. Only code **currently reused** by 2+ repos is extracted. Each module has a single canonical master source.

**Goal:** deduplicate shared code. **Non-goal:** speculative extraction for hypothetical future use.

---

## Architecture

```
agentkit/
    pyproject.toml
    AGENTS.md
    src/agentkit/
        __init__.py
        core/
            __init__.py
            _common.py           # repo_root() — master: swim (used by 4 repos)
            _errors.py           # AgentError, LLMFailureWithTranscript (used by 2 repos)
        llm/
            __init__.py
            _mlx.py              # MlxLlm + Qwen model variants — master: local-chat (used by 1 repo)
            _litellm.py          # Cloud LLM via litellm + DeepSeek fallback (used by 3 repos)
        gmail/
            __init__.py
            _client.py           # GmailFacade, GmailApiBackend — master: invoice-admin (used by 3 repos)
        browser/
            __init__.py
            _browser.py          # Selenium Brave attach + WebDriver utils — master: invoice-admin (used by 2 repos)
        speech/
            __init__.py
            _tts.py              # MlxTts + Kokoro constants — master: local-chat (used by 2 repos)
    tests/
        ...
```

**Import convention:**

```python
from agentkit.core import repo_root, AgentError, LLMFailureWithTranscript
from agentkit.llm import MlxLlm, complete, complete_with_tools
from agentkit.gmail import GmailFacade, GmailApiBackend
from agentkit.browser import attach_brave_browser, chrome_options
from agentkit.speech import MlxTts, KOKORO_VOICES
```

Private modules (`_` prefix) are re-exported by their `__init__.py`. Users never type `agentkit.core._common`.

---

## Extraction order & dependency graph

```
1. core/          (zero deps, pure stdlib)                          ✅
       ↓
2. llm/           (mlx: mlx-lm only; litellm: litellm + auth.json)  ✅
       ↓
3. gmail/         (google-api-client + auth)                         ✅ (decisionmaker only)
       ↓
4. speech/        (mlx-audio, sounddevice, parakeet-mlx)             ✅
       ↓
5. browser/       (selenium, optional)                               ✅
```

Rationale: Hardest modules first (llm → gmail). Speech is self-contained, done whenever. Browser is last — smallest scope, no blocking dependencies.

Each module is extracted, tested in isolation, then its consumers are migrated via re-export shims.

---

## Shared design decisions

### Model defaults

| Project | Primary backend | Rationale |
|---------|----------------|-----------|
| local-chat | Local MLX (Qwen) | Latency, privacy, offline |
| email-digest | Cloud (litellm DeepSeek) | Quality, tool calling |
| decisionmaker | Cloud (litellm DeepSeek) | Quality, tool calling |
| invoice-admin | Cloud (litellm DeepSeek) | Quality, multimodal PDF |

**Rule for extraction:** Both local (MLX) and cloud (litellm) backends ship in `agentkit`. Each importing repo keeps its own default alias. The module is agnostic. Refactoring notes are provided per consumer.

### DeepSeek API key fallback

```
Priority 1: OpenCode subscription key
    Source: ~/.local/share/opencode/auth.json → block "opencode" or "opencode-go"
    Reason: Zero-config, uses opencode subscription
    
Priority 2: User's personal DeepSeek API key  
    Source: ~/.local/share/opencode/auth.json → block "deepseek"
    Reason: Fallback when opencode subscription lapses

Priority 3: Environment variable
    Source: DEEPSEEK_API_KEY env var
    Reason: Explicit override

Print to console: "DeepSeek auth: using [opencode subscription | personal API key | env var]"
On fallback: "OpenCode subscription key failed, falling back to personal DeepSeek API key"
```

All three sources are checked by a single utility function. The subscription key and personal key both live in `auth.json` — no env var setup required for either.

### Migration method: re-export shims

Every extraction follows this pattern per consuming repo:

1. **Extract** code from master repo into `agentkit`
2. **Write smoke tests** in agentkit for the extracted module
3. **In consumer repo**, replace original file body with re-export from agentkit:
   ```python
   from agentkit.llm import complete  # noqa: F401
   ```
4. **Run consumer's test suite** — all existing imports still work through the shim
5. **Delete shim** in a follow-up commit (after all consumers migrated)
6. **Git history** preserves the original; revert by checking out the file from git

---

## Module 1 — `core/`

### User perspective

Two tiny stdlib modules every project needs:

- **`repo_root()`** — finds the project root directory. Call it without arguments. Works across env vars, CWD, and file-location fallbacks. No more hardcoded paths.
- **`AgentError` / `LLMFailureWithTranscript`** — base exception for all agent-tool errors. `LLMFailureWithTranscript` carries conversation state (transcript, cost, rounds) so callers can retry or resume after failure.

```python
from agentkit.core import repo_root, AgentError, LLMFailureWithTranscript

data_dir = repo_root() / "data"

try:
    result = llm.complete(...)
except Exception as e:
    raise LLMFailureWithTranscript(
        "LLM failed",
        transcript=messages,
        cost_usd=cost,
        rounds=n,
    ) from e
```

### Technical

| | |
|---|---|
| **Master source** | `swim/src/swim/common.py` (`repo_root`) + new code (`errors`) |
| **Consumers** | swim, decisionmaker, email-digest, invoice-admin (repo_root); decisionmaker, invoice-admin (errors) |
| **Dependencies** | None (stdlib only) |
| **Lines** | ~30 total |
| **Target** | `src/agentkit/core/_common.py`, `src/agentkit/core/_errors.py`, `src/agentkit/core/__init__.py` |

**`repo_root()` algorithm (from swim):**
1. Check `$PROJECT_REPO_ROOT` env var
2. Walk up from CWD looking for `pyproject.toml`
3. Walk up from `__file__` looking for `pyproject.toml`
4. Raise `FileNotFoundError` if not found

Parameterized: env var name and marker file are configurable via kwargs.

**`errors.py` contents:**
```python
class AgentError(Exception):
    """Base exception for all agent tool errors."""

class LLMFailureWithTranscript(AgentError):
    def __init__(self, message, *, transcript, cost_usd=0.0, rounds=0):
        ...
```

### Walkthrough questions

> Before implementing this module, ask:
> 1. Should `repo_root()` raise `FileNotFoundError` or `RuntimeError`? (Current: swim uses RuntimeError; plan suggests FileNotFoundError)
> 2. Should `LLMFailureWithTranscript` be in `core/` or in `llm/`? It's LLM-specific but used independently from the LLM module (decisionmaker catches it at the orchestrator level).
> 3. Any other 10-line utility that's duplicated across repos to bundle here?

### Migration procedure

**1. Write agentkit code and tests:**
```bash
cd ~/Software/Prototypes/agentkit
# Write src/agentkit/core/_common.py  (repo_root)
# Write src/agentkit/core/_errors.py  (AgentError, LLMFailureWithTranscript)
# Write src/agentkit/core/__init__.py (re-exports)
# Write tests/test_core.py
python -m pytest tests/test_core.py -x -q
git add -A && git commit -m "agentkit: core/ (repo_root + errors)"
```

**2. Migrate swim (repo_root consumer):**
```bash
cd ~/Software/Prototypes/swim
# Add agentkit to pyproject.toml dependencies (no extras needed):
#   "agentkit>=0.2.0"
pip install -e ~/Software/Prototypes/agentkit
# In src/swim/common.py, replace repo_root() body with:
#   from agentkit.core import repo_root as _repo_root
#   def repo_root(): return _repo_root()
python -c "from agentkit.core import repo_root; print(repo_root())"
git add -A && git commit -m "shared-migration: core — repo_root from agentkit"
```

**3. Migrate decisionmaker (repo_root + errors consumer):**
```bash
cd ~/Software/Prototypes/decisionmaker
# Add agentkit to pyproject.toml dependencies (no extras needed)
pip install -e ~/Software/Prototypes/agentkit
# In src/decisionmaker/common.py, replace repo_root() body with:
#   from agentkit.core import repo_root as _repo_root
#   def repo_root(): return _repo_root()
# In src/decisionmaker/core/errors.py, change base:
#   from agentkit.core import AgentError
#   class DecisionMakerError(AgentError): ...
#   Keep LLMFailureWithTranscript as-is (it inherits from shared.LLMFailureWithTranscript or wraps it)
python -m pytest tests/ -x -q
git add -A && git commit -m "shared-migration: core — repo_root + errors from agentkit"
```

**4. Migrate email-digest (repo_root consumer):**
```bash
cd ~/Software/Prototypes/email-digest
# Add agentkit to pyproject.toml dependencies (no extras needed)
pip install -e ~/Software/Prototypes/agentkit
# In src/email_digest/paths.py, replace repo_root() body with:
#   from agentkit.core import repo_root as _repo_root
#   def repo_root(): return _repo_root()
python -m pytest tests/ -x -q
git add -A && git commit -m "shared-migration: core — repo_root from agentkit"
```

**5. Migrate invoice-admin (repo_root + errors consumer):**
```bash
cd ~/Software/Prototypes/invoice-admin
# Add agentkit to pyproject.toml dependencies (no extras needed)
pip install -e ~/Software/Prototypes/agentkit
# In src/invoice_admin/core/config.py, replace inline repo_root() with:
#   from agentkit.core import repo_root
# In src/invoice_admin/core/errors.py, change base:
#   from agentkit.core import AgentError
#   class InvoiceError(AgentError): ...
python -m pytest tests/ -x -q
git add -A && git commit -m "shared-migration: core — repo_root + errors from agentkit"
```

**6. Verify all projects:**
```bash
cd ~/Software/Prototypes/agentkit && python -m pytest tests/ -x -q
cd ~/Software/Prototypes/swim && python -c "from agentkit.core import repo_root; print(repo_root())"
cd ~/Software/Prototypes/decisionmaker && python -m pytest tests/ -x -q
cd ~/Software/Prototypes/email-digest && python -m pytest tests/ -x -q
cd ~/Software/Prototypes/invoice-admin && python -m pytest tests/ -x -q
```
**Exit criteria:** All 4 test suites pass. `from agentkit.core import repo_root, AgentError` works in every project.

---

## Module 2 — `llm/`

Two backends, one import path. Both ship in module 2.

### 2A — `llm/mlx` (local)

#### User perspective

Local LLM via MLX. Supports Qwen variants (0.8B, 2B, 4B) on Apple Silicon. Lazy-loads model and tokenizer.

```python
from agentkit.llm import MlxLlm

llm = MlxLlm(model_path="/path/to/model", use_vlm=False)
reply = llm.generate(
    [{"role": "user", "content": "Explain quantum computing in one sentence."}],
    max_tokens=80,
    temp=0.7,
)
print(f"Tokens: prompt={llm.last_prompt_tokens}, gen={llm.last_gen_tokens}")
```

#### Technical

| | |
|---|---|
| **Master source** | `local-chat/src/llm.py` (108 lines) |
| **Consumers** | local-chat (primary), others optional |
| **Dependencies** | `mlx-lm>=0.20.0` |
| **Lines** | ~108 |
| **Target** | `src/agentkit/llm/_mlx.py`, re-exported via `src/agentkit/llm/__init__.py` |

**What ships:**
- `MlxLlm` class — lazy-loading MLX model wrapper
- `MODEL_VARIANTS` dict — paths to Qwen3 4B, Qwen3.5 0.8B/2B/4B under `~/.lmstudio/models/`
- `DEFAULT_MODEL_PATH` — Qwen3.5 2B
- Token counting (`last_prompt_tokens`, `last_gen_tokens`)
- Qwen3.5 VLM workaround (`strict=False` for multimodal weights)

**Default:** Local-chat uses MLX as primary. Cloud repos (email-digest, decisionmaker, invoice-admin) default to litellm but can opt in for offline/cost-free usage. Both backends importable from `agentkit.llm`.

#### Walkthrough questions

> 1. Qwen3.5 VLM weights need `strict=False`. Should `use_vlm` be auto-detected from model path or kept explicit?
> 2. Model paths are hardcoded to `~/.lmstudio/models/`. Should the module accept a `models_root` parameter globally, or pass full paths?
> 3. Should `MlxLlm` and the cloud `complete()` share a common interface signature?

#### Migration procedure (2A — mlx)

**1. Write agentkit code and tests:**
```bash
cd ~/Software/Prototypes/agentkit
# Copy local-chat/src/llm.py → src/agentkit/llm/_mlx.py
# Update src/agentkit/llm/__init__.py to re-export MlxLlm
# Write tests/test_llm.py (import MlxLlm, MODEL_VARIANTS — no model loading)
python -m pytest tests/test_llm.py -x -q
git add -A && git commit -m "agentkit: llm/mlx (MlxLlm + Qwen variants)"
```

**2. Migrate local-chat:**
```bash
cd ~/Software/Prototypes/local-chat
# Add to pyproject.toml or requirements.txt: agentkit[llm]
pip install -e ~/Software/Prototypes/agentkit[llm]
# Replace src/llm.py with re-export shim:
#   from agentkit.llm import MlxLlm, MODEL_VARIANTS, DEFAULT_MODEL_PATH
python -c "from src.llm import MlxLlm; print('ok')"
# Delete src/llm.py, update all callers (improv_loop.py etc.) to:
#   from agentkit.llm import MlxLlm
python improv.py  # smoke test (requires MLX models)
git add -A && git commit -m "shared-migration: llm/mlx — MlxLlm from agentkit"
```

### 2B — `llm/litellm` (cloud)

#### User perspective

Cloud LLM via litellm with model aliases. Zero-config API key resolution from opencode auth.

```python
from agentkit.llm import complete, complete_with_tools, response_cost_usd

# Simple completion
reply = complete(
    [{"role": "user", "content": "Summarize this document..."}],
    alias="smart",          # → deepseek/deepseek-v4-pro
    max_tokens=2000,
)

# With tool calling
resp = complete_with_tools(
    messages,
    tools=[question_tool_schema],
    alias="smart",
)

cost = response_cost_usd(resp)
```

**DeepSeek auth (automatic):**
```
DeepSeek auth: using opencode subscription
# ... or if subscription lapsed:
OpenCode subscription key failed, falling back to personal DeepSeek API key
DeepSeek auth: using personal API key
```

#### Technical

| | |
|---|---|
| **Master source** | `email-digest/src/email_digest/llm.py` (402 lines, most mature) |
| **Also in** | `decisionmaker/src/decisionmaker/core/llm.py` (149 lines), `invoice-admin/src/invoice_admin/core/llm.py` (535 lines) |
| **Consumers** | email-digest, decisionmaker, invoice-admin |
| **Dependencies** | `litellm>=1.55.0` |
| **Target** | `src/agentkit/llm/_litellm.py`, re-exported via `src/agentkit/llm/__init__.py` |

**What ships:**
- `DEFAULT_MODEL_ALIASES` — `fast`/`smart`/`local`/`local_smart`/`cheap` → provider model IDs
- `resolve_model(alias, *, aliases=None)` — resolve alias to provider model string; overridable per project
- `complete(messages, alias, *, max_tokens, temperature, json_mode, log_fn, **kwargs) → str`
- `complete_with_tools(messages, tools, tool_choice, alias, *, max_tokens, temperature, log_fn) → litellm response`
- `response_cost_usd(response) → float`
- `_resolve_deepseek_auth() → tuple[str, str]` — returns `(key, source_description)` with fallback logic

**DeepSeek auth resolution (`_resolve_deepseek_auth`):**
```python
def _resolve_deepseek_auth() -> tuple[str, str]:
    """Return (api_key, source_description) for DeepSeek.
    
    Priority:
    1. OPENCODE_API_KEY env var
    2. auth.json → block "opencode", "opencode-go", "zen", "opencode-zen"
    3. auth.json → block "deepseek" (personal key)
    4. DEEPSEEK_API_KEY env var
    
    Prints which source was used.
    """
```

**Logging:** Optional `log_fn(record)` callback receives `{alias, model, input_tokens, output_tokens, cost_usd, duration_ms, error}`. Consumers wire their own logging (SQLite or stdout).

**What does NOT ship:**
- SQLite call logging — each consumer wires its own via `log_fn`
- Multimodal PDF (OCR fallback) — stays in invoice-admin
- `LLMProvider` class — each consumer wraps the functions as needed
- Per-project model aliases — each project passes its own dict

**Per-consumer defaults (noted for refactoring):**

| Consumer | Default alias | Backend |
|----------|--------------|---------|
| local-chat | `local` | MLX (uses `llm/mlx`, not litellm) |
| email-digest | `smart` | Cloud DeepSeek |
| decisionmaker | `smart` | Cloud DeepSeek |
| invoice-admin | `fast` | Cloud DeepSeek |

#### Walkthrough questions

> 1. The `_resolve_deepseek_auth` logic prints to console. Should it use `logging` instead? (Current: print is acceptable for CLI tools, but logging would let headless consumers suppress it.)
> 2. `complete_with_tools()` returns the raw litellm response object. Should it parse and return the tool call instead? (Current: consumers parse the response themselves.)
> 3. LM Studio local model support (`local` alias with `api_base` override) — should this be in `litellm.py` or `mlx.py`? LM Studio uses litellm's `openai/` provider under the hood.
> 4. Retry logic: decisionmaker retries 2x on `LLMError`. Should retry be built into the shared module or left to consumers?

#### Migration procedure (2B — litellm)

**1. Write agentkit code and tests:**
```bash
cd ~/Software/Prototypes/agentkit
# Write src/agentkit/llm/_litellm.py:
#   - DEFAULT_MODEL_ALIASES, resolve_model(), complete(), complete_with_tools()
#   - response_cost_usd(), log_fn callback plumbing
#   - _resolve_deepseek_auth() with 4-tier fallback + console reporting
# Update src/agentkit/llm/__init__.py to re-export complete, complete_with_tools, etc.
# Write tests/test_litellm.py (mock litellm, test alias resolution, auth fallback)
pip install -e ".[llm]"
python -m pytest tests/ -x -q
git add -A && git commit -m "agentkit: llm/litellm (complete + DeepSeek auth fallback)"
```

**2. Migrate email-digest:**
```bash
cd ~/Software/Prototypes/email-digest
# agentkit[llm] already in deps from 2A; verify:
pip install -e ~/Software/Prototypes/agentkit[llm]
# Replace src/email_digest/llm.py with re-export shim:
#   from agentkit.llm import (
#       DEFAULT_MODEL_ALIASES as MODEL_ALIASES,
#       complete, complete_with_tools, response_cost_usd,
#       resolve_model as _resolve_model,
#       _resolve_deepseek_auth,
#   )
# Keep email-digest-specific functions (MLX_MODEL_VARIANTS, SQLite logging) in
# a separate module or inline them. Wire log_fn to email-digest's SQLite logger.
python -m pytest tests/ -x -q
git add -A && git commit -m "shared-migration: llm/litellm — complete from agentkit"
```

**3. Migrate decisionmaker:**
```bash
cd ~/Software/Prototypes/decisionmaker
# agentkit already in deps from Milestone 1; add [llm] extra:
# Edit pyproject.toml: agentkit[llm]>=0.3.0
pip install -e ~/Software/Prototypes/agentkit[llm]
# Replace src/decisionmaker/core/llm.py with re-export shim:
#   from agentkit.llm import (
#       DEFAULT_MODEL_ALIASES as MODEL_ALIASES,
#       complete, complete_with_tools, response_cost_usd,
#       resolve_model as resolve_model_id,
#   )
#   from agentkit.llm._litellm import _resolve_deepseek_auth as _ensure_deepseek_env_from_opencode
python -m pytest tests/ -x -q
git add -A && git commit -m "shared-migration: llm/litellm — complete from agentkit"
```

**4. Migrate invoice-admin:**
```bash
cd ~/Software/Prototypes/invoice-admin
# Add [llm] extra to pyproject.toml
pip install -e ~/Software/Prototypes/agentkit[llm]
# In src/invoice_admin/core/llm.py:
#   Replace complete() body with call to agentkit.llm.complete()
#   Keep LLMProvider class as thin wrapper
#   Keep complete_with_pdf() (multimodal, not shared)
#   Wire log_fn to invoice-admin's SQLite log table
python -m pytest tests/ -x -q
git add -A && git commit -m "shared-migration: llm/litellm — LLMProvider wired to agentkit"
```

**5. Verify all projects:**
```bash
cd ~/Software/Prototypes/agentkit && python -m pytest tests/ -x -q
cd ~/Software/Prototypes/local-chat && python -c "from agentkit.llm import MlxLlm, complete; print('ok')"
cd ~/Software/Prototypes/decisionmaker && python -m pytest tests/ -x -q
cd ~/Software/Prototypes/email-digest && python -m pytest tests/ -x -q
cd ~/Software/Prototypes/invoice-admin && python -m pytest tests/ -x -q
```
**Exit criteria:** All 4 test suites pass. `from agentkit.llm import complete` works in every cloud consumer. DeepSeek auth prints source to console.

---

## Module 3 — `gmail/`

### User perspective

Gmail API client with Protocol-based testability. Fetch and search emails with minimal setup.

```python
from agentkit.gmail import GmailApiBackend, GmailFacade, GmailError

backend = GmailApiBackend()                          # creds from ~/.config/gmail_token.json
client = GmailFacade(backend)

body = client.get_message("message_id_123")          # returns plaintext body
results = client.search("from:user@example.com", max_results=5)
# → [{"id": "...", "threadId": "..."}, ...]
```

Inject a mock backend for tests:
```python
class FakeBackend:
    def fetch_message_body(self, msg_id): return "fake body"
    def search_messages(self, query, max_results): return [{"id": "1", "threadId": "t1"}]

client = GmailFacade(FakeBackend())
```

### Technical

| | |
|---|---|
| **Master source** | `invoice-admin/src/invoice_admin/googleads/gmail_api_backend.py` (286 lines) |
| **Also in** | `decisionmaker/src/decisionmaker/core/gmail.py` (267 lines), `email-digest` (via unsubscribe) |
| **Consumers** | invoice-admin, decisionmaker, email-digest |
| **Dependencies** | `google-api-python-client>=2.0`, `google-auth>=2.0` |
| **Target** | `src/agentkit/gmail/_client.py`, `src/agentkit/gmail/__init__.py` |

**What ships:**
- `GmailBackend` Protocol — pluggable backend interface (2 methods)
- `GmailApiBackend` — real Gmail API implementation
- `GmailFacade` — wraps backend with error handling
- `_extract_body_from_payload(payload) → str` — MIME parsing, base64 decode, HTML→plaintext
- `clean_email_body(raw) → str` — strip quotes, forward blocks, German/English sign-offs
- `resolve_spec_to_message(client, spec, *, pick_index) → (msg_id, body)` — message ID or Gmail search query resolver

**Exception hierarchy:**
- `GmailError` — base
- `GmailAuthError` — credentials failure
- `GmailMessageNotFoundError` — 404 on message fetch

**What does NOT ship:**
- Gmail query builder — 60-line duplicate across 2 repos, each keeps their copy (trivial, not worth the dependency)
- SMTP send — stays in invoice-admin
- `GmailClient.from_env()` — each consumer wraps as needed

### Walkthrough questions

> 1. `clean_email_body()` strips German sign-offs (Mit freundlichen Grüßen, etc.). Should sign-off patterns be parameterized or is German+English the universal default?
> 2. `resolve_spec_to_message()` is decisionmaker-specific (message ID vs query resolution). Does this belong in gmail/ or is it an orchestrator concern?
> 3. The credential loading defaults to `~/.config/gmail_token.json`. Should this path be configurable or is the default sufficient?

### Migration procedure

**1. Write agentkit code and tests:**
```bash
cd ~/Software/Prototypes/agentkit
# Copy invoice-admin's GmailApiBackend → src/agentkit/gmail/_client.py
# Strip invoice-admin imports (errors.py), add GmailError/GmailAuthError/GmailMessageNotFoundError locally
# Include: GmailBackend Protocol, GmailFacade, GmailApiBackend, _extract_body_from_payload, clean_email_body, resolve_spec_to_message
# Write src/agentkit/gmail/__init__.py re-exports
# Write tests/test_gmail.py (mock googleapiclient, test payload decoding, body cleaning, message resolution)
pip install -e ".[gmail]"
python -m pytest tests/ -x -q
git add -A && git commit -m "agentkit: gmail/ (Protocol + Facade + Backend)"
```

**2. Migrate invoice-admin (master — keep domain code):**
```bash
cd ~/Software/Prototypes/invoice-admin
pip install -e ~/Software/Prototypes/agentkit[gmail]
# In src/invoice_admin/googleads/gmail_api_backend.py → re-export shim:
#   from agentkit.gmail import GmailApiBackend, GmailBackend, GmailError
# In src/invoice_admin/googleads/gmail_facade.py → re-export shim:
#   from agentkit.gmail import GmailFacade
# Keep gmail_smtp.py (SMTP send is invoice-admin-specific)
python -m pytest tests/ -x -q
git add -A && git commit -m "shared-migration: gmail — shim from agentkit"
```

**3. Migrate decisionmaker:**
```bash
cd ~/Software/Prototypes/decisionmaker
pip install -e ~/Software/Prototypes/agentkit[gmail]
# Replace src/decisionmaker/core/gmail.py with re-export shim:
#   from agentkit.gmail import (
#       GmailApiBackend as GmailClient,
#       GmailFacade, resolve_spec_to_message,
#       clean_email_body, GmailError, GmailAuthError, GmailMessageNotFoundError,
#   )
# If GmailClient.from_env() is used, add thin wrapper:
#   class GmailClient(GmailApiBackend):
#       @classmethod
#       def from_env(cls): return cls()
python -m pytest tests/ -x -q
git add -A && git commit -m "shared-migration: gmail — shim from agentkit"
```

**4. Migrate email-digest:**
```bash
cd ~/Software/Prototypes/email-digest
pip install -e ~/Software/Prototypes/agentkit[gmail]
# Replace unsubscribe/gmail_api_backend.py and unsubscribe/gmail_facade.py with re-exports
# Orig imports through facade → pipeline.py/cli.py unchanged
python -m pytest tests/ -x -q
git add -A && git commit -m "shared-migration: gmail — shim from agentkit"
```

**5. Verify all projects:**
```bash
cd ~/Software/Prototypes/agentkit && python -m pytest tests/ -x -q
cd ~/Software/Prototypes/invoice-admin && python -m pytest tests/ -x -q
cd ~/Software/Prototypes/decisionmaker && python -m pytest tests/ -x -q
cd ~/Software/Prototypes/email-digest && python -m pytest tests/ -x -q
```
**Exit criteria:** All 3 test suites pass. `from agentkit.gmail import GmailFacade` works in every project.

---

## Module 4 — `speech/`

### User perspective

Selenium helpers for Brave/Chrome browser automation on macOS. Attach to an already-running browser (no driver management).

```python
from agentkit.browser import attach_brave_browser, default_chrome_options

driver = attach_brave_browser(debugger_address="127.0.0.1:9222")
# ... use Selenium normally ...
driver.quit()
```

### Technical

| | |
|---|---|
| **Master source** | `invoice-admin/src/invoice_admin/googleads/browser_download.py` |
| **Also in** | `email-digest/src/unsubscribe/browser_unsubscribe.py` (Selenium WebDriver usage) |
| **Consumers** | invoice-admin, email-digest |
| **Dependencies** | `selenium` |
| **Target** | `src/agentkit/browser/_browser.py`, `src/agentkit/browser/__init__.py` |

**What ships:**
- `attach_brave_browser(debugger_address="127.0.0.1:9222") → WebDriver` — attach to running Brave
- `default_chrome_options() → Options` — common Chrome options for automation (headless, user data dir, etc.)
- `chrome_driver_attach(debugger_address) → WebDriver` — generic Chrome-family attachment

**What does NOT ship:**
- Google Ads-specific download logic (invoice-admin domain)
- Unsubscribe page confirmation logic (email-digest domain)
- Playwright helpers (invoice-admin uses Playwright separately for Foyer claims)

### Walkthrough questions

> 1. Invoice-admin uses both Selenium (Google Ads) and Playwright (Foyer claims). Email-digest uses only Selenium. Should Playwright helpers be extracted too?
> 2. The `debugger_address` pattern requires the user to start Brave with `--remote-debugging-port=9222`. Should the module include a launcher helper?
> 3. Should this be `browser/` or a flat `browser.py`? (Single file, ~150 lines — subpackage might be overkill.)

### Migration procedure

**1. Write agentkit code and tests:**
```bash
cd ~/Software/Prototypes/agentkit
# Extract from invoice-admin/src/invoice_admin/googleads/browser_download.py:
#   - attach_brave_browser(), chrome_driver_attach(), default_chrome_options()
# Write → src/agentkit/browser/_browser.py
# Write src/agentkit/browser/__init__.py re-exports
# Write tests/test_browser.py (import functions, no live browser — mock selenium)
pip install -e ".[all]"
python -m pytest tests/ -x -q
git add -A && git commit -m "agentkit: browser/ (Selenium Brave attach + utils)"
```

**2. Migrate invoice-admin (master):**
```bash
cd ~/Software/Prototypes/invoice-admin
pip install -e ~/Software/Prototypes/agentkit[browser]
# Replace src/invoice_admin/googleads/browser_download.py with re-export shim:
#   from agentkit.browser import attach_brave_browser, chrome_driver_attach, default_chrome_options
# Update callers (run_month.py, live_brave_download.py) to import from agentkit.browser
python -m pytest tests/ -x -q
git add -A && git commit -m "shared-migration: browser — shim from agentkit"
```

**3. Migrate email-digest:**
```bash
cd ~/Software/Prototypes/email-digest
pip install -e ~/Software/Prototypes/agentkit[browser]
# In unsubscribe/browser_unsubscribe.py, replace Selenium WebDriver attachment with:
#   from agentkit.browser import attach_brave_browser
# Keep unsubscribe-specific page confirmation logic
python -m pytest tests/ -x -q
git add -A && git commit -m "shared-migration: browser — WebDriver from agentkit"
```

**4. Verify all projects:**
```bash
cd ~/Software/Prototypes/agentkit && python -m pytest tests/ -x -q
cd ~/Software/Prototypes/invoice-admin && python -m pytest tests/test_browser_download.py -x -q
cd ~/Software/Prototypes/email-digest && python -m pytest tests/ -x -q
```
**Exit criteria:** Both test suites pass. `from agentkit.browser import attach_brave_browser` works in both projects.

---

## Module 5 — `browser/`

### User perspective

Text-to-speech via MLX Kokoro-82M. Lazy-loads the model on first use.

```python
from agentkit.speech import MlxTts, KOKORO_VOICES, KOKORO_DEFAULT_VOICE

tts = MlxTts()
tts.load()
audio, sample_rate = tts.synthesize("Hello world", voice="af_heart")
tts.synthesize_to_file("Hello world", "/tmp/out.wav", voice="af_heart")
```

### Technical

| | |
|---|---|
| **Master source** | `local-chat/src/tts.py` (109 lines) |
| **Consumers** | local-chat, decisionmaker |
| **Dependencies** | `mlx-audio>=0.3.0`, `numpy`, `soundfile` |
| **Lines** | ~109 |
| **Target** | `src/agentkit/speech/_tts.py`, `src/agentkit/speech/__init__.py` |

**What ships:**
- `MlxTts` class — lazy-loading wrapper around Kokoro-82M
- `KOKORO_MODEL_ID`, `KOKORO_VOICES`, `KOKORO_DEFAULT_VOICE`, `KOKORO_VOICE_DESCRIPTIONS`
- `synthesize(text, voice) → (np.ndarray, sample_rate)`
- `synthesize_to_file(text, path, voice) → float` (duration seconds)

**What does NOT ship:**
- No `speak_synthesis()` convenience function (that's local-chat's orchestrator logic — stays in local-chat)

**Current state in consumers:**
- `local-chat/src/tts.py` — canonical, self-contained
- `decisionmaker/src/decisionmaker/render/tts.py` — does `sys.path.insert` + imports from local-chat. Also has duplicated voice constants.

**Migration:**
- local-chat: re-export shim `from agentkit.speech import *`
- decisionmaker: delete `render/tts.py` entirely. Inline the 5-line speak logic in `cli.py`.

### Walkthrough questions

> 1. Decisionmaker currently uses `sys.path.insert` to import from local-chat. After extraction, both import from agentkit. Any circular dependency risk?
> 2. Should voice constants stay in `tts.py` or move to a separate data file?
> 3. Kokoro is only one TTS model. If local-chat adds another (e.g., Orpheus), does the module stay flat or split?

### Migration procedure

**1. Write agentkit code and tests:**
```bash
cd ~/Software/Prototypes/agentkit
# Copy local-chat/src/tts.py → src/agentkit/speech/_tts.py (as-is, no changes needed)
# Write src/agentkit/speech/__init__.py re-exports:
#   from agentkit.speech._tts import MlxTts, KOKORO_VOICES, KOKORO_DEFAULT_VOICE, KOKORO_VOICE_DESCRIPTIONS
# Write tests/test_tts.py (import class and constants, no model loading)
pip install -e ".[speech]"
python -m pytest tests/test_tts.py -x -q
git add -A && git commit -m "agentkit: speech/tts (MlxTts + Kokoro)"
```

**2. Migrate local-chat (canonical source):**
```bash
cd ~/Software/Prototypes/local-chat
pip install -e ~/Software/Prototypes/agentkit[speech]
# Replace src/tts.py with re-export shim:
#   from agentkit.speech import MlxTts, KOKORO_VOICES, KOKORO_DEFAULT_VOICE, KOKORO_VOICE_DESCRIPTIONS
# All callers (improv_loop.py, improv.py) continue working via shim
python -c "from src.tts import MlxTts; print('ok')"
# Delete src/tts.py, update callers to import from agentkit.speech
python improv.py  # live TTS smoke test
git add -A && git commit -m "shared-migration: tts — MlxTts from agentkit"
```

**3. Migrate decisionmaker:**
```bash
cd ~/Software/Prototypes/decisionmaker
pip install -e ~/Software/Prototypes/agentkit[speech]
# Delete src/decisionmaker/render/tts.py entirely
# In cli.py, replace _speak_synthesis():
#   from agentkit.speech import MlxTts
#   tts = MlxTts(); tts.load()
#   audio, sr = tts.synthesize(synthesis, voice=voice)
#   import sounddevice as sd; sd.play(audio, samplerate=sr); sd.wait()
# Replace voice constant imports:
#   from agentkit.speech import KOKORO_DEFAULT_VOICE, KOKORO_VOICES
python -m pytest tests/ -x -q
git add -A && git commit -m "shared-migration: tts — MlxTts inlined from agentkit"
```

**4. Verify all projects:**
```bash
cd ~/Software/Prototypes/agentkit && python -m pytest tests/ -x -q
cd ~/Software/Prototypes/local-chat && python -c "from agentkit.speech import MlxTts; print('ok')"
cd ~/Software/Prototypes/decisionmaker && python -m pytest tests/ -x -q
```
**Exit criteria:** Both projects pass. `from agentkit.speech import MlxTts` works everywhere.

---

## Per-consumer migration summary

```
local-chat:
    agentkit[speech,llm]
    from agentkit.speech import MlxTts, KOKORO_VOICES
    from agentkit.llm import MlxLlm
    Removes: src/tts.py, src/llm.py
    Default: local MLX models

decisionmaker:
    agentkit[core,llm,gmail,speech]
    from agentkit.core import repo_root, LLMFailureWithTranscript
    from agentkit.llm import complete, complete_with_tools
    from agentkit.gmail import GmailFacade, GmailApiBackend
    from agentkit.speech import MlxTts
    Removes: core/llm.py, core/gmail.py, core/gmail_query.py, common.py, render/tts.py
    Default: cloud DeepSeek

email-digest:
    agentkit[core,llm,gmail,browser]
    from agentkit.core import repo_root
    from agentkit.llm import complete
    from agentkit.gmail import GmailApiBackend
    from agentkit.browser import attach_brave_browser
    Removes: llm.py, gmail_api_backend.py, gmail_facade.py, paths.py, gmail_query.py
    Default: cloud DeepSeek

invoice-admin:
    agentkit[core,llm,gmail,browser]
    from agentkit.core import repo_root, AgentError
    from agentkit.llm import complete
    from agentkit.gmail import GmailApiBackend, GmailFacade
    from agentkit.browser import attach_brave_browser
    Removes: core/llm.py, googleads/gmail_api_backend.py, googleads/gmail_facade.py, browser_download.py
    Default: cloud DeepSeek

swim:
    agentkit[core]
    from agentkit.core import repo_root
    Removes: core/common.py (repo_root only, keeps swim-specific functions)
    Default: N/A (no LLM)
```

---

## Test checklist

After each module, run test suites in all affected repos:

```bash
# agentkit itself
cd ~/Software/Prototypes/agentkit
python -m pytest tests/ -x -q

# decisionmaker (52 tests)
cd ~/Software/Prototypes/decisionmaker
python -m pytest tests/ -x -q

# email-digest
cd ~/Software/Prototypes/email-digest
python -m pytest tests/ -x -q

# invoice-admin
cd ~/Software/Prototypes/invoice-admin
python -m pytest tests/ -x -q

# local-chat (no test suite — smoke test)
cd ~/Software/Prototypes/local-chat
python -c "from agentkit.speech import MlxTts; from agentkit.llm import MlxLlm; print('ok')"

# swim (no test suite — smoke test)
cd ~/Software/Prototypes/swim
python -c "from agentkit.core import repo_root; print(repo_root())"
```

---

## Rollback per module

Every module is independently reversible:

1. **During migration:** old file exists as a re-export shim. All callers work.
2. **If tests fail:** revert the shim to the original file content (from git).
3. **After successful migration:** delete the shim in a separate commit.

```bash
cd ~/Software/Prototypes/<project>
# if anything fails:
git checkout main -- src/path/to/broken_file.py
```

---

## Versioning

| Version | Milestone |
|---------|-----------|
| 0.1.0 | Phase 0 skeleton (done) |
| 0.2.0 | `core/` (repo_root + errors) |
| 0.3.0 | `llm/` (mlx + litellm, breaking for 3 consumers) |
| 0.4.0 | `gmail/` |
| 0.5.0 | `browser/` |
| 0.6.0 | `speech/tts` |
| 0.7.0 | All shims deleted from consuming repos |
| 1.0.0 | All 5 projects migrated |
