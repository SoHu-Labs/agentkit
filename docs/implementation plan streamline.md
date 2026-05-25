# streamline.md — agentkit skills + cross-repo streamlining (implementation guide)

This is a **literal, do-exactly-this** implementation guide. Follow the tasks
**in order**. After every code change, run the stated command. **If a test is
red and the task did not say "expect red", stop and fix before continuing.**
Do not refactor anything not named here. Do not change axis ranges, schemas,
colors, or any user-visible output (see `/Users/chaehan/CLAUDE.md` scope rules).

The repos involved (all under `/Users/chaehan/Software/Prototypes/`):
`agentkit` (the library), `email-digest`, `invoice-admin`, `decisionmaker`,
`swim` (consumers).

---

## 0. Background (read once, then start)

`agentkit` is a Python library installed editable into each consumer. Consumers
do `from agentkit.<module> import ...`. We are **keeping the library** (it is the
right design). We are only:

- **Part A**: adding *Agent Skills* (SKILL.md runbooks) under `agentkit/skills/`.
  These help the coding agent operate the repos. They do **not** change any
  consumer's runtime imports.
- **Part B**: small refactors to remove duplication and pin versions.

The key fact you must rely on: `agentkit.llm.complete()` already:
- resolves auth (opencode-go key, then personal DeepSeek key) — see
  `src/agentkit/llm/_litellm.py` functions `_get_go_api_key` /
  `_get_personal_deepseek_key`;
- accepts `aliases=<dict>` and `log_fn=<callable>`; after each call it invokes
  `log_fn(record)` where `record` is exactly:
  `{"alias", "model", "input_tokens", "output_tokens", "cost_usd", "duration_ms", "error"}`.

### Environment setup (do this first)
```bash
# Install agentkit editable so consumers can import it locally.
cd /Users/chaehan/Software/Prototypes/agentkit
pip install -e ".[llm]"
# Each consumer is run from its own folder with: python -m pytest -q
```

### Execution order
T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8. T1/T2 are agentkit library changes that
later tasks depend on. Do them first.

---

## Pre-implementation Q&A (answered — read before T8/T6/C5/C6)

Five issues were raised against the first draft. All five were checked against the
actual source. Answers below are authoritative; the inline task code further down
has been corrected to match.

**Q1 — Skill 2 `gmail_fetch.py` accesses fields that don't exist.**
`resolve_spec_to_message(backend, spec, *, pick_index=0)` returns
`tuple[str, str]` = `(message_ref, body)` (verified `src/agentkit/gmail/_client.py:245`).
There is **no message object and no subject** — Gmail subject is not fetched by
this API at all. (`getattr(a_tuple, "subject", "?")` would not raise — it would
silently return `"?"` — so the script wouldn't crash, it would just print
garbage.) **Fix:** unpack the tuple, drop the subject line, print the ref + cleaned
body:
```python
    msg_ref, body = resolve_spec_to_message(backend, spec)
    print(f"message: {msg_ref}")
    print(clean_email_body(body)[:500])
```
The Skill 2 script block below has been updated to this.

**Q2 — Skill 3 `brave_attach.py` calls two functions wrong.** Verified against
`src/agentkit/browser/_browser.py`:
- `build_chrome_options_for_remote_debugging(*, debugger_address, download_dir=None)`
  — `debugger_address` is keyword-only and **required**; calling it with no args
  raises `TypeError`.
- `chrome_driver_attach(*, debugger_address, download_dir=None)` — all args are
  keyword-only, and it **builds the options internally** (line 117). Passing
  `options` positionally raises `TypeError`.

**Fix:** don't build options separately at all. `ensure_brave_running` already
defaults its address to `127.0.0.1:9222`; reuse that one address constant:
```python
    ensure_brave_running(_ADDR)
    driver = chrome_driver_attach(debugger_address=_ADDR)
```
The Skill 3 script block below has been updated (and its
`build_chrome_options_for_remote_debugging` import removed).

**Q3 — C5 (Gmail unification): explore first, do NOT auto-unify.** The four
duplicate files are 409 / 60 / 286 / 62 LOC. The two large ones almost certainly
carry behavior agentkit's read-only backend does **not** have (OAuth bootstrap,
SMTP send, custom spec syntax). Treat C5 as a **separate analysis task**: read
each file, diff its public surface against `src/agentkit/gmail/`, and report a
concrete per-file plan (port-into-agentkit / re-export / leave-as-is) **before**
editing. No blind extraction. C5 stays out of the core T1–T7 pass.

**Q4 — C6 (shared `LLMProvider`): explore first, and it's optional.** No
implementation code is given because the right generalization depends on what
invoice-admin's `LLMProvider` actually does. **Recommendation:** skip for the
first pass. If wanted, do a focused design pass that reports the proposed
`agentkit.llm.LLMProvider` API + the invoice-admin subclass shape before coding.
Not required for T1–T7 to land.

**Q5 — T6 tag: use `v0.1.0` as written, no bump needed.** Verified:
`pyproject.toml` version is `0.1.0`, and `git ls-remote --tags origin`
(`SoHu-Labs/agentkit`) returns **no tags** — `v0.1.0` does not exist on the
remote. Tag and push `v0.1.0`; use `v0.1.0` in all three CI refs and the
vendor-bump example. Only bump to `v0.1.1` if a tag collision appears at push
time.

---

## Part B — refactors

### T1 — Expose public auth readers in agentkit (B2 library side)

**Goal:** make agentkit's two private auth helpers public so consumers stop
re-implementing them. Do **not** rename or delete the private ones (agentkit's
own tests import the private names).

**Step 1 (red): add a test.** Append to
`/Users/chaehan/Software/Prototypes/agentkit/tests/test_llm_litellm.py` (at end
of file):
```python
class TestPublicAuthReaders:
    def test_public_names_are_the_private_impls(self):
        from agentkit.llm import get_go_api_key, get_personal_deepseek_key
        from agentkit.llm._litellm import _get_go_api_key, _get_personal_deepseek_key
        assert get_go_api_key is _get_go_api_key
        assert get_personal_deepseek_key is _get_personal_deepseek_key
```
Run (expect **red** — ImportError):
```bash
cd /Users/chaehan/Software/Prototypes/agentkit && python -m pytest tests/test_llm_litellm.py::TestPublicAuthReaders -q
```

**Step 2 (green): implement.**

(a) In `src/agentkit/llm/_litellm.py`, add two module-level aliases immediately
**after** the `_get_personal_deepseek_key` function definition (after its
`return None`, around line 91):
```python


# Public aliases (consumers import these instead of re-implementing auth readers)
get_go_api_key = _get_go_api_key
get_personal_deepseek_key = _get_personal_deepseek_key
```

(b) In `src/agentkit/llm/__init__.py`, edit the lazy `__getattr__` so the name
tuple and the import include the two new names. Replace the whole `__getattr__`
function with:
```python
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
```

Run (expect **green**):
```bash
cd /Users/chaehan/Software/Prototypes/agentkit && python -m pytest tests/test_llm_litellm.py -q
```

**Done when:** the new test passes and the rest of `test_llm_litellm.py` still
passes.

---

### T2 — Add `SqliteCallLogger` to agentkit (B4 library side)

**Goal:** a reusable, `log_fn`-compatible SQLite logger for the canonical
`complete()` record, with optional extra columns.

**Step 1 (red): add a test file.** Create
`/Users/chaehan/Software/Prototypes/agentkit/tests/test_llm_logging.py`:
```python
"""Tests for agentkit.llm.SqliteCallLogger."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _record(**over):
    base = {
        "alias": "fast",
        "model": "deepseek/deepseek-v4-flash",
        "input_tokens": 10,
        "output_tokens": 5,
        "cost_usd": 0.001,
        "duration_ms": 12.5,
        "error": None,
    }
    base.update(over)
    return base


def test_logger_creates_table_and_inserts(tmp_path: Path):
    from agentkit.llm import SqliteCallLogger
    db = tmp_path / "calls.sqlite"
    logger = SqliteCallLogger(db)
    logger(_record())
    rows = sqlite3.connect(str(db)).execute(
        "SELECT alias, model, input_tokens, output_tokens, cost_usd, error FROM llm_calls"
    ).fetchall()
    assert rows == [("fast", "deepseek/deepseek-v4-flash", 10, 5, 0.001, None)]


def test_logger_extra_columns(tmp_path: Path):
    from agentkit.llm import SqliteCallLogger
    db = tmp_path / "calls.sqlite"
    logger = SqliteCallLogger(db, extra_columns={"handler": "TEXT", "purpose": "TEXT"})
    logger(_record(handler="sepa", purpose="extract"))
    row = sqlite3.connect(str(db)).execute(
        "SELECT handler, purpose FROM llm_calls"
    ).fetchone()
    assert row == ("sepa", "extract")


def test_logger_is_idempotent_across_instances(tmp_path: Path):
    from agentkit.llm import SqliteCallLogger
    db = tmp_path / "calls.sqlite"
    SqliteCallLogger(db)(_record())
    SqliteCallLogger(db)(_record())  # second instance must not crash on CREATE
    n = sqlite3.connect(str(db)).execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0]
    assert n == 2


def test_logger_rejects_bad_identifier(tmp_path: Path):
    from agentkit.llm import SqliteCallLogger
    with pytest.raises(ValueError):
        SqliteCallLogger(tmp_path / "x.sqlite", table="bad name;DROP")
```
Run (expect **red**):
```bash
cd /Users/chaehan/Software/Prototypes/agentkit && python -m pytest tests/test_llm_logging.py -q
```

**Step 2 (green): implement.** Create
`/Users/chaehan/Software/Prototypes/agentkit/src/agentkit/llm/_logging.py`:
```python
"""SQLite logger for agentkit.llm.complete() call records (optional, opt-in)."""
from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Any

# Canonical columns produced by complete()'s log_fn record.
_CANONICAL_COLUMNS: dict[str, str] = {
    "alias": "TEXT",
    "model": "TEXT",
    "input_tokens": "INTEGER",
    "output_tokens": "INTEGER",
    "cost_usd": "REAL",
    "duration_ms": "REAL",
    "error": "TEXT",
}

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _check_ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


class SqliteCallLogger:
    """Callable that logs a complete() record to a SQLite table.

    Pass an instance as ``log_fn`` to ``agentkit.llm.complete``. The table is
    created on first use with the canonical columns plus any ``extra_columns``
    (a ``{name: sql_type}`` mapping). Extra column values are read from matching
    keys in the record, so callers stuff e.g. ``record["handler"]`` themselves.
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        table: str = "llm_calls",
        extra_columns: dict[str, str] | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._table = _check_ident(table)
        self._extra = {_check_ident(k): v for k, v in (extra_columns or {}).items()}
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path))
            cols = {**_CANONICAL_COLUMNS, **self._extra}
            col_defs = ", ".join(f"{name} {decl}" for name, decl in cols.items())
            self._conn.execute(
                f"CREATE TABLE IF NOT EXISTS {self._table} "
                f"(id INTEGER PRIMARY KEY AUTOINCREMENT, {col_defs}, "
                f"created_at TEXT NOT NULL)"
            )
            self._conn.commit()
        return self._conn

    def __call__(self, record: dict[str, Any]) -> None:
        conn = self._connect()
        cols = list(_CANONICAL_COLUMNS) + list(self._extra)
        created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        values = [record.get(c) for c in cols] + [created]
        col_names = ", ".join(cols + ["created_at"])
        placeholders = ", ".join("?" for _ in range(len(cols) + 1))
        conn.execute(
            f"INSERT INTO {self._table} ({col_names}) VALUES ({placeholders})",
            values,
        )
        conn.commit()
```

Then export it from `src/agentkit/llm/__init__.py`. Add this import line directly
below the existing `from agentkit.llm._mlx import ...` line at the top
(it is stdlib-only, safe to import eagerly):
```python
from agentkit.llm._logging import SqliteCallLogger
```
And add `"SqliteCallLogger"` to the `__all__` list at the bottom so it becomes:
```python
__all__ = [
    "MlxLlm",
    "MODEL_VARIANTS",
    "DEFAULT_MODEL_PATH",
    "SqliteCallLogger",
]
```

Run (expect **green**):
```bash
cd /Users/chaehan/Software/Prototypes/agentkit && python -m pytest -q
```

**Done when:** all agentkit tests pass.

---

### T3 — Retire email-digest's duplicate auth readers (B2 consumer side)

**Context:** `email-digest/src/email_digest/llm.py` re-implements opencode/deepseek
key reading that agentkit already owns. Those functions are used **only by
email-digest's own tests** (verified by grep), never by production code. We
remove them and delete the now-redundant tests (agentkit's `test_llm_litellm.py`
already covers the same behavior via `TestGoApiKey` / `TestPersonalDeepSeekKey`).

**Step 1: edit `src/email_digest/llm.py`.**
Delete these blocks **entirely**:
- the constant `_OPENCODE_AUTH_PATH = ...` (line ~32),
- `def _opencode_auth_json_path()` (lines ~35–36),
- `def _read_opencode_zen_auth_key()` (lines ~39–54),
- `def read_deepseek_key_from_opencode_auth_files()` (lines ~57–72).

**Keep** `_MODELS`, `MLX_MODEL_VARIANTS`, `MODEL_ALIASES`, `resolve_model_alias`,
`_log_to_sqlite`, and `complete` unchanged.

**Step 2: fix the coupled tests.**

(a) `email-digest/tests/test_llm_env.py`:
- Change the import on line 10 from
  `from email_digest.llm import complete, read_deepseek_key_from_opencode_auth_files`
  to
  `from email_digest.llm import complete`.
- **Delete** the whole test function `test_read_deepseek_from_opencode_auth_json`
  (lines ~25–34). (Reason: it tested the removed function; agentkit's
  `TestPersonalDeepSeekKey.test_deepseek_block` covers it.)
- Keep `test_complete_raises_clear_error_when_deepseek_key_missing` and
  `test_complete_uses_opencode_when_env_empty` unchanged — they patch
  `agentkit.llm._litellm._AUTH_PATH` and still pass.

(b) `email-digest/tests/test_llm_resolve_alias.py`:
- Change the import (lines 9–14) to drop `_read_opencode_zen_auth_key`:
  ```python
  from email_digest.llm import (
      MLX_MODEL_VARIANTS,
      MODEL_ALIASES,
      resolve_model_alias,
  )
  ```
- **Delete** all six `test_read_opencode_zen_auth_key_*` functions (lines ~48–98).
  (Reason: redundant with agentkit's `TestGoApiKey`.)
- Keep all `resolve_model_alias` / `test_resolve_*` tests unchanged.

**Step 3: run the email-digest suite.**
```bash
cd /Users/chaehan/Software/Prototypes/email-digest
pip install -e /Users/chaehan/Software/Prototypes/agentkit  # ensure latest agentkit
python -m pytest -q
```
**Done when:** the full email-digest suite is green and `email_digest/llm.py`
no longer mentions opencode/deepseek key reading.

---

### T4 — Fold invoice-admin `complete_with_pdf` onto agentkit (B3)

**Context:** `invoice-admin/src/invoice_admin/core/llm.py` method
`complete_with_pdf` (lines ~162–229) calls `litellm.completion` **directly**,
skipping agentkit's auth fallback and central logging. Route it through
`agentkit.llm.complete` instead (already imported as `_agentkit_complete`).

**Step 1 (red): add a test.** Create
`/Users/chaehan/Software/Prototypes/invoice-admin/tests/test_llm_pdf_via_agentkit.py`:
```python
"""complete_with_pdf must route through agentkit.complete (auth + logging)."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from invoice_admin.core.llm import LLMProvider


def test_complete_with_pdf_uses_agentkit_and_logs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENCODE_API_KEY", "sk-test")

    class _U:
        prompt_tokens = 7
        completion_tokens = 3
        total_tokens = 10

    class _Msg:
        content = "PDF-OK"

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]
        usage = _U()

    captured: dict[str, Any] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _Resp()

    monkeypatch.setattr("agentkit.llm._litellm.litellm.completion", fake_completion)
    monkeypatch.setattr(
        "agentkit.llm._litellm.litellm.completion_cost", lambda **_: 0.002
    )

    log = tmp_path / "llm_calls.sqlite"
    provider = LLMProvider(log_path=log)
    out = provider.complete_with_pdf(
        "extract", b"%PDF-1.4 fake", model_alias="smart", handler="t", purpose="p"
    )

    assert out == "PDF-OK"
    # routed through agentkit -> the multimodal message reached litellm
    assert isinstance(captured.get("messages"), list)
    # logged a row with the captured cost
    row = sqlite3.connect(str(log)).execute(
        "SELECT cost_usd, handler, purpose FROM llm_calls"
    ).fetchone()
    assert row == (0.002, "t", "p")
```
Run (expect **red**):
```bash
cd /Users/chaehan/Software/Prototypes/invoice-admin
pip install -e /Users/chaehan/Software/Prototypes/agentkit
python -m pytest tests/test_llm_pdf_via_agentkit.py -q
```

**Step 2 (green): replace the method body.** In
`src/invoice_admin/core/llm.py`, replace the entire `complete_with_pdf` method
(lines ~162–229) with:
```python
    def complete_with_pdf(
        self,
        prompt: str,
        pdf_bytes: bytes,
        model_alias: str = "fast",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        handler: str = "unknown",
        purpose: str = "general",
    ) -> str:
        import base64

        self._init_log()
        t0 = time.perf_counter()
        err: str | None = None
        text = ""
        model = model_alias
        record_data: dict[str, Any] = {}

        def _log_fn(log_rec: dict[str, Any]) -> None:
            nonlocal record_data
            record_data = log_rec

        try:
            b64 = base64.b64encode(pdf_bytes).decode("ascii")
            messages: list[dict[str, Any]] = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:application/pdf;base64,{b64}"},
                        },
                    ],
                }
            ]
            text = _agentkit_complete(
                messages,
                alias=model_alias,
                max_tokens=max_tokens,
                temperature=temperature,
                aliases=self._aliases,
                log_fn=_log_fn,
            )
            model = record_data.get("model", model_alias)
            return text
        except Exception as e:
            err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            raise
        finally:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            self._log_call(
                LLMCallRecord(
                    model=model,
                    prompt_tokens=record_data.get("input_tokens", 0),
                    completion_tokens=record_data.get("output_tokens", 0),
                    cost_usd=record_data.get("cost_usd", 0.0),
                    duration_ms=duration_ms,
                    handler=handler,
                    purpose=purpose,
                    success=err is None,
                    error=err,
                )
            )
```
Notes:
- Do **not** touch the `from agentkit.llm import (...)` block at the top. The
  now-unused `resolve_model` / `response_cost_usd` imports are harmless (mypy
  does not flag unused imports) and may be re-exported elsewhere — leave them.
- Do **not** change the existing `LLMCallRecord`, `_LOG_SCHEMA`, `complete`,
  `complete_with_pdf` signature, or `format_llm_cost_report`. The SQLite schema
  is unchanged.

**Step 3 (verify): run the full invoice-admin suite.**
```bash
cd /Users/chaehan/Software/Prototypes/invoice-admin && python -m pytest -q
```
**Caveat to flag to the human (do not auto-decide):** the model that
`model_alias` resolves to must accept a `data:application/pdf` content block. If
the live PDF path later returns errors, that is a model-capability question, not
a regression from this change.

**Done when:** the new test passes and the full suite is green.

---

### T5 — Adopt `SqliteCallLogger` in decisionmaker (B4 consumer side)

**Context:** `decisionmaker/src/decisionmaker/core/llm.py` does no logging today.
Add **opt-in** logging that is disabled unless the env var
`DECISIONMAKER_LLM_LOG` (a SQLite path) is set. Default behavior is unchanged.

**Step 1 (red): add a test.** Create
`/Users/chaehan/Software/Prototypes/decisionmaker/tests/test_llm_logging_optin.py`:
```python
"""decisionmaker.core.llm logs to SQLite only when DECISIONMAKER_LLM_LOG is set."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from decisionmaker.core.llm import complete


def _patch_litellm(monkeypatch):
    class _Msg:
        content = "ok"

    class _Choice:
        message = _Msg()

    class _U:
        prompt_tokens = 2
        completion_tokens = 1
        total_tokens = 3

    class _Resp:
        choices = [_Choice()]
        usage = _U()

    monkeypatch.setenv("OPENCODE_API_KEY", "sk-test")
    monkeypatch.setattr(
        "agentkit.llm._litellm.litellm.completion", lambda **k: _Resp()
    )
    monkeypatch.setattr(
        "agentkit.llm._litellm.litellm.completion_cost", lambda **k: 0.003
    )


def test_logs_when_env_set(tmp_path: Path, monkeypatch):
    _patch_litellm(monkeypatch)
    db = tmp_path / "calls.sqlite"
    monkeypatch.setenv("DECISIONMAKER_LLM_LOG", str(db))
    assert complete([{"role": "user", "content": "hi"}], alias="fast") == "ok"
    n = sqlite3.connect(str(db)).execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0]
    assert n == 1


def test_no_log_when_env_unset(monkeypatch):
    _patch_litellm(monkeypatch)
    monkeypatch.delenv("DECISIONMAKER_LLM_LOG", raising=False)
    assert complete([{"role": "user", "content": "hi"}], alias="fast") == "ok"
```
Run (expect **red**):
```bash
cd /Users/chaehan/Software/Prototypes/decisionmaker
pip install -e /Users/chaehan/Software/Prototypes/agentkit
python -m pytest tests/test_llm_logging_optin.py -q
```

**Step 2 (green): edit `src/decisionmaker/core/llm.py`.** Replace the whole file
with:
```python
"""litellm-backed completion — re-exports from agentkit.llm with backward compat."""
from __future__ import annotations

import os
from typing import Any

from agentkit.llm import (
    DEFAULT_MODEL_ALIASES as _DEFAULT_ALIASES,
    SqliteCallLogger,
    complete as _agentkit_complete,
    complete_with_tools,
    response_cost_usd,
    resolve_model as resolve_model_id,
)

MODEL_ALIASES: dict[str, str] = dict(_DEFAULT_ALIASES)

_LOGGERS: dict[str, SqliteCallLogger] = {}


def _resolve_logger() -> SqliteCallLogger | None:
    """Return a SQLite logger if DECISIONMAKER_LLM_LOG is set, else None."""
    path = os.environ.get("DECISIONMAKER_LLM_LOG", "").strip()
    if not path:
        return None
    logger = _LOGGERS.get(path)
    if logger is None:
        logger = SqliteCallLogger(path)
        _LOGGERS[path] = logger
    return logger


def _resolve_model(alias: str) -> str:
    from agentkit.llm import resolve_model
    return resolve_model(alias, aliases=MODEL_ALIASES)


def complete(
    messages: list[dict[str, Any]],
    alias: str = "smart",
    *,
    max_tokens: int = 2000,
    temperature: float = 0.3,
    json_mode: bool = False,
) -> str:
    return _agentkit_complete(
        messages,
        alias=alias,
        max_tokens=max_tokens,
        temperature=temperature,
        json_mode=json_mode,
        aliases=MODEL_ALIASES,
        log_fn=_resolve_logger(),
    )
```
(Only additions: `import os`, `SqliteCallLogger` import, `_LOGGERS`,
`_resolve_logger`, and `log_fn=_resolve_logger()` in the `complete` call.
Everything else is identical to the original.)

**Step 3 (verify): run the full decisionmaker suite.**
```bash
cd /Users/chaehan/Software/Prototypes/decisionmaker && python -m pytest -q
```
**Done when:** both new tests pass and the full suite is green.

---

### T6 — Pin agentkit to a tag in consumer CI (B1)

**Step 1: tag agentkit on its GitHub remote (`SoHu-Labs/agentkit`).** From the
agentkit repo (whose remote is that GitHub repo):
```bash
cd /Users/chaehan/Software/Prototypes/agentkit
git tag v0.1.0
git push origin v0.1.0
```
(If `v0.1.0` already exists, pick the next free patch tag, e.g. `v0.1.1`, and use
that everywhere below.)

**Step 2: add `ref: v0.1.0` to each consumer's agentkit checkout block.** In each
file, the block currently is:
```yaml
      - uses: actions/checkout@v4
        with:
          repository: SoHu-Labs/agentkit
          path: vendor/agentkit
          token: ${{ secrets.GITHUB_TOKEN }}
```
Add one line `          ref: v0.1.0` directly under `repository:` so it becomes:
```yaml
      - uses: actions/checkout@v4
        with:
          repository: SoHu-Labs/agentkit
          ref: v0.1.0
          path: vendor/agentkit
          token: ${{ secrets.GITHUB_TOKEN }}
```
Edit all three files:
- `email-digest/.github/workflows/test.yml` (block at lines 15–19)
- `invoice-admin/.github/workflows/ci.yml` (block at lines 13–17)
- `decisionmaker/.github/workflows/ci.yml` (block at lines 16–20)

**Done when:** all three workflows pin `ref: v0.1.0`. No code/runtime change.

---

### T7 — Decouple swim from agentkit (B5)

**Context:** `swim/src/swim/common.py` imports agentkit only for `repo_root`, and
swim has no CI installing agentkit. Inline the tiny utility and drop the
dependency. Behavior (incl. `SWIM_REPO_ROOT`) must stay identical.

**Step 1: edit `swim/src/swim/common.py`.** `os` and `Path` are already imported
at the top (lines 5–7). Replace the current `repo_root` function (lines 10–17)
with:
```python
def repo_root() -> Path:
    """Return the absolute path of the repository root.

    Resolution order: SWIM_REPO_ROOT env var, then walk up from CWD for
    pyproject.toml, then walk up from this file. Raises FileNotFoundError.
    """
    env_val = os.environ.get("SWIM_REPO_ROOT", "").strip()
    if env_val:
        return Path(env_val).expanduser().resolve()
    cwd = Path.cwd()
    for ancestor in [cwd, *cwd.parents]:
        if (ancestor / "pyproject.toml").is_file():
            return ancestor
    file_dir = Path(__file__).resolve().parent
    for ancestor in [file_dir, *file_dir.parents]:
        if (ancestor / "pyproject.toml").is_file():
            return ancestor
    raise FileNotFoundError(
        "Could not find pyproject.toml. Set SWIM_REPO_ROOT or run from the swim repo."
    )
```

**Step 2: confirm nothing else in swim imports agentkit.**
```bash
cd /Users/chaehan/Software/Prototypes/swim && grep -rn "agentkit" src tests 2>/dev/null
```
Expect **no output**. If anything else appears, stop and report it (do not edit
further).

**Step 3: run the swim suite.**
```bash
cd /Users/chaehan/Software/Prototypes/swim && python -m pytest -q
```
**Done when:** swim tests pass and swim no longer references agentkit.

---

## Part A — Agent Skills

### T8 — Create `agentkit/skills/`

These are SKILL.md runbooks + helper scripts for the coding agent that operates
these repos. They wrap agentkit; they do not replace any import. Create the
directory tree below under `/Users/chaehan/Software/Prototypes/agentkit/skills/`.

> Before finalizing scripts 2 and 3, verify the exact signatures against the
> source: `resolve_spec_to_message` and the message object fields in
> `src/agentkit/gmail/_client.py`; `chrome_driver_attach` /
> `build_chrome_options_for_remote_debugging` in `src/agentkit/browser/_browser.py`.
> Adjust the script calls if the real signatures differ.

#### Skill 1 — `skills/llm-smoke/SKILL.md`
```markdown
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
```
`skills/llm-smoke/scripts/llm_smoke.py`:
```python
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
```

#### Skill 2 — `skills/gmail-setup/SKILL.md`
```markdown
---
name: gmail-setup
description: Authenticate Gmail via agentkit and fetch one test message. Use when wiring up or debugging Gmail access (GOOGLE_OAUTH_TOKEN), or to confirm credentials work before running an email pipeline.
---

# agentkit Gmail setup check

## Steps
1. Set `GOOGLE_OAUTH_TOKEN` to the path of your OAuth token/credentials file.
2. `python skills/gmail-setup/scripts/gmail_fetch.py "<gmail-search-spec>"`
   (default spec: `is:unread`).
3. A subject line and a cleaned body excerpt print on success. An auth error
   means the token path or scopes are wrong.
```
`skills/gmail-setup/scripts/gmail_fetch.py`:
```python
#!/usr/bin/env python3
"""Fetch + clean one Gmail message. Usage: gmail_fetch.py "<spec>".

resolve_spec_to_message returns (message_ref, body) — a tuple, not an object,
and subject is not available from this API. Verified against
src/agentkit/gmail/_client.py:245.
"""
from __future__ import annotations

import os
import sys

from agentkit.gmail import GmailApiBackend, clean_email_body, resolve_spec_to_message


def main() -> int:
    token = os.environ.get("GOOGLE_OAUTH_TOKEN", "").strip()
    if not token:
        print("Set GOOGLE_OAUTH_TOKEN to your OAuth token file path.", file=sys.stderr)
        return 1
    spec = sys.argv[1] if len(sys.argv) > 1 else "is:unread"
    backend = GmailApiBackend(credentials_path=token)
    msg_ref, body = resolve_spec_to_message(backend, spec)
    print(f"message: {msg_ref}")
    print(clean_email_body(body)[:500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

#### Skill 3 — `skills/brave-attach/SKILL.md`
```markdown
---
name: brave-attach
description: Start Brave with remote debugging and attach a Selenium driver on macOS. Use before any browser-automation task (email-digest unsubscribe, invoice-admin Google Ads download) or to debug "cannot connect to Brave / chromedriver" errors.
---

# agentkit Brave attach check

## Steps
1. `python skills/brave-attach/scripts/brave_attach.py`.
2. On success it prints `attached. current_url=...`. If it fails, the printed
   error tells you whether Brave failed to launch or the debugging port was not
   reachable.
```
`skills/brave-attach/scripts/brave_attach.py`:
```python
#!/usr/bin/env python3
"""Start Brave with remote debugging and attach a Selenium driver (macOS).

chrome_driver_attach builds its own options internally and takes keyword-only
args; debugger_address is required. Verified against
src/agentkit/browser/_browser.py:112.
"""
from __future__ import annotations

from agentkit.browser import chrome_driver_attach, ensure_brave_running

_ADDR = "127.0.0.1:9222"  # matches ensure_brave_running's default


def main() -> int:
    ensure_brave_running(_ADDR)
    driver = chrome_driver_attach(debugger_address=_ADDR)
    print(f"attached. current_url={driver.current_url!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

#### Skill 4 — `skills/vendor-bump/SKILL.md`
```markdown
---
name: vendor-bump
description: Bump the pinned agentkit ref in every consumer repo's CI after tagging a new agentkit release. Use right after creating an agentkit tag (see streamline.md T6) to roll all consumers to it deliberately.
---

# Bump pinned agentkit ref across consumers

## Steps
1. Tag + push the new agentkit version first (e.g. `git tag v0.1.1 && git push origin v0.1.1`).
2. `python skills/vendor-bump/scripts/bump_agentkit.py v0.1.1`.
3. Review the diffs it reports, commit each consumer repo, and let CI run on the
   pinned ref.
```
`skills/vendor-bump/scripts/bump_agentkit.py`:
```python
#!/usr/bin/env python3
"""Set `ref: <new>` in each consumer's agentkit checkout block.

Assumes the standard block shape:
    repository: SoHu-Labs/agentkit
    [ref: <old>]
    path: vendor/agentkit
"""
from __future__ import annotations

import sys
from pathlib import Path

# Workflow files relative to the Prototypes parent of this agentkit repo.
_PARENT = Path(__file__).resolve().parents[4]  # .../Prototypes
_WORKFLOWS = [
    _PARENT / "email-digest/.github/workflows/test.yml",
    _PARENT / "invoice-admin/.github/workflows/ci.yml",
    _PARENT / "decisionmaker/.github/workflows/ci.yml",
]


def bump(path: Path, new_ref: str) -> bool:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    changed = False
    i = 0
    while i < len(lines):
        out.append(lines[i])
        if "repository: SoHu-Labs/agentkit" in lines[i]:
            indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
            # Does a ref: line follow within the block?
            if i + 1 < len(lines) and lines[i + 1].strip().startswith("ref:"):
                out.append(f"{indent}ref: {new_ref}\n")
                i += 2  # skip old ref line
                changed = True
                continue
            out.append(f"{indent}ref: {new_ref}\n")
            changed = True
        i += 1
    if changed:
        path.write_text("".join(out), encoding="utf-8")
    return changed


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: bump_agentkit.py <ref>", file=sys.stderr)
        return 2
    new_ref = sys.argv[1]
    for wf in _WORKFLOWS:
        if not wf.is_file():
            print(f"skip (missing): {wf}")
            continue
        print(f"{'bumped' if bump(wf, new_ref) else 'unchanged'}: {wf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

#### Skill 5 (optional) — `skills/llm-cost/`
A SKILL.md + script that prints a per-window cost report from a repo's
`llm_calls` SQLite. Generalize the logic already in
`invoice_admin/core/llm.py::format_llm_cost_report` (group by `purpose`, sum
`cost_usd` over last 7 / 30 days). Only build this if you actually want a
cross-repo cost view; it is not required by anything above.

#### Expose skills to the agent (how discovery actually works)
Skills are **not** found through the Python library. An agent discovers a skill
by **scanning a skills directory** and reading each skill's `name` + `description`
from its `SKILL.md`. To make these usable by an agent that knows nothing about
agentkit, the skill must live where that agent already looks:

- **Claude Code:** symlink each skill folder into `~/.claude/skills/<name>`,
  mirroring the pattern already on this machine (its entries are symlinks, e.g.
  `caveman -> ~/.agents/skills/caveman`). Keep the master under
  `agentkit/skills/<name>` and point the symlink at it:
  ```bash
  ln -s "/Users/chaehan/Software/Prototypes/agentkit/skills/llm-smoke" ~/.claude/skills/llm-smoke
  # repeat per skill
  ```
  For use across machines, package the skills as a Claude Code **plugin** instead
  of symlinking — then "install once, available everywhere", no repo awareness.
- **opencode:** this setup has **no SKILL.md scanner** (only `AGENTS.md` +
  `~/.config/opencode/agent/`). The global `AGENTS.md` is **not** a skill
  registry — it is always-loaded instruction text, so listing skills there does
  not make them discoverable the way a skills dir does (and it wastes context).
  At most add a one-line pointer there, or wrap a skill as an opencode
  agent/command if you need opencode itself to invoke it.

**Never edit through a symlink** — edit the master under `agentkit/skills/`.

**Done when:** the four skill folders exist with `SKILL.md` + script, and
`python skills/llm-smoke/scripts/llm_smoke.py` prints a key source,
model, response, and cost.

---

## Part C — Cross-repo consolidation (max-share, multi-repo)

Decision: stay multi-repo, but pull duplicated **infrastructure** into agentkit.
**Do not merge domain logic** — email/invoice/decision/swim stay separate apps.
Order: **C1 first** (agentkit gains the helpers), then consumer migrations
C2–C4. C5–C7 are independent of each other.

### C1 — Add config primitives to agentkit.core
Approved: (1) a shared YAML→mapping loader; (2) best-practice env/path helpers.

**Step 1 (red): tests.** Create
`/Users/chaehan/Software/Prototypes/agentkit/tests/test_core_config.py`:
```python
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
```
Run (expect **red**):
```bash
cd /Users/chaehan/Software/Prototypes/agentkit && python -m pytest tests/test_core_config.py -q
```

**Step 2 (green): implement.**

(a) In `src/agentkit/core/_errors.py`, add a `ConfigError` subclass of
`AgentError` (next to the other error classes):
```python
class ConfigError(AgentError):
    """Raised when configuration is missing or malformed."""
```

(b) Create `src/agentkit/core/_env.py`:
```python
"""Best-practice environment-variable + path helpers."""
from __future__ import annotations

import os
from pathlib import Path

from agentkit.core._errors import ConfigError

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _raw(key: str) -> str:
    return os.environ.get(key, "").strip()


def env_str(key: str, default: str = "", *, required: bool = False) -> str:
    raw = _raw(key)
    if raw:
        return raw
    if required:
        raise ConfigError(f"Required env var {key!r} is not set")
    return default


def env_int(key: str, default: int = 0, *, required: bool = False) -> int:
    raw = _raw(key)
    if not raw:
        if required:
            raise ConfigError(f"Required env var {key!r} is not set")
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ConfigError(f"Env var {key!r} must be an integer, got {raw!r}") from e


def env_bool(key: str, default: bool = False) -> bool:
    raw = _raw(key).lower()
    if not raw:
        return default
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    raise ConfigError(f"Env var {key!r} must be a boolean, got {raw!r}")


def expand_path(value: str | Path | None, default: Path) -> Path:
    """Resolve *value* (e.g. from YAML) to an absolute path, or *default*.

    Relative paths resolve against the current working directory.
    """
    if value is None or value == "":
        return default
    p = Path(value).expanduser()
    return p.resolve() if p.is_absolute() else (Path.cwd() / p).resolve()


def env_path(key: str, default: Path, *, required: bool = False) -> Path:
    raw = _raw(key)
    if not raw:
        if required:
            raise ConfigError(f"Required env var {key!r} is not set")
        return default
    return Path(raw).expanduser().resolve()
```

(c) Create `src/agentkit/core/_config.py`:
```python
"""YAML configuration loading."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from agentkit.core._errors import ConfigError


def load_yaml_mapping(
    path: Path,
    *,
    allow_empty: bool = True,
    error_cls: type[Exception] = ConfigError,
) -> dict[str, Any]:
    """Load a YAML file that must contain a mapping (dict).

    Raises *error_cls* if the file is missing, empty (unless *allow_empty*),
    or not a mapping. Pass *error_cls* to keep a consumer's own error type.
    Requires PyYAML (``pip install 'agentkit[config]'``).
    """
    import yaml  # lazy: keeps `import agentkit.core` dependency-free

    if not path.is_file():
        raise error_cls(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        if allow_empty:
            return {}
        raise error_cls(f"Config file is empty: {path}")
    if not isinstance(data, dict):
        raise error_cls(f"Config root must be a mapping: {path}")
    return data
```

(d) Update `src/agentkit/core/__init__.py` to export the new names:
```python
from agentkit.core._common import repo_root
from agentkit.core._config import load_yaml_mapping
from agentkit.core._env import env_bool, env_int, env_path, env_str, expand_path
from agentkit.core._errors import (
    AgentError,
    ConfigError,
    LLMError,
    LLMFailureWithTranscript,
)

__all__ = [
    "repo_root",
    "AgentError",
    "ConfigError",
    "LLMError",
    "LLMFailureWithTranscript",
    "env_str",
    "env_int",
    "env_bool",
    "env_path",
    "expand_path",
    "load_yaml_mapping",
]
```

(e) In `pyproject.toml`, add a `config` optional-dependency group and include it
in `all`:
```toml
config = ["pyyaml>=6"]
```
(So `all = ["agentkit[llm,speech,mlx_llm,audio,gmail,youtube,config]"]`.)

Run (expect **green**):
```bash
cd /Users/chaehan/Software/Prototypes/agentkit && python -m pytest -q
```

### C2 — email-digest: use `load_yaml_mapping`
In `src/email_digest/config.py`, inside `load_topic_config`, replace:
```python
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"topic YAML must be a mapping: {path}")
```
with:
```python
    raw = load_yaml_mapping(path)
```
Add `from agentkit.core import load_yaml_mapping` to the imports, and remove
`import yaml` **if** nothing else in the file uses it
(`grep -n "yaml" src/email_digest/config.py`). This is the approved behavior
change: a missing/non-mapping file now raises agentkit `ConfigError` (not
`ValueError`); an empty file yields `{}`.
**Migrate coupled tests:** `grep -rn "topic YAML must be a mapping\|ValueError" email-digest/tests`
and update any test that expected `ValueError` to expect
`agentkit.core.ConfigError`. Then `cd email-digest && python -m pytest -q`.

### C3 — invoice-admin: use `load_yaml_mapping` (own error) + `expand_path`
In `src/invoice_admin/core/config.py`:
- Delegate `_load_yaml` while **keeping invoice-admin's own `ConfigError` type**
  (zero behavior change):
  ```python
  from agentkit.core import load_yaml_mapping
  def _load_yaml(path: Path) -> dict[str, Any]:
      return load_yaml_mapping(path, error_cls=ConfigError)
  ```
  (`ConfigError` here is the existing `invoice_admin.core.errors.ConfigError`.)
- Delete the local `_expand_path` and alias agentkit's (identical logic, so call
  sites are unchanged):
  ```python
  from agentkit.core import expand_path as _expand_path
  ```
- **Do NOT touch** the `os.environ.get(x) or notify_block.get(...)` overlays or
  `INVOICE_ADMIN_ROOT` handling — they carry `None` semantics the env helpers
  intentionally do not express. Leave them exactly as-is.

Run `cd invoice-admin && python -m pytest -q` — expect no behavior change.

### C4 — decisionmaker: use `env_str` / `env_int` / `env_path`
In `src/decisionmaker/core/config.py`, delete the local `_env_path`, `_env_int`,
`_env_str` and import agentkit's:
```python
from agentkit.core import env_int, env_path, env_str
```
Then update call sites in `load_config` (`_env_path`→`env_path`,
`_env_int`→`env_int`, `_env_str`→`env_str`). Behavior is identical except a
non-integer `DECISIONMAKER_MAX_ROUNDS` now raises a clear `ConfigError` instead of
a bare `ValueError`. Run `cd decisionmaker && python -m pytest -q`.

### C5 — Unify Gmail on `agentkit.gmail`
Four files duplicate Gmail logic `agentkit.gmail` already provides
(`GmailApiBackend`, `resolve_spec_to_message`, `clean_email_body`, error types):
- `email-digest/src/unsubscribe/gmail_api_backend.py`
- `email-digest/src/email_digest/gmail_query.py`
- `invoice-admin/src/invoice_admin/googleads/gmail_api_backend.py`
- `decisionmaker/src/decisionmaker/core/gmail_query.py`
(`decisionmaker/core/gmail.py` already wraps agentkit — use it as the template.)

For **each** file, in this order (extraction rule: *do not simplify*):
1. **Read** it and **diff its public behavior** against `src/agentkit/gmail/`.
2. If it does something agentkit's version does **not** (extra parsing, a
   different spec syntax, etc.), **port that into `agentkit.gmail` first** (with
   its own failing test), keeping two functions as two functions.
3. Replace the duplicate with a thin re-export
   (`from agentkit.gmail import ...  # noqa: F401`) or repoint its importers.
4. Run that repo's full suite; keep patched module paths intact.

Note: `invoice-admin/.../gmail_smtp.py` is **send**, which agentkit.gmail may not
cover — only fold it in if agentkit grows a send capability; otherwise leave it.

### C6 — Shared `LLMProvider` in agentkit (optional, builds on T2)
invoice-admin's `LLMProvider` (handler/purpose/duration/success logging) is the
richest LLM wrapper. Generalize it onto `complete` + `SqliteCallLogger`:
- Add `agentkit.llm.LLMProvider` logging via `SqliteCallLogger` with
  `extra_columns={"handler": "TEXT", "purpose": "TEXT", "success": "INTEGER", "duration_ms": "REAL"}`
  (caller stuffs `handler`/`purpose` into the record).
- invoice-admin's `LLMProvider` becomes a thin subclass (keeps its table,
  `complete_with_pdf`, `format_llm_cost_report`).
- email-digest / decisionmaker may adopt later; **not required**.
- **Caveat (data):** do not migrate existing `llm_calls` tables — adoption is for
  new tables only unless you decide otherwise.

### C7 — Reusable CI workflow (supersedes T6)
Replace the three copy-pasted vendoring blocks with one reusable workflow in
agentkit.
- Create `agentkit/.github/workflows/reusable-ci.yml` with `on: workflow_call`
  and inputs `agentkit_ref`, `python_version`, `test_cmd`; its steps checkout the
  caller, checkout agentkit at `inputs.agentkit_ref` into `vendor/agentkit`, set
  up Python, `pip install -e vendor/agentkit && pip install -e ".[dev]"`, then run
  `inputs.test_cmd`.
- Each consumer workflow shrinks to a caller:
  ```yaml
  jobs:
    ci:
      uses: SoHu-Labs/agentkit/.github/workflows/reusable-ci.yml@v0.1.0
      with:
        agentkit_ref: v0.1.0
        python_version: "3.12"
        test_cmd: "python -m pytest"
  ```
- **If you do C7, skip T6** (the `@v0.1.0` on `uses:` is the pin). The
  `vendor-bump` skill then edits the `@ref` on the `uses:` line.

---

## Final verification (run everything)
```bash
cd /Users/chaehan/Software/Prototypes/agentkit     && python -m pytest -q
cd /Users/chaehan/Software/Prototypes/email-digest && python -m pytest -q
cd /Users/chaehan/Software/Prototypes/invoice-admin&& python -m pytest -q
cd /Users/chaehan/Software/Prototypes/decisionmaker&& python -m pytest -q
cd /Users/chaehan/Software/Prototypes/swim         && python -m pytest -q
```
All five suites must be green.

## Hard rules (do not break)
- Do **not** change any consumer's runtime imports except the deliberate edits
  in T3/T4/T5 and C2/C3/C4 (and C5/C6 if you do them).
- Do **not** alter existing SQLite schemas in invoice-admin or email-digest, or
  change visible output anywhere.
- Do **not** `git checkout`/overwrite a production or data file to make a test
  pass — fix the test instead.
- Keep the module paths tests patch (`agentkit.llm._litellm.litellm.completion`,
  `...completion_cost`, `agentkit.llm._litellm._AUTH_PATH`) intact.
- Commit/push only when the human says so.
