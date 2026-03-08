import os
import time

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from lib.csv_fetch import fetch_csv
from lib.llm import OpenAIProvider

load_dotenv()

MODEL = "gpt-5.2"
TARGET_COLUMN = "conversation_json"


@st.cache_data(ttl=60)
def fetch_csv_cached(url: str) -> pd.DataFrame:
    return fetch_csv(url)


def render() -> None:
    st.title("CSV Eval Runner")

    api_key = os.getenv("OPENAI_API_KEY", "") or st.secrets.get("OPENAI_API_KEY", "")

    with st.sidebar:
        st.header("Settings")
        mode = st.radio("Mode", ["Row-by-row", "All at once"], key="legacy_mode")
        auto_refresh = st.checkbox("Auto-refresh (interval)", key="legacy_auto_refresh")
        interval_min = 15
        if auto_refresh:
            interval_min = st.number_input(
                "Interval (minutes)",
                min_value=1,
                max_value=1440,
                value=15,
                key="legacy_interval",
            )

    csv_url = st.text_input(
        "Google Sheets Published CSV URL",
        placeholder="https://docs.google.com/spreadsheets/d/e/.../pub?output=csv",
        key="legacy_csv_url",
    )

    system_prompt = st.text_area(
        "System Prompt",
        height=150,
        placeholder="e.g. 'Evaluate this conversation for policy compliance. Return PASS or FAIL with reasoning.'",
        key="legacy_system_prompt",
    )

    def run_eval() -> None:
        if not api_key:
            st.error("OpenAI API key not configured. Set OPENAI_API_KEY in environment or Streamlit secrets.")
            return
        if not csv_url:
            st.error("Please provide a CSV URL.")
            return
        if not system_prompt:
            st.error("Please provide a system prompt.")
            return

        provider = OpenAIProvider(api_key=api_key, model=MODEL)

        with st.spinner("Fetching CSV..."):
            try:
                dataframe = fetch_csv_cached(csv_url)
            except Exception as exc:
                st.error(f"Failed to fetch CSV: {exc}")
                return

        if TARGET_COLUMN not in dataframe.columns:
            st.error(f"Column '{TARGET_COLUMN}' not found. Available columns: {', '.join(dataframe.columns)}")
            return

        conversations = dataframe[TARGET_COLUMN].dropna().reset_index(drop=True)
        st.info(f"Found {len(conversations)} rows with '{TARGET_COLUMN}' data.")
        st.subheader("Eval Results")

        if mode == "All at once":
            all_convos = "\n\n---\n\n".join(f"[Row {i + 1}]\n{c}" for i, c in enumerate(conversations))
            user_content = f"Here are all conversations:\n\n{all_convos}"
            with st.spinner("Running eval on full dataset..."):
                try:
                    result = provider.call(system_prompt, user_content)
                except Exception as exc:
                    st.error(f"LLM error: {exc}")
                    return
            st.markdown(result)
        else:
            progress = st.progress(0)
            results = []
            for i, convo in enumerate(conversations):
                with st.spinner(f"Evaluating row {i + 1}/{len(conversations)}..."):
                    try:
                        result = provider.call(system_prompt, str(convo))
                    except Exception as exc:
                        result = f"ERROR: {exc}"
                results.append(result)
                progress.progress((i + 1) / len(conversations))

            result_df = pd.DataFrame({TARGET_COLUMN: conversations, "eval_result": results})
            st.dataframe(result_df, use_container_width=True)

            csv_out = result_df.to_csv(index=False)
            st.download_button(
                "Download results as CSV",
                csv_out,
                file_name="eval_results.csv",
                mime="text/csv",
            )

    if st.button("Run Eval", type="primary", key="legacy_run_eval"):
        run_eval()

    if auto_refresh:
        st.info(f"Auto-refreshing every {interval_min} minute(s).")
        time.sleep(interval_min * 60)
        st.rerun()
