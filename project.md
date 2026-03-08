# CSV Eval Runner

## Overview

CSV Eval Runner is now a modular Streamlit evaluation platform with two user flows:

1. **Quick Eval**: legacy single-run CSV-to-LLM evaluation flow.
2. **Projects**: persistent project configs stored in a meta Google Sheet, with manual run execution, per-project cache, and run history.

This reflects completion of **Phase 1** and **Phase 2** from `BUILDPLAN.md`.

**Repo:** github.com/jaycaldwell-hs/csv-eval  
**Hosting:** Streamlit Community Cloud  
**Primary LLM backend today:** OpenAI models via API key (project-configurable model string)

## Current architecture

```
csv_eval/
  app.py
  lib/
    csv_fetch.py
    llm.py
    models.py
    sheets.py
    store.py
    cache.py
    runner.py
  ui/
    legacy.py
    project_list.py
    project_editor.py
    run_dashboard.py
```

### Separation of concerns

- `lib/` contains business logic only (no Streamlit imports).
- `ui/` contains Streamlit rendering/components.
- Google Sheets acts as persistent storage for:
  - project metadata (`_projects`)
  - run logs (`_run_logs`)
  - per-project cache tabs (`_cache_{project_id}`)

## What is implemented

## Phase 1 (complete)

- Refactored app into `lib/` + `ui/` modules.
- Preserved old behavior under `Quick Eval` tab (`ui/legacy.py`).
- Added Sheets integration scaffolding:
  - auth/client creation
  - tab creation + header management
  - append/read/upsert helpers
- Added project model dataclasses and serialization helpers.
- Added `ProjectStore` CRUD against `_projects`.
- Updated dependencies with `gspread` and `google-auth`.

## Phase 2 (complete)

- Added project cache logic (`lib/cache.py`):
  - row key computation (`hash` or `columns`)
  - fingerprinting for change detection
  - cache load/save/clear per project
- Added runner engine (`lib/runner.py`) for manual runs:
  - fetch CSV with project parsing config
  - diff against cache
  - process new/changed rows up to `max_rows_per_run`
  - call LLM per row
  - map output into configured header schema
  - write to output sheet (append or upsert)
  - update cache and run metrics
  - persist run logs
- Expanded project store for run logs:
  - `write_run_log`
  - `get_run_logs`
- Built Projects UI:
  - sidebar project list + Draft project creation (`ui/project_list.py`)
  - editor tabs for General / Headers / Output (`ui/project_editor.py`)
  - cache controls (`Clear Cache`, `Reset & Relink Sheet`)
  - actions (`Save`, `Run Now`, `Delete`->archive)
  - run result + recent run history view (`ui/run_dashboard.py`)
- Wired `app.py` Projects tab with cached store initialization from Streamlit secrets:
  - `META_SPREADSHEET_ID`
  - `GOOGLE_SERVICE_ACCOUNT`

## Coherent standalone workflow status

Yes. With Phase 2 complete, the app supports a coherent standalone workflow:

1. Create/configure a project.
2. Run project manually.
3. Write structured output rows to destination Google Sheet.
4. Skip already-processed rows via cache.
5. Clear cache to force reprocessing.
6. Review recent run results/history.

Phase 3 is operational automation (auto-polling + lifecycle controls), not required for core manual use.

## Required secrets/config

### Streamlit secrets

```toml
OPENAI_API_KEY = "sk-proj-..."
META_SPREADSHEET_ID = "..."

[GOOGLE_SERVICE_ACCOUNT]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
```

Service account must have editor access to both:
- meta spreadsheet (`META_SPREADSHEET_ID`)
- each configured output spreadsheet

## Current status and risks

### Working now

- Quick Eval legacy flow remains available.
- Projects CRUD and project configuration UI.
- Manual `Run Now` processing path end-to-end in code.
- Per-project cache and run log persistence in Google Sheets.
- Append/upsert sheet write modes.

### Validation performed so far

- Static syntax validation via AST parse across all Python modules.
- Confirmed no Streamlit imports in `lib/`.

### Not yet fully validated in this branch

- Full live end-to-end system test against real sheets/API credentials for every Phase 2 acceptance criterion.

## Remaining roadmap

## Phase 3 (next)

- Auto-polling scheduler behavior in app loop.
- Project lifecycle controls: Activate/Pause/Resume/Archive.
- Due-project prioritization and dashboard/history expansion.
- Guardrail: avoid poll interruptions while editing.

## Phase 4 (later)

- Multi-provider LLM routing (Gemini Vertex, Claude Vertex).
- Prompt versioning behaviors and reprocess-on-change integration.
- UI polish and bulk actions.

## Key files

| File | Purpose |
|---|---|
| `app.py` | Entrypoint and tab router (`Quick Eval`, `Projects`) |
| `ui/legacy.py` | Legacy Quick Eval flow |
| `ui/project_list.py` | Sidebar list + project creation |
| `ui/project_editor.py` | Project config editor + Run Now + cache controls |
| `ui/run_dashboard.py` | Run result + run history display |
| `lib/runner.py` | Core project execution loop |
| `lib/cache.py` | Row key/fingerprint and cache persistence |
| `lib/store.py` | Project + run log persistence |
| `lib/sheets.py` | Google Sheets read/write primitives |
| `lib/models.py` | Datamodels and serialization |
| `lib/csv_fetch.py` | CSV fetching/parsing helpers |
| `lib/llm.py` | LLM provider abstraction + OpenAI provider |
