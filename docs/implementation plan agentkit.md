# Agents Shared — Cross-Project Shareable Functionality

Analysis across 5 repos under `~/Software/Prototypes/`. Purpose: identify code that can be extracted into a shared library (`shared_agents/`) for import by all projects.

**Repos analyzed:** `local-chat`, `decisionmaker`, `email-digest`, `invoice-admin`, `swim`

---

## Design decisions (confirmed)

| Decision | Choice | Rationale |
|---|---|---|
| Package structure | **Nested by domain** | Scales better as modules grow; import remains clean (`from agentkit.speech import MlxTts`) |
| Packaging | **One package + optional extras** | `pip install agentkit[llm,tts,gmail]` — single version, single repo |
| Agent config | **One AGENTS.md, symlinked** | Shared repo root has `AGENTS.md` defining tools; each project symlinks `~/.config/opencode/agents/agentkit.md` → it |
| Platform | **Apple Silicon only** | MLX modules are the reason this exists; no Linux/Windows abstraction needed |
| Versioning | **0.x during extraction, 1.0 after** | Breaking changes in 0.x allowed; pin to 1.0 when all 5 projects migrated |
| CI | **Lightweight** | Unit tests in shared repo; manual cross-project smoke test script |

---

## Name candidates

| # | Name | Vibe |
|---|---|---|
| 1 | `agentkit` | Toolkit convention, composable |
| 2 | `agentcore` | Core plumbing for agents |
| 3 | `llm-toolbox` | LLM focus, familiar metaphor |
| 4 | `soloagents` | SOund + LOcal LLM + LIteLLM |
| 5 | `mlx-agents` | MLX-native, self-descriptive |
| 6 | `basecamp` | Base layer all projects share |
| 7 | `foundry` | Casts tools from raw deps |
| 8 | `understudy` | Infrastructure behind the lead actors |
| 9 | `echobox` | Speech + LLM + notifications — echo back |
| 10 | `substrate` | The layer everything else builds on |

---

## 1. LLM Abstraction (`litellm` wrapper)

| | |  
|---|---|
| **Canonical source** | `email-digest/src/email_digest/llm.py` (402 lines) — most mature |
| **Also in** | `decisionmaker/src/decisionmaker/core/llm.py` (149 lines), `invoice-admin/src/invoice_admin/core/llm.py` (535 lines) |
| **Shared module** | `shared_agents/llm.py` |
| **Priority** | **Highest** — duplicated 3× with diverging features |

### Features common to all three
- `MODEL_ALIASES` dict: `fast`/`smart`/`local`/`local_smart`/`cheap` → provider model IDs
- `complete(messages, alias, max_tokens, temperature)` → `str`
- `resolve_model_alias(alias)` with env var overrides
- API key resolution from `~/.local/share/opencode/auth.json` (DeepSeek)
- LM Studio local model support via `api_base` env var

### Feature divergence

| Feature | email-digest | decisionmaker | invoice-admin |
|---|---|---|---|
| SQLite call logging + cost tracking | Yes | No | Yes |
| Multimodal PDF (OCR fallback) | No | No | Yes |
| JSON mode | Yes | No | No |
| `complete_with_tools()` | No | Yes | No |
| MLX local model support | Yes | No | No |
| Cost reporting dashboard | Yes | No | Yes |
| Retry logic | No | Yes (2×) | No |

### Recommendation
Extract a unified `shared_agents/llm.py` with:
- Core: `MODEL_ALIASES`, `complete()`, `complete_with_tools()`, cost estimation
- Optional: SQLite logging (injectable callback), JSON mode, PDF multimodal
- Backward-compat aliases for each project's existing import path

---

## 2. TTS — MLX Kokoro Text-to-Speech

| | |
|---|---|
| **Canonical source** | `local-chat/src/tts.py` (109 lines) |
| **Also in** | `decisionmaker/src/decisionmaker/render/tts.py` (64 lines, imports canonical via path) |
| **Shared module** | `shared_agents/tts.py` |
| **Priority** | **Highest** — already shared via path import, formalize |

### What it is
- `MlxTts` class wrapping `mlx_audio` Kokoro-82M
- `KOKORO_MODEL_ID`, `KOKORO_VOICES`, `KOKORO_DEFAULT_VOICE`, `KOKORO_VOICE_DESCRIPTIONS`
- `synthesize(text, voice) → (np.ndarray, sample_rate)`
- `synthesize_to_file(text, output_path, voice) → float` (duration)
- Lazy loading, stdout suppression, latency tracking

### Current state
- `local-chat` owns the canonical implementation
- `decisionmaker` does `sys.path.insert` + `from tts import MlxTts`
- Duplicated voice constants in `decisionmaker/render/tts.py`

### Recommendation
Lift `local-chat/src/tts.py` into `shared_agents/tts.py` as-is. Both projects import from it. Voice constants stay in one place.

---

## 3. STT — Parakeet Speech-to-Text

| | |
|---|---|
| **Canonical source** | `local-chat/src/stt.py` (63 lines) |
| **Also in** | *nowhere else yet* |
| **Shared module** | `shared_agents/stt.py` |
| **Priority** | **High** — clean wrapper, ready to extract |

### What it is
- `MlxStt` class wrapping `parakeet-mlx` (Parakeet TDT transducer)
- `transcribe(audio, sample_rate) → str`
- Lower latency than Whisper for short utterances
- Lazy model download/load

### Recommendation
Extract as-is. Decisionmaker could use this for voice-input dilemmas later.

---

## 4. Audio I/O — Recording + Playback

| | |
|---|---|
| **Canonical source** | `local-chat/src/audio_io.py` (160 lines) |
| **Also in** | *nowhere else yet* |
| **Shared module** | `shared_agents/audio_io.py` |
| **Priority** | **High** — zero project-specific imports |

### What it is
- `AudioRecorder` with WebRTC VAD, silence detection, fixed-duration recording
- `AudioPlayer` with blocking and async playback
- Sounddevice backend
- Constant `WHISPER_SAMPLE_RATE = 16000`

### Recommendation
Extract as-is. Generic audio utility, useful for any voice-enabled agent.

---

## 5. MLX LLM — Local Language Model

| | |
|---|---|
| **Canonical source** | `local-chat/src/llm.py` (108 lines) |
| **Also in** | *nowhere else yet* |
| **Shared module** | `shared_agents/mlx_llm.py` |
| **Priority** | **Medium** — clean, but only local-chat uses it |

### What it is
- `MlxLlm` class wrapping `mlx_lm`
- Supports Qwen variants (0.8B, 2B, 4B, Qwen3-4B)
- `generate(messages, max_tokens, temp) → str`
- Token counting (`last_prompt_tokens`, `last_gen_tokens`)
- Model paths hardcoded to `~/.lmstudio/models/`

### Recommendation
Extract with configurable model path (already supported via constructor). The hardcoded `MODEL_VARIANTS` dict should accept overrides.

---

## 6. Config Loading — Frozen Dataclass + YAML/Env

| | |
|---|---|
| **Pattern used by** | all 5 repos |
| **Shared module** | `shared_agents/config.py` |
| **Priority** | **High** — every project needs this |

### Pattern
- Frozen `@dataclass` for config objects (immutability, type safety)
- YAML file loading + environment variable overlay
- Path resolution relative to repo root
- Config validation on load

### Divergence

| Project | Config Source | Fields |
|---|---|---|
| decisionmaker | Env vars only | 5 fields (model, rounds, vocab, data_dir, db_path) |
| email-digest | YAML per topic | 15 fields (name, senders, keywords, folders, models, etc.) |
| invoice-admin | YAML (default + handlers) | Paths, models, notify, dry_run |
| swim | YAML (swim + corrections + course) | Paths, corrections, pinned dates |
| local-chat | Ad-hoc (env/kwargs/constants) | Voice, model path, flags |

### Recommendation
Extract shared helpers:
- `repo_root()` — the canonical copy from `swim/common.py` (195 lines, best implementation)
- `load_yaml_config(path, dataclass_type)` — generic YAML→frozen dataclass loader
- `env_override(dataclass, prefix)` — overlay env vars onto config fields

---

## 7. `repo_root()` — Repository Root Detection

| | |
|---|---|
| **Canonical source** | `swim/src/swim/common.py` (195 lines) — most complete |
| **Also in** | `decisionmaker/src/decisionmaker/common.py` (36 lines), `email-digest/src/email_digest/paths.py` (24 lines), `invoice-admin/src/invoice_admin/core/config.py` (inline) |
| **Shared module** | `shared_agents/common.py` |
| **Priority** | **Highest** — duplicated 4× |

### Algorithm (from swim)
1. Check `$SWIM_REPO_ROOT` / `$PROJECT_REPO_ROOT` env var
2. Walk up from CWD looking for `pyproject.toml`
3. Walk up from package location (`__file__`) looking for `pyproject.toml`
4. Raise error if not found

### Differences
- `decisionmaker`: simpler, no CWD walk
- `email-digest`: simpler, only from `__file__`
- `invoice-admin`: inlined in `load_config()`
- `swim`: most robust (env, CWD, package fallback)

### Recommendation
Extract swim's implementation as the canonical copy. Parameterize the env var name and root marker file.

---

## 8. Error Hierarchy — Domain Exceptions

| | |
|---|---|
| **Canonical source** | `invoice-admin/src/invoice_admin/core/errors.py` (53 lines) — cleanest |
| **Also in** | `decisionmaker/src/decisionmaker/core/errors.py` (48 lines) |
| **Shared module** | Not extracted — pattern only |
| **Priority** | **Medium** — pattern, not code |

### Pattern
- Single base exception per project
- Domain-specific subclasses
- `LLMFailureWithTranscript` pattern (decisionmaker) carries state for retry/resume

### Recommendation
Document as a pattern. The base `AgentError` + subclasses approach is simple enough that each project writes its own. The `LLMFailureWithTranscript` (carrying transcript + cost + rounds for resume) is worth a reusable base class.

---

## 9. SQLite Session/Tracker Persistence

| | |
|---|---|
| **Used by** | `decisionmaker`, `email-digest`, `invoice-admin` |
| **Shared module** | `shared_agents/sqlite_store.py` |
| **Priority** | **Medium** — schemas differ, but CRUD patterns identical |

### Common patterns
- `connect(db_path) → Connection` with auto-directory-creation
- `init_schema(conn)` with `CREATE TABLE IF NOT EXISTS`
- Row factory returning dicts or frozen dataclasses
- WAL mode
- Dynamic `update(table, id, **kwargs)`

### Divergence
- `decisionmaker`: Sessions table (transcript, synthesis, state machine)
- `email-digest`: LLM calls + extraction cache + embedding cache (3 tables)
- `invoice-admin`: Invoice tracker (22 fields, idempotency, status lifecycle)

### Recommendation
Extract a generic `SqliteStore` base class with `connect()`, `init_schema()`, `insert()`, `update()`, `get()`, `list()`. Each project subclasses with its own schema DDL and typed row factory.

---

## 10. Gmail API Client

| | |
|---|---|
| **Canonical source** | `invoice-admin/src/invoice_admin/googleads/gmail_api_backend.py` (286 lines) — most complete |
| **Also in** | `decisionmaker/src/decisionmaker/core/gmail.py` (267 lines), `email-digest` (through unsubscribe package) |
| **Shared module** | `shared_agents/gmail.py` |
| **Priority** | **High** — duplicated 3× |

### Common features
- OAuth credential loading
- Gmail API `build("gmail", "v1")` client
- Message fetch by ID with payload decoding (base64url)
- HTML → plaintext conversion
- Search with Gmail `q` syntax

### Recommendation
Extract `invoice-admin`'s implementation (it has the Protocol/facade pattern for testability). The `GmailBackend` Protocol + `GmailFacade` wrapping pattern is excellent. Decisionmaker's body cleaner (German sign-off stripping) could be an optional post-processing hook.

---

## 11. Gmail Query Builder

| | |
|---|---|
| **Canonical source** | `email-digest/src/email_digest/gmail_query.py` (60 lines) |
| **Also in** | `decisionmaker/src/decisionmaker/core/gmail_query.py` (62 lines) — near-identical copy |
| **Shared module** | `shared_agents/gmail_query.py` |
| **Priority** | **High** — literal copy-paste duplicate |

Both implementations:
- `sender_pattern_to_from_clause(pattern) → str`
- `build_digest_gmail_query(window_days, senders, keywords, folders, since) → str`

### Recommendation
Pick one, delete the other. They're functionally identical.

---

## 12. Push Notifications

| | |
|---|---|
| **Canonical source** | `invoice-admin/src/invoice_admin/core/notify.py` (70 lines) |
| **Also in** | *nowhere else yet* |
| **Shared module** | `shared_agents/notify.py` |
| **Priority** | **High** — zero external deps, generic utility |

### What it is
- `Notifier` class with `send(notification) → bool`
- Sends to `ntfy.sh` HTTP API
- Pushover support structured but not yet wired
- `Notification` frozen dataclass (title, body, priority, click_url)

### Recommendation
Extract as-is. Generic push notification module with zero dependencies. Add Pushover support to complete it.

---

## 13. IMAP Email Collector

| | |
|---|---|
| **Canonical source** | `invoice-admin/src/invoice_admin/core/imap.py` (183 lines) |
| **Also in** | *nowhere else yet* |
| **Shared module** | `shared_agents/imap.py` |
| **Priority** | **Medium** — clean, but only one project uses it |

### What it is
- `ImapCollector` context manager
- `collect_unseen() → Iterator[EmailMessage]` — iterates UNSEEN emails with PDF attachments
- `fetch_email_by_message_id(host, user, password, message_id) → EmailMessage`
- RFC822 parsing, HTML body extraction, PDF attachment decoding

### Recommendation
Extract as-is. The invoice-subject heuristic regex should be parameterized.

---

## 14. Prompt Management — Markdown Sections

| | |
|---|---|
| **Canonical source** | `local-chat/src/prompts.py` (62 lines) |
| **Also in** | *nowhere else yet* |
| **Shared module** | `shared_agents/prompts.py` |
| **Priority** | **Medium** — generic, zero deps |

### What it is
- `load_prompt(persona, section) → str` — extracts `## section` body from `prompts/<persona>.md`
- `available_personas()` / `available_sections(persona)`
- Section extraction via regex `## section_name\n\n(.*?)(?=\n##|\Z)`

### Recommendation
Extract with a configurable `prompts_dir: Path` parameter instead of computing from `__file__`.

---

## 15. YouTube Transcript Fetcher

| | |
|---|---|
| **Canonical source** | `local-chat/src/youtube_scraper.py` (130 lines) |
| **Also in** | *nowhere else yet* |
| **Shared module** | `shared_agents/youtube.py` |
| **Priority** | **Low-Medium** — single-purpose utility |

### What it is
- `get_video_transcript(url) → YouTubeVideo` (dataclass: id, title, transcript, url, views)
- `extract_video_id(url)` — regex URL→ID
- `clean_transcript(text)` — removes `[Music]`, timestamps, whitespace

### Recommendation
Extract. Replace module-level `Console()` singleton with injected logger for headless use.

---

## 16. HTML Template Renderer

| | |
|---|---|
| **Pattern used by** | `email-digest` (Jinja2), `swim` (string replacement), `invoice-admin` (Jinja2) |
| **Shared module** | `shared_agents/render.py` |
| **Priority** | **Medium** — pattern is trivial |

### What it is
- `email-digest/render.py`: Jinja2 with Spark deep-link enrichment
- `swim/dashboard/renderer.py`: String `__PLACEHOLDER__` replacement + JSON injection
- `invoice-admin`: Jinja2 for email HTML

### Recommendation
Too thin to extract as a library. Document the string-replacement pattern (`template.replace("__PAYLOAD__", json.dumps(data))`) as a lightweight alternative to Jinja2.

---

## 17. CSV/JSON Write Utilities

| | |
|---|---|
| **Canonical source** | `swim/src/swim/common.py` (195 lines) |
| **Also in** | *scattered across all repos* |
| **Shared module** | `shared_agents/file_io.py` |
| **Priority** | **Low** — stdlib wrappers |

### What it is
- `write_csv(path, rows, fieldnames)` — write list-of-dicts to CSV
- `write_md(path, rows, schema)` — write to markdown table
- `sort_rows(rows, key)` — sort list-of-dicts by field
- `parse_float(v, default=0.0)` — safe float coercion

### Recommendation
Bundle with `repo_root()` in `shared_agents/common.py`.

---

## 18. Apple Health XML Parser

| | |
|---|---|
| **Canonical source** | `swim/src/swim/ingest/apple_stroke_map.py` (385 lines) |
| **Also in** | *nowhere else yet* |
| **Shared module** | `shared_agents/apple_health.py` |
| **Priority** | **Low** — niche domain |

### What it is
- Stream-parse Apple Health `export.xml` using `iterparse` (memory-efficient)
- Half-open interval overlap computation for time-window matching
- SWOLFScore enrichment
- Multi-format datetime parsing

### Recommendation
Extract the XML iterparse pattern and interval overlap logic as standalone utilities. The swim-specific stroke/SWOLF logic stays in swim.

---

## 19. Chart/Axis Helpers

| | |
|---|---|
| **Canonical source** | `swim/src/swim/charts/ticks.py` (46 lines) + `charts/dates.py` (29 lines) |
| **Also in** | *nowhere else yet* |
| **Shared module** | `shared_agents/chart_utils.py` |
| **Priority** | **Low** — niche, but clever |

### What it is
- `r_pretty_y_axis()` — calls R's `pretty()` for nice axis ticks, falls back to numpy
- `panel2_x_axis_mondays_and_breaks()` — Monday-grid date axis computation

### Recommendation
Extract as reusable matplotlib helpers. The R-subprocess-with-lru_cache pattern is worth documenting.

---

## 20. Time/Duration Utilities

| | |
|---|---|
| **Canonical source** | `swim/src/swim/drills/pace.py` (106 lines) |
| **Also in** | *scattered across repos* |
| **Shared module** | `shared_agents/time_utils.py` |
| **Priority** | **Low-Medium** |

### What it is
- `sec_to_pace(seconds) → "m:ss"` — formatted pace string
- `parse_avg_100m_pace_sec("MM:SS") → float` — pace string to seconds
- `capped_block_duration()` — clamp with max plausible

### Recommendation
Extract generic time formatting helpers. Swim-specific pace caps stay in swim.

---

## 21. YouTube/Music Generation

| | |
|---|---|
| **Canonical source** | `local-chat/generate_speech.py` (410 lines) + `local-chat/musicgen.py` |
| **Also in** | *nowhere else yet* |
| **Shared module** | N/A — single application |
| **Priority** | **Not shared** — single-purpose app |

### What it is
- Summarize YouTube transcript → Kokoro speech → optional background music
- SunoAPI.org vocal song generation
- ffmpeg mixing

### Recommendation
Not a shared library component. Standalone application logic.

---

## 22. Pipeline Orchestration Patterns

| | |
|---|---|
| **Pattern used by** | all 5 repos |
| **Shared module** | N/A — pattern documentation only |
| **Priority** | **Low** — pattern, not code |

### Common patterns
- `ingest → extract → classify → handle → notify` (invoice-admin)
- `collect → filter → extract → embed → cluster → synthesize → render` (email-digest)
- `parse → match → correct → output` (swim drills)
- `question → question → ... → synthesize` (decisionmaker)

### Recommendation
Document as architecture patterns. Each project's pipeline is unique enough that shared code isn't practical.

---

## Extraction Priority Summary

| Priority | Module | Repos Affected | Effort |
|---|---|---|---|
| **1** | LLM abstraction (`llm.py`) | 3 | High (unify diverged features) |
| **2** | TTS (`tts.py`) | 2 | Low (already shared via path) |
| **3** | `repo_root()` + common utils | 4 | Low (pick canonical, delete duplicates) |
| **4** | Gmail API client | 3 | Medium (unify interfaces) |
| **5** | Gmail query builder | 2 | Low (identical copies) |
| **6** | Config loading helpers | 5 | Medium (extract pattern) |
| **7** | STT (`stt.py`) | 1 | Low (extract as-is) |
| **8** | Audio I/O (`audio_io.py`) | 1 | Low (extract as-is) |
| **9** | Push notifications (`notify.py`) | 1 | Low (extract as-is) |
| **10** | IMAP client | 1 | Low (extract as-is) |
| **11** | Prompt markdown loader | 1 | Low (extract as-is) |
| **12** | MLX LLM wrapper | 1 | Low (extract as-is) |
| **13** | SQLite store base | 3 | Medium (generic base class) |
| **14** | YouTube scraper | 1 | Low (extract as-is) |

---

## Recommended Shared Library Structure

```
agentkit/
    pyproject.toml
    AGENTS.md                          # symlinked to ~/.config/opencode/agents/
    src/agentkit/
        __init__.py
        common.py                      # repo_root(), write_csv(), parse_float()
        errors.py                      # AgentError, LLMFailureWithTranscript
        config.py                      # load_yaml_config(), env_override()
        sqlite_store.py                # SqliteStore base class

        speech/
            __init__.py
            tts.py                     # MlxTts, KOKORO_* constants
            stt.py                     # MlxStt
            audio_io.py                # AudioRecorder, AudioPlayer

        llm/
            __init__.py
            litellm.py                 # complete(), complete_with_tools(), MODEL_ALIASES
            mlx.py                     # MlxLlm (local Qwen models)

        gmail/
            __init__.py
            client.py                  # GmailBackend Protocol, GmailFacade, GmailApiBackend
            query.py                   # Gmail query builder
            body_cleaner.py            # clean_email_body()

        imap/
            __init__.py
            collector.py               # ImapCollector, EmailMessage

        notify/
            __init__.py
            push.py                    # Notifier, Notification

        prompts/
            __init__.py
            loader.py                  # load_prompt(), available_personas()

        youtube/
            __init__.py
            transcript.py              # YouTubeVideo, get_video_transcript()

        apple/
            __init__.py
            health.py                  # parse_apple_export_datetime(), interval overlap

        charts/
            __init__.py
            ticks.py                   # r_pretty_y_axis()
            dates.py                   # x-axis helpers

        time_utils.py                  # sec_to_pace(), parse_avg_100m_pace_sec()

    tests/
        conftest.py
        test_common.py
        test_errors.py
        test_config.py
        test_sqlite_store.py
        speech/
            test_tts.py
            test_stt.py
            test_audio_io.py
        llm/
            test_litellm.py
        gmail/
            test_client.py
            test_query.py
            test_body_cleaner.py
        imap/
            test_collector.py
        notify/
            test_push.py
        prompts/
            test_loader.py
        youtube/
            test_transcript.py
        apple/
            test_health.py
        charts/
            test_ticks.py
        test_time_utils.py
```

### Import convention per project

```python
# local-chat (uses: speech, llm/mlx, prompts)
from agentkit.speech.tts import MlxTts, KOKORO_VOICES
from agentkit.speech.stt import MlxStt
from agentkit.speech.audio_io import AudioRecorder, AudioPlayer
from agentkit.llm.mlx import MlxLlm
from agentkit.prompts.loader import load_prompt

# decisionmaker (uses: speech/tts, llm/litellm, gmail, common)
from agentkit.speech.tts import MlxTts, KOKORO_VOICES
from agentkit.llm.litellm import complete, complete_with_tools
from agentkit.gmail.client import GmailFacade, GmailApiBackend
from agentkit.gmail.query import build_digest_gmail_query
from agentkit.common import repo_root

# email-digest (uses: llm/litellm, gmail, config, sqlite_store)
from agentkit.llm.litellm import complete
from agentkit.gmail.client import GmailBackend, GmailApiBackend
from agentkit.gmail.query import build_digest_gmail_query

# invoice-admin (uses: llm/litellm, gmail, notify, imap, sqlite_store)
from agentkit.llm.litellm import complete
from agentkit.gmail.client import GmailApiBackend
from agentkit.notify.push import Notifier, Notification
from agentkit.imap.collector import ImapCollector

# swim (uses: common, charts, time_utils, apple)
from agentkit.common import repo_root
from agentkit.apple.health import parse_apple_export_datetime
from agentkit.time_utils import sec_to_pace
```

Each project imports only what it needs. Unused modules sit on disk at negligible cost. The shared library is a normal pip-installable package.

---

# Implementation Guide

## Critical rules (read first)

1. **Every file operation** below specifies exact source and destination paths.
2. **Change imports BEFORE deleting** any file. The re-export shim pattern lets you verify tests pass before removing originals.
3. **One project at a time** per phase. Never touch files in two repos simultaneously.
4. **Commit after every phase** in each affected repo with message `shared-migration: phase N — <description>`.
5. **If a test fails**, stop. Do not proceed to next step. The shim means you can revert by changing one import line back.

---

## Phase 0 — Create the shared library

### 0.1 Create directory structure

```bash
mkdir -p ~/Software/Prototypes/shared_agents/src/shared_agents
mkdir -p ~/Software/Prototypes/shared_agents/tests
```

### 0.2 Write pyproject.toml

Create `~/Software/Prototypes/shared_agents/pyproject.toml`:

```toml
[project]
name = "shared_agents"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[project.optional-dependencies]
llm = ["litellm>=1.55.0"]
speech = ["mlx-audio>=0.3.0", "numpy", "sounddevice", "parakeet-mlx>=0.2.0", "soundfile"]
mlx_llm = ["mlx-lm>=0.20.0"]
audio = ["sounddevice", "numpy", "webrtcvad"]
gmail = ["google-api-python-client>=2.0", "google-auth>=2.0"]
imap = []
notify = []
youtube = ["youtube-transcript-api", "requests"]
all = ["agentkit[llm,speech,mlx_llm,audio,gmail,youtube]"]

[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

### 0.3 Write __init__.py

Create `~/Software/Prototypes/shared_agents/src/shared_agents/__init__.py`:

```python
"""Shared agent infrastructure — import only what you need.

Each module is independent. Install optional dependencies per module:
    pip install shared_agents[llm,tts]
"""
```

### 0.4 Install in dev mode

```bash
cd ~/Software/Prototypes/shared_agents
pip install -e .
```

Each project will later add `shared_agents[subset]` to its own `pyproject.toml` and re-run `pip install -e .` for that project.

### 0.5 Commit

```bash
cd ~/Software/Prototypes/shared_agents
git init
git add -A
git commit -m "shared_agents: initial package skeleton"
```

---

## Phase 1 — Extract single-repo modules

These modules exist in exactly one repo. No conflicts with other projects.

### 1.1 notify.py (from invoice-admin)

Source: `~/Software/Prototypes/invoice-admin/src/invoice_admin/core/notify.py`

1. **Copy** the file to `~/Software/Prototypes/shared_agents/src/shared_agents/notify.py`
2. **Change** the docstring from whatever it says to `"""Push notifications via ntfy.sh."""`
3. **Remove** the module-level `logger = logging.getLogger(__name__)` if the shared version just uses `print()` warnings or accepts a logger parameter. For now, keep it as-is — it's self-contained.
4. **Write smoke test** at `~/Software/Prototypes/shared_agents/tests/test_notify.py`:

```python
from shared_agents.notify import Notifier, Notification

def test_notification_dataclass():
    n = Notification(title="test", body="hello", priority=3)
    assert n.title == "test"
    assert n.priority == 3
```

5. **Verify**: `cd ~/Software/Prototypes/shared_agents && python -m pytest tests/test_notify.py -v`
6. **In invoice-admin**, change `src/invoice_admin/core/notify.py` to a re-export shim:

```python
from shared_agents.notify import *  # noqa: F401, F403
```

7. Run invoice-admin tests. If they pass, delete `src/invoice_admin/core/notify.py` and update all imports in invoice-admin from `invoice_admin.core.notify` to `shared_agents.notify`. Then run tests again.

8. Commit invoice-admin with message `shared-migration: phase 1.1 — notify.py moved to shared_agents`.

### 1.2 imap.py (from invoice-admin)

Source: `~/Software/Prototypes/invoice-admin/src/invoice_admin/core/imap.py`

1. **Copy** to `~/Software/Prototypes/shared_agents/src/shared_agents/imap.py`
2. **Fix imports**: the original likely does `from invoice_admin.core.errors import ...`. Remove that. Define a minimal `ImapError(Exception)` in the shared file if needed, or make error handling a callback.
3. **Write smoke test** at `tests/test_imap.py` that imports `ImapCollector, EmailMessage`.
4. Follow the same shim→test→delete→update-imports pattern as 1.1.

### 1.3 prompts.py (from local-chat)

Source: `~/Software/Prototypes/local-chat/src/prompts.py`

1. **Copy** to `~/Software/Prototypes/shared_agents/src/shared_agents/prompts.py`
2. **Fix the hardcoded path**: the original uses `Path(__file__).parent.parent / "prompts"`. Change to accept an explicit `prompts_dir: Path` parameter with a default of `Path.cwd() / "prompts"`:

```python
def load_prompt(persona: str, section: str, *, prompts_dir: Path | None = None) -> str:
    if prompts_dir is None:
        prompts_dir = Path.cwd() / "prompts"
    path = prompts_dir / f"{persona}.md"
    ...
```

3. Write smoke test that creates a temp dir with a `.md` file containing `## greeting` section.

4. In local-chat, change `src/prompts.py` to a shim that calls shared but passes `prompts_dir` pointing to local-chat's `prompts/` directory.

5. All local-chat callers (`from src.prompts import load_prompt`) continue working via the shim.

### 1.4 stt.py (from local-chat)

Source: `~/Software/Prototypes/local-chat/src/stt.py`

1. **Copy** to `~/Software/Prototypes/shared_agents/src/shared_agents/stt.py`
2. No code changes needed — it's fully self-contained.
3. Write smoke test that imports `MlxStt` (does not call `.load()` — too heavy).
4. Shim → test → delete → update imports.

### 1.5 audio_io.py (from local-chat)

Source: `~/Software/Prototypes/local-chat/src/audio_io.py`

1. **Copy** to `~/Software/Prototypes/shared_agents/src/shared_agents/audio_io.py`
2. No code changes needed.
3. Smoke test: import `AudioRecorder, AudioPlayer, WHISPER_SAMPLE_RATE`.
4. Shim → test → delete → update imports.

### 1.6 mlx_llm.py (from local-chat)

**CRITICAL — naming conflict**: The canonical source is `local-chat/src/llm.py`. But `shared_agents/llm.py` will be the litellm wrapper (Phase 5). So the shared module must be named `mlx_llm.py`, NOT `llm.py`.

Source: `~/Software/Prototypes/local-chat/src/llm.py` → Target: `~/Software/Prototypes/shared_agents/src/shared_agents/mlx_llm.py`

1. **Copy** the file, renaming it to `mlx_llm.py`.
2. No code changes needed — it's self-contained. The class is `MlxLlm`.
3. Smoke test: `from shared_agents.mlx_llm import MlxLlm, MODEL_VARIANTS`.
4. In local-chat, change `src/llm.py` to a re-export shim:

```python
from shared_agents.mlx_llm import *  # noqa: F401, F403
```

5. All local-chat callers (`from src.llm import MlxLlm`) continue working.
6. After all consumers updated to `from shared_agents.mlx_llm import MlxLlm`, delete `src/llm.py`.

### 1.7 youtube.py (from local-chat)

Source: `~/Software/Prototypes/local-chat/src/youtube_scraper.py` → Target: `~/Software/Prototypes/shared_agents/src/shared_agents/youtube.py`

1. **Copy and rename** to `youtube.py`.
2. **Fix the Rich console global**: the original has `console = Console()` at module level. Remove it. Change all `console.print(...)` to use `logging.getLogger(__name__).info(...)` or accept an optional `console: Console | None = None` parameter on public functions.
3. Alternatively for minimal change: keep `console` but wrap in `if _console is None: _console = Console()`. Document that callers can replace it.
4. Smoke test: mock `youtube_transcript_api`, test `extract_video_id()`.
5. In local-chat, change `src/youtube_scraper.py` to shim. Update `generate_speech.py` which does `from src.youtube_scraper import get_video_transcript`.

### 1.8 time_utils.py (from swim)

Source: `~/Software/Prototypes/swim/src/swim/drills/pace.py`

Extract only these functions (they are self-contained, pure math, no swim imports):
- `sec_to_pace(seconds: float) -> str` — converts seconds to "m:ss" format
- `parse_avg_100m_pace_sec(pace: str) -> float` — converts "MM:SS" to seconds

These are the only functions in `pace.py` with no swim-specific semantics. Leave everything else (`cap_duration_per_segment`, `max_plausible_swim_min`, `is_rest_merged_lap`, `capped_block_duration`, `pace_sec_from_seg`) in swim — they depend on swim distance/lap constants.

Target: `~/Software/Prototypes/shared_agents/src/shared_agents/time_utils.py`

```python
"""Generic time formatting utilities."""
from __future__ import annotations
import math

def sec_to_pace(seconds: float) -> str:
    """Convert seconds to m:ss formatted pace string."""
    if seconds <= 0:
        return "0:00"
    minutes = int(seconds // 60)
    secs = round(seconds % 60)
    if secs == 60:
        minutes += 1
        secs = 0
    return f"{minutes}:{secs:02d}"

def parse_avg_100m_pace_sec(pace: str) -> float:
    """Parse M:SS or MM:SS pace string to float seconds."""
    parts = pace.strip().split(":")
    if len(parts) != 2:
        return 0.0
    try:
        return int(parts[0]) * 60 + float(parts[1])
    except (ValueError, TypeError):
        return 0.0
```

1. Smoke test: convert round-trip (sec_to_pace → parse_avg_100m_pace_sec).
2. In swim, `pace.py` replaces those two function bodies with imports from shared.
3. Run swim tests. Delete originals once tests pass.

### 1.9 chart_utils.py (from swim)

Source: `~/Software/Prototypes/swim/src/swim/charts/ticks.py` + the Monday-grid logic from `charts/dates.py`

Extract:
- `r_pretty_y_axis(data_min, data_max, n=5)` from `ticks.py`
- `panel2_x_axis_mondays_and_breaks(dates)` from `dates.py`

Target: `~/Software/Prototypes/shared_agents/src/shared_agents/chart_utils.py`

These functions are fully self-contained (pure numpy + stdlib). No swim-specific imports.

1. Copy both functions, keeping the `lru_cache` on the R subprocess call.
2. Smoke test: call `r_pretty_y_axis(0, 100)` — should fall back to numpy linspace since Rscript may not be available. Test that it returns a list of floats.
3. In swim, replace original function bodies with imports from shared. Run swim tests.

### 1.10 apple_health.py (from swim)

Source: `~/Software/Prototypes/swim/src/swim/ingest/apple_stroke_map.py`

Extract only the generic XML and time utilities (no swim-specific stroke/SWOLF logic):
- `parse_apple_export_datetime(value: str) -> datetime` — multi-format datetime parser
- `intervals_overlap_half_open(start1, end1, start2, end2) -> bool` — half-open interval overlap check

Target: `~/Software/Prototypes/shared_agents/src/shared_agents/apple_health.py`

```python
"""Generic Apple Health data utilities."""
from __future__ import annotations
from datetime import datetime, timezone

def parse_apple_export_datetime(value: str) -> datetime:
    """Parse Apple Health export.xml datetime string (multiple formats)."""
    # Copy the original function body exactly
    ...

def intervals_overlap_half_open(
    start1: datetime, end1: datetime, start2: datetime, end2: datetime
) -> bool:
    """Check if two half-open intervals [start, end) overlap."""
    return start1 < end2 and start2 < end1
```

The bulk of `apple_stroke_map.py` (385 lines: XML iterparse, stroke summing, SWOLF enrichment, row enrichment) stays in swim — it's domain-specific.

Smoke test: parse a few known datetime strings, test interval overlap with obvious cases.

---

**Phase 1 exit criteria:** All 10 smoke tests pass. Zero originals deleted yet — they're still behind shims.

---

## Phase 2 — repo_root() + common.py

### 2.1 Write the canonical repo_root()

Create `~/Software/Prototypes/shared_agents/src/shared_agents/common.py`:

```python
"""Shared utilities: repo root detection, CSV/markdown writing, safe parsing."""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any


def repo_root(
    *,
    marker: str = "pyproject.toml",
    env_var: str = "REPO_ROOT",
    start: Path | None = None,
) -> Path:
    """Find the repository root directory.

    Resolution order:
    1. ``$REPO_ROOT`` environment variable (or ``env_var``)
    2. Walk up from ``start`` (defaults to CWD) looking for ``marker``
    3. Walk up from this file's location looking for ``marker``
    4. Raise FileNotFoundError
    """
    env_val = os.environ.get(env_var, "").strip()
    if env_val:
        return Path(env_val).expanduser().resolve()

    search = start.resolve() if start else Path.cwd()
    for ancestor in [search, *search.parents]:
        if (ancestor / marker).is_file():
            return ancestor

    file_dir = Path(__file__).resolve().parent
    for ancestor in [file_dir, *file_dir.parents]:
        if (ancestor / marker).is_file():
            return ancestor

    raise FileNotFoundError(
        f"Could not find {marker} walking up from {search} or {file_dir}"
    )


def parse_float(value: Any, default: float = 0.0) -> float:
    """Safely coerce a value to float, returning *default* on failure."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    """Write a list of dicts to a CSV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_md(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    """Write a list of dicts to a markdown table file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        header = "| " + " | ".join(fieldnames) + " |"
        sep = "|" + "|".join("---" for _ in fieldnames) + "|"
        f.write(header + "\n" + sep + "\n")
        for row in rows:
            vals = [str(row.get(k, "")) for k in fieldnames]
            f.write("| " + " | ".join(vals) + " |\n")


def sort_rows(
    rows: list[dict[str, Any]], key: str, *, reverse: bool = False
) -> list[dict[str, Any]]:
    """Sort a list of dicts by a key, with None values sorted last."""
    def sort_key(r: dict[str, Any]) -> tuple[bool, Any]:
        v = r.get(key)
        return (v is None, v if v is not None else "")
    return sorted(rows, key=sort_key, reverse=reverse)
```

### 2.2 Migrate each project

**swim** (`swim/src/swim/common.py` — 195 lines):
1. Add `shared_agents` to swim's `pyproject.toml` dependencies (no extras needed — `common.py` uses stdlib only):
   ```toml
   dependencies = ["shared_agents>=0.1.0", ...]
   ```
2. Reinstall: `pip install -e ~/Software/Prototypes/swim`
3. In `swim/src/swim/common.py`, keep swim-specific constants (`FIELDNAMES`, `MD_SCHEMA`, `format_avg_100m`, `avg_strokes_per_lap`). Replace `repo_root()`, `parse_float()`, `write_csv()`, `write_md()`, `sort_rows()` with re-exports:
   ```python
   from shared_agents.common import (
       repo_root,
       parse_float,
       write_csv,
       write_md,
       sort_rows,
   )
   ```
4. Run swim tests: `python -m pytest tests/ -x` (if tests exist). Otherwise run: `python -m swim dashboard`.

**decisionmaker** (`decisionmaker/src/decisionmaker/common.py` — 36 lines):
1. Add `shared_agents` to dependencies, reinstall.
2. Replace the entire file with:
   ```python
   from shared_agents.common import repo_root  # noqa: F401
   ```
3. Run: `python -m pytest tests/ -x`

**email-digest** (`email_digest/paths.py` — 24 lines):
1. Add dependency, reinstall.
2. Replace `repo_root()` body with:
   ```python
   from shared_agents.common import repo_root as _repo_root
   def repo_root() -> Path:
       return _repo_root()
   ```
   (Keep the function wrapper so existing callers don't break. The original uses no parameters.)
3. Run email-digest tests.

**invoice-admin** (inlined in `core/config.py`):
1. Add dependency, reinstall.
2. Replace the inline `repo_root()` function with `from shared_agents.common import repo_root`.
3. Run invoice-admin tests.

---

## Phase 3 — Gmail query builder (trivial duplicate)

Source: `~/Software/Prototypes/email-digest/src/email_digest/gmail_query.py` (60 lines)

The implementations in email-digest and decisionmaker are near-identical. Pick email-digest's version (it's the canonical source from the original port, per `cli.py` comment).

1. **Copy** to `~/Software/Prototypes/shared_agents/src/shared_agents/gmail_query.py`
2. **Write smoke test**: 

```python
from shared_agents.gmail_query import sender_pattern_to_from_clause, build_digest_gmail_query

def test_sender_pattern_basic():
    assert "from:foo@bar.com" in sender_pattern_to_from_clause("foo@bar.com")

def test_sender_pattern_wildcard():
    clause = sender_pattern_to_from_clause("*@bar.com")
    assert "bar.com" in clause

def test_build_query_defaults():
    q = build_digest_gmail_query(window_days=7, senders=[], folders=[], since=None)
    assert "newer_than:7d" in q
    assert "-in:chats" in q
```

3. **decisionmaker**: replace `src/decisionmaker/core/gmail_query.py` with shim:
   ```python
   from shared_agents.gmail_query import *  # noqa: F401, F403
   ```
4. **email-digest**: replace `src/email_digest/gmail_query.py` with same shim.
5. Run both test suites. Delete originals.

---

## Phase 4 — TTS module (2 repos, already half-done)

Source: `~/Software/Prototypes/local-chat/src/tts.py` (109 lines) — canonical

### 4.1 Lift canonical copy

1. **Copy** `local-chat/src/tts.py` to `~/Software/Prototypes/shared_agents/src/shared_agents/tts.py`
2. No code changes — it's fully self-contained.

### 4.2 Migrate local-chat

1. Add `shared_agents[tts]` to local-chat's `requirements.txt` or `pyproject.toml`.
2. Run `pip install -e ~/Software/Prototypes/shared_agents[tts]` (or install mlx-audio etc. if not already present).
3. Change `local-chat/src/tts.py` to re-export shim:
   ```python
   from shared_agents.tts import *  # noqa: F401, F403
   ```
4. All callers (`from src.tts import MlxTts`) continue working.
5. Run improv to verify (loads models, so this is a real integration test).

### 4.3 Migrate decisionmaker

1. Add `shared_agents[tts]` to decisionmaker's `pyproject.toml` dependencies.
2. Run `pip install -e ~/Software/Prototypes/decisionmaker`.
3. **Delete** `decisionmaker/src/decisionmaker/render/tts.py` (the duplicate with voice constants).
4. In `decisionmaker/src/decisionmaker/cli.py`, change:
   ```python
   # Before
   from decisionmaker.render.tts import KOKORO_DEFAULT_VOICE, KOKORO_VOICES, KOKORO_TTS_AVAILABLE
   # After
   from shared_agents.tts import KOKORO_DEFAULT_VOICE, KOKORO_VOICES
   KOKORO_TTS_AVAILABLE = True  # decisionmaker always runs where sounddevice is present
   ```
   
   And in `_speak_synthesis()`:
   ```python
   # Before
   from decisionmaker.render.tts import speak_synthesis
   # After
   from shared_agents.tts import MlxTts
   import sounddevice as sd
   tts = MlxTts()
   tts.load()
   audio, sample_rate = tts.synthesize(synthesis, voice=voice)
   sd.play(audio, samplerate=sample_rate)
   sd.wait()
   ```
   
   Rationale: `shared_agents.tts` doesn't have a `speak_synthesis()` convenience function (it's local-chat's wrapper). Inline the 5-line speak logic directly in `_speak_synthesis()` where it belongs.

5. Run: `python -m pytest tests/ -x`

---

## Phase 5 — Error base class (low risk, pattern copy)

### 5.1 Write shared errors

Create `~/Software/Prototypes/shared_agents/src/shared_agents/errors.py`:

```python
"""Shared exception hierarchy for agent tools."""
from __future__ import annotations
from typing import Any


class AgentError(Exception):
    """Base exception for all agent tool errors."""


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
```

### 5.2 Migrate decisionmaker

decisionmaker already has `LLMFailureWithTranscript` in `core/errors.py`. Change it to:

```python
from shared_agents.errors import LLMFailureWithTranscript as _BaseLLMFailure

class LLMFailureWithTranscript(_BaseLLMFailure):
    """LLM call failed with partial transcript for resume."""
```

This preserves backward compatibility (same class name, same module path) while inheriting from shared. No other imports in decisionmaker need to change — `from decisionmaker.core.errors import LLMFailureWithTranscript` still works.

### 5.3 Migrate invoice-admin

invoice-admin's `core/errors.py` has `InvoiceError` as base. Change to:

```python
from shared_agents.errors import AgentError

class InvoiceError(AgentError):
    """Base exception for invoice-admin."""
```

All subclasses (`ConfigError`, `TrackerError`, etc.) inherit from `InvoiceError` which now inherits from `AgentError`. No other imports change.

---

## Phase 6 — Config loading helpers (low risk, all repos)

Create `~/Software/Prototypes/shared_agents/src/shared_agents/config.py`:

```python
"""Config loading helpers: YAML→frozen dataclass, env var overlay."""
from __future__ import annotations

import os
from pathlib import Path
from typing import TypeVar
import dataclasses

T = TypeVar("T")


def load_yaml_config(path: Path, dataclass_type: type[T]) -> T:
    """Load a YAML file into a frozen dataclass instance.

    Fields in the dataclass with no corresponding YAML key keep their defaults.
    Extra YAML keys are ignored.
    """
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    fields = {f.name for f in dataclasses.fields(dataclass_type)}
    filtered = {k: v for k, v in data.items() if k in fields}

    return dataclass_type(**filtered)


def env_override(config: T, *, prefix: str = "") -> T:
    """Override dataclass field values from environment variables.

    Field ``foo_bar`` maps to env var ``PREFIX_FOO_BAR``.
    Returns a new instance (works with frozen dataclasses).
    """
    overrides: dict[str, str] = {}
    field_map = {f.name.upper(): f.name for f in dataclasses.fields(config)}

    for env_key, env_val in os.environ.items():
        if prefix and not env_key.startswith(prefix.upper()):
            continue
        stripped = env_key[len(prefix):] if prefix else env_key
        field_name = field_map.get(stripped.upper())
        if field_name is not None:
            overrides[field_name] = env_val

    if not overrides:
        return config

    current = {f.name: getattr(config, f.name) for f in dataclasses.fields(config)}
    for name, val in overrides.items():
        field_type = type(current[name])
        if field_type is bool:
            current[name] = val.lower() in ("1", "true", "yes")
        elif field_type is int:
            current[name] = int(val)
        elif field_type is float:
            current[name] = float(val)
        elif field_type is Path:
            current[name] = Path(val).expanduser().resolve()
        else:
            current[name] = val

    return dataclasses.replace(config, **current)
```

Each project uses these as building blocks in their own `load_config()`. Example for decisionmaker:

```python
# decisionmaker/core/config.py — keep load_config() but add:
from shared_agents.config import env_override

def load_config() -> DecisionMakerConfig:
    cfg = DecisionMakerConfig(...)  # existing constructor logic
    return env_override(cfg, prefix="DECISIONMAKER_")
```

This is optional. If a project has no YAML config, it doesn't need `load_yaml_config`. The helpers are ~60 lines — zero cost to import, zero cost if unused.

---

## Phase 7 — Gmail API client (3 repos, needs unification)

This is the first hard phase. Three repos have Gmail code with different features.

### 7.1 What goes into shared_agents/gmail.py

Write `~/Software/Prototypes/shared_agents/src/shared_agents/gmail.py` with these concrete components (NOT stubs):

```python
"""Gmail API client — Protocol-based backend, facade, and utilities."""
from __future__ import annotations

import base64
import json
import os
import re
from html import unescape
from pathlib import Path
from typing import Any, Protocol


# ———— Backend Protocol ————

class GmailBackend(Protocol):
    """Pluggable Gmail read-only backend.

    Implementations: GmailApiBackend (googleapiclient), MockGmailBackend (tests),
    ImapBackend (via imaplib).
    """
    def fetch_message_body(self, message_id: str) -> str: ...
    def search_messages(self, query: str, max_results: int = 10) -> list[dict[str, str]]: ...


# ———— GmailFacade ————

class GmailFacade:
    """Wraps a GmailBackend with error handling and payload decoding."""

    def __init__(self, backend: GmailBackend) -> None:
        self._backend = backend

    def get_message(self, message_id: str) -> str:
        try:
            return self._backend.fetch_message_body(message_id)
        except Exception as e:
            raise GmailError(f"Failed to fetch message {message_id}: {e}") from e

    def search(self, query: str, max_results: int = 10) -> list[dict[str, str]]:
        try:
            return self._backend.search_messages(query, max_results=max_results)
        except Exception as e:
            raise GmailError(f"Search failed for '{query}': {e}") from e


# ———— Gmail API Backend ————

class GmailApiBackend:
    """GmailBackend using googleapiclient (the standard Gmail REST API)."""

    def __init__(self, credentials_path: Path | None = None) -> None:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        self._creds = self._load_credentials(credentials_path)
        self._service = build("gmail", "v1", credentials=self._creds)

    def fetch_message_body(self, message_id: str) -> str:
        from googleapiclient.errors import HttpError
        try:
            msg = self._service.users().messages().get(
                userId="me", id=message_id, format="full"
            ).execute()
        except HttpError as e:
            if e.resp.status == 404:
                raise GmailMessageNotFoundError(f"Message {message_id} not found")
            raise GmailError(str(e)) from e
        return _extract_body_from_payload(msg.get("payload", {}))

    def search_messages(self, query: str, max_results: int = 10) -> list[dict[str, str]]:
        results = self._service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        return [
            {"id": m["id"], "threadId": m.get("threadId", "")}
            for m in results.get("messages", [])
        ]

    @staticmethod
    def _load_credentials(path: Path | None) -> Any:
        from google.oauth2.credentials import Credentials

        if path is None:
            path = Path.home() / ".config" / "gmail_token.json"

        if path.is_file():
            creds = Credentials.from_authorized_user_file(str(path))
            if creds and creds.valid:
                return creds

        # Fall back to service account or env var credentials
        key_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if key_path:
            from google.oauth2 import service_account
            return service_account.Credentials.from_service_account_file(
                key_path,
                scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            )

        raise GmailAuthError(
            f"No valid Gmail credentials found. Place token at {path} "
            f"or set GOOGLE_APPLICATION_CREDENTIALS."
        )


# ———— Payload decoding utilities ————

def _extract_body_from_payload(payload: dict) -> str:
    """Extract plaintext or HTML body from a Gmail message payload part."""
    if "parts" in payload:
        for part in payload["parts"]:
            result = _extract_body_from_payload(part)
            if result:
                return result
        return ""

    mime = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data", "")
    if not data:
        return ""

    decoded = base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")

    if mime == "text/plain":
        return decoded
    if mime == "text/html":
        return _strip_html(decoded)

    return ""


def _strip_html(html: str) -> str:
    """Convert HTML email body to plaintext."""
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</p>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", "", html)
    text = unescape(html)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    return text.strip()


# ———— Body cleaning ————

def clean_email_body(raw: str) -> str:
    """Remove quoted replies, forwarded blocks, signatures, and excess whitespace.

    Handles German sign-offs (Mit freundlichen Grüßen, Viele Grüße, etc.).
    Adapted from decisionmaker's body_cleaner.py.
    """
    # Remove quoted lines (email clients prefix with >)
    cleaned = re.sub(r"^>.*$", "", raw, flags=re.MULTILINE)

    # Remove forwarded message blocks
    cleaned = re.sub(
        r"(?i)-+ ?forwarded message ?-+.*$",
        "",
        cleaned,
        flags=re.DOTALL,
    )

    # Remove signature blocks (German + English)
    sign_offs = [
        r"Mit freundlichen Gr(ü|u)(ß|ss)en.*$",
        r"Viele Gr(ü|u)(ß|ss)e.*$",
        r"Liebe Gr(ü|u)(ß|ss)e.*$",
        r"Herzliche Gr(ü|u)(ß|ss)e.*$",
        r"Beste Gr(ü|u)(ß|ss)e.*$",
        r"Best regards.*$",
        r"Kind regards.*$",
        r"Cheers.*$",
        r"Thanks.*$",
        r"Sent from my.*$",
        r"Get Outlook for.*$",
    ]
    for pattern in sign_offs:
        cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL | re.IGNORECASE | re.MULTILINE)

    # Collapse whitespace
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()
    return cleaned


# ———— Exceptions ————

class GmailError(Exception):
    """Base for Gmail-related errors."""


class GmailAuthError(GmailError):
    """Authentication/credentials failure."""


class GmailMessageNotFoundError(GmailError):
    """Requested message not found in mailbox."""


# ———— Spec resolution (decisionmaker-specific) ————

def resolve_spec_to_message(
    client: GmailFacade,
    spec: str,
    *,
    pick_index: int = 0,
) -> tuple[str, str]:
    """Resolve a message ID or Gmail search query to (message_ref, body).

    If *spec* looks like a message ID (contains '@'), fetch directly.
    Otherwise, treat it as a Gmail search query and return the first result.
    *pick_index* selects which search result to use (0 = first).
    """
    if "@" in spec and "." in spec.split("@")[-1]:
        try:
            body = client.get_message(spec)
            return spec, body
        except GmailError:
            pass

    results = client.search(spec, max_results=max(pick_index + 1, 5))
    if not results:
        raise GmailError(f"No messages found for query: {spec}")

    if pick_index >= len(results):
        raise GmailError(
            f"Query returned {len(results)} results, but pick_index={pick_index}"
        )

    msg = results[pick_index]
    body = client.get_message(msg["id"])
    return msg["id"], body
```

### 7.2 Migrate each project

**invoice-admin** — already has `GmailBackend` Protocol + `GmailFacade` + `GmailApiBackend`. Replace them with shared imports:

```python
# invoice_admin/googleads/gmail_facade.py — becomes shim
from shared_agents.gmail import GmailBackend, GmailFacade, GmailApiBackend

# invoice_admin/googleads/gmail_api_backend.py — becomes shim  
from shared_agents.gmail import GmailApiBackend
```

Keep invoice-admin-specific things (SMTP send, app passwords) in `gmail_smtp.py` — those aren't shared.

**decisionmaker** — currently has `GmailClient`, `resolve_spec_to_message`, payload decoders, and `body_cleaner`. Replace with shared imports:

```python
# decisionmaker/core/gmail.py
from shared_agents.gmail import (
    GmailApiBackend as GmailClient,  # rename for backward compat
    GmailFacade,
    resolve_spec_to_message,
    clean_email_body as _clean,
    GmailError,
    GmailAuthError,
    GmailMessageNotFoundError,
)
```

Keep the `GmailClient.from_env()` factory method if decisionmaker relies on it — add it as a thin wrapper:

```python
class GmailClient(GmailApiBackend):
    @classmethod
    def from_env(cls) -> "GmailClient":
        return cls()
```

**email-digest** — uses Gmail through the `unsubscribe` subpackage (`gmail_api_backend`, `gmail_facade`). This is the most coupled. Minimum change: add `shared_agents.gmail` as a dependency and replace the `unsubscribe/gmail_api_backend.py` + `unsubscribe/gmail_facade.py` with re-exports. The email-digest `pipeline.py` and `cli.py` continue working unchanged since they import through the facade.

### 7.3 Verification

After migrating each project, run its test suite. The Protocol-based design means any project can inject `MockGmailBackend` for tests.

---

## Phase 8 — SQLite store base class (optional, medium risk)

### 8.1 Write SqliteStore

Create `~/Software/Prototypes/shared_agents/src/shared_agents/sqlite_store.py`:

```python
"""Generic SQLite storage base class."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SqliteStore:
    """Base class for SQLite-backed persistent storage.

    Subclass and provide *schema_ddl* (CREATE TABLE IF NOT EXISTS ...).
    """
    def __init__(self, db_path: Path, schema_ddl: str) -> None:
        self.db_path = db_path
        self._schema = schema_ddl

    def connect(self) -> sqlite3.Connection:
        """Open connection, ensure directory and schema exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(self._schema)
        conn.commit()
        return conn

    def insert(self, table: str, **kwargs: Any) -> int:
        """Insert a row. Returns the new rowid."""
        keys = list(kwargs)
        placeholders = ", ".join("?" for _ in keys)
        columns = ", ".join(keys)
        values = list(kwargs.values())
        conn = self.connect()
        try:
            cur = conn.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                values,
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def update(self, table: str, row_id: int, **kwargs: Any) -> None:
        """Update a row by id column. Sets ``updated_at`` to UTC now if the column exists."""
        if not kwargs:
            return
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [row_id]
        conn = self.connect()
        try:
            conn.execute(
                f"UPDATE {table} SET {sets} WHERE id = ?",
                values,
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, table: str, row_id: int) -> dict[str, Any] | None:
        """Return a row as a dict, or None."""
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(
                f"SELECT * FROM {table} WHERE id = ?",
                (row_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list(
        self,
        table: str,
        *,
        where: str = "",
        params: tuple[Any, ...] = (),
        order_by: str = "id DESC",
    ) -> list[dict[str, Any]]:
        """Return all matching rows as dicts."""
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        sql += f" ORDER BY {order_by}"
        conn = self.connect()
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
```

### 8.2 Migrate decisionmaker

`decisionmaker/persistence/sessions.py` (150 lines) subclasses:

```python
from shared_agents.sqlite_store import SqliteStore

SCHEMA = """CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    ...
);"""

class SessionStore(SqliteStore):
    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path, SCHEMA)

    def create_session(self, **kwargs: Any) -> int:
        kwargs.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        kwargs.setdefault("updated_at", kwargs["created_at"])
        kwargs.setdefault("state", "collecting")
        kwargs.setdefault("transcript", "[]")
        kwargs.setdefault("rounds", 0)
        kwargs.setdefault("cost_usd", 0.0)
        return self.insert("sessions", **kwargs)

    def finalize_synthesis(self, sid: int, synthesis: str, cost: float) -> None:
        self.update("sessions", sid, synthesis=synthesis, state="done", cost_usd=cost)

    def set_state(self, sid: int, state: str) -> None:
        self.update("sessions", sid, state=state)

    def set_transcript(self, sid: int, transcript: list[dict]) -> None:
        import json
        self.update("sessions", sid, transcript=json.dumps(transcript))

    def get_session(self, sid: int) -> dict | None:
        return self.get("sessions", sid)

    def list_sessions(self) -> list[dict]:
        return self.list("sessions")
```

Then update `cli.py` to use `SessionStore` instead of raw `sessions.*` functions.

### 8.3 Other projects

email-digest and invoice-admin subclass similarly. This phase is **optional** — if the base class doesn't reduce code meaningfully, skip it. The benefit is standardized connection handling (WAL mode, auto-directory creation, schema init) rather than each project implementing it slightly differently.

---

## Phase 9 — LLM module (hardest, 3 repos, diverged features)

### 9.1 Build shared_agents/llm.py

Write `~/Software/Prototypes/shared_agents/src/shared_agents/llm.py`. This is a **write-once** module — do not iterate across projects. All three repos will import from it.

Key design decisions:
- **Model aliases are project-specific.** Each project defines its own `MODEL_ALIASES` dict. The shared module provides default aliases as a fallback.
- **API key resolution** from `~/.local/share/opencode/auth.json` is shared behavior — identical in all three.
- **Logging is injectable.** Pass an optional `log_fn` callback instead of hardcoding SQLite.

```python
"""LLM abstraction via litellm — provider aliases, completion, cost tracking."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

# ———— Default model aliases (overridable per project) ————

DEFAULT_MODEL_ALIASES: dict[str, str] = {
    "fast": "deepseek/deepseek-v4-flash",
    "smart": "deepseek/deepseek-v4-pro",
    "local": "openai/local-model",
    "local_smart": "openai/local-model",
}


def resolve_model(alias: str, *, aliases: dict[str, str] | None = None) -> str:
    """Resolve a model alias to a provider model ID.

    Environment variable ``DECISIONMAKER_MODEL`` (or the alias name itself
    uppercased + _MODEL) overrides the alias lookup.
    """
    alias_map = aliases or DEFAULT_MODEL_ALIASES
    env_key = f"{alias.upper()}_MODEL"
    env_val = os.environ.get(env_key, "").strip()
    if env_val:
        return env_val
    return alias_map.get(alias, alias)


# ———— API key resolution ————

def _opencode_auth_path() -> Path:
    return Path.home() / ".local" / "share" / "opencode" / "auth.json"


def read_api_key_from_opencode(provider: str) -> str | None:
    """Read an API key from OpenCode's auth.json for the given provider."""
    path = _opencode_auth_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    block = data.get(provider)
    if isinstance(block, dict):
        key = block.get("key")
        if isinstance(key, str) and key.strip():
            return key.strip()
    return None


def ensure_api_key(provider: str, env_var: str) -> None:
    """Set *env_var* from OpenCode auth if not already in environment."""
    if os.environ.get(env_var, "").strip():
        return
    key = read_api_key_from_opencode(provider)
    if key:
        os.environ[env_var] = key


# ———— Core completion ————

LogFn = Callable[[dict[str, Any]], None]
"""Optional callback: log(record) where record has alias, model, tokens, cost, duration, error."""


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
    """Send a chat completion request via litellm. Returns the response text."""
    import time
    import litellm

    model = resolve_model(alias, aliases=aliases)

    if "deepseek" in model.lower():
        ensure_api_key("deepseek", "DEEPSEEK_API_KEY")

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        **extra_kwargs,
    }

    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    t0 = time.perf_counter()
    error_msg: str | None = None
    try:
        resp = litellm.completion(**kwargs)
    except Exception as e:
        error_msg = str(e)
        raise LLMError(error_msg) from e
    finally:
        if log_fn:
            duration_ms = (time.perf_counter() - t0) * 1000
            usage = {}
            if error_msg is None:
                try:
                    usage = _extract_usage(resp)
                except Exception:
                    pass
            try:
                cost = float(litellm.completion_cost(completion_response=resp))
            except Exception:
                cost = 0.0
            log_fn({
                "alias": alias,
                "model": model,
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "cost_usd": cost,
                "duration_ms": duration_ms,
                "error": error_msg,
            })

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
    """Send a chat completion request with tool definitions. Returns the litellm response object."""
    import litellm

    model = resolve_model(alias, aliases=aliases)

    if "deepseek" in model.lower():
        ensure_api_key("deepseek", "DEEPSEEK_API_KEY")

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": tool_choice,
        "max_tokens": max_tokens,
        "temperature": temperature,
        **extra_kwargs,
    }

    try:
        return litellm.completion(**kwargs)
    except Exception as e:
        raise LLMError(str(e)) from e


def response_cost_usd(response: Any) -> float:
    """Estimate USD cost of a litellm response."""
    try:
        import litellm
        return float(litellm.completion_cost(completion_response=response))
    except Exception:
        return 0.0


# ———— Helpers ————

def _extract_usage(resp: Any) -> dict[str, int]:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return {}
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }


def resolve_model_id(alias: str, *, aliases: dict[str, str] | None = None) -> str:
    """Resolved provider model string for a configured alias."""
    return resolve_model(alias, aliases=aliases)


# ———— LM Studio local model support ————

def _local_kwargs(alias: str) -> dict[str, Any]:
    """Extra kwargs for LM Studio / local OpenAI-compatible endpoints."""
    if alias not in ("local", "local_smart"):
        return {}
    return {
        "api_base": os.environ.get("LM_STUDIO_BASE_URL", "http://localhost:1234/v1").rstrip("/"),
        "api_key": os.environ.get("LM_STUDIO_API_KEY", "lm-studio"),
    }


# ———— Exception ————

class LLMError(Exception):
    """LLM call failed."""
```

### 9.2 Migrate decisionmaker (easiest — smallest divergence)

1. Add `shared_agents[llm]` to `pyproject.toml`, reinstall.
2. Replace `decisionmaker/core/llm.py` with a shim preserving backward compat:

```python
"""LLM abstraction — re-exports from shared_agents."""
from shared_agents.llm import (
    DEFAULT_MODEL_ALIASES as MODEL_ALIASES,
    complete,
    complete_with_tools,
    response_cost_usd,
    resolve_model_id,
    resolve_model as _resolve_model,
    _local_kwargs,
    _opencode_auth_path,
    read_api_key_from_opencode,
    ensure_api_key as _ensure_deepseek_env_from_opencode,
)
```

Wait — decisionmaker has specific functions like `_ensure_deepseek_env_from_opencode()` that are called by name. Keep those as re-exports with aliases. The shared `ensure_api_key("deepseek", "DEEPSEEK_API_KEY")` is equivalent but has a different signature.

Actually, simpler approach: in the decisionmaker shim, wrap the shared functions to match the old API:

```python
def _ensure_deepseek_env_from_opencode() -> None:
    from shared_agents.llm import ensure_api_key
    ensure_api_key("deepseek", "DEEPSEEK_API_KEY")

def read_deepseek_key_from_opencode_auth_files() -> str | None:
    from shared_agents.llm import read_api_key_from_opencode
    return read_api_key_from_opencode("deepseek")
```

3. Run `python -m pytest tests/ -x`. All existing imports (`from decisionmaker.core.llm import complete`) still work through the shim.

### 9.3 Migrate email-digest (medium)

Similar shim approach. email-digest's `llm.py` has `MLX_MODEL_VARIANTS` for local MLX models — keep those in a project-specific config or a separate `mlx_config.py`. The shared `complete()` with `log_fn` callback replaces email-digest's hardcoded SQLite logging.

### 9.4 Migrate invoice-admin (medium)

invoice-admin's `llm.py` has `LLMProvider` class with `complete()` and `complete_with_pdf()`. Replace the `complete()` method body with a call to shared `complete()`. Keep `complete_with_pdf()` in invoice-admin (it's multimodal-specific and not used by other projects). The `LLMProvider` class becomes a thin wrapper:

```python
class LLMProvider:
    def complete(self, prompt, alias, **kwargs) -> str:
        from shared_agents.llm import complete
        return complete(
            [{"role": "user", "content": prompt}],
            alias=alias,
            log_fn=self._log_call,
            **kwargs,
        )
    
    def complete_with_pdf(self, prompt, pdf_bytes, alias, **kwargs) -> str:
        # stays in invoice-admin — multimodal PDF is not shared
        ...
    
    def _log_call(self, record: dict) -> None:
        # write to invoice-admin's SQLite log table
        ...
```

---

## Migration Execution Order

```
Phase 0  — Create shared_agents repo, pyproject.toml, __init__.py
Phase 1  — notify, imap, prompts, stt, audio_io, mlx_llm, youtube, time_utils, chart_utils, apple_health
Phase 2  — repo_root() + common.py
Phase 3  — gmail_query.py
Phase 4  — tts.py
Phase 5  — errors.py (AgentError, LLMFailureWithTranscript)
Phase 6  — config.py (load_yaml_config, env_override)
Phase 7  — gmail.py (Protocol + Facade + Backend + cleaners)
Phase 8  — sqlite_store.py (SqliteStore base class)
Phase 9  — llm.py (litellm wrapper, last because hardest)
```

**Rule:** Each phase must pass `python -m pytest tests/ -x` in every affected project before proceeding. Commit each project after its phase with `shared-migration: phase N — <module>`.

---

## Per-project dependency summary

After full migration, each project's `pyproject.toml` dependencies include:

```toml
# decisionmaker
dependencies = [
    "agentkit[llm,speech,gmail]>=1.0.0",
    "litellm>=1.55.0",
    ...
]

# local-chat
dependencies = [
    "agentkit[all]>=1.0.0",
    "mlx>=0.20.0",
    "mlx-lm>=0.20.0",
    "mlx-audio>=0.3.0",
    ...
]

# email-digest
dependencies = [
    "agentkit[llm,gmail]>=1.0.0",
    "litellm>=1.55.0",
    ...
]

# invoice-admin
dependencies = [
    "agentkit[llm,gmail,notify,imap]>=1.0.0",
    "litellm>=1.55.0",
    ...
]

# swim
dependencies = [
    "agentkit>=1.0.0",  # common.py + utils only, no extras needed
    "pyyaml>=6.0",
    "numpy",
    "pandas",
    "matplotlib",
]
```

---

## AGENTS.md

The shared repo has one `AGENTS.md` at its root describing the available tools. Each project that uses OpenCode agents symlinks it:

```bash
ln -s ~/Software/Prototypes/agentkit/AGENTS.md ~/.config/opencode/agents/agentkit.md
```

Content is minimal — lists the modules, their purpose, and import paths:

```markdown
# AgentKit

Shared infrastructure for AI agent projects on Apple Silicon.

## Modules

| Path | Purpose | Install |
|------|---------|---------|
| `agentkit.llm.litellm` | LLM abstraction via litellm | `[llm]` |
| `agentkit.speech.tts` | Kokoro text-to-speech | `[speech]` |
| `agentkit.speech.stt` | Parakeet speech-to-text | `[speech]` |
| `agentkit.speech.audio_io` | Mic recording + speaker playback | `[audio]` |
| `agentkit.gmail.client` | Gmail API (OAuth, fetch, search) | `[gmail]` |
| `agentkit.gmail.query` | Gmail search query builder | `[gmail]` |
| `agentkit.notify.push` | Push notifications (ntfy.sh) | `[notify]` |
| `agentkit.imap.collector` | IMAP email collector | `[imap]` |
| `agentkit.prompts.loader` | Markdown prompt loader | (stdlib) |
| `agentkit.sqlite_store` | SQLite store base class | (stdlib) |
| `agentkit.common` | repo_root(), CSV/MD writers | (stdlib) |
| `agentkit.config` | YAML config + env override | (stdlib + pyyaml) |
| `agentkit.errors` | AgentError, LLMFailureWithTranscript | (stdlib) |

All modules are Apple Silicon only. MLX-dependent modules require macOS with M-series chip.
```

---

## CI/CD

Lightweight CI (`.github/workflows/ci.yml`):

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: macos-latest  # Apple Silicon required
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[all]"
      - run: python -m pytest tests/ -x -q
```

Cross-project verification is a manual smoke test script (`scripts/smoke-test.sh`):

```bash
#!/bin/bash
set -e
echo "=== decisionmaker ==="
cd ~/Software/Prototypes/decisionmaker && python -m pytest tests/ -x -q
echo "=== email-digest ==="
cd ~/Software/Prototypes/email-digest && python -m pytest tests/ -x -q
echo "=== invoice-admin ==="
cd ~/Software/Prototypes/invoice-admin && python -m pytest tests/ -x -q
echo "=== local-chat ==="
cd ~/Software/Prototypes/local-chat && python -c "from agentkit.speech.tts import MlxTts; print('ok')"
echo "=== swim ==="
cd ~/Software/Prototypes/swim && python -m swim dashboard 2>&1 | head -5
echo "=== all passed ==="
```

Run this after any change to agentkit before tagging a release.

---

## Version policy

| Version | Meaning |
|---|---|
| `0.1.0` | Initial extraction, each module matches canonical source |
| `0.2.0` | LLM module unified (breaking for email-digest, invoice-admin) |
| `0.3.0` | Gmail module unified (breaking for all 3 projects) |
| `0.4.0` | SQLite store unified |
| `0.5.0` | All shims removed from consuming projects |
| `1.0.0` | All 5 projects migrated, stable API |

Breaking changes are allowed at any 0.x release. Each project pins `>=0.1.0,<0.2` and updates the upper bound when verified against the new release.

---

## Phase 0 implementation (updated for nested structure)

### 0.1 Create directory structure

```bash
mkdir -p ~/Software/Prototypes/agentkit/src/agentkit/{speech,llm,gmail,imap,notify,prompts,youtube,apple,charts}
mkdir -p ~/Software/Prototypes/agentkit/tests/{speech,llm,gmail,imap,notify,prompts,youtube,apple,charts}
```

### 0.2 Write pyproject.toml

Create `~/Software/Prototypes/agentkit/pyproject.toml` — same as above with name `agentkit`.

### 0.3 Write AGENTS.md

Create `~/Software/Prototypes/agentkit/AGENTS.md` — content as shown above.

### 0.4 Write __init__.py stubs

Each `__init__.py` is empty except the top-level one:

```python
# src/agentkit/__init__.py
"""AgentKit — shared infrastructure for AI agent projects on Apple Silicon.

Usage:
    pip install agentkit[llm,speech,gmail]
    from agentkit.speech.tts import MlxTts
"""
```

### 0.5 Install and symlink

```bash
cd ~/Software/Prototypes/agentkit
pip install -e .
ln -s ~/Software/Prototypes/agentkit/AGENTS.md ~/.config/opencode/agents/agentkit.md
```

### 0.6 Commit

```bash
cd ~/Software/Prototypes/agentkit
git init
git add -A
git commit -m "agentkit: initial package skeleton with nested subpackages"
```

---

## Testing checklist per project

After each phase, run these exact commands:

```bash
# decisionmaker (52 tests)
cd ~/Software/Prototypes/decisionmaker
python -m pytest tests/ -x -q

# email-digest
cd ~/Software/Prototypes/email-digest
python -m pytest tests/ -x -q

# invoice-admin
cd ~/Software/Prototypes/invoice-admin
python -m pytest tests/ -x -q

# local-chat (if tests exist)
cd ~/Software/Prototypes/local-chat
python -m pytest tests/ -x -q || echo "no test suite"

# swim (if tests exist)
cd ~/Software/Prototypes/swim
python -m pytest tests/ -x -q || echo "no test suite"
```

If any project lacks a test suite, run its main flow as a smoke test instead.

---

## Rollback per project

Every phase is independently reversible. The shim pattern means:

1. **During migration**: old file exists as a shim re-exporting from shared. All callers work.
2. **If tests fail**: revert the shim to the original file content (from git). Tests pass again.
3. **After successful migration**: delete the shim in a separate commit. The git history preserves the original.

Git workflow per project:
```bash
cd ~/Software/Prototypes/decisionmaker
git checkout -b shared-migration
# ... make changes for one phase ...
python -m pytest tests/ -x -q
git add -A && git commit -m "shared-migration: phase N — <module>"
# if anything fails:
git checkout main -- src/decisionmaker/path/to/broken_file.py
```

Never force-push. Never skip the test run between phases.
