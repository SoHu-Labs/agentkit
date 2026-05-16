# Lessons learned — agentkit module extraction CI failures

## Root cause chain

Three independent issues cascaded into repeated CI failures across 4 repos:

| # | Issue | Commits affected | When detected |
|---|---|---|---|
| 1 | `slugify_vendor` missing from `naming.py` | Pre-existing since repo creation | Post-migration CI run |
| 2 | `agentkit` not installed in project mamba envs or CI | `core/` migration commit | User runtime + CI |
| 3 | `agentkit` was a private repo — cross-repo CI checkout failed | All migration commits | CI |
| 4 | `ensure_brave_running` not mocked in CLI tests | Pre-existing since refactor | CI |

## Fixes

### 1. `slugify_vendor` missing (invoice-admin)

**Root cause:** Test `test_core/test_naming.py` imported `slugify_vendor` from `invoice_admin.core.naming`, but the function was never implemented. The test had been broken since the repo's initial commit.

**Fix:** Added `slugify_vendor(text)` to `naming.py` — lowercases, hyphenates, falls back to `"vendor"` for symbol-only input. Also unified filename separators (spaces → underscores) to match test expectations.

**Fixed in:** `56daa8d` ("Fix: LLM provider routing via OpenCode Go API, OCR fallback for scanned PDFs, and human-readable filenames"), amended.

### 2. `agentkit` not installed

**Root cause:** `pip install -e agentkit` was run in the base miniforge3 env, but each project uses its own mamba env (`invoice-admin`, `decisionmaker`, `email-digest`, `swim`, `localai`). The migration added `from agentkit.core import AgentError` which failed at runtime because agentkit wasn't in those envs.

**Fix:** `pip install -e ~/Software/Prototypes/agentkit` in every mamba env. For CI, added agentkit checkout step to each project's workflow.

**Lesson:** After extracting shared code, install it in EVERY consumer environment — not just the current shell. CI needs it too.

### 3. Private repo — CI can't clone

**Root cause:** `agentkit` was a private GitHub repo. Even with `token: ${{ secrets.GITHUB_TOKEN }}` in the `actions/checkout` step, cross-repo access is blocked — the token is scoped to the current repo only.

**Fix:** Made `agentkit` public. No secrets in the repo (just shared library code), so public visibility is correct.

**Attempted fixes that did NOT work:**
- `"agentkit @ git+https://github.com/..."` in `pyproject.toml` dependencies → Hatchling rejects direct URL refs unless `[tool.hatch.metadata] allow-direct-references = true` is set
- `token: ${{ secrets.GITHUB_TOKEN }}` in checkout step → token is repo-scoped, can't access other private repos

### 4. `ensure_brave_running` not mocked in CI (invoice-admin)

**Root cause:** `test_run_month.py::TestCliSend` calls `main(["send"])` which invokes `ensure_brave_running()` — a macOS-only function that looks for Brave at `/Applications/Brave Browser.app/...`. The test mocks `run_month.run_month` but does not mock `ensure_brave_running`. On Ubuntu CI, the function raises `RuntimeError` before reaching the mocked code.

**Fix:** Added `@patch("invoice_admin.googleads.browser_download.ensure_brave_running")` to `test_happy_path` and `test_propagates_run_month_error`. These tests validate CLI orchestration, not browser launch — mocking the browser check is correct.

**Lesson:** Tests that call CLI entry points need to mock ALL side effects in the call chain, not just the primary function. Platform-specific functions (macOS-only browser paths) will always fail on Ubuntu CI unless explicitly mocked.

## Process lessons

1. **Test in the project's env, not global env.** Every project has its own mamba environment. `pip install` in base doesn't help. Run `~/Software/miniforge3/envs/<name>/bin/python -m pytest` or use `mamba run -n <name>`.

2. **Run the full test suite.** I validated with selective tests (`test_smoke.py`, `test_config.py`) but missed `test_naming.py` and `test_run_month.py`. Python's `-x` flag stops at the first failure — but import errors and platform-specific runtime errors happen during collection or execution before targeted tests run.

3. **Fix CI in the commit that broke it, reference it by title.** The `slugify_vendor` fix was amended into `56daa8d` ("Fix: LLM provider routing via OpenCode Go API, OCR fallback for scanned PDFs, and human-readable filenames") — the commit where the test originally broke. Amending keeps `git bisect` clean. Always reference the broken commit by its full title in documentation.

4. **Check repo visibility before cross-repo dependencies.** If a shared library repo is private, CI in consumer repos can't access it unless a deploy key or org-level PAT is set up. Making it public is the simplest fix when there are no secrets.

5. **Don't use direct URL deps in pyproject.toml with Hatchling.** Hatchling blocks them by default. Either set `allow-direct-references = true` or handle installation in CI steps instead.

6. **Mock platform-specific functions in CLI tests.** macOS-only functions (Brave browser path) will always fail on Ubuntu CI. Tests calling CLI entry points must mock every platform-specific side effect in the call chain, not just the primary business logic.
