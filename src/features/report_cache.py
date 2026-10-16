"""Кэш готовых таблиц отчёта в session_state.

Ключ включает версию данных и отпечаток входов. Большие кадры продаж
опознаются по объекту в сессии, небольшие справочники — по содержимому,
чтобы копия с теми же значениями попадала в кэш, а изменение ячеек — нет.
Вне приложения Streamlit кэш не используется.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TypeVar

import pandas as pd

# Совпадает с ui.data_session.DATA_VERSION_KEY; не импортируем data_session (цикл).
_DATA_VERSION_KEY = "data_version"
REPORT_CACHE_STATE_KEY = "report_table_cache"
REPORT_CACHE_VERSION_KEY = "report_table_cache_version"

_T = TypeVar("_T")
# Мелкие справочники хешируем по значениям; продажи остаются по id объекта.
_CONTENT_HASH_CELL_LIMIT = 4000


def frame_token(df: pd.DataFrame | None):
    """Стабильный отпечаток кадра для ключа кэша."""
    if df is None:
        return None
    rows, cols = int(df.shape[0]), int(df.shape[1])
    columns = tuple(str(column) for column in df.columns)
    if rows * max(cols, 1) <= _CONTENT_HASH_CELL_LIMIT:
        try:
            hashed = int(pd.util.hash_pandas_object(df, index=True).sum())
        except Exception:  # noqa: BLE001 — нестандартные ячейки не должны ломать отчёт
            hashed = id(df)
        return ("values", rows, cols, columns, hashed)
    return ("frame", id(df), rows, cols)


def seq_token(values) -> tuple | None:
    """Список или None — в ключ кэша без учёта того, тот ли это объект."""
    if values is None:
        return None
    return tuple(values)


def _copy_cached(value: _T) -> _T:
    """Копия результата, чтобы вызывающий код не менял запись в кэше."""
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, tuple):
        return tuple(_copy_cached(item) for item in value)
    return value


def _cache_dict() -> dict | None:
    """Словарь кэша текущей сессии или None вне Streamlit."""
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import (
            get_script_run_ctx,
        )

        if get_script_run_ctx(suppress_warning=True) is None:
            return None
        import streamlit as st

        version = int(st.session_state.get(_DATA_VERSION_KEY, 0))
        if st.session_state.get(REPORT_CACHE_VERSION_KEY) != version:
            st.session_state[REPORT_CACHE_STATE_KEY] = {}
            st.session_state[REPORT_CACHE_VERSION_KEY] = version
        return st.session_state[REPORT_CACHE_STATE_KEY]
    except Exception:  # noqa: BLE001 — smoke-тесты идут без сессии Streamlit
        return None


def cached_report_value(name: str, identity: tuple, builder: Callable[[], _T]) -> _T:
    """Возвращает результат builder; повтор с тем же ключом не пересчитывает."""
    cache = _cache_dict()
    if cache is None:
        return builder()
    key = (name, identity)
    if key in cache:
        return _copy_cached(cache[key])
    value = builder()
    cache[key] = value
    return _copy_cached(value)


def lookup_report_value(name: str, identity: tuple) -> tuple[bool, object]:
    """(найден, значение). Не запускает расчёт."""
    cache = _cache_dict()
    if cache is None:
        return False, None
    key = (name, identity)
    if key not in cache:
        return False, None
    return True, _copy_cached(cache[key])


def store_report_value(name: str, identity: tuple, value: object) -> None:
    """Кладёт уже посчитанное значение. Вне Streamlit ничего не делает."""
    cache = _cache_dict()
    if cache is None:
        return
    cache[(name, identity)] = value


def cached_report(name: str, key_fn: Callable):
    """Декоратор: ключ из аргументов, тело функции без изменений."""

    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                identity = key_fn(*args, **kwargs)
            except Exception:  # noqa: BLE001
                return fn(*args, **kwargs)
            return cached_report_value(name, identity, lambda: fn(*args, **kwargs))

        return wrapper

    return decorator
