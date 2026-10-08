"""Компактная высота st.dataframe на странице (без циклических импортов)."""

from __future__ import annotations

import html

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
    value_column: str | tuple[str, ...] | list[str],
    name_column: str = STACKED_ORDER_NAME_COL,
) -> pd.DataFrame:
    """Склеить секции в одну таблицу, разделяя пустой строкой."""
    value_columns = (
        (value_column,) if isinstance(value_column, str) else tuple(value_column)
    )
    frames: list[pd.DataFrame] = []
    blank = pd.DataFrame(
        {name_column: [""], **{column: [""] for column in value_columns}}
    )
    for table in tables:
        if table is None or table.empty:
            continue
        first_col = str(table.columns[0])
        chunk = table.rename(columns={first_col: name_column})
        missing = [column for column in value_columns if column not in chunk.columns]
        if missing:
            continue
        chunk = chunk[[name_column, *value_columns]].copy()
        chunk[name_column] = chunk[name_column].fillna("").astype(str)
        for column in value_columns:
            chunk[column] = chunk[column].fillna("").astype(str)
        if frames:
            frames.append(blank)
        frames.append(chunk.reset_index(drop=True))
    if not frames:
        return pd.DataFrame(columns=[name_column, *value_columns])
    return pd.concat(frames, ignore_index=True)


def merge_named_metric_tables(
    left: pd.DataFrame | None,
    right: pd.DataFrame | None,
    *,
    left_value: str,
    right_value: str,
    name_column: str = STACKED_ORDER_NAME_COL,
) -> pd.DataFrame:
    """Свести две таблицы порядка в Название + два показателя."""

    def _prep(table: pd.DataFrame | None, value: str) -> pd.DataFrame:
        if table is None or table.empty:
            return pd.DataFrame(columns=[name_column, value])
        first_col = str(table.columns[0])
        chunk = table.rename(columns={first_col: name_column})
        if value not in chunk.columns:
            chunk[value] = ""
        out = chunk[[name_column, value]].copy()
        out[name_column] = out[name_column].fillna("").astype(str)
        out[value] = out[value].fillna("").astype(str)
        return out.reset_index(drop=True)

    left_df = _prep(left, left_value)
    right_df = _prep(right, right_value)
    empty = pd.DataFrame(columns=[name_column, left_value, right_value])
    if left_df.empty and right_df.empty:
        return empty
    if left_df.empty:
        right_df[left_value] = ""
        return right_df[[name_column, left_value, right_value]]
    if right_df.empty:
        left_df[right_value] = ""
        return left_df[[name_column, left_value, right_value]]
    if (
        len(left_df) == len(right_df)
        and left_df[name_column].tolist() == right_df[name_column].tolist()
    ):
        out = left_df.copy()
        out[right_value] = right_df[right_value].to_numpy()
        return out[[name_column, left_value, right_value]]

    right_map = dict(zip(right_df[name_column], right_df[right_value]))
    out = left_df.copy()
    out[right_value] = out[name_column].map(lambda name: right_map.get(name, ""))
    used = set(out[name_column].tolist())
    extra = right_df.loc[~right_df[name_column].isin(used)].copy()
    if not extra.empty:
        extra[left_value] = ""
        out = pd.concat(
            [out, extra[[name_column, left_value, right_value]]],
            ignore_index=True,
        )
    return out[[name_column, left_value, right_value]]


def fixed_width_table_html(
    table: pd.DataFrame,
    column_widths: dict[str, str],
    *,
    right_aligned: set[str] | frozenset[str] | None = None,
    visible_rows: int = STACKED_ORDER_TABLE_VISIBLE_ROWS,
    row_height_px: int = FINANCIAL_TABLE_ROW_HEIGHT_PX,
    header_height_px: int = FINANCIAL_TABLE_HEADER_HEIGHT_PX,
) -> str:
    """HTML-таблица с table-layout:fixed — ширины колонок не зависят от текста."""
    right_aligned = set(right_aligned or ())
    max_height = header_height_px + max(int(visible_rows), 1) * row_height_px
    columns = [str(col) for col in table.columns]
    colgroup = "".join(
        f'<col style="width:{html.escape(column_widths.get(col, "auto"), quote=True)}">'
        for col in columns
    )
    header_cells = []
    for col in columns:
        align = "right" if col in right_aligned else "left"
        header_cells.append(
            f'<th style="text-align:{align}">{html.escape(col)}</th>'
        )
    body_rows = []
    for row in table.itertuples(index=False, name=None):
        cells = []
        for col, value in zip(columns, row):
            align = "right" if col in right_aligned else "left"
            text = "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value)
            cells.append(
                f'<td style="text-align:{align}" title="{html.escape(text, quote=True)}">'
                f"{html.escape(text)}</td>"
            )
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    if not body_rows:
        body_rows.append(
            f'<tr><td colspan="{len(columns)}" style="text-align:center;opacity:0.65">Нет данных</td></tr>'
        )
    return f"""
<div class="rnp-fixed-table" style="max-height:{max_height}px">
<style>
.rnp-fixed-table {{
  overflow: auto;
  width: 100%;
  border: 1px solid rgba(128, 128, 128, 0.35);
  border-radius: 8px;
  background: transparent;
  user-select: text !important;
  -webkit-user-select: text !important;
  -moz-user-select: text !important;
}}
.rnp-fixed-table,
.rnp-fixed-table table,
.rnp-fixed-table th,
.rnp-fixed-table td {{
  user-select: text !important;
  -webkit-user-select: text !important;
  -moz-user-select: text !important;
}}
.rnp-fixed-table table {{
  table-layout: fixed;
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}}
.rnp-fixed-table th,
.rnp-fixed-table td {{
  padding: 6px 8px;
  border-bottom: 1px solid rgba(128, 128, 128, 0.22);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.25;
  height: {row_height_px}px;
  cursor: text;
}}
.rnp-fixed-table th {{
  position: sticky;
  top: 0;
  z-index: 1;
  font-weight: 600;
  white-space: normal;
  height: auto;
  min-height: {header_height_px}px;
  background: var(--secondary-background-color, rgba(128, 128, 128, 0.18));
}}
</style>
<table>
<colgroup>{colgroup}</colgroup>
<thead><tr>{"".join(header_cells)}</tr></thead>
<tbody>{"".join(body_rows)}</tbody>
</table>
</div>
"""


def render_fixed_width_table(
    table: pd.DataFrame,
    column_widths: dict[str, str],
    *,
    right_aligned: set[str] | frozenset[str] | None = None,
    visible_rows: int = STACKED_ORDER_TABLE_VISIBLE_ROWS,
    row_height_px: int = FINANCIAL_TABLE_ROW_HEIGHT_PX,
    header_height_px: int = FINANCIAL_TABLE_HEADER_HEIGHT_PX,
) -> None:
    """Показать таблицу с фиксированными колонками; текст в ячейках можно выделять и копировать."""
    import streamlit as st

    markup = fixed_width_table_html(
        table,
        column_widths,
        right_aligned=right_aligned,
        visible_rows=visible_rows,
        row_height_px=row_height_px,
        header_height_px=header_height_px,
    )
    # st.html не оборачивает разметку в markdown-контейнер, где Streamlit глушит выделение.
    html_fn = getattr(st, "html", None)
    if callable(html_fn):
        html_fn(markup)
        return
    st.markdown(
        "<style>"
        '[data-testid="stMarkdownContainer"] .rnp-fixed-table,'
        '[data-testid="stMarkdownContainer"] .rnp-fixed-table * {'
        "user-select:text !important;-webkit-user-select:text !important;"
        "}</style>"
        + markup,
        unsafe_allow_html=True,
    )


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
