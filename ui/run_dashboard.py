from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from lib.models import RunLog


def _duration_seconds(run_log: RunLog) -> float | None:
    try:
        start = datetime.fromisoformat(run_log.started_at)
        end = datetime.fromisoformat(run_log.completed_at)
        return (end - start).total_seconds()
    except Exception:
        return None


def _status_message(run_log: RunLog) -> None:
    if run_log.status == "success":
        st.success("Run completed successfully.")
    elif run_log.status == "partial_failure":
        st.warning("Run completed with row-level errors.")
    else:
        st.error("Run failed.")


def render_run_result(run_log: RunLog) -> None:
    st.subheader("Run Result")
    _status_message(run_log)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Status", run_log.status)
    col2.metric("Rows total", run_log.rows_total)
    col3.metric("Rows processed", run_log.rows_processed)
    col4.metric("Rows skipped", run_log.rows_skipped)
    col5.metric("Rows errored", run_log.rows_errored)

    duration = _duration_seconds(run_log)
    details = [f"Model: {run_log.model or 'n/a'}", f"Prompt version: {run_log.prompt_version}"]
    if duration is not None:
        details.append(f"Duration: {duration:.2f}s")
    st.caption(" | ".join(details))

    if run_log.error_summary:
        st.error(run_log.error_summary)


def render_history(store, project_id: str) -> None:
    logs = store.get_run_logs(project_id, limit=20)
    if not logs:
        st.caption("No run history yet.")
        return

    rows = []
    for log in logs:
        rows.append(
            {
                "Run Time": log.started_at,
                "Status": log.status,
                "Rows Total": log.rows_total,
                "Rows Processed": log.rows_processed,
                "Rows Skipped": log.rows_skipped,
                "Rows Errored": log.rows_errored,
                "Model": log.model,
                "Prompt Version": log.prompt_version,
                "Duration (s)": _duration_seconds(log),
            }
        )

    st.subheader("Recent Runs")
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
