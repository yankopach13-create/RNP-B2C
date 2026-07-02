"""Блок «Fill free» в РНП B2C — уникальные клиенты по B2C и группам."""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from features.clients import _has_client_code
from features.hookah_products import (
    FOCUS_TABLE_VISIBLE_ROWS,
    HOOKAH_GROUP_LABELS,
    HOOKAH_GROUP_LABEL_TO_REF,
)
from features.metrics import (
    FINANCIAL_TABLE_ROW_HEIGHT_PX,
    _financial_dataframe_height,
)

COL_GROUP = "Группа"
COL_CUMULATIVE = "Накопительно"
COL_YEAR_WEEK = "Год-Неделя"
COL_SHOP = "Магазин"
COL_WEEK = "Неделя"
COL_CLIENTS = "Клиентов"
COL_CLIENT = "Код клиента"

ROW_B2C = "Весь B2C"

_FILL_FREE_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    COL_YEAR_WEEK: (COL_YEAR_WEEK, "год-неделя", "Год неделя"),
    COL_SHOP: (COL_SHOP, "магазин"),
    COL_WEEK: (COL_WEEK, "неделя"),
    COL_CLIENTS: (COL_CLIENTS, "клиентов", "Клиенты"),
    COL_CLIENT: (COL_CLIENT, "код-клиента", "код клиента", "Код-клиента"),
}

_FILL_FREE_COLUMNS_BY_POSITION: tuple[str, ...] = (
    COL_YEAR_WEEK,
    COL_SHOP,
    COL_WEEK,
    COL_CLIENTS,
    COL_CLIENT,
)


def build_fill_free_table(
    focus_fill_free: pd.DataFrame | None = None,
    groups_df: pd.DataFrame | None = None,
    report_week: int | None = None,
) -> tuple[pd.DataFrame | None, list[str]]:
    """Таблица уникальных клиентов: B2C и группы (как в кальянной продукции)."""
    prepared, warnings = _prepare_fill_free(focus_fill_free)
    if prepared is None or prepared.empty:
        return None, warnings

    if report_week is None:
        report_week = int(prepared[COL_WEEK].max())

    week_label = f"Неделя {report_week}"
    week_df = prepared.loc[prepared[COL_WEEK] == report_week].copy()

    shop_group_map = _build_shop_group_map(groups_df)
    prepared = prepared.copy()
    prepared["_group"] = (
        prepared[COL_SHOP].map(_normalize_shop_key).map(shop_group_map)
    )
    week_df["_group"] = (
        week_df[COL_SHOP].map(_normalize_shop_key).map(shop_group_map)
    )

    rows: list[dict[str, str]] = [
        _fill_free_row(ROW_B2C, prepared, week_df, week_label),
    ]
    for group_label in HOOKAH_GROUP_LABELS:
        ref_group = HOOKAH_GROUP_LABEL_TO_REF.get(group_label, group_label)
        group_key = _normalize_label(ref_group)
        group_all = prepared.loc[
            prepared["_group"].map(_normalize_label) == group_key
        ]
        group_week = week_df.loc[
            week_df["_group"].map(_normalize_label) == group_key
        ]
        rows.append(_fill_free_row(group_label, group_all, group_week, week_label))

    return pd.DataFrame(rows, columns=[COL_GROUP, COL_CUMULATIVE, week_label]), warnings


def render_fill_free_products_block(
    *,
    focus_fill_free: pd.DataFrame | None = None,
    groups_df: pd.DataFrame | None = None,
    report_week: int | None = None,
    embedded: bool = False,
) -> None:
    """Уникальные клиенты по B2C и группам магазинов."""
    if not embedded:
        st.markdown("---")
        st.subheader("Fill free")
    else:
        st.markdown("**Fill free**")

    table, warnings = build_fill_free_table(
        focus_fill_free,
        groups_df,
        report_week,
    )
    for message in warnings:
        st.warning(message)

    if table is None:
        st.info("Загрузите файл Fill free.")
        return

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        height=_financial_dataframe_height(FOCUS_TABLE_VISIBLE_ROWS),
        row_height=FINANCIAL_TABLE_ROW_HEIGHT_PX,
    )


def _fill_free_row(
    label: str,
    cumulative_df: pd.DataFrame,
    week_df: pd.DataFrame,
    week_label: str,
) -> dict[str, str]:
    return {
        COL_GROUP: label,
        COL_CUMULATIVE: _fmt_unique_clients(cumulative_df),
        week_label: _fmt_unique_clients(week_df),
    }


def _prepare_fill_free(
    raw: pd.DataFrame | None,
) -> tuple[pd.DataFrame | None, list[str]]:
    if raw is None or raw.empty:
        return None, []

    try:
        df = _resolve_fill_free_columns(raw)
    except ValueError as exc:
        return None, [str(exc)]

    df[COL_WEEK] = pd.to_numeric(df[COL_WEEK], errors="coerce")
    df = df.dropna(subset=[COL_WEEK])
    if df.empty:
        return None, ["В файле Fill free нет строк с корректной «Неделей»."]

    df[COL_WEEK] = df[COL_WEEK].astype(int)
    df[COL_SHOP] = df[COL_SHOP].astype(str).str.strip()
    df = df.loc[df[COL_SHOP].ne("")]
    if df.empty:
        return None, ["В файле Fill free нет строк с магазинами."]

    return df, []


def _resolve_fill_free_columns(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df.columns = df.columns.astype(str).str.strip()

    if len(df.columns) >= len(_FILL_FREE_COLUMNS_BY_POSITION):
        try:
            return _resolve_columns(df, _FILL_FREE_COLUMN_ALIASES)
        except ValueError:
            renamed = df.iloc[:, : len(_FILL_FREE_COLUMNS_BY_POSITION)].copy()
            renamed.columns = list(_FILL_FREE_COLUMNS_BY_POSITION)
            return renamed

    return _resolve_columns(df, _FILL_FREE_COLUMN_ALIASES)


def _resolve_columns(
    raw: pd.DataFrame,
    aliases: dict[str, tuple[str, ...]],
) -> pd.DataFrame:
    df = raw.copy()
    df.columns = df.columns.astype(str).str.strip()
    lower_map = {str(c).strip().casefold(): c for c in df.columns}
    resolved: dict[str, str] = {}
    for canonical, names in aliases.items():
        found = None
        for alias in names:
            key = alias.casefold()
            if key in lower_map:
                found = lower_map[key]
                break
        if found is None:
            raise ValueError(f"Отсутствует столбец «{canonical}»")
        resolved[canonical] = found

    keep = [resolved[c] for c in aliases]
    df = df[keep].copy()
    rename = {src: dst for dst, src in resolved.items() if src != dst}
    if rename:
        df = df.rename(columns=rename)
    return df


def _unique_clients_count(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    mask = _has_client_code(df[COL_CLIENT])
    codes = df.loc[mask, COL_CLIENT]
    if codes.empty:
        return 0
    return int(codes.nunique())


def _fmt_unique_clients(df: pd.DataFrame) -> str:
    count = _unique_clients_count(df)
    if count <= 0:
        return ""
    return _fmt_int(count)


def _build_shop_group_map(groups_df: pd.DataFrame | None) -> dict[str, str]:
    if groups_df is None or groups_df.empty:
        return {}
    if COL_SHOP not in groups_df.columns or "Группа" not in groups_df.columns:
        return {}
    mapping: dict[str, str] = {}
    for _, row in groups_df.iterrows():
        shop = str(row[COL_SHOP]).strip()
        group = str(row["Группа"]).strip()
        if shop:
            mapping[_normalize_shop_key(shop)] = group
    return mapping


def _normalize_label(value: object) -> str:
    text = str(value or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip().casefold()


def _normalize_shop_key(value: object) -> str:
    return _normalize_label(value)


def _fmt_int(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")
