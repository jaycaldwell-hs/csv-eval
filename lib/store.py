from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.cache import ProjectCache
from lib.models import PROJECT_ROW_FIELDS, RUN_LOG_FIELDS, Project, RunLog, project_to_row, row_to_project
from lib.sheets import append_rows, ensure_tab, read_all_rows, upsert_rows


class ProjectStore:
    mode = "sheets"
    requires_output_sheet_config = True

    def __init__(self, meta_spreadsheet_id: str, service_account_info: dict[str, Any]) -> None:
        from lib.sheets import get_gspread_client

        self.client = get_gspread_client(service_account_info)
        self.meta_spreadsheet_id = meta_spreadsheet_id
        self.projects_ws = ensure_tab(self.client, meta_spreadsheet_id, "_projects", PROJECT_ROW_FIELDS)
        self.run_logs_ws = ensure_tab(self.client, meta_spreadsheet_id, "_run_logs", RUN_LOG_FIELDS)

    def list_projects(self) -> list[Project]:
        rows = read_all_rows(self.projects_ws)
        projects = [row_to_project(row) for row in rows if row.get("id")]
        return [project for project in projects if not project.archived]

    def get_project(self, project_id: str) -> Project | None:
        for project in self.list_projects():
            if project.id == project_id:
                return project
        return None

    def save_project(self, project: Project) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        if not project.created_at:
            project.created_at = now_iso
        project.updated_at = now_iso

        records = self.projects_ws.get_all_records(default_blank="")
        for index, record in enumerate(records, start=2):
            if str(record.get("id", "")) == project.id:
                self.projects_ws.update(f"A{index}", [project_to_row(project)])
                return

        append_rows(self.projects_ws, [project_to_row(project)])

    def delete_project(self, project_id: str) -> None:
        project = self.get_project(project_id)
        if not project:
            return
        project.archived = True
        self.save_project(project)

    def load_cache(self, project_id: str) -> dict[str, str]:
        cache = ProjectCache(self.client, self.meta_spreadsheet_id)
        return cache.load(project_id)

    def save_cache(self, project_id: str, entries: dict[str, str]) -> None:
        cache = ProjectCache(self.client, self.meta_spreadsheet_id)
        cache.save(project_id, entries)

    def clear_cache(self, project_id: str) -> None:
        cache = ProjectCache(self.client, self.meta_spreadsheet_id)
        cache.clear(project_id)

    def write_output_rows(self, project: Project, output_rows: list[list[Any]]) -> None:
        output_ws = ensure_tab(
            self.client,
            project.config.gsheet_spreadsheet_id,
            project.config.gsheet_tab_name,
            project.config.output_headers,
        )

        if project.config.write_mode == "upsert":
            if not project.config.upsert_key_column:
                raise ValueError("upsert_key_column is required when write_mode is 'upsert'")
            if project.config.upsert_key_column not in project.config.output_headers:
                raise ValueError("upsert_key_column must exist in output_headers")
            key_index = project.config.output_headers.index(project.config.upsert_key_column)
            upsert_rows(output_ws, output_rows, key_index)
        else:
            append_rows(output_ws, output_rows)

    def write_run_log(self, log: RunLog) -> None:
        append_rows(
            self.run_logs_ws,
            [
                [
                    log.run_id,
                    log.project_id,
                    log.started_at,
                    log.completed_at,
                    log.status,
                    log.rows_total,
                    log.rows_processed,
                    log.rows_skipped,
                    log.rows_errored,
                    log.model,
                    log.prompt_version,
                    log.error_summary,
                ]
            ],
        )

    def get_run_logs(self, project_id: str, limit: int = 20) -> list[RunLog]:
        rows = [row for row in read_all_rows(self.run_logs_ws) if str(row.get("project_id", "")) == project_id]
        rows.sort(key=lambda row: str(row.get("started_at", "")), reverse=True)
        selected = rows[:limit]
        return [_run_log_from_row(row) for row in selected]


class LocalProjectStore:
    mode = "local"
    requires_output_sheet_config = False

    def __init__(self, base_dir: str | Path = ".local_data") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.data_path = self.base_dir / "store.json"
        self.output_dir = self.base_dir / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _read_data(self) -> dict[str, Any]:
        if not self.data_path.exists():
            return {"projects": [], "run_logs": [], "caches": {}}
        raw = json.loads(self.data_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {"projects": [], "run_logs": [], "caches": {}}
        raw.setdefault("projects", [])
        raw.setdefault("run_logs", [])
        raw.setdefault("caches", {})
        return raw

    def _write_data(self, payload: dict[str, Any]) -> None:
        self.data_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def _project_row_dict(self, project: Project) -> dict[str, Any]:
        values = project_to_row(project)
        return dict(zip(PROJECT_ROW_FIELDS, values))

    def list_projects(self) -> list[Project]:
        data = self._read_data()
        projects = [row_to_project(row) for row in data.get("projects", []) if row.get("id")]
        return [project for project in projects if not project.archived]

    def get_project(self, project_id: str) -> Project | None:
        for project in self.list_projects():
            if project.id == project_id:
                return project
        return None

    def save_project(self, project: Project) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        if not project.created_at:
            project.created_at = now_iso
        project.updated_at = now_iso

        data = self._read_data()
        row = self._project_row_dict(project)

        projects = data.get("projects", [])
        for index, existing in enumerate(projects):
            if str(existing.get("id", "")) == project.id:
                projects[index] = row
                data["projects"] = projects
                self._write_data(data)
                return

        projects.append(row)
        data["projects"] = projects
        self._write_data(data)

    def delete_project(self, project_id: str) -> None:
        project = self.get_project(project_id)
        if not project:
            return
        project.archived = True
        self.save_project(project)

    def load_cache(self, project_id: str) -> dict[str, str]:
        data = self._read_data()
        cache = data.get("caches", {}).get(project_id, {})
        return {str(k): str(v) for k, v in dict(cache).items()}

    def save_cache(self, project_id: str, entries: dict[str, str]) -> None:
        data = self._read_data()
        caches = data.get("caches", {})
        caches[project_id] = {str(k): str(v) for k, v in entries.items()}
        data["caches"] = caches
        self._write_data(data)

    def clear_cache(self, project_id: str) -> None:
        data = self._read_data()
        caches = data.get("caches", {})
        caches[project_id] = {}
        data["caches"] = caches
        self._write_data(data)

    def _output_path(self, project: Project) -> Path:
        parts = [project.config.gsheet_spreadsheet_id.strip(), project.config.gsheet_tab_name.strip()]
        name = "_".join([part for part in parts if part])
        if not name:
            name = project.id
        safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name)
        return self.output_dir / f"{safe_name}.csv"

    def write_output_rows(self, project: Project, output_rows: list[list[Any]]) -> None:
        if not output_rows:
            return

        output_path = self._output_path(project)
        headers = project.config.output_headers

        existing_rows: list[list[str]] = []
        if output_path.exists():
            with output_path.open("r", encoding="utf-8", newline="") as f:
                reader = list(csv.reader(f))
                if reader:
                    existing_rows = reader[1:]

        if project.config.write_mode == "upsert":
            if not project.config.upsert_key_column:
                raise ValueError("upsert_key_column is required when write_mode is 'upsert'")
            if project.config.upsert_key_column not in headers:
                raise ValueError("upsert_key_column must exist in output_headers")
            key_index = headers.index(project.config.upsert_key_column)

            key_map: dict[str, list[str]] = {}
            ordered_keys: list[str] = []
            for row in existing_rows:
                key = row[key_index] if key_index < len(row) else ""
                if key and key not in key_map:
                    ordered_keys.append(key)
                if key:
                    key_map[key] = row

            for row in output_rows:
                as_str = [str(v) for v in row]
                key = as_str[key_index] if key_index < len(as_str) else ""
                if key:
                    if key not in key_map:
                        ordered_keys.append(key)
                    key_map[key] = as_str
                else:
                    ordered_keys.append(f"__append_{len(ordered_keys)}")
                    key_map[ordered_keys[-1]] = as_str

            final_rows = [key_map[k] for k in ordered_keys]
        else:
            final_rows = existing_rows + [[str(v) for v in row] for row in output_rows]

        with output_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(final_rows)

    def write_run_log(self, log: RunLog) -> None:
        data = self._read_data()
        logs = data.get("run_logs", [])
        logs.append(
            {
                "run_id": log.run_id,
                "project_id": log.project_id,
                "started_at": log.started_at,
                "completed_at": log.completed_at,
                "status": log.status,
                "rows_total": log.rows_total,
                "rows_processed": log.rows_processed,
                "rows_skipped": log.rows_skipped,
                "rows_errored": log.rows_errored,
                "model": log.model,
                "prompt_version": log.prompt_version,
                "error_summary": log.error_summary,
            }
        )
        data["run_logs"] = logs
        self._write_data(data)

    def get_run_logs(self, project_id: str, limit: int = 20) -> list[RunLog]:
        data = self._read_data()
        rows = [row for row in data.get("run_logs", []) if str(row.get("project_id", "")) == project_id]
        rows.sort(key=lambda row: str(row.get("started_at", "")), reverse=True)
        return [_run_log_from_row(row) for row in rows[:limit]]


def _run_log_from_row(row: dict[str, Any]) -> RunLog:
    return RunLog(
        run_id=str(row.get("run_id", "")),
        project_id=str(row.get("project_id", "")),
        started_at=str(row.get("started_at", "")),
        completed_at=str(row.get("completed_at", "")),
        status=str(row.get("status", "error")),
        rows_total=int(row.get("rows_total", row.get("rows_fetched", 0)) or 0),
        rows_processed=int(row.get("rows_processed", 0) or 0),
        rows_skipped=int(
            row.get(
                "rows_skipped",
                max(
                    int(row.get("rows_fetched", 0) or 0) - int(row.get("rows_processed", 0) or 0),
                    0,
                ),
            )
            or 0
        ),
        rows_errored=int(row.get("rows_errored", row.get("rows_failed", 0)) or 0),
        model=str(row.get("model", "")),
        prompt_version=int(row.get("prompt_version", 1) or 1),
        error_summary=str(row.get("error_summary", "")),
    )
