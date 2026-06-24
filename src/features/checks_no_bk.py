"""Блок «% чеков без БК»: продавцы, магазины, группы."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config.constants import (
    PCT_NO_BK_COLUMN_GROUPS,
    PCT_NO_BK_COLUMN_SELLERS,
    PCT_NO_BK_COLUMN_SHOPS,
)
from data.loaders import _read_excel
from data.references import REF_PCT_NO_BK, get_reference_label, load_reference

COL_PCT_NO_BK = "% без БК"
COL_SELLER = "Продавец"
COL_SHOP = "Магазин"
COL_GROUP = "Группа"

_TABLE_ROW_HEIGHT_PX = 35
_NAME_COL_WIDTH_PX = 210
_VALUE_COL_WIDTH_PX = 90

_XLSX_TYPES = ["xlsx", "xls"]
_SESSION_FILE_KEY = "checks_no_bk_uploaded_file"


def _column_names_from_reference(df: pd.DataFrame, column: str) -> list[str]:
    names: list[str] = []
    for val in df[column]:
        if pd.isna(val):
            continue
        name = str(val).strip()
        if name and name.lower() not in ("nan", "none"):
            names.append(name)
    return names


def _build_order_table(
    reference_df: pd.DataFrame | None,
    order_column: str,
    name_column: str,
) -> pd.DataFrame:
    """Таблица: список из справочника + пустой столбец «% без БК»."""
    if reference_df is None or reference_df.empty:
        return pd.DataFrame(columns=[name_column, COL_PCT_NO_BK])

    df = reference_df.copy()
    df.columns = df.columns.astype(str).str.strip()
    if order_column not in df.columns:
        return pd.DataFrame(columns=[name_column, COL_PCT_NO_BK])

    names = _column_names_from_reference(df, order_column)
    if not names:
        return pd.DataFrame(columns=[name_column, COL_PCT_NO_BK])

    return pd.DataFrame(
        {name_column: names, COL_PCT_NO_BK: [""] * len(names)},
    )


def build_sellers_no_bk_table(
    reference_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    return _build_order_table(reference_df, PCT_NO_BK_COLUMN_SELLERS, COL_SELLER)


def build_shops_no_bk_table(
    reference_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    return _build_order_table(reference_df, PCT_NO_BK_COLUMN_SHOPS, COL_SHOP)


def build_groups_no_bk_table(
    reference_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    return _build_order_table(reference_df, PCT_NO_BK_COLUMN_GROUPS, COL_GROUP)


def _load_pct_no_bk_reference() -> pd.DataFrame | None:
    try:
        return load_reference(REF_PCT_NO_BK)
    except FileNotFoundError:
        st.warning(
            f"Справочник «% без БК» не найден ({get_reference_label(REF_PCT_NO_BK)}). "
            "Таблицы будут пустыми."
        )
        return None
    except Exception as exc:  # noqa: BLE001
        st.error(f"Не удалось загрузить справочник «% без БК»: {exc}")
        return None


def _read_checks_no_bk_upload(file: object) -> pd.DataFrame | None:
    if file is None:
        return None
    try:
        return _read_excel(file, label="Файл % без БК")
    except ValueError as exc:
        st.error(str(exc))
        return None


def _render_order_table(
    table: pd.DataFrame,
    *,
    name_column: str,
) -> None:
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        row_height=_TABLE_ROW_HEIGHT_PX,
        column_config={
            name_column: st.column_config.TextColumn(
                name_column,
                width=_NAME_COL_WIDTH_PX,
            ),
            COL_PCT_NO_BK: st.column_config.TextColumn(
                COL_PCT_NO_BK,
                width=_VALUE_COL_WIDTH_PX,
            ),
        },
    )


def render_checks_no_bk_block() -> None:
    """Загрузчик Excel и три таблицы (продавцы, магазины, группы) из справочника %_bk."""
    st.markdown("---")

    uploaded = st.file_uploader(
        "Файл % без БК",
        type=_XLSX_TYPES,
        key="checks_no_bk_uploader",
        help="Загрузите отчёт из Qlik в формате Excel (.xlsx).",
    )
    if uploaded is not None:
        st.session_state[_SESSION_FILE_KEY] = uploaded
        df = _read_checks_no_bk_upload(uploaded)
        if df is not None and not df.empty:
            st.caption(f"Файл загружен: {uploaded.name} ({len(df)} строк).")

    reference_df = _load_pct_no_bk_reference()
    if reference_df is not None:
        reference_df = reference_df.copy()
        reference_df.columns = reference_df.columns.astype(str).str.strip()
        missing = [
            col
            for col in (
                PCT_NO_BK_COLUMN_SELLERS,
                PCT_NO_BK_COLUMN_SHOPS,
                PCT_NO_BK_COLUMN_GROUPS,
            )
            if col not in reference_df.columns
        ]
        if missing:
            st.warning(
                "В справочнике «%_bk» отсутствуют столбцы: "
                + ", ".join(f"«{c}»" for c in missing)
                + "."
            )

    col_sellers, col_shops, col_groups = st.columns([1, 1, 1])

    with col_sellers:
        st.markdown("**Продавцы**")
        _render_order_table(
            build_sellers_no_bk_table(reference_df),
            name_column=COL_SELLER,
        )

    with col_shops:
        st.markdown("**Магазины**")
        _render_order_table(
            build_shops_no_bk_table(reference_df),
            name_column=COL_SHOP,
        )

    with col_groups:
        st.markdown("**Группы**")
        _render_order_table(
            build_groups_no_bk_table(reference_df),
            name_column=COL_GROUP,
        )
