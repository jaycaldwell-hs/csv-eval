# Build Plan (Stripped-Down MVP)

## Goal
Refactor CSV Eval to a manual Projects MVP that works on Streamlit Community Cloud without any scheduler/background service.

## Scope
- Keep Projects as persistent Google Sheets-backed configs.
- Keep Quick Eval flow intact.
- Keep per-project cache (`_cache_{project_id}`) and run logs (`_run_logs`).
- Support `Run Now` only for project execution.
- Remove/neutralize scheduling and lifecycle automation (`active/paused/interval/next_run`).

## Architecture

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

- `lib/` stays Streamlit-free.
- `ui/` contains all Streamlit rendering and action handlers.
- Google Sheets remains the persistence layer.

## Data Model (Current)

### `_projects`
- `id`
- `archived`
- `created_at`
- `updated_at`
- `last_run_at`
- `last_run_rows_processed`
- `last_run_rows_errored`
- `config_json`

`config_json` includes manual-run configuration only:
- basic project metadata
- CSV parsing options
- model/system prompt/temperature
- output sheet settings
- header and field mapping
- cache diff behavior and max rows per run

### `_run_logs`
- `run_id`
- `project_id`
- `started_at`
- `completed_at`
- `status`
- `rows_total`
- `rows_processed`
- `rows_skipped`
- `rows_errored`
- `model`
- `prompt_version`
- `error_summary`

## Execution Model
- Runs only occur when user clicks `Run Now` in Projects UI.
- `lib.runner.run_project(...)` performs:
  - fetch CSV
  - load cache
  - diff rows (new/changed)
  - process up to `max_rows_per_run`
  - write output sheet rows (append/upsert)
  - update cache
  - write run log summary
- No background polling loops, timers, or scheduler hooks.

## Cache and Relink Semantics
- `Clear Cache` empties `_cache_{project_id}`.
- `Reset & Relink Sheet` updates spreadsheet/tab and offers:
  - keep cache
  - reset cache

## Validation Checklist
- Project save/load works with manual-only fields.
- Legacy `_projects` rows still load (deprecated fields ignored).
- `Run Now` writes output, cache, and run log.
- Re-running unchanged CSV skips rows via cache.
- Clearing cache forces reprocessing on next run.
- Relink supports keep-cache and reset-cache behavior.

## Future Work (Out of Scope)
- Background scheduler / Cloud Scheduler integration.
- Lifecycle state machine (`active`, `paused`, `next_run_at`).
- External metrics/monitoring infrastructure.
