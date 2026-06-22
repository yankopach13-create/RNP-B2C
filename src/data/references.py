"""Справочники: Google Sheets (основной источник) с fallback на локальные xlsx."""

from __future__ import annotations

import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, TypeVar

import numpy as np
import pandas as pd
import streamlit as st

_T = TypeVar("_T")
_SHEETS_CACHE_TTL_SEC = 600
_SHEETS_RETRY_ATTEMPTS = 5
_SHEETS_RETRY_BASE_DELAY_SEC = 2.0

from config.constants import REFERENCE_DIR, REFERENCE_GROUPS_FILENAMES

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SECRETS_PATH = _PROJECT_ROOT / ".streamlit" / "secrets.toml"

REF_SHOP_GROUPS = "shop_groups"
REF_CATEGORIES = "categories"
REF_CATEGORY_ORDER = "category_order"
REF_GROUPS_ORDER = "groups_order"
REF_FOCUS = "focus"

_REFERENCE_META: dict[str, dict[str, Any]] = {
    REF_SHOP_GROUPS: {
        "sheet": "shop_groups",
        "local": REFERENCE_GROUPS_FILENAMES,
        "title": "Магазины",
    },
    REF_CATEGORIES: {
        "sheet": "categories",
        "local": ("categories.xlsx",),
        "title": "Категории товаров",
    },
    REF_CATEGORY_ORDER: {
        "sheet": "category_order",
        "local": ("category_order.xlsx", "category_order.xls"),
        "title": "Порядок категорий",
    },
    REF_GROUPS_ORDER: {
        "sheet": "groups_order",
        "local": ("groups_order.xlsx", "groups_order.xls"),
        "title": "Порядок групп и магазинов",
    },
    REF_FOCUS: {
        "sheet": "focus",
        "local": ("focus.xlsx",),
        "title": "Фокусные позиции",
    },
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
_PLACEHOLDER_SPREADSHEET_ID = "REPLACE_WITH_YOUR_SPREADSHEET_ID"


def _is_streamlit_cloud() -> bool:
    """Streamlit Community Cloud / Snowflake — локальные xlsx в контейнере не персистятся."""
    if os.environ.get("STREAMLIT_CLOUD") or os.environ.get("STREAMLIT_SHARING_BASE_URL"):
        return True
    server_url = os.environ.get("STREAMLIT_SERVER_URL", "")
    return "streamlit.app" in server_url


def _secrets_setup_hint() -> str:
    if _is_streamlit_cloud():
        return (
            "Streamlit Cloud → Manage app → Settings → Secrets: "
            "вставьте содержимое из .streamlit/secrets.toml.example "
            "(данные service-account) и перезапустите приложение."
        )
    return (
        "Локально: положите service-account.json в корень проекта и выполните "
        "python scripts/build_secrets.py, либо настройте .streamlit/secrets.toml."
    )


@lru_cache(maxsize=1)
def _file_secrets() -> dict[str, Any]:
    if not _SECRETS_PATH.is_file():
        return {}
    import tomllib

    return tomllib.loads(_SECRETS_PATH.read_text(encoding="utf-8"))


def _gcp_service_account_info() -> dict[str, Any]:
    try:
        if "gcp_service_account" in st.secrets:
            return dict(st.secrets["gcp_service_account"])
    except Exception:  # noqa: BLE001
        pass
    return dict(_file_secrets().get("gcp_service_account", {}))


def _references_config() -> dict[str, Any]:
    try:
        refs = dict(st.secrets.get("references", {}))
        if refs:
            return refs
    except Exception:  # noqa: BLE001
        pass
    return dict(_file_secrets().get("references", {}))


def sheets_configured() -> bool:
    """True, если в secrets заданы учётные данные и ID таблицы."""
    info = _gcp_service_account_info()
    if not info.get("client_email") or not info.get("private_key"):
        return False
    refs = _references_config()
    spreadsheet_id = str(refs.get("spreadsheet_id", "")).strip()
    return bool(spreadsheet_id) and spreadsheet_id != _PLACEHOLDER_SPREADSHEET_ID


def get_reference_storage_hint(key: str) -> str:
    """Куда попадёт запись — для сообщений в UI."""
    if sheets_configured():
        return f"Google Sheets, лист «{_sheet_name(key)}»"
    return get_reference_label(key)


def get_sheets_connection_message() -> tuple[str, str]:
    """
    Статус подключения к Google Sheets для UI.
    Возвращает (уровень: ok|warn|error, текст).
    """
    if sheets_configured():
        refs = _references_config()
        sid = str(refs.get("spreadsheet_id", "")).strip()
        email = str(_gcp_service_account_info().get("client_email", "")).strip()
        return (
            "ok",
            f"Справочники: Google Sheets ({email or 'service account'})",
        )
    if _is_streamlit_cloud():
        return (
            "error",
            "Google Sheets не подключён. Задайте Secrets в панели Streamlit Cloud "
            "(см. .streamlit/secrets.toml.example).",
        )
    return (
        "warn",
        "Google Sheets не подключён — используются локальные файлы src/data/reference/.",
    )


def _sheet_name(key: str) -> str:
    refs = _references_config()
    override = refs.get(f"sheet_{key}")
    if override:
        return str(override).strip()
    return _REFERENCE_META[key]["sheet"]


def get_reference_title(key: str) -> str:
    return _REFERENCE_META[key]["title"]


def get_reference_label(key: str) -> str:
    if sheets_configured():
        return f"лист «{_sheet_name(key)}»"
    local = _REFERENCE_META[key]["local"]
    if isinstance(local, tuple):
        return " или ".join(local)
    return str(local)


def _local_path(key: str) -> Path | None:
    local = _REFERENCE_META[key]["local"]
    names = local if isinstance(local, tuple) else (local,)
    for name in names:
        path = REFERENCE_DIR / name
        if path.is_file():
            return path
    return None


def reference_exists(key: str) -> bool:
    if key not in _REFERENCE_META:
        return False
    if sheets_configured():
        try:
            load_reference(key)
            return True
        except Exception:  # noqa: BLE001
            return False
    return _local_path(key) is not None


def _resolve_ssl_verify() -> bool | str:
    refs = _references_config()
    ssl_verify = refs.get("ssl_verify", True)
    if isinstance(ssl_verify, str):
        if ssl_verify.strip().lower() in {"false", "0", "no", "off"}:
            return False
        if ssl_verify.strip().lower() in {"true", "1", "yes", "on"}:
            return True
    if ssl_verify is False:
        return False
    ca_bundle = refs.get("ssl_ca_bundle")
    if ca_bundle:
        path = Path(str(ca_bundle).strip())
        if path.is_file():
            return str(path)
    for env_name in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
        env_path = os.environ.get(env_name, "").strip()
        if env_path and Path(env_path).is_file():
            return env_path
    return True


def _apply_ssl_verify(client) -> None:
    verify = _resolve_ssl_verify()
    if verify is not True:
        client.http_client.session.verify = verify


@st.cache_resource
def _get_gspread_client():
    import gspread
    from google.oauth2.service_account import Credentials

    info = _gcp_service_account_info()
    credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
    client = gspread.authorize(credentials)
    _apply_ssl_verify(client)
    return client


@st.cache_resource
def _open_spreadsheet(spreadsheet_id: str):
    client = _get_gspread_client()
    return _sheets_api_with_retry(lambda: client.open_by_key(spreadsheet_id))


def is_sheets_quota_error(exc: BaseException) -> bool:
    """True для 429 / Quota exceeded Google Sheets API."""
    message = str(exc)
    if "429" in message or "Quota exceeded" in message:
        return True
    if "sheets.googleapis.com" in message and "quota" in message.lower():
        return True
    try:
        from gspread.exceptions import APIError

        if isinstance(exc, APIError):
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 429:
                return True
    except ImportError:
        pass
    return False


def _is_retryable_sheets_error(exc: BaseException) -> bool:
    if is_sheets_quota_error(exc):
        return True
    message = str(exc).lower()
    return "503" in message or "service unavailable" in message


def _sheets_api_with_retry(action: Callable[[], _T]) -> _T:
    last_error: BaseException | None = None
    for attempt in range(_SHEETS_RETRY_ATTEMPTS):
        try:
            return action()
        except Exception as exc:  # noqa: BLE001
            if not _is_retryable_sheets_error(exc) or attempt >= _SHEETS_RETRY_ATTEMPTS - 1:
                raise
            last_error = exc
            time.sleep(_SHEETS_RETRY_BASE_DELAY_SEC * (2**attempt))
    if last_error is not None:
        raise last_error
    raise RuntimeError("Не удалось выполнить запрос к Google Sheets.")


def _worksheet_to_dataframe(worksheet) -> pd.DataFrame:
    rows = _sheets_api_with_retry(worksheet.get_all_values)
    if not rows:
        return pd.DataFrame()
    header = [str(cell).strip() for cell in rows[0]]
    if len(rows) == 1:
        return pd.DataFrame(columns=header)
    return pd.DataFrame(rows[1:], columns=header)


def _cell_value(value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if pd.isna(value):
        return ""
    return value


def _dataframe_to_sheet_values(df: pd.DataFrame) -> list[list[Any]]:
    payload = df.copy().where(pd.notnull(df), "")
    values: list[list[Any]] = [[str(c) for c in payload.columns.tolist()]]
    for row in payload.itertuples(index=False, name=None):
        values.append([_cell_value(v) for v in row])
    return values


@st.cache_data(ttl=_SHEETS_CACHE_TTL_SEC, show_spinner=False)
def _load_all_references_from_sheets(spreadsheet_id: str) -> dict[str, pd.DataFrame]:
    """Один open таблицы и пакетная загрузка листов — меньше read-запросов к API."""
    spreadsheet = _open_spreadsheet(spreadsheet_id)
    loaded: dict[str, pd.DataFrame] = {}
    for key in _REFERENCE_META:
        worksheet_name = _sheet_name(key)
        worksheet = _sheets_api_with_retry(lambda name=worksheet_name: spreadsheet.worksheet(name))
        loaded[key] = _worksheet_to_dataframe(worksheet)
    return loaded


def _save_to_sheets(spreadsheet_id: str, worksheet_name: str, df: pd.DataFrame) -> None:
    spreadsheet = _open_spreadsheet(spreadsheet_id)
    worksheet = _sheets_api_with_retry(lambda: spreadsheet.worksheet(worksheet_name))

    def _write() -> None:
        worksheet.clear()
        if df.empty and list(df.columns):
            worksheet.update([list(df.columns)], value_input_option="USER_ENTERED")
            return
        if df.empty:
            return
        values = _dataframe_to_sheet_values(df)
        worksheet.update(values, value_input_option="USER_ENTERED")

    _sheets_api_with_retry(_write)


def load_reference(key: str) -> pd.DataFrame:
    """Загружает справочник из Google Sheets или локального xlsx."""
    if key not in _REFERENCE_META:
        raise ValueError(f"Неизвестный справочник: {key}")

    if sheets_configured():
        refs = _references_config()
        spreadsheet_id = str(refs["spreadsheet_id"]).strip()
        batch = _load_all_references_from_sheets(spreadsheet_id)
        return batch[key].copy()

    if _is_streamlit_cloud():
        raise FileNotFoundError(
            f"Справочник «{get_reference_title(key)}» недоступен: Google Sheets не настроен. "
            f"{_secrets_setup_hint()}"
        )

    local_path = _local_path(key)
    if local_path is None:
        raise FileNotFoundError(
            f"Справочник «{get_reference_title(key)}» не найден: {get_reference_label(key)}"
        )
    return pd.read_excel(local_path)


def save_reference(key: str, df: pd.DataFrame) -> None:
    """Сохраняет справочник в Google Sheets или локальный xlsx."""
    if key not in _REFERENCE_META:
        raise ValueError(f"Неизвестный справочник: {key}")

    if sheets_configured():
        refs = _references_config()
        spreadsheet_id = str(refs["spreadsheet_id"]).strip()
        _save_to_sheets(spreadsheet_id, _sheet_name(key), df)
    elif _is_streamlit_cloud():
        raise RuntimeError(
            f"Нельзя сохранить справочник «{get_reference_title(key)}» без Google Sheets. "
            f"{_secrets_setup_hint()}"
        )
    else:
        local_path = _local_path(key)
        if local_path is None:
            local_names = _REFERENCE_META[key]["local"]
            first = local_names[0] if isinstance(local_names, tuple) else local_names
            local_path = REFERENCE_DIR / first
        local_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(local_path, index=False)
    clear_reference_cache()


def clear_reference_cache() -> None:
    _load_all_references_from_sheets.clear()
