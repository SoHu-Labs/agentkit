# Lessons learned — agentkit module extraction

**Read this before touching any consumer repo.**

---

## 1. CRITICAL: Never mix module extraction with CLI refactoring

**The cycle:** `browser_download.py` was BOTH extracted to agentkit AND refactored for `--dry-run`. Every fix to one broke the other.

**Timeline:**
1. CLI refactor (test-run→dry-run, save-commission-pdf→save) — works
2. browser/ extraction → shim replaces `browser_download.py` — **broken: renamed function** `chrome_options_for_debugger`
3. Reverted `browser_download.py` to original — **broken: commission PDF parsing** (format missing)
4. **SHOULD HAVE just fixed parsing here (format 4 in `invoice_pdf.py`). Instead:** re-applied agentkit shim — **broken: download again**
5. Reverted download again, fixed SMTP `None` in `run_month.py` — **broken: `status` unbound**
6. Fixed `status` — ✅

**The mistake at step 4:** User said "fix the parsing error." I interpreted it as "keep trying to make the shim work" instead of the obvious fix: add one regex to `invoice_pdf.py` while the original download code was already working.

**Root cause:** Two tasks sharing the same files (`browser_download.py`, `run_month.py`). Every revert to fix extraction undid CLI progress. Every CLI fix was tested against the original file, not the shim.

**DO THIS:** Finish ONE task completely. Test it. Commit. ONLY THEN start the next task. Never interleave.

**How the user's instructions could have prevented this:** They said "don't change the download method" and "fix the parsing error" repeatedly. I interpreted this as "revert the shim" instead of "fix the extracted code in agentkit so it matches the original exactly, then fix parsing".

---

## 2. WRONG: Not installing agentkit in every project's mamba env

**Symptom:** `ModuleNotFoundError: No module named 'agentkit'` at runtime.

**DO THIS:**
```bash
~/Software/miniforge3/envs/decisionmaker/bin/pip install -e ~/Software/Prototypes/agentkit
~/Software/miniforge3/envs/email-digest/bin/pip install -e ~/Software/Prototypes/agentkit
~/Software/miniforge3/envs/invoice-admin/bin/pip install -e ~/Software/Prototypes/agentkit
~/Software/miniforge3/envs/swim/bin/pip install -e ~/Software/Prototypes/agentkit
~/Software/miniforge3/envs/localai/bin/pip install -e ~/Software/Prototypes/agentkit
```

Also add to each repo's CI workflow:
```yaml
- uses: actions/checkout@v4
  with:
    repository: SoHu-Labs/agentkit
    path: vendor/agentkit
- run: pip install -e vendor/agentkit
```

---

## 3. WRONG: Not running the full test suite before pushing

**DO THIS:**
```bash
cd ~/Software/Prototypes/<project>
~/Software/miniforge3/envs/<env>/bin/python -m pytest tests/ -q
```
Never push with known failures.

---

## 4. WRONG: Fixing CI in a separate commit

**DO THIS:** `git commit --amend --no-edit` and force push.

---

## 5. WRONG: Patching pyproject.toml with git URL dependencies

Hatchling blocks direct URL refs. Use CI checkout step instead.

---

## 6. WRONG: Making litellm a hard dependency for mlx-only consumers

Use lazy imports via `__getattr__` in `__init__.py`.

---

## 7. WRONG: Not adding `py.typed` marker to agentkit

Create empty `src/agentkit/py.typed` and add to pyproject.toml:
```toml
[tool.setuptools.package-data]
agentkit = ["py.typed"]
```

---

## 8. WRONG: Forgetting to push agentkit BEFORE consumer pushes

Push agentkit first, wait, THEN push consumer repo.

---

## 9. WRONG: Renaming functions during extraction

When extracting code to agentkit, keep function names IDENTICAL to the original. The agentkit `_browser.py` renamed `build_chrome_options_for_remote_debugging` → `chrome_options_for_debugger`. The shim had to alias it back. This caused the download to break because the alias wasn't applied everywhere.

**DO THIS:** `diff` the original and extracted file. Every function name, signature, and import must match exactly. Only then write the shim.
