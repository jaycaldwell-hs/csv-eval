import streamlit as st

from lib.store import LocalProjectStore, ProjectStore
from ui import legacy, project_editor, project_list, run_dashboard

st.set_page_config(page_title="CSV Eval", layout="wide")


@st.cache_resource
def get_store() -> ProjectStore | LocalProjectStore:
    meta_spreadsheet_id = st.secrets.get("META_SPREADSHEET_ID", "")
    service_account_section = st.secrets.get("GOOGLE_SERVICE_ACCOUNT", {})
    service_account_info = dict(service_account_section) if service_account_section else {}

    if not meta_spreadsheet_id or not service_account_info:
        return LocalProjectStore()

    try:
        return ProjectStore(meta_spreadsheet_id=meta_spreadsheet_id, service_account_info=service_account_info)
    except Exception:
        return LocalProjectStore()


tab_quick, tab_projects = st.tabs(["Quick Eval", "Projects"])

with tab_quick:
    legacy.render()

with tab_projects:
    store = get_store()
    if getattr(store, "mode", "") == "local":
        st.info("Projects running in local mode (no Google Sheets secrets). Data is stored under `.local_data/`.")

    selected_id = project_list.render(store)
    if selected_id:
        project = store.get_project(selected_id)
        if project is None:
            st.warning("Selected project no longer exists.")
        else:
            run_log = project_editor.render(project, store)
            if run_log:
                run_dashboard.render_run_result(run_log)
            run_dashboard.render_history(store, project.id)
    else:
        st.info("Create a project from the sidebar to get started.")
