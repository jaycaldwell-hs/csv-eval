from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from lib.models import PROJECT_ROW_FIELDS, RUN_LOG_FIELDS, Project, ProjectStatus, RunLog, project_to_row, row_to_project
from lib.sheets import append_rows, ensure_tab, read_all_rows


class ProjectStore:
    def __init__(self, meta_spreadsheet_id: str, service_account_info: dict[str, Any]) -> None:
        from lib.sheets import get_gspread_client

        self.client = get_gspread_client(service_account_info)
        self.meta_spreadsheet_id = meta_spreadsheet_id
        self.projects_ws = ensure_tab(self.client, meta_spreadsheet_id, "_projects", PROJECT_ROW_FIELDS)
        self.run_logs_ws = ensure_tab(self.client, meta_spreadsheet_id, "_run_logs", RUN_LOG_FIELDS)

    def list_projects(self) -> list[Project]:
        rows = read_all_rows(self.projects_ws)
        return [row_to_project(row) for row in rows if row.get("id")]

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
        project.status = ProjectStatus.ARCHIVED
        self.save_project(project)

    def write_run_log(self, log: RunLog) -> None:
        append_rows(self.run_logs_ws, [
            [
                log.run_id,
                log.project_id,
                log.started_at,
                log.completed_at,
                log.status,
                log.rows_fetched,
                log.rows_new,
                log.rows_processed,
                log.rows_failed,
                log.error_summary,
            ]
        ])

    def get_run_logs(self, project_id: str, limit: int = 20) -> list[RunLog]:
        rows = [row for row in read_all_rows(self.run_logs_ws) if str(row.get("project_id", "")) == project_id]
        rows.sort(key=lambda row: str(row.get("started_at", "")), reverse=True)
        selected = rows[:limit]
        return [
            RunLog(
                run_id=str(row.get("run_id", "")),
                project_id=str(row.get("project_id", "")),
                started_at=str(row.get("started_at", "")),
                completed_at=str(row.get("completed_at", "")),
                status=str(row.get("status", "error")),
                rows_fetched=int(row.get("rows_fetched", 0) or 0),
                rows_new=int(row.get("rows_new", 0) or 0),
                rows_processed=int(row.get("rows_processed", 0) or 0),
                rows_failed=int(row.get("rows_failed", 0) or 0),
                error_summary=str(row.get("error_summary", "")),
            )
            for row in selected
        ]
