"""Smoke-test подключения к Google Sheets справочникам B2C."""

from __future__ import annotations

import tomllib
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

ROOT = Path(__file__).resolve().parents[1]
SECRETS_PATH = ROOT / ".streamlit" / "secrets.toml"

SHEET_KEYS = (
    "shop_groups",
    "categories",
    "category_order",
    "groups_order",
    "focus",
)


def main() -> None:
    secrets = tomllib.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    info = secrets["gcp_service_account"]
    refs = secrets.get("references", {})
    spreadsheet_id = refs["spreadsheet_id"]

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    client = gspread.authorize(Credentials.from_service_account_info(info, scopes=scopes))
    if refs.get("ssl_verify") is False:
        client.http_client.session.verify = False

    sheet = client.open_by_key(spreadsheet_id)
    print(f"OK: таблица «{sheet.title}»")

    for key in SHEET_KEYS:
        ws_name = refs.get(f"sheet_{key}", key)
        ws = sheet.worksheet(ws_name)
        rows = len(ws.get_all_values())
        print(f"  - {ws_name}: {rows} строк")


if __name__ == "__main__":
    main()
