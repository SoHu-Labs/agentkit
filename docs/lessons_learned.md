# Lessons learned — agentkit module extraction CI failures

## Root cause chain

Three independent issues cascaded into repeated CI failures across 4 repos:

| # | Issue | Commits affected | When detected |
|---|---|---|---|
| 1 | `slugify_vendor` missing from `naming.py` | Pre-existing since repo creation | Post-migration CI run |
| 2 | `agentkit` not installed in project mamba envs or CI | `core/` migration commit | User runtime + CI |
| 3 | `agentkit` was a private repo — cross-repo CI checkout failed | All migration commits | CI |

## Fixes

### 1. `slugify_vendor` missing (invoice-admin)

**Root cause:** Test `test_core/test_naming.py` imported `slugify_vendor` from `invoice_admin.core.naming`, but the function was never implemented. The test had been broken since the repo's initial commit.

**Fix:** Added `slugify_vendor(text)` to `naming.py` — lowercases, hyphenates, falls back to `"vendor"` for symbol-only input. Also unified filename separators (spaces → underscores) to match test expectations.

**Fixed in:** The commit where the test originally broke (`56daa8d`), amended.

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

## Process lessons

1. **Test in the project's env, not global env.** Every project has its own mamba environment. `pip install` in base doesn't help. Run `~/Software/miniforge3/envs/<name>/bin/python -m pytest` or use `mamba run -n <name>`.

2. **Run the full test suite.** I validated with selective tests (`test_smoke.py`, `test_config.py`) but missed `test_naming.py`. Python's `-x` flag stops at the first failure — but import errors happen during collection before any test runs.

3. **Fix CI in the commit that broke it.** The `slugify_vendor` fix should have been amended into the first commit where the agentkit import was added (the core migration), not layered on top as a separate commit. Amending keeps `git bisect` clean and the history honest.

4. **Check repo visibility before cross-repo dependencies.** If a shared library repo is private, CI in consumer repos can't access it unless a deploy key or org-level PAT is set up. Making it public is the simplest fix when there are no secrets.

5. **Don't use direct URL deps in pyproject.toml with Hatchling.** Hatchling blocks them by default. Either set `allow-direct-references = true` or handle installation in CI steps instead.
