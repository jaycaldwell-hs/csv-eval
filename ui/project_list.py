from __future__ import annotations

from uuid import uuid4

import streamlit as st

from lib.models import Project, ProjectConfig, ProjectStatus


BADGE_COLORS = {
    ProjectStatus.DRAFT: "#6b7280",
    ProjectStatus.ACTIVE: "#16a34a",
    ProjectStatus.PAUSED: "#d97706",
    ProjectStatus.ARCHIVED: "#374151",
}


def _status_badge(status: ProjectStatus) -> str:
    color = BADGE_COLORS.get(status, "#6b7280")
    return f"<span style='background:{color};color:white;padding:2px 8px;border-radius:999px;font-size:12px;'>{status.value}</span>"


def render(store) -> str | None:
    if "selected_project_id" not in st.session_state:
        st.session_state.selected_project_id = None

    with st.sidebar:
        st.subheader("Projects")
        if st.button("Create New Project", use_container_width=True):
            project = Project(
                id=str(uuid4()),
                config=ProjectConfig(name="New Project"),
                status=ProjectStatus.DRAFT,
            )
            store.save_project(project)
            st.session_state.selected_project_id = project.id
            st.rerun()

        projects = [p for p in store.list_projects() if p.status != ProjectStatus.ARCHIVED]
        projects.sort(key=lambda p: p.updated_at or "", reverse=True)

        if not projects:
            st.caption("No projects yet.")
            return None

        options = [p.id for p in projects]
        labels = {p.id: (p.config.name or "Untitled Project") for p in projects}

        selected = st.radio(
            "Project",
            options,
            format_func=lambda value: labels.get(value, value),
            index=options.index(st.session_state.selected_project_id)
            if st.session_state.selected_project_id in options
            else 0,
            key="project_selector",
            label_visibility="collapsed",
        )
        st.session_state.selected_project_id = selected

        project = next((p for p in projects if p.id == selected), None)
        if project:
            st.markdown(_status_badge(project.status), unsafe_allow_html=True)
            st.caption(f"Last run: {project.last_run_at or 'Never'}")

    return st.session_state.selected_project_id
