"""Компактная высота st.dataframe на странице (без циклических импортов)."""

from __future__ import annotations

import pandas as pd

# Высота таблиц на листе: видно 5 строк данных + прокрутка; fullscreen — все строки.
FINANCIAL_TABLE_VISIBLE_ROWS = 5
FINANCIAL_TABLE_ROW_HEIGHT_PX = 35
FINANCIAL_TABLE_HEADER_HEIGHT_PX = 38
STACKED_ORDER_TABLE_VISIBLE_ROWS = 10
STACKED_ORDER_NAME_COL = "Название"
# Панель st.dataframe (кнопка fullscreen и т.п.) — не входит в параметр height.
FINANCIAL_TABLE_TOOLBAR_HEIGHT_PX = 48
RNP_COMPACT_TABLE_KEY_PREFIX = "rnp_compact_"


def compact_dataframe_height(
    visible_rows: int = FINANCIAL_TABLE_VISIBLE_ROWS,
) -> int:
    """Компактная высота таблицы на странице (без полноэкранного режима)."""
    return FINANCIAL_TABLE_HEADER_HEIGHT_PX + visible_rows * FINANCIAL_TABLE_ROW_HEIGHT_PX


def compact_dataframe_kwargs(**extra) -> dict:
    """Общие параметры st.dataframe: компактно на листе, полный список в fullscreen."""
    kwargs = {
        "use_container_width": True,
        "hide_index": True,
        "height": compact_dataframe_height(),
        "row_height": FINANCIAL_TABLE_ROW_HEIGHT_PX,
    }
    kwargs.update(extra)
    return kwargs


def stack_named_metric_tables(
    tables: list[pd.DataFrame],
    *,
    value_column: str,
    name_column: str = STACKED_ORDER_NAME_COL,
) -> pd.DataFrame:
    """Склеить секции в одну таблицу, разделяя пустой строкой."""
    frames: list[pd.DataFrame] = []
    blank = pd.DataFrame({name_column: [""], value_column: [""]})
    for table in tables:
        if table is None or table.empty:
            continue
        first_col = str(table.columns[0])
        chunk = table.rename(columns={first_col: name_column})
        if value_column not in chunk.columns:
            continue
        chunk = chunk[[name_column, value_column]].copy()
        chunk[name_column] = chunk[name_column].fillna("").astype(str)
        chunk[value_column] = chunk[value_column].fillna("").astype(str)
        if frames:
            frames.append(blank)
        frames.append(chunk.reset_index(drop=True))
    if not frames:
        return pd.DataFrame(columns=[name_column, value_column])
    return pd.concat(frames, ignore_index=True)


def compact_dataframe_layout_css() -> str:
    """CSS: резерв высоты блока, чтобы таблицы не наслаивались (без обрезки UI)."""
    grid_height_px = compact_dataframe_height()
    block_height_px = grid_height_px + FINANCIAL_TABLE_TOOLBAR_HEIGHT_PX
    prefix = RNP_COMPACT_TABLE_KEY_PREFIX
    return f"""
    [class*="{prefix}"] {{
        display: flow-root;
        min-height: {block_height_px}px;
        margin-bottom: 0.65rem;
    }}
    """
