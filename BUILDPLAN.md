# BQ Eval Runner — Build Plan

## Overview

Transform the existing single-file CSV Eval Runner (Streamlit app that fetches a CSV, runs each row through an LLM, displays results) into a persistent multi-project eval platform that auto-polls CSV sources, writes structured output to Google Sheets, and caches processed rows.

**Source spec:** `BQ Eval Runner Specs.pdf`
**Current app:** `app.py` (~160 lines, single-run Streamlit app)
**Deployed to:** Streamlit Community Cloud

---

## Target Architecture

```
csv_eval/
  app.py                    # Entrypoint — tab router + poll loop
  requirements.txt
  .streamlit/
    config.toml
    secrets.toml            # Local only (gitignored): API keys + service account JSON
  lib/
    __init__.py
    models.py               # Dataclasses: Project, ProjectConfig, RunLog
    store.py                # ProjectStore — CRUD backed by meta Google Sheet
    csv_fetch.py            # CSV fetching + URL normalization (extracted from app.py)
    llm.py                  # LLM provider abstraction
    sheets.py               # Google Sheets read/write via gspread
    runner.py               # Core loop: fetch → diff → eval → write → cache
    cache.py                # Row key computation + cache diff logic
  ui/
    __init__.py
    project_list.py         # Left sidebar: project list with status badges
    project_editor.py       # Right panel: config form (General / Headers / Output tabs)
    header_config.py        # Output header ordering + field mapping UI
    run_dashboard.py        # Run history, metrics, status display
    legacy.py               # "Quick Eval" — current app.py behavior preserved
```

### Design Principles

- **`lib/` has zero Streamlit imports.** Pure business logic, testable independently.
- **`ui/` handles rendering only.** Calls into `lib/` for all logic.
- **Google Sheets as the database.** Streamlit Cloud has no persistent filesystem. A dedicated "meta" spreadsheet stores project configs, caches, and run logs. No external database needed.
- **Non-breaking migration.** The existing "Quick Eval" flow works through all phases until intentionally retired.

---

## Data Model

### Project

```python
class ProjectStatus(Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"

@dataclass
class ProjectConfig:
    name: str
    csv_url: str
    poll_interval_minutes: int          # default 15
    # CSV parsing
    delimiter: str                       # default ","
    encoding: str                        # default "utf-8"
    json_columns: list[str]             # default ["conversation_json"]
    # Row identity
    row_key_strategy: str               # "hash" (SHA256 of full row) or "columns"
    row_key_columns: list[str]          # used when strategy = "columns"
    # Model
    model: str                          # e.g. "gpt-5.2"
    system_prompt: str
    system_prompt_version: int          # incremented on change
    # Output destination
    gsheet_spreadsheet_id: str
    gsheet_tab_name: str
    # Output schema
    output_headers: list[str]           # ordered column names for sheet row 1
    field_mapping: dict[str, str]       # internal_field -> header_name
    write_mode: str                     # "append" or "upsert"
    upsert_key_column: str              # required when write_mode = "upsert"
    # Limits
    max_rows_per_run: int               # default 100
    # Behavior
    reprocess_on_change: bool           # re-run if row fingerprint changed
    keep_cache_on_relink: bool          # preserve cache when changing target sheet

@dataclass
class Project:
    id: str                             # UUID
    config: ProjectConfig
    status: ProjectStatus
    created_at: str                     # ISO timestamp
    updated_at: str
    last_run_at: str
    last_run_rows_processed: int
    last_run_rows_failed: int
```

### Default Output Headers

```
Row ID, Task Number, Artist, Task ID, Turn,
Prompt, Response, Violative, Policy, Subtopic,
Severity, Justification, category_number, category_name,
tactic_id, tactic_name, reasoning, classification_error, task_error
```

### RunLog

```python
@dataclass
class RunLog:
    run_id: str                         # UUID
    project_id: str
    started_at: str
    completed_at: str
    status: str                         # "success", "partial_failure", "error"
    rows_fetched: int
    rows_new: int
    rows_processed: int
    rows_failed: int
    error_summary: str                  # empty if clean run
```

### Meta Spreadsheet Layout

One Google Spreadsheet (ID stored in Streamlit secrets as `META_SPREADSHEET_ID`) with tabs:

| Tab | Contents |
|-----|----------|
| `_projects` | One row per project. Columns = all ProjectConfig fields + status + timestamps |
| `_cache_{project_id}` | One row per processed row_key. Columns: `row_key`, `fingerprint`, `processed_at` |
| `_run_logs` | One row per run. Columns = all RunLog fields |

---

## Secrets Configuration

### Streamlit secrets (`.streamlit/secrets.toml` locally, Secrets UI on Cloud)

```toml
OPENAI_API_KEY = "sk-proj-..."
META_SPREADSHEET_ID = "1aBcDeFgHiJkLmNoPqRsTuVwXyZ..."

[GOOGLE_SERVICE_ACCOUNT]
type = "service_account"
project_id = "handshake-production"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "csv-eval@handshake-production.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
```

The service account must be shared (Editor) on both the meta spreadsheet and any output spreadsheets.

---

## Runner Loop (per project, per interval)

```
1. Fetch CSV from project.csv_url
   - Apply delimiter, encoding from config
   - JSON-decode columns listed in json_columns[]
   - Capture parse failures as row-level errors

2. Compute row keys
   - strategy=hash: SHA256 of full row content
   - strategy=columns: concatenate specified column values

3. Diff against cache
   - Load processed row_keys from _cache_{project_id}
   - New rows: key not in cache
   - Changed rows (if reprocess_on_change): key exists but fingerprint differs

4. For each new/changed row (up to max_rows_per_run):
   a. Build LLM request: system_prompt + row payload (JSON-encoded row data)
   b. Call model, get response
   c. Parse response into internal result fields
   d. Map to output row using output_headers[] + field_mapping
   e. On parse/model error: set task_error, write row with blank eval fields
   f. On mapping error: set classification_error

5. Write to Google Sheet
   - Append mode: append all new rows after last row
   - Upsert mode: match on key_column, update existing or append new
   - On first run: create tab if missing, write headers as row 1

6. Update cache
   - Write new row_keys + fingerprints to _cache_{project_id}

7. Record run metrics
   - Write RunLog entry to _run_logs tab
```

---

## Phase 1: Foundation + Non-Breaking Migration

### Goal
Extract current logic into modules. Add Google Sheets API integration. Existing app continues to work as "Quick Eval."

### Files to Create

**`lib/__init__.py`** — empty

**`lib/csv_fetch.py`** — extracted from app.py
- `normalize_sheets_url(url: str) -> str` — existing logic (lines 44-57 of app.py)
- `fetch_csv(url: str, delimiter: str = ",", encoding: str = "utf-8", json_columns: list[str] | None = None) -> pd.DataFrame` — existing logic (lines 60-71) extended with configurable delimiter/encoding + optional JSON-decode of specified columns

**`lib/llm.py`** — extracted from app.py
- `class LLMProvider(Protocol)` — `call(system: str, user_content: str) -> str`
- `class OpenAIProvider` — wraps existing `call_llm()` logic (lines 74-83). Constructor takes `api_key` and `model`.

**`lib/models.py`** — new
- `ProjectStatus` enum
- `ProjectConfig` dataclass (all fields from spec, with defaults)
- `Project` dataclass
- `RunLog` dataclass
- `DEFAULT_HEADERS` list constant
- `project_to_row(project) -> list` / `row_to_project(row) -> Project` — serialization for sheet storage

**`lib/sheets.py`** — new
- `get_gspread_client() -> gspread.Client` — authenticate using service account from Streamlit secrets
- `ensure_tab(client, spreadsheet_id, tab_name, headers: list[str]) -> gspread.Worksheet` — create tab if missing, validate/write header row
- `append_rows(worksheet, rows: list[list]) -> int` — batch append, return count written
- `read_all_rows(worksheet) -> list[dict]` — read all data rows as dicts
- `upsert_rows(worksheet, rows: list[list], key_col_index: int) -> int` — match on key column, update or append

**`lib/store.py`** — new
- `class ProjectStore` — backed by `_projects` tab in meta spreadsheet
  - `__init__(self)` — gets gspread client, opens meta spreadsheet
  - `list_projects() -> list[Project]`
  - `get_project(project_id: str) -> Project | None`
  - `save_project(project: Project) -> None` — create or update
  - `delete_project(project_id: str) -> None` — sets status to ARCHIVED

**`ui/__init__.py`** — empty

**`ui/legacy.py`** — new
- `render()` function containing the current app.py logic (lines 29-160), refactored to import from `lib/csv_fetch` and `lib/llm` instead of inline functions

### Files to Modify

**`app.py`** — gut and replace with tab router:
```python
import streamlit as st
from ui import legacy

st.set_page_config(page_title="CSV Eval", layout="wide")

tab_quick, tab_projects = st.tabs(["Quick Eval", "Projects"])

with tab_quick:
    legacy.render()

with tab_projects:
    st.info("Projects — coming in the next update.")
```

**`requirements.txt`** — add:
```
gspread>=6.0.0
google-auth>=2.0.0
```

**`.gitignore`** — add `service_account.json` if not already present

### Validation Criteria
- [ ] `streamlit run app.py` — Quick Eval tab works identically to current behavior
- [ ] `lib/sheets.py` can authenticate and write a test row to a Google Sheet
- [ ] `lib/store.py` can create and read back a Project from the meta spreadsheet
- [ ] No Streamlit imports in any `lib/` file

---

## Phase 2: Project CRUD + Manual Run

### Goal
Working project creation, configuration, and manual "Run Now" that writes results to a Google Sheet.

### Files to Create

**`lib/cache.py`** — new
- `compute_row_key(row: dict, strategy: str, key_columns: list[str]) -> str` — hash-based (SHA256 of sorted JSON) or column-based (joined values)
- `compute_fingerprint(row: dict) -> str` — SHA256 of full row for change detection
- `class ProjectCache` — backed by `_cache_{project_id}` tab in meta spreadsheet
  - `load(project_id: str) -> dict[str, str]` — returns `{row_key: fingerprint}`
  - `save(project_id: str, entries: dict[str, str]) -> None` — overwrite cache tab
  - `clear(project_id: str) -> None` — delete all rows in cache tab

**`lib/runner.py`** — new
- `run_project(project: Project, store: ProjectStore) -> RunLog` — the full loop:
  1. Call `csv_fetch.fetch_csv()` with project config
  2. Compute row keys via `cache.compute_row_key()`
  3. Load cache, diff to find new rows
  4. For each new row (up to `max_rows_per_run`):
     - Build LLM payload (system_prompt + JSON-encoded row)
     - Call provider
     - Parse response, map to output_headers via field_mapping
     - Collect output row or error
  5. Call `sheets.ensure_tab()` + `sheets.append_rows()` or `sheets.upsert_rows()`
  6. Update cache with new keys
  7. Write RunLog to `_run_logs`
  8. Update project's `last_run_at` in store
  9. Return RunLog

**`ui/project_list.py`** — new
- `render(store: ProjectStore) -> str | None` — sidebar widget
  - "Create New Project" button (creates Draft, returns new project ID)
  - List of projects: name, status badge (colored with `st.markdown` + HTML), last run time
  - Click/select sets `st.session_state.selected_project_id`
  - Returns selected project ID

**`ui/project_editor.py`** — new
- `render(project: Project, store: ProjectStore) -> None` — right-panel form
  - Title: "Edit Project: {name}" (or "New Project" for unsaved Draft)
  - Three tabs via `st.tabs(["General", "Headers", "Output"])`:

  **General tab:**
  - `st.text_input("Project Name")`
  - `st.text_input("CSV URL")`
  - `st.selectbox("Polling Interval", [5, 10, 15, 30, 60] minutes)`
  - `st.selectbox("Model", ["gpt-5.2", "gpt-5.1", "gpt-4.1", ...])`
  - `st.text_area("System Prompt")`

  **Headers tab:**
  - `st.data_editor` showing output_headers as an editable numbered list
  - "Add Header" button
  - Field mapping: for each header, optional `st.selectbox` mapping to internal field
  - "Reset to Defaults" button

  **Output tab:**
  - `st.text_input("Spreadsheet ID")`
  - `st.text_input("Sheet/Tab Name")`
  - `st.radio("Write Mode", ["Append Rows", "Upsert (Update by Key)"])`
  - If upsert: `st.selectbox("Key Column", options=output_headers)`
  - **Cache Controls section:**
    - "Clear Cache" button — clears processed rows, next run reprocesses all
    - "Reset & Relink Sheet" button — change spreadsheet/tab with option to keep or reset cache

  **Bottom bar:**
  - "Save" button — validates and writes to store
  - "Run Now" button — saves then calls `runner.run_project()`
  - "Delete" button — archives project

**`ui/run_dashboard.py`** — new (minimal version)
- `render_run_result(run_log: RunLog) -> None` — show results of the last Run Now:
  - Status (success/partial/error)
  - Rows fetched / new / processed / failed
  - Duration
  - Error summary if any

### Files to Modify

**`app.py`** — expand Projects tab:
```python
with tab_projects:
    store = get_store()  # cached via st.cache_resource
    selected_id = project_list.render(store)
    if selected_id:
        project = store.get_project(selected_id)
        project_editor.render(project, store)
```

### Validation Criteria
- [ ] Can create a new project from the sidebar
- [ ] Can configure all fields (name, URL, model, prompt, headers, sheet target)
- [ ] "Run Now" fetches CSV, evaluates new rows, writes to target Google Sheet with correct headers
- [ ] Running again skips already-processed rows (cache works)
- [ ] "Clear Cache" causes next run to reprocess all rows
- [ ] Row-level errors populate `task_error` column, don't crash the run
- [ ] Quick Eval tab still works

---

## Phase 3: Auto-Polling + Lifecycle Controls

### Goal
Active projects auto-run on their poll interval. Full state machine with Activate/Pause/Resume.

### Files to Modify

**`ui/project_editor.py`** — add status controls:
- If Draft: "Activate" button → sets status to ACTIVE
- If Active: "Pause" button → PAUSED
- If Paused: "Resume" button → ACTIVE
- Status badge displayed next to project name
- "Archive" button (any state → ARCHIVED, removed from active list)

**`ui/run_dashboard.py`** — expand:
- `render(project: Project, store: ProjectStore) -> None`
- Show run history table: last 20 runs from `_run_logs` filtered by project_id
- Columns: run time, status, rows new, rows processed, rows failed, duration
- Auto-refresh indicator when project is Active

**`app.py`** — add poll loop:
```python
# After rendering UI, check for due projects
if st.session_state.get("view") != "editing":
    active_projects = store.get_projects_by_status(ProjectStatus.ACTIVE)
    now = datetime.utcnow()
    due = [p for p in active_projects if is_due(p, now)]
    if due:
        project = min(due, key=lambda p: next_run_at(p))
        with st.spinner(f"Running {project.config.name}..."):
            runner.run_project(project, store)
        st.rerun()
    elif active_projects:
        next_due_seconds = min(seconds_until_due(p, now) for p in active_projects)
        sleep_seconds = max(10, min(next_due_seconds, 300))
        time.sleep(sleep_seconds)
        st.rerun()
```

**`lib/store.py`** — add:
- `get_projects_by_status(status: ProjectStatus) -> list[Project]`
- `get_run_logs(project_id: str, limit: int = 20) -> list[RunLog]`
- `write_run_log(log: RunLog) -> None`

### UX Notes
- Auto-poll only runs when user is on the dashboard/list view, NOT while editing a project (tracked via `st.session_state["view"]`)
- Show a countdown or "next run in X min" for active projects in the sidebar
- If multiple projects are due simultaneously, run the most overdue first, then `st.rerun()` to pick up the next

### Validation Criteria
- [ ] Activating a project starts the poll cycle
- [ ] Project runs automatically at configured interval
- [ ] Pausing stops polling; resuming restarts it
- [ ] Run history shows in the dashboard with correct metrics
- [ ] Editing a project does not get interrupted by auto-poll
- [ ] Multiple active projects are processed in priority order

---

## Phase 4: Multi-Model + Polish

### Goal
Support Vertex AI models (Gemini, Claude), prompt versioning, UX refinements.

### Files to Modify

**`lib/llm.py`** — add providers:
```python
class GeminiVertexProvider:
    """Uses google-genai SDK. Project: handshake-production, location: global."""
    def __init__(self, model: str = "gemini-3-pro-preview"):
        ...
    def call(self, system: str, user_content: str) -> str:
        ...

class ClaudeVertexProvider:
    """Uses anthropic[vertex] SDK. Project: handshake-production, region: us-east5."""
    def __init__(self, model: str = "claude-sonnet-4-5@20250929"):
        ...
    def call(self, system: str, user_content: str) -> str:
        ...

def get_provider(model: str, api_key: str = "") -> LLMProvider:
    """Route to correct provider based on model name prefix."""
    if model.startswith("gemini"):
        return GeminiVertexProvider(model)
    elif model.startswith("claude"):
        return ClaudeVertexProvider(model)
    else:
        return OpenAIProvider(api_key, model)
```

SDK patterns from `notes.md`:
- Gemini: `google.genai.Client(vertexai=True, project="handshake-production", location="global")`
- Claude: `AnthropicVertex(region="us-east5", project_id="handshake-production")`

**`ui/project_editor.py`** — update model selector:
```python
MODEL_OPTIONS = {
    "OpenAI": ["gpt-5.2", "gpt-5.2-pro", "gpt-5.1", "gpt-4.1", "gpt-4.1-mini"],
    "Gemini (Vertex)": ["gemini-3-pro-preview"],
    "Claude (Vertex)": ["claude-sonnet-4-5@20250929"],
}
```

**`lib/models.py`** — add prompt versioning:
- When `system_prompt` changes on save, auto-increment `system_prompt_version`
- If `reprocess_on_change` is enabled, clear cache on prompt version change

**`requirements.txt`** — add:
```
google-genai>=1.0.0
anthropic[vertex]>=0.40.0
```

### Additional Polish
- Header drag-and-drop: use `st.data_editor` with a position column for reordering
- Bulk actions: pause/archive multiple projects
- Export project config as JSON (backup/restore)
- Remove "Quick Eval" tab or convert it to a shortcut that creates a temporary Draft project

### Validation Criteria
- [ ] Can create a project using Gemini model, run it, results written to sheet
- [ ] Can create a project using Claude model, run it, results written to sheet
- [ ] Changing system prompt increments version
- [ ] With reprocess_on_change enabled, prompt change triggers full reprocess
- [ ] Model selector shows grouped options by provider

---

## Dependencies by Phase

| Phase | New packages |
|-------|-------------|
| 1 | `gspread>=6.0.0`, `google-auth>=2.0.0` |
| 2 | (none) |
| 3 | (none) |
| 4 | `google-genai>=1.0.0`, `anthropic[vertex]>=0.40.0` |

## Risks

| Risk | Phase | Mitigation |
|------|-------|------------|
| Meta-sheet Sheets API rate limits (300 req/min) | 2+ | Batch reads/writes; cache project list in `st.session_state` per session |
| `time.sleep` polling interrupts active editing | 3 | Track UI view state; only poll on dashboard view |
| No persistent filesystem on Streamlit Cloud | 1+ | All state in Google Sheets; nothing stored on disk |
| Service account needs Editor access on every output sheet | 2+ | Document in setup; consider sharing from UI |
| Large CSV batches slow to write | 2+ | `max_rows_per_run` caps batch size; gspread batch update API |
| Streamlit Cloud cold starts lose session state | 3 | All persistent state in Sheets; session state is UI-only |
