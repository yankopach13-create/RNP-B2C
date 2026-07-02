"""Компактная высота st.dataframe на странице (без циклических импортов)."""

from __future__ import annotations

# Высота таблиц на листе: видно 5 строк данных + прокрутка; fullscreen — все строки.
FINANCIAL_TABLE_VISIBLE_ROWS = 5
FINANCIAL_TABLE_ROW_HEIGHT_PX = 35
FINANCIAL_TABLE_HEADER_HEIGHT_PX = 38
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
