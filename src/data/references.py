"""Справочники: Google Sheets (основной источник) с fallback на локальные xlsx."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
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

from config.constants import (
    REFERENCE_DIR,
    REFERENCE_GROUPS_FILENAMES,
    REFERENCE_PCT_NO_BK_FILENAMES,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SECRETS_PATH = _PROJECT_ROOT / ".streamlit" / "secrets.toml"

REF_SHOP_GROUPS = "shop_groups"
REF_CATEGORIES = "categories"
REF_CATEGORY_ORDER = "category_order"
REF_GROUPS_ORDER = "groups_order"
REF_FOCUS = "focus"
REF_PCT_NO_BK = "pct_no_bk"

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
    REF_PCT_NO_BK: {
        "sheet": "%_bk",
        "local": REFERENCE_PCT_NO_BK_FILENAMES,
        "title": "% без БК",
    },
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
_PLACEHOLDER_SPREADSHEET_ID = "REPLACE_WITH_YOUR_SPREADSHEET_ID"


class ReferencesBatchSaveError(RuntimeError):
    """Частичная запись пакета справочников в Google Sheets / локальные файлы."""

    def __init__(
        self,
        saved_keys: list[str],
        failed_key: str,
        cause: BaseException,
    ) -> None:
        self.saved_keys = saved_keys
        self.failed_key = failed_key
        self.cause = cause
        saved_titles = ", ".join(get_reference_title(k) for k in saved_keys) or "—"
        super().__init__(
            f"Ошибка при сохранении «{get_reference_title(failed_key)}»: {cause}. "
            f"Уже сохранено: {saved_titles}."
        )


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


def _sheet_range_name(worksheet_name: str, cell_range: str = "A:ZZ") -> str:
    """A1-диапазон листа для batchGet (экранирование имён с пробелами)."""
    escaped = worksheet_name.replace("'", "''")
    if re.search(r"[^\w]", worksheet_name):
        return f"'{escaped}'!{cell_range}"
    return f"{worksheet_name}!{cell_range}"


def _column_letter(col_idx: int) -> str:
    """1-based индекс столбца → буква(ы) Excel."""
    if col_idx < 1:
        return "A"
    result = ""
    n = col_idx
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def _rows_to_dataframe(rows: list[list[Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    header = [str(cell).strip() for cell in rows[0]]
    if len(rows) == 1:
        return pd.DataFrame(columns=header)
    return pd.DataFrame(rows[1:], columns=header)


def _worksheet_to_dataframe(worksheet) -> pd.DataFrame:
    rows = _sheets_api_with_retry(worksheet.get_all_values)
    return _rows_to_dataframe(rows)


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


@dataclass(frozen=True)
class _SheetWritePlan:
    """План записи одного листа: диапазон update и опциональная очистка хвоста."""

    range_name: str
    values: list[list[Any]]
    n_rows: int
    tail_clear_range: str | None = None


def _sheet_write_plan(
    worksheet_name: str,
    df: pd.DataFrame,
    *,
    old_row_count: int = 0,
    old_col_count: int = 0,
) -> _SheetWritePlan | None:
    """Формирует диапазоны для values_batch_update и batchClear."""
    if df.empty and not list(df.columns):
        return None
    if df.empty and list(df.columns):
        values: list[list[Any]] = [list(df.columns)]
    else:
        values = _dataframe_to_sheet_values(df)

    n_rows = len(values)
    n_cols = len(values[0]) if values else 0
    if n_cols == 0:
        return None

    end_col = _column_letter(n_cols)
    range_name = _sheet_range_name(worksheet_name, f"A1:{end_col}{n_rows}")
    tail_clear_range = None
    if old_row_count > n_rows:
        tail_end_col = _column_letter(max(n_cols, old_col_count))
        tail_clear_range = _sheet_range_name(
            worksheet_name,
            f"A{n_rows + 1}:{tail_end_col}{old_row_count}",
        )
    return _SheetWritePlan(
        range_name=range_name,
        values=values,
        n_rows=n_rows,
        tail_clear_range=tail_clear_range,
    )


def build_sheets_batch_write_body(
    plans: list[_SheetWritePlan],
) -> dict[str, Any]:
    """Тело запроса values_batch_update для нескольких листов."""
    data = [{"range": p.range_name, "values": p.values} for p in plans]
    return {"valueInputOption": "USER_ENTERED", "data": data}


def _save_many_to_sheets(spreadsheet_id: str, updates: dict[str, pd.DataFrame]) -> None:
    """Запись нескольких листов одним values_batch_update (+ batchClear хвостов)."""
    spreadsheet = _open_spreadsheet(spreadsheet_id)
    plans: list[_SheetWritePlan] = []
    verify: list[tuple[Any, int]] = []

    for key, df in updates.items():
        ws_name = _sheet_name(key)
        worksheet = _sheets_api_with_retry(
            lambda name=ws_name: spreadsheet.worksheet(name)
        )
        plan = _sheet_write_plan(
            ws_name,
            df,
            old_row_count=worksheet.row_count,
            old_col_count=worksheet.col_count,
        )
        if plan is None:
            continue
        plans.append(plan)
        verify.append((worksheet, plan.n_rows))

    if not plans:
        return

    def _batch_write() -> None:
        spreadsheet.values_batch_update(body=build_sheets_batch_write_body(plans))

    _sheets_api_with_retry(_batch_write)

    tail_ranges = [p.tail_clear_range for p in plans if p.tail_clear_range]
    if tail_ranges:

        def _batch_clear() -> None:
            spreadsheet.values_batch_clear(body={"ranges": tail_ranges})

        _sheets_api_with_retry(_batch_clear)

    for worksheet, n_rows in verify:
        _verify_sheet_row_count(worksheet, n_rows)


def _load_references_via_batch_get(spreadsheet) -> dict[str, pd.DataFrame]:
    """Все листы одним values_batch_get."""
    keys_and_names = [(key, _sheet_name(key)) for key in _REFERENCE_META]
    ranges = [_sheet_range_name(name) for _, name in keys_and_names]

    def _batch_get():
        return spreadsheet.values_batch_get(ranges)

    result = _sheets_api_with_retry(_batch_get)
    value_ranges = result.get("valueRanges", []) if isinstance(result, dict) else []
    loaded: dict[str, pd.DataFrame] = {}
    for i, (key, _) in enumerate(keys_and_names):
        vr = value_ranges[i] if i < len(value_ranges) else {}
        rows = vr.get("values", []) if isinstance(vr, dict) else []
        loaded[key] = _rows_to_dataframe(rows)
    return loaded


def _load_references_via_worksheets(spreadsheet) -> dict[str, pd.DataFrame]:
    """Fallback: по одному get_all_values на лист."""
    loaded: dict[str, pd.DataFrame] = {}
    for key in _REFERENCE_META:
        worksheet_name = _sheet_name(key)
        worksheet = _sheets_api_with_retry(
            lambda name=worksheet_name: spreadsheet.worksheet(name)
        )
        loaded[key] = _worksheet_to_dataframe(worksheet)
    return loaded


@st.cache_data(ttl=_SHEETS_CACHE_TTL_SEC, show_spinner=False)
def _load_all_references_from_sheets(spreadsheet_id: str) -> dict[str, pd.DataFrame]:
    """Один open таблицы и пакетная загрузка листов — меньше read-запросов к API."""
    spreadsheet = _open_spreadsheet(spreadsheet_id)
    try:
        return _load_references_via_batch_get(spreadsheet)
    except Exception:  # noqa: BLE001
        return _load_references_via_worksheets(spreadsheet)


def _save_to_sheets(spreadsheet_id: str, worksheet_name: str, df: pd.DataFrame) -> None:
    """Запись без предварительного clear — сначала update, затем обрезка хвоста."""
    spreadsheet = _open_spreadsheet(spreadsheet_id)
    worksheet = _sheets_api_with_retry(lambda: spreadsheet.worksheet(worksheet_name))
    plan = _sheet_write_plan(
        worksheet_name,
        df,
        old_row_count=worksheet.row_count,
        old_col_count=worksheet.col_count,
    )
    if plan is None:
        return

    cell_range = plan.range_name.split("!", 1)[-1]

    def _write() -> None:
        worksheet.update(cell_range, plan.values, value_input_option="USER_ENTERED")
        if plan.tail_clear_range:
            tail_cell = plan.tail_clear_range.split("!", 1)[-1]
            worksheet.batch_clear([tail_cell])
        _verify_sheet_row_count(worksheet, plan.n_rows)

    _sheets_api_with_retry(_write)


def _worksheet_has_data(worksheet) -> bool:
    """Проверка «лист пуст» одной ячейкой A1 — без загрузки всего листа."""
    cell = _sheets_api_with_retry(lambda: worksheet.acell("A1").value)
    return bool(str(cell or "").strip())


def _verify_sheet_row_count(worksheet, expected_rows: int) -> None:
    """Сверка числа строк после записи (заголовок + данные)."""
    if expected_rows < 1:
        return
    actual = worksheet.row_count
    if actual < expected_rows:
        raise RuntimeError(
            f"Верификация не прошла: ожидалось ≥{expected_rows} строк, в листе {actual}."
        )


def _append_rows_to_sheets(
    spreadsheet_id: str,
    worksheet_name: str,
    df: pd.DataFrame,
) -> None:
    """Добавляет строки в конец листа, не трогая существующие данные."""
    if df.empty:
        return
    spreadsheet = _open_spreadsheet(spreadsheet_id)
    worksheet = _sheets_api_with_retry(lambda: spreadsheet.worksheet(worksheet_name))

    if not _worksheet_has_data(worksheet):
        _save_to_sheets(spreadsheet_id, worksheet_name, df)
        return

    payload = df.copy().where(pd.notnull(df), "")
    rows: list[list[Any]] = []
    for row in payload.itertuples(index=False, name=None):
        rows.append([_cell_value(v) for v in row])

    def _append() -> None:
        before_rows = worksheet.row_count
        worksheet.append_rows(rows, value_input_option="USER_ENTERED")
        if worksheet.row_count < before_rows + len(rows):
            raise RuntimeError(
                f"Верификация append: ожидалось +{len(rows)} строк, "
                f"было {before_rows}, стало {worksheet.row_count}."
            )

    _sheets_api_with_retry(_append)


def load_all_references(keys: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """Загружает несколько справочников за один проход (кэш / batchGet)."""
    wanted = keys if keys is not None else list(_REFERENCE_META.keys())
    unknown = [k for k in wanted if k not in _REFERENCE_META]
    if unknown:
        raise ValueError(f"Неизвестные справочники: {', '.join(unknown)}")

    if sheets_configured():
        refs = _references_config()
        spreadsheet_id = str(refs["spreadsheet_id"]).strip()
        batch = _load_all_references_from_sheets(spreadsheet_id)
        return {k: batch[k].copy() for k in wanted}

    loaded: dict[str, pd.DataFrame] = {}
    for key in wanted:
        loaded[key] = load_reference(key)
    return loaded


def load_reference(key: str) -> pd.DataFrame:
    """Загружает справочник из Google Sheets или локального xlsx."""
    if key not in _REFERENCE_META:
        raise ValueError(f"Неизвестный справочник: {key}")

    if sheets_configured():
        refs = _references_config()
        spreadsheet_id = str(refs["spreadsheet_id"]).strip()
        batch = _load_all_references_from_sheets(spreadsheet_id)
        if key not in batch:
            _load_all_references_from_sheets.clear()
            batch = _load_all_references_from_sheets(spreadsheet_id)
        if key not in batch:
            raise FileNotFoundError(
                f"Справочник «{get_reference_title(key)}» не найден: {get_reference_label(key)}"
            )
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


def _save_reference_local(key: str, df: pd.DataFrame) -> None:
    local_path = _local_path(key)
    if local_path is None:
        local_names = _REFERENCE_META[key]["local"]
        first = local_names[0] if isinstance(local_names, tuple) else local_names
        local_path = REFERENCE_DIR / first
    local_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(local_path, index=False)


def _save_reference_impl(key: str, df: pd.DataFrame) -> None:
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
        _save_reference_local(key, df)


def save_reference(key: str, df: pd.DataFrame, *, invalidate_cache: bool = True) -> None:
    """Сохраняет справочник в Google Sheets или локальный xlsx."""
    if key not in _REFERENCE_META:
        raise ValueError(f"Неизвестный справочник: {key}")

    _save_reference_impl(key, df)
    if invalidate_cache:
        clear_reference_cache()


def save_references_batch(updates: dict[str, pd.DataFrame]) -> None:
    """Сохраняет несколько справочников; кэш чтения сбрасывается один раз в конце."""
    for key in updates:
        if key not in _REFERENCE_META:
            raise ValueError(f"Неизвестный справочник: {key}")

    saved: list[str] = []
    try:
        if sheets_configured():
            refs = _references_config()
            spreadsheet_id = str(refs["spreadsheet_id"]).strip()
            _save_many_to_sheets(spreadsheet_id, updates)
        else:
            for key, df in updates.items():
                if _is_streamlit_cloud():
                    raise RuntimeError(
                        f"Нельзя сохранить справочник «{get_reference_title(key)}» без Google Sheets. "
                        f"{_secrets_setup_hint()}"
                    )
                _save_reference_local(key, df)
                saved.append(key)
    except Exception as exc:  # noqa: BLE001
        clear_reference_cache()
        if saved:
            raise ReferencesBatchSaveError(saved, key, exc) from exc
        raise
    clear_reference_cache()


def append_reference_rows(key: str, df: pd.DataFrame, *, invalidate_cache: bool = True) -> None:
    """Добавляет строки в конец справочника (без перезаписи всего листа)."""
    if key not in _REFERENCE_META:
        raise ValueError(f"Неизвестный справочник: {key}")
    if df.empty:
        return

    if sheets_configured():
        refs = _references_config()
        spreadsheet_id = str(refs["spreadsheet_id"]).strip()
        _append_rows_to_sheets(spreadsheet_id, _sheet_name(key), df)
    elif _is_streamlit_cloud():
        raise RuntimeError(
            f"Нельзя сохранить справочник «{get_reference_title(key)}» без Google Sheets. "
            f"{_secrets_setup_hint()}"
        )
    else:
        existing = load_reference(key)
        combined = pd.concat([existing, df], ignore_index=True)
        _save_reference_impl(key, combined)

    if invalidate_cache:
        clear_reference_cache()


def clear_reference_cache() -> None:
    _load_all_references_from_sheets.clear()
    try:
        from features.categories import clear_category_maps_cache

        clear_category_maps_cache()
    except ImportError:
        pass
