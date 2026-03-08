from __future__ import annotations

import os
from copy import deepcopy

import pandas as pd
import streamlit as st

from lib.cache import ProjectCache
from lib.models import DEFAULT_HEADERS, Project
from lib.runner import run_project


MODEL_OPTIONS = ["gpt-5.2", "gpt-5.1", "gpt-4.1", "gpt-4.1-mini"]
INTERNAL_FIELDS = [
    "row_id",
    "task_number",
    "artist",
    "task_id",
    "turn",
    "prompt",
    "response",
    "violative",
    "policy",
    "subtopic",
    "severity",
    "justification",
    "category_number",
    "category_name",
    "tactic_id",
    "tactic_name",
    "reasoning",
    "classification_error",
    "task_error",
]


def _project_state_key(project: Project, suffix: str) -> str:
    return f"project_{project.id}_{suffix}"


def _get_api_key() -> str:
    return os.getenv("OPENAI_API_KEY", "") or st.secrets.get("OPENAI_API_KEY", "")


def _current_headers(project: Project) -> list[str]:
    key = _project_state_key(project, "headers")
    if key not in st.session_state:
        st.session_state[key] = list(project.config.output_headers)
    return list(st.session_state[key])


def _set_headers(project: Project, headers: list[str]) -> None:
    key = _project_state_key(project, "headers")
    st.session_state[key] = [str(h).strip() for h in headers if str(h).strip()]


def _render_headers_editor(project: Project) -> list[str]:
    headers = _current_headers(project)
    editor_key = _project_state_key(project, "headers_editor")
    df = pd.DataFrame({"header": headers})
    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=editor_key)
    new_headers = [str(value).strip() for value in edited["header"].tolist() if str(value).strip()]

    col_a, col_b = st.columns(2)
    if col_a.button("Add Header", key=_project_state_key(project, "add_header")):
        new_headers.append("new_header")
    if col_b.button("Reset to Defaults", key=_project_state_key(project, "reset_headers")):
        new_headers = list(DEFAULT_HEADERS)

    _set_headers(project, new_headers)
    return new_headers


def _render_field_mapping(project: Project, headers: list[str]) -> dict[str, str]:
    st.markdown("Field Mapping")
    mapping = deepcopy(project.config.field_mapping)
    options = [""] + headers

    for internal_field in INTERNAL_FIELDS:
        current_value = mapping.get(internal_field, "")
        if current_value not in options:
            current_value = ""
        mapping[internal_field] = st.selectbox(
            internal_field,
            options,
            index=options.index(current_value),
            key=_project_state_key(project, f"map_{internal_field}"),
        )

    return {k: v for k, v in mapping.items() if v}


def _build_updated_project(
    project: Project,
    name: str,
    csv_url: str,
    poll_interval: int,
    model: str,
    system_prompt: str,
    headers: list[str],
    field_mapping: dict[str, str],
    spreadsheet_id: str,
    tab_name: str,
    write_mode_label: str,
    upsert_key_column: str,
    max_rows_per_run: int,
    row_key_strategy_label: str,
    row_key_columns: str,
    delimiter: str,
    encoding: str,
    json_columns: str,
    reprocess_on_change: bool,
    keep_cache_on_relink: bool,
) -> Project:
    updated = deepcopy(project)
    cfg = updated.config

    cfg.name = name.strip()
    cfg.csv_url = csv_url.strip()
    cfg.poll_interval_minutes = int(poll_interval)
    cfg.model = model
    cfg.system_prompt = system_prompt
    cfg.output_headers = headers
    cfg.field_mapping = field_mapping
    cfg.gsheet_spreadsheet_id = spreadsheet_id.strip()
    cfg.gsheet_tab_name = tab_name.strip()
    cfg.write_mode = "upsert" if write_mode_label.startswith("Upsert") else "append"
    cfg.upsert_key_column = upsert_key_column.strip() if cfg.write_mode == "upsert" else ""
    cfg.max_rows_per_run = int(max_rows_per_run)
    cfg.row_key_strategy = "columns" if row_key_strategy_label.startswith("Columns") else "hash"
    cfg.row_key_columns = [c.strip() for c in row_key_columns.split(",") if c.strip()]
    cfg.delimiter = delimiter
    cfg.encoding = encoding
    cfg.json_columns = [c.strip() for c in json_columns.split(",") if c.strip()]
    cfg.reprocess_on_change = bool(reprocess_on_change)
    cfg.keep_cache_on_relink = bool(keep_cache_on_relink)

    return updated


def _validate_before_save(project: Project) -> list[str]:
    cfg = project.config
    errors = []
    if not cfg.name:
        errors.append("Project name is required.")
    if not cfg.csv_url:
        errors.append("CSV URL is required.")
    if not cfg.output_headers:
        errors.append("At least one output header is required.")
    if cfg.write_mode == "upsert" and not cfg.upsert_key_column:
        errors.append("Upsert key column is required in upsert mode.")
    if cfg.write_mode == "upsert" and cfg.upsert_key_column not in cfg.output_headers:
        errors.append("Upsert key column must be one of the output headers.")
    return errors


def render(project: Project, store):
    st.subheader(f"Edit Project: {project.config.name or 'New Project'}")

    cfg = project.config
    tab_general, tab_headers, tab_output = st.tabs(["General", "Headers", "Output"])

    with tab_general:
        name = st.text_input("Project Name", value=cfg.name, key=_project_state_key(project, "name"))
        csv_url = st.text_input("CSV URL", value=cfg.csv_url, key=_project_state_key(project, "csv_url"))
        poll_interval = st.selectbox(
            "Polling Interval (minutes)",
            [5, 10, 15, 30, 60],
            index=[5, 10, 15, 30, 60].index(cfg.poll_interval_minutes)
            if cfg.poll_interval_minutes in [5, 10, 15, 30, 60]
            else 2,
            key=_project_state_key(project, "poll_interval"),
        )
        model = st.selectbox(
            "Model",
            MODEL_OPTIONS,
            index=MODEL_OPTIONS.index(cfg.model) if cfg.model in MODEL_OPTIONS else 0,
            key=_project_state_key(project, "model"),
        )
        system_prompt = st.text_area(
            "System Prompt",
            value=cfg.system_prompt,
            height=180,
            key=_project_state_key(project, "prompt"),
        )
        max_rows_per_run = st.number_input(
            "Max Rows Per Run",
            min_value=1,
            max_value=10000,
            value=int(cfg.max_rows_per_run or 100),
            key=_project_state_key(project, "max_rows_per_run"),
        )
        row_key_strategy_label = st.radio(
            "Row Key Strategy",
            ["Hash (full row)", "Columns"],
            index=1 if cfg.row_key_strategy == "columns" else 0,
            key=_project_state_key(project, "row_key_strategy"),
        )
        row_key_columns = st.text_input(
            "Row Key Columns (comma-separated)",
            value=", ".join(cfg.row_key_columns),
            key=_project_state_key(project, "row_key_columns"),
        )
        delimiter = st.text_input("CSV Delimiter", value=cfg.delimiter, key=_project_state_key(project, "delimiter"))
        encoding = st.text_input("CSV Encoding", value=cfg.encoding, key=_project_state_key(project, "encoding"))
        json_columns = st.text_input(
            "JSON Columns (comma-separated)",
            value=", ".join(cfg.json_columns),
            key=_project_state_key(project, "json_columns"),
        )
        reprocess_on_change = st.checkbox(
            "Reprocess rows when fingerprint changes",
            value=cfg.reprocess_on_change,
            key=_project_state_key(project, "reprocess_on_change"),
        )

    with tab_headers:
        headers = _render_headers_editor(project)
        field_mapping = _render_field_mapping(project, headers)

    with tab_output:
        spreadsheet_id = st.text_input(
            "Spreadsheet ID",
            value=cfg.gsheet_spreadsheet_id,
            key=_project_state_key(project, "spreadsheet_id"),
        )
        tab_name = st.text_input("Sheet/Tab Name", value=cfg.gsheet_tab_name, key=_project_state_key(project, "tab_name"))
        write_mode_label = st.radio(
            "Write Mode",
            ["Append Rows", "Upsert (Update by Key)"],
            index=1 if cfg.write_mode == "upsert" else 0,
            key=_project_state_key(project, "write_mode"),
        )

        upsert_key_column = ""
        if write_mode_label.startswith("Upsert"):
            upsert_options = headers if headers else [""]
            current = cfg.upsert_key_column if cfg.upsert_key_column in upsert_options else upsert_options[0]
            upsert_key_column = st.selectbox(
                "Key Column",
                upsert_options,
                index=upsert_options.index(current),
                key=_project_state_key(project, "upsert_key"),
            )

        st.markdown("Cache Controls")
        keep_cache_on_relink = st.checkbox(
            "Keep Cache On Relink",
            value=cfg.keep_cache_on_relink,
            key=_project_state_key(project, "keep_cache_on_relink"),
        )

        cache = ProjectCache(store.client, store.meta_spreadsheet_id)
        c1, c2 = st.columns(2)
        if c1.button("Clear Cache", key=_project_state_key(project, "clear_cache")):
            cache.clear(project.id)
            st.success("Cache cleared.")

        if c2.button("Reset & Relink Sheet", key=_project_state_key(project, "relink_sheet")):
            relinked = deepcopy(project)
            relinked.config.gsheet_spreadsheet_id = spreadsheet_id.strip()
            relinked.config.gsheet_tab_name = tab_name.strip()
            relinked.config.keep_cache_on_relink = keep_cache_on_relink
            store.save_project(relinked)
            if not keep_cache_on_relink:
                cache.clear(project.id)
            st.success("Sheet relinked.")

    candidate = _build_updated_project(
        project,
        name,
        csv_url,
        poll_interval,
        model,
        system_prompt,
        _current_headers(project),
        field_mapping,
        spreadsheet_id,
        tab_name,
        write_mode_label,
        upsert_key_column,
        int(max_rows_per_run),
        row_key_strategy_label,
        row_key_columns,
        delimiter,
        encoding,
        json_columns,
        reprocess_on_change,
        keep_cache_on_relink,
    )

    col_save, col_run, col_delete = st.columns(3)
    if col_save.button("Save", type="primary", key=_project_state_key(project, "save")):
        errors = _validate_before_save(candidate)
        if errors:
            for error in errors:
                st.error(error)
        else:
            store.save_project(candidate)
            st.success("Project saved.")
            st.rerun()

    run_log = None
    if col_run.button("Run Now", key=_project_state_key(project, "run_now")):
        errors = _validate_before_save(candidate)
        if errors:
            for error in errors:
                st.error(error)
        else:
            api_key = _get_api_key()
            if not api_key:
                st.error("OpenAI API key missing. Set OPENAI_API_KEY in env or Streamlit secrets.")
            else:
                store.save_project(candidate)
                with st.spinner("Running project..."):
                    run_log = run_project(candidate, store, api_key=api_key)
                st.session_state[_project_state_key(project, "last_run_log")] = run_log
                st.success(f"Run completed with status: {run_log.status}")

    if col_delete.button("Delete", key=_project_state_key(project, "delete")):
        store.delete_project(project.id)
        st.success("Project archived.")
        st.session_state.selected_project_id = None
        st.rerun()

    return run_log
