"""Smoke-test Google Sheets (локально: secrets.toml или Streamlit secrets)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data.references import (  # noqa: E402
    REF_CATEGORIES,
    REF_CATEGORY_ORDER,
    REF_FOCUS,
    REF_GROUPS_ORDER,
    REF_SHOP_GROUPS,
    _sheet_name,
    sheets_configured,
)

SHEET_KEYS = (
    REF_SHOP_GROUPS,
    REF_CATEGORIES,
    REF_CATEGORY_ORDER,
    REF_GROUPS_ORDER,
    REF_FOCUS,
)


def main() -> None:
    if not sheets_configured():
        raise SystemExit(
            "Google Sheets не настроен. Выполните: python scripts/build_secrets.py"
        )

    import gspread
    from google.oauth2.service_account import Credentials
    from data.references import _gcp_service_account_info, _references_config, _resolve_ssl_verify

    info = _gcp_service_account_info()
    refs = _references_config()
    spreadsheet_id = str(refs["spreadsheet_id"]).strip()

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    client = gspread.authorize(Credentials.from_service_account_info(info, scopes=scopes))
    if _resolve_ssl_verify() is False:
        client.http_client.session.verify = False

    sheet = client.open_by_key(spreadsheet_id)
    print(f"OK: таблица «{sheet.title}»")

    for key in SHEET_KEYS:
        ws_name = _sheet_name(key)
        ws = sheet.worksheet(ws_name)
        rows = len(ws.get_all_values())
        print(f"  - {ws_name}: {rows} строк")


if __name__ == "__main__":
    main()
