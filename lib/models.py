from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


DEFAULT_HEADERS = [
    "Row ID",
    "Task Number",
    "Artist",
    "Task ID",
    "Turn",
    "Prompt",
    "Response",
    "Violative",
    "Policy",
    "Subtopic",
    "Severity",
    "Justification",
    "category_number",
    "category_name",
    "tactic_id",
    "tactic_name",
    "reasoning",
    "classification_error",
    "task_error",
]


@dataclass
class ProjectConfig:
    name: str = ""
    csv_url: str = ""
    delimiter: str = ","
    encoding: str = "utf-8"
    header_row_index: int = 0
    json_columns: list[str] = field(default_factory=lambda: ["conversation_json"])
    row_key_strategy: str = "hash"
    row_key_columns: list[str] = field(default_factory=list)
    model: str = "gpt-5.2"
    system_prompt: str = ""
    temperature: float = 0.0
    system_prompt_version: int = 1
    gsheet_spreadsheet_id: str = ""
    gsheet_tab_name: str = ""
    output_headers: list[str] = field(default_factory=lambda: list(DEFAULT_HEADERS))
    field_mapping: dict[str, str] = field(default_factory=dict)
    write_mode: str = "append"
    upsert_key_column: str = ""
    max_rows_per_run: int = 100
    reprocess_on_change: bool = False


@dataclass
class Project:
    id: str
    config: ProjectConfig
    archived: bool = False
    created_at: str = ""
    updated_at: str = ""
    last_run_at: str = ""
    last_run_rows_processed: int = 0
    last_run_rows_errored: int = 0


@dataclass
class RunLog:
    run_id: str
    project_id: str
    started_at: str
    completed_at: str
    status: str
    rows_total: int
    rows_processed: int
    rows_skipped: int
    rows_errored: int
    model: str = ""
    prompt_version: int = 1
    error_summary: str = ""


PROJECT_ROW_FIELDS = [
    "id",
    "archived",
    "created_at",
    "updated_at",
    "last_run_at",
    "last_run_rows_processed",
    "last_run_rows_errored",
    "config_json",
]


RUN_LOG_FIELDS = [
    "run_id",
    "project_id",
    "started_at",
    "completed_at",
    "status",
    "rows_total",
    "rows_processed",
    "rows_skipped",
    "rows_errored",
    "model",
    "prompt_version",
    "error_summary",
]


def _is_archived(row: dict[str, Any]) -> bool:
    status = str(row.get("status", "")).strip().lower()
    if status == "archived":
        return True
    archived_raw = str(row.get("archived", "")).strip().lower()
    return archived_raw in {"1", "true", "yes"}


def _coerce_config(config_data: dict[str, Any]) -> ProjectConfig:
    return ProjectConfig(
        name=str(config_data.get("name", "")),
        csv_url=str(config_data.get("csv_url", "")),
        delimiter=str(config_data.get("delimiter", ",")),
        encoding=str(config_data.get("encoding", "utf-8")),
        header_row_index=int(config_data.get("header_row_index", 0) or 0),
        json_columns=[str(v) for v in list(config_data.get("json_columns", ["conversation_json"]))],
        row_key_strategy=str(config_data.get("row_key_strategy", "hash")),
        row_key_columns=[str(v) for v in list(config_data.get("row_key_columns", []))],
        model=str(config_data.get("model", "gpt-5.2")),
        system_prompt=str(config_data.get("system_prompt", "")),
        temperature=float(config_data.get("temperature", 0.0) or 0.0),
        system_prompt_version=int(config_data.get("system_prompt_version", 1) or 1),
        gsheet_spreadsheet_id=str(config_data.get("gsheet_spreadsheet_id", "")),
        gsheet_tab_name=str(config_data.get("gsheet_tab_name", "")),
        output_headers=[str(v) for v in list(config_data.get("output_headers", list(DEFAULT_HEADERS)))],
        field_mapping={str(k): str(v) for k, v in dict(config_data.get("field_mapping", {})).items()},
        write_mode=str(config_data.get("write_mode", "append")),
        upsert_key_column=str(config_data.get("upsert_key_column", "")),
        max_rows_per_run=int(config_data.get("max_rows_per_run", 100) or 100),
        reprocess_on_change=bool(config_data.get("reprocess_on_change", False)),
    )


def project_to_row(project: Project) -> list[Any]:
    import json

    config_json = json.dumps(asdict(project.config), ensure_ascii=True)
    return [
        project.id,
        str(bool(project.archived)),
        project.created_at,
        project.updated_at,
        project.last_run_at,
        project.last_run_rows_processed,
        project.last_run_rows_errored,
        config_json,
    ]


def row_to_project(row: dict[str, Any]) -> Project:
    import json

    config_raw = row.get("config_json", "{}")
    config_data = json.loads(config_raw) if config_raw else {}

    return Project(
        id=str(row.get("id", "")),
        archived=_is_archived(row),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
        last_run_at=str(row.get("last_run_at", "")),
        last_run_rows_processed=int(row.get("last_run_rows_processed", 0) or 0),
        last_run_rows_errored=int(
            row.get("last_run_rows_errored", row.get("last_run_rows_failed", 0)) or 0
        ),
        config=_coerce_config(config_data if isinstance(config_data, dict) else {}),
    )
