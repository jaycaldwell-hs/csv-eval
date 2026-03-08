from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ProjectStatus(Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


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
    poll_interval_minutes: int = 15
    delimiter: str = ","
    encoding: str = "utf-8"
    json_columns: list[str] = field(default_factory=lambda: ["conversation_json"])
    row_key_strategy: str = "hash"
    row_key_columns: list[str] = field(default_factory=list)
    model: str = "gpt-5.2"
    system_prompt: str = ""
    system_prompt_version: int = 1
    gsheet_spreadsheet_id: str = ""
    gsheet_tab_name: str = ""
    output_headers: list[str] = field(default_factory=lambda: list(DEFAULT_HEADERS))
    field_mapping: dict[str, str] = field(default_factory=dict)
    write_mode: str = "append"
    upsert_key_column: str = ""
    max_rows_per_run: int = 100
    reprocess_on_change: bool = False
    keep_cache_on_relink: bool = True


@dataclass
class Project:
    id: str
    config: ProjectConfig
    status: ProjectStatus = ProjectStatus.DRAFT
    created_at: str = ""
    updated_at: str = ""
    last_run_at: str = ""
    last_run_rows_processed: int = 0
    last_run_rows_failed: int = 0


@dataclass
class RunLog:
    run_id: str
    project_id: str
    started_at: str
    completed_at: str
    status: str
    rows_fetched: int
    rows_new: int
    rows_processed: int
    rows_failed: int
    error_summary: str = ""


PROJECT_ROW_FIELDS = [
    "id",
    "status",
    "created_at",
    "updated_at",
    "last_run_at",
    "last_run_rows_processed",
    "last_run_rows_failed",
    "config_json",
]

RUN_LOG_FIELDS = [
    "run_id",
    "project_id",
    "started_at",
    "completed_at",
    "status",
    "rows_fetched",
    "rows_new",
    "rows_processed",
    "rows_failed",
    "error_summary",
]


def project_to_row(project: Project) -> list[Any]:
    import json

    config_json = json.dumps(asdict(project.config), ensure_ascii=True)
    return [
        project.id,
        project.status.value,
        project.created_at,
        project.updated_at,
        project.last_run_at,
        project.last_run_rows_processed,
        project.last_run_rows_failed,
        config_json,
    ]


def row_to_project(row: dict[str, Any]) -> Project:
    import json

    config_raw = row.get("config_json", "{}")
    config_data = json.loads(config_raw) if config_raw else {}

    return Project(
        id=str(row.get("id", "")),
        status=ProjectStatus(str(row.get("status", ProjectStatus.DRAFT.value))),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
        last_run_at=str(row.get("last_run_at", "")),
        last_run_rows_processed=int(row.get("last_run_rows_processed", 0) or 0),
        last_run_rows_failed=int(row.get("last_run_rows_failed", 0) or 0),
        config=ProjectConfig(**config_data),
    )
