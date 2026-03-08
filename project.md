# CSV Eval Runner

## Overview
CSV Eval Runner has two flows:

1. **Quick Eval**: stateless one-off CSV -> LLM evaluation.
2. **Projects**: persistent, cache-backed configs with manual `Run Now` execution.

This repository is now scoped to a stripped-down MVP optimized for Streamlit Community Cloud:
- no background scheduler
- no auto-polling
- no pause/resume lifecycle automation

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

- `lib/` contains business logic only.
- `ui/` contains Streamlit UI.
- Google Sheets stores `_projects`, `_run_logs`, and `_cache_{project_id}` tabs.

## Current Behavior
- Projects are manually configured and persisted.
- Runs happen only when user clicks `Run Now`.
- Cache tracks row fingerprints to process only new/changed rows.
- `Clear Cache` and `Reset & Relink Sheet` are supported.
- Run logs capture per-run metrics (`rows_total`, `rows_processed`, `rows_skipped`, `rows_errored`) and summary errors.

## Legacy Compatibility
- Existing `_projects` rows with legacy fields (for example status/interval) are still loadable.
- Deprecated fields are ignored by runtime behavior and not shown in UI.

## Secrets

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

Service account must have editor access to the meta spreadsheet and project output spreadsheets.

## Future Work
- Optional external scheduler/background runner.
- Lifecycle controls and project state machine.
- Additional provider integrations and observability enhancements.
