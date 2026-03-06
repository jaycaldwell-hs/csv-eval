import io
import re
import time

import pandas as pd
import requests
import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

st.set_page_config(page_title="CSV Eval", layout="wide")
st.title("CSV Eval Runner")

# --- Sidebar config ---
api_key = os.getenv("OPENAI_API_KEY", "") or st.secrets.get("OPENAI_API_KEY", "")

MODEL = "gpt-5.2"

with st.sidebar:
    st.header("Settings")
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
    placeholder="e.g. 'Evaluate this conversation for policy compliance. Return PASS or FAIL with reasoning.'",
)

TARGET_COLUMN = "conversation_json"


def normalize_sheets_url(url: str) -> str:
    """Convert any Google Sheets URL to a CSV export URL."""
    # Already a pub?output=csv link
    if "pub?output=csv" in url or "/export?format=csv" in url:
        return url
    # Regular edit URL: extract sheet ID and convert to export
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if m:
        sheet_id = m.group(1)
        # Check for gid param
        gid_match = re.search(r"gid=(\d+)", url)
        gid = gid_match.group(1) if gid_match else "0"
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    return url


@st.cache_data(ttl=60)
def fetch_csv(url: str) -> pd.DataFrame:
    url = normalize_sheets_url(url)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "")
    if "text/html" in content_type:
        raise ValueError(
            "Got HTML instead of CSV. The sheet may not be shared publicly. "
            "Set sharing to 'Anyone with the link' can view."
        )
    return pd.read_csv(io.StringIO(resp.text), engine="python", on_bad_lines="skip")


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

    if TARGET_COLUMN not in df.columns:
        st.error(f"Column '{TARGET_COLUMN}' not found. Available columns: {', '.join(df.columns)}")
        return

    conversations = df[TARGET_COLUMN].dropna().reset_index(drop=True)
    st.info(f"Found {len(conversations)} rows with '{TARGET_COLUMN}' data.")

    st.subheader("Eval Results")

    if mode == "All at once":
        all_convos = "\n\n---\n\n".join(
            f"[Row {i + 1}]\n{c}" for i, c in enumerate(conversations)
        )
        user_content = f"Here are all conversations:\n\n{all_convos}"
        with st.spinner("Running eval on full dataset..."):
            try:
                result = call_llm(client, system_prompt, user_content, MODEL)
            except Exception as e:
                st.error(f"LLM error: {e}")
                return
        st.markdown(result)
    else:
        progress = st.progress(0)
        results = []
        for i, convo in enumerate(conversations):
            with st.spinner(f"Evaluating row {i + 1}/{len(conversations)}..."):
                try:
                    result = call_llm(client, system_prompt, str(convo), MODEL)
                except Exception as e:
                    result = f"ERROR: {e}"
            results.append(result)
            progress.progress((i + 1) / len(conversations))

        result_df = pd.DataFrame({
            TARGET_COLUMN: conversations,
            "eval_result": results,
        })
        st.dataframe(result_df, use_container_width=True)

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
