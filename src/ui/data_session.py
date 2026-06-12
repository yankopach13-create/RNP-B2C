"""Кэш данных и отчётов в session_state (меньше повторных read_excel и сборки Excel)."""

from __future__ import annotations

import streamlit as st

from data.loaders import AppData, load_all_data
from features.data_prep import PreparedSalesResult, filter_sales_by_report_week, prepare_sales_dataset
from features.excise_liquid import WeekCalculationConfig
from features.excel_export import build_rnp_b2c_excel_bytes
from features.metrics import _build_turnover_summary
from ui.upload_panel import UploadedFiles

RELOAD_REQUESTED_KEY = "data_reload_requested"
DATA_VERSION_KEY = "data_version"
APP_DATA_KEY = "app_data"
PREPARED_KEY = "prepared"
EXCEL_CACHE_KEY = "excel_cache"
DF_REPORT_CACHE_KEY = "df_report_cache"
DF_REPORT_CACHE_VERSION_KEY = "df_report_cache_version"
TURNOVER_TABLE_KEY = "turnover_table"
TURNOVER_CACHE_VERSION_KEY = "turnover_cache_version"


def _bump_data_version() -> int:
    version = int(st.session_state.get(DATA_VERSION_KEY, 0)) + 1
    st.session_state[DATA_VERSION_KEY] = version
    return version


def _clear_derived_caches() -> None:
    st.session_state[EXCEL_CACHE_KEY] = {}
    st.session_state[DF_REPORT_CACHE_KEY] = {}
    st.session_state.pop(TURNOVER_TABLE_KEY, None)
    st.session_state.pop(TURNOVER_CACHE_VERSION_KEY, None)


def load_and_store_app_data(files: UploadedFiles) -> tuple[AppData, PreparedSalesResult | None]:
    """Читает Excel и подготавливает продажи; сбрасывает производные кэши."""
    data = load_all_data(files)
    prepared = None
    if data.sales is not None and data.groups is not None:
        prepared = prepare_sales_dataset(data)

    _bump_data_version()
    _clear_derived_caches()
    st.session_state[APP_DATA_KEY] = data
    st.session_state[PREPARED_KEY] = prepared
    _warm_turnover_cache(data)
    return data, prepared


def get_stored_app_data() -> AppData | None:
    return st.session_state.get(APP_DATA_KEY)


def get_stored_prepared() -> PreparedSalesResult | None:
    return st.session_state.get(PREPARED_KEY)


def should_reload_data() -> bool:
    if st.session_state.pop(RELOAD_REQUESTED_KEY, False):
        return True
    return get_stored_app_data() is None


def excel_cache_key(
    week_config: WeekCalculationConfig | None,
    data_version: int,
) -> tuple:
    if week_config is None:
        return (data_version, None, None, 0.0, 0.0)
    return (
        data_version,
        week_config.lfl_week,
        week_config.report_week,
        week_config.excise_liquid_lfl,
        week_config.excise_liquid_report,
    )


def get_cached_excel_bytes(
    data: AppData,
    prepared: PreparedSalesResult | None,
    week_config: WeekCalculationConfig | None,
) -> bytes | None:
    """Сборка xlsx только при новой комбинации настроек (недели + акциз + версия данных)."""
    version = int(st.session_state.get(DATA_VERSION_KEY, 0))
    key = excel_cache_key(week_config, version)
    cache: dict = st.session_state.setdefault(EXCEL_CACHE_KEY, {})
    if key in cache:
        return cache[key]
    with st.spinner("Формируем Excel…"):
        cache[key] = build_rnp_b2c_excel_bytes(data, prepared, week_config)
    return cache[key]


def get_df_report_cached(
    df,
    week_config: WeekCalculationConfig | None,
):
    """Фильтр продаж по отчётной неделе с кэшем по номеру недели."""
    if df is None:
        return None
    if week_config is None:
        return df

    report_week = int(week_config.report_week)
    version = int(st.session_state.get(DATA_VERSION_KEY, 0))
    if st.session_state.get(DF_REPORT_CACHE_VERSION_KEY) != version:
        st.session_state[DF_REPORT_CACHE_KEY] = {}
        st.session_state[DF_REPORT_CACHE_VERSION_KEY] = version

    cache: dict = st.session_state.setdefault(DF_REPORT_CACHE_KEY, {})
    if report_week in cache:
        return cache[report_week]

    filtered = filter_sales_by_report_week(df, report_week)
    cache[report_week] = filtered
    return filtered


def get_cached_turnover_table(data: AppData):
    """Оборачиваемость 7/90 дней — не зависит от недель продаж, кэш на версию данных."""
    version = int(st.session_state.get(DATA_VERSION_KEY, 0))
    if (
        st.session_state.get(TURNOVER_CACHE_VERSION_KEY) == version
        and TURNOVER_TABLE_KEY in st.session_state
    ):
        return st.session_state[TURNOVER_TABLE_KEY]
    return _warm_turnover_cache(data)


def _warm_turnover_cache(data: AppData):
    version = int(st.session_state.get(DATA_VERSION_KEY, 0))
    table = _build_turnover_summary(
        data.turnover_90,
        data.turnover_week,
        data.categories,
        data.category_order_rnp,
    )
    st.session_state[TURNOVER_TABLE_KEY] = table
    st.session_state[TURNOVER_CACHE_VERSION_KEY] = version
    return table
