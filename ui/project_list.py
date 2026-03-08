from __future__ import annotations

from uuid import uuid4

import streamlit as st

from lib.models import Project, ProjectConfig


def render(store) -> str | None:
    if "selected_project_id" not in st.session_state:
        st.session_state.selected_project_id = None

    with st.sidebar:
        st.subheader("Projects")
        st.caption("Projects run only when you click Run Now.")

        if st.button("Create New Project", use_container_width=True):
            project = Project(
                id=str(uuid4()),
                config=ProjectConfig(name="New Project"),
            )
            store.save_project(project)
            st.session_state.selected_project_id = project.id
            st.rerun()

        projects = store.list_projects()
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
            st.caption(f"Last run: {project.last_run_at or 'Never'}")

    return st.session_state.selected_project_id
