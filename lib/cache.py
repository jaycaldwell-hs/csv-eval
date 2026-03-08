from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from lib.sheets import append_rows, ensure_tab, read_all_rows


CACHE_HEADERS = ["row_key", "fingerprint", "processed_at"]


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)


def compute_row_key(row: dict, strategy: str, key_columns: list[str]) -> str:
    if strategy == "columns":
        parts = [str(row.get(column, "")) for column in key_columns]
        return "|".join(parts)
    payload = _stable_json(row)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_fingerprint(row: dict) -> str:
    payload = _stable_json(row)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ProjectCache:
    def __init__(self, client, meta_spreadsheet_id: str) -> None:
        self.client = client
        self.meta_spreadsheet_id = meta_spreadsheet_id

    def _tab_name(self, project_id: str) -> str:
        return f"_cache_{project_id}"

    def load(self, project_id: str) -> dict[str, str]:
        worksheet = ensure_tab(self.client, self.meta_spreadsheet_id, self._tab_name(project_id), CACHE_HEADERS)
        rows = read_all_rows(worksheet)
        return {str(row.get("row_key", "")): str(row.get("fingerprint", "")) for row in rows if row.get("row_key")}

    def save(self, project_id: str, entries: dict[str, str]) -> None:
        worksheet = ensure_tab(self.client, self.meta_spreadsheet_id, self._tab_name(project_id), CACHE_HEADERS)
        worksheet.clear()
        worksheet.update("A1", [CACHE_HEADERS])

        timestamp = datetime.now(timezone.utc).isoformat()
        rows = [[row_key, fingerprint, timestamp] for row_key, fingerprint in entries.items()]
        append_rows(worksheet, rows)

    def clear(self, project_id: str) -> None:
        worksheet = ensure_tab(self.client, self.meta_spreadsheet_id, self._tab_name(project_id), CACHE_HEADERS)
        worksheet.clear()
        worksheet.update("A1", [CACHE_HEADERS])
