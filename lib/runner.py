from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from lib.cache import ProjectCache, compute_fingerprint, compute_row_key
from lib.csv_fetch import fetch_csv
from lib.llm import OpenAIProvider
from lib.models import Project, RunLog
from lib.sheets import append_rows, ensure_tab, upsert_rows


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_parse_llm_output(content: str) -> dict:
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        return {}
    return {}


def _build_output_row(project: Project, row: dict, llm_output: str, task_error: str = "") -> list:
    headers = project.config.output_headers
    output = {header: "" for header in headers}

    # Copy matching source fields when header names align with CSV columns.
    for header in headers:
        if header in row:
            output[header] = row.get(header, "")

    classification_error = ""
    parsed = _safe_parse_llm_output(llm_output)

    if parsed:
        for internal_field, header_name in project.config.field_mapping.items():
            if header_name not in output:
                classification_error = f"Mapped header '{header_name}' not found in output headers"
                continue
            output[header_name] = parsed.get(internal_field, "")
    else:
        if "Response" in output:
            output["Response"] = llm_output
        elif "reasoning" in output:
            output["reasoning"] = llm_output

    if "classification_error" in output and classification_error:
        output["classification_error"] = classification_error

    if "task_error" in output and task_error:
        output["task_error"] = task_error

    return [output.get(header, "") for header in headers]


def run_project(project: Project, store, api_key: str = "") -> RunLog:
    started_at = _utc_now_iso()
    run_id = str(uuid4())

    rows_fetched = 0
    rows_new = 0
    rows_processed = 0
    rows_failed = 0
    errors: list[str] = []

    try:
        dataframe = fetch_csv(
            project.config.csv_url,
            delimiter=project.config.delimiter,
            encoding=project.config.encoding,
            json_columns=project.config.json_columns,
        )
        records = dataframe.to_dict(orient="records")
        rows_fetched = len(records)

        cache = ProjectCache(store.client, store.meta_spreadsheet_id)
        existing_cache = cache.load(project.id)

        candidates = []
        for row in records:
            row_key = compute_row_key(row, project.config.row_key_strategy, project.config.row_key_columns)
            fingerprint = compute_fingerprint(row)
            cached_fingerprint = existing_cache.get(row_key)

            is_new = cached_fingerprint is None
            is_changed = bool(project.config.reprocess_on_change and cached_fingerprint and cached_fingerprint != fingerprint)
            if is_new or is_changed:
                candidates.append((row, row_key, fingerprint))

        rows_new = len(candidates)
        to_process = candidates[: project.config.max_rows_per_run]

        output_ws = ensure_tab(
            store.client,
            project.config.gsheet_spreadsheet_id,
            project.config.gsheet_tab_name,
            project.config.output_headers,
        )

        provider = OpenAIProvider(api_key=api_key, model=project.config.model)
        output_rows: list[list] = []

        for row, row_key, fingerprint in to_process:
            rows_processed += 1
            task_error = ""
            llm_output = ""
            try:
                llm_output = provider.call(project.config.system_prompt, json.dumps(row, ensure_ascii=True, default=str))
            except Exception as exc:
                task_error = str(exc)
                rows_failed += 1
                errors.append(f"row_key={row_key}: {exc}")

            output_row = _build_output_row(project, row, llm_output, task_error=task_error)
            if task_error:
                # Keep error rows in output for observability.
                pass
            elif "classification_error" in project.config.output_headers:
                idx = project.config.output_headers.index("classification_error")
                if str(output_row[idx]).strip():
                    rows_failed += 1
                    errors.append(f"row_key={row_key}: {output_row[idx]}")

            output_rows.append(output_row)
            existing_cache[row_key] = fingerprint

        if project.config.write_mode == "upsert":
            if not project.config.upsert_key_column:
                raise ValueError("upsert_key_column is required when write_mode is 'upsert'")
            if project.config.upsert_key_column not in project.config.output_headers:
                raise ValueError("upsert_key_column must exist in output_headers")
            key_index = project.config.output_headers.index(project.config.upsert_key_column)
            upsert_rows(output_ws, output_rows, key_index)
        else:
            append_rows(output_ws, output_rows)

        cache.save(project.id, existing_cache)

        project.last_run_at = _utc_now_iso()
        project.last_run_rows_processed = rows_processed
        project.last_run_rows_failed = rows_failed
        store.save_project(project)

        status = "success"
        if rows_failed > 0:
            status = "partial_failure"

        run_log = RunLog(
            run_id=run_id,
            project_id=project.id,
            started_at=started_at,
            completed_at=_utc_now_iso(),
            status=status,
            rows_fetched=rows_fetched,
            rows_new=rows_new,
            rows_processed=rows_processed,
            rows_failed=rows_failed,
            error_summary="; ".join(errors[:5]),
        )
        store.write_run_log(run_log)
        return run_log

    except Exception as exc:
        error_summary = str(exc)
        run_log = RunLog(
            run_id=run_id,
            project_id=project.id,
            started_at=started_at,
            completed_at=_utc_now_iso(),
            status="error",
            rows_fetched=rows_fetched,
            rows_new=rows_new,
            rows_processed=rows_processed,
            rows_failed=max(rows_failed, 1),
            error_summary=error_summary,
        )
        store.write_run_log(run_log)
        return run_log
