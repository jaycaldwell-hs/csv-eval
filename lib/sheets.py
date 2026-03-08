from __future__ import annotations

from typing import Any

import gspread
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_gspread_client(service_account_info: dict[str, Any]) -> gspread.Client:
    credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    return gspread.authorize(credentials)


def ensure_tab(
    client: gspread.Client,
    spreadsheet_id: str,
    tab_name: str,
    headers: list[str],
) -> gspread.Worksheet:
    spreadsheet = client.open_by_key(spreadsheet_id)

    try:
        worksheet = spreadsheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=max(26, len(headers) + 5))

    first_row = worksheet.row_values(1)
    if not first_row:
        worksheet.update("A1", [headers])
    elif first_row != headers:
        worksheet.update("A1", [headers])

    return worksheet


def append_rows(worksheet: gspread.Worksheet, rows: list[list[Any]]) -> int:
    if not rows:
        return 0
    worksheet.append_rows(rows, value_input_option="RAW")
    return len(rows)


def read_all_rows(worksheet: gspread.Worksheet) -> list[dict[str, Any]]:
    return worksheet.get_all_records(default_blank="")


def upsert_rows(worksheet: gspread.Worksheet, rows: list[list[Any]], key_col_index: int) -> int:
    if not rows:
        return 0

    existing_values = worksheet.get_all_values()
    if not existing_values:
        worksheet.append_rows(rows, value_input_option="RAW")
        return len(rows)

    data_rows = existing_values[1:]
    key_to_row_num: dict[str, int] = {}
    for idx, existing_row in enumerate(data_rows, start=2):
        if key_col_index < len(existing_row):
            key_to_row_num[str(existing_row[key_col_index])] = idx

    updates = []
    append_batch = []
    for row in rows:
        key = str(row[key_col_index]) if key_col_index < len(row) else ""
        if key and key in key_to_row_num:
            row_num = key_to_row_num[key]
            updates.append((row_num, row))
        else:
            append_batch.append(row)

    for row_num, row in updates:
        worksheet.update(f"A{row_num}", [row])

    if append_batch:
        worksheet.append_rows(append_batch, value_input_option="RAW")

    return len(rows)
