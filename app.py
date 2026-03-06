import io
import time

import pandas as pd
import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

st.set_page_config(page_title="CSV Eval", layout="wide")
st.title("CSV Eval Runner")

# --- Sidebar config ---
api_key = os.getenv("OPENAI_API_KEY", "") or st.secrets.get("OPENAI_API_KEY", "")

with st.sidebar:
    st.header("Settings")
    model = st.selectbox("Model", ["gpt-5.2", "gpt-5.2-mini", "gpt-4.1", "gpt-4.1-mini"], index=0)
    mode = st.radio("Mode", ["Row-by-row", "All at once"])
    auto_refresh = st.checkbox("Auto-refresh (interval)")
    if auto_refresh:
        interval_min = st.number_input("Interval (minutes)", min_value=1, max_value=1440, value=15)

# --- Main UI ---
csv_url = st.text_input(
    "Google Sheets Published CSV URL",
    placeholder="https://docs.google.com/spreadsheets/d/e/.../pub?output=csv",
)

system_prompt = st.text_area(
    "System Prompt",
    height=150,
    placeholder="e.g. 'For each row, evaluate whether the conversation contains a policy violation. Return PASS or FAIL with a brief reason.'",
)


@st.cache_data(ttl=60)
def fetch_csv(url: str) -> pd.DataFrame:
    return pd.read_csv(url)


def call_llm(client: OpenAI, system: str, user_content: str, model_name: str) -> str:
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
    )
    return response.choices[0].message.content


def run_eval():
    if not api_key:
        st.error("OpenAI API key not configured. Set OPENAI_API_KEY in environment or Streamlit secrets.")
        return
    if not csv_url:
        st.error("Please provide a CSV URL.")
        return
    if not system_prompt:
        st.error("Please provide a system prompt.")
        return

    client = OpenAI(api_key=api_key)

    with st.spinner("Fetching CSV..."):
        try:
            df = fetch_csv(csv_url)
        except Exception as e:
            st.error(f"Failed to fetch CSV: {e}")
            return

    st.subheader("Source Data")
    st.dataframe(df, use_container_width=True)

    st.subheader("Eval Results")

    if mode == "All at once":
        csv_text = df.to_csv(index=False)
        user_content = f"Here is the full CSV data:\n\n{csv_text}"
        with st.spinner("Running eval on full dataset..."):
            result = call_llm(client, system_prompt, user_content, model)
        st.markdown(result)
    else:
        progress = st.progress(0)
        results = []
        for i, row in df.iterrows():
            row_text = "\n".join(f"{col}: {val}" for col, val in row.items())
            user_content = f"Row {i + 1}:\n{row_text}"
            with st.spinner(f"Evaluating row {i + 1}/{len(df)}..."):
                result = call_llm(client, system_prompt, user_content, model)
            results.append(result)
            progress.progress((i + 1) / len(df))

        result_df = df.copy()
        result_df["eval_result"] = results
        st.dataframe(result_df, use_container_width=True)

        # Download option
        csv_out = result_df.to_csv(index=False)
        st.download_button(
            "Download results as CSV",
            csv_out,
            file_name="eval_results.csv",
            mime="text/csv",
        )


if st.button("Run Eval", type="primary"):
    run_eval()

if auto_refresh:
    st.info(f"Auto-refreshing every {interval_min} minute(s).")
    time.sleep(interval_min * 60)
    st.rerun()
