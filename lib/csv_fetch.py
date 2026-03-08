import io
import json
import re

import pandas as pd
import requests


def normalize_sheets_url(url: str) -> str:
    """Convert any Google Sheets URL to a CSV export URL."""
    if "output=csv" in url or "/export?format=csv" in url:
        return url

    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        return url

    sheet_id = match.group(1)
    gid_match = re.search(r"gid=(\d+)", url)
    gid = gid_match.group(1) if gid_match else "0"
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def fetch_csv(
    url: str,
    delimiter: str = ",",
    encoding: str = "utf-8",
    header_row_index: int = 0,
    json_columns: list[str] | None = None,
) -> pd.DataFrame:
    normalized_url = normalize_sheets_url(url)
    response = requests.get(normalized_url, timeout=30)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        raise ValueError(
            "Got HTML instead of CSV. The sheet may not be shared publicly. "
            "Set sharing to 'Anyone with the link' can view."
        )

    header = header_row_index if header_row_index >= 0 else None
    dataframe = pd.read_csv(
        io.StringIO(response.content.decode(encoding)),
        sep=delimiter,
        header=header,
        engine="python",
        on_bad_lines="skip",
    )

    if header is None:
        dataframe.columns = [f"column_{idx}" for idx in range(len(dataframe.columns))]

    if not json_columns:
        return dataframe

    for column in json_columns:
        if column not in dataframe.columns:
            continue

        def parse_json_cell(value):
            if pd.isna(value):
                return value
            if isinstance(value, (dict, list)):
                return value
            if not isinstance(value, str):
                return value
            stripped = value.strip()
            if not stripped:
                return value
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value

        dataframe[column] = dataframe[column].apply(parse_json_cell)

    return dataframe
