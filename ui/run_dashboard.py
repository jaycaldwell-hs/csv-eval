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


def render_run_result(run_log: RunLog) -> None:
    st.subheader("Run Result")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Status", run_log.status)
    col2.metric("Rows fetched", run_log.rows_fetched)
    col3.metric("Rows processed", run_log.rows_processed)
    col4.metric("Rows failed", run_log.rows_failed)

    duration = _duration_seconds(run_log)
    if duration is not None:
        st.caption(f"Duration: {duration:.2f}s")

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
                "Rows New": log.rows_new,
                "Rows Processed": log.rows_processed,
                "Rows Failed": log.rows_failed,
                "Duration (s)": _duration_seconds(log),
            }
        )

    st.subheader("Recent Runs")
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
