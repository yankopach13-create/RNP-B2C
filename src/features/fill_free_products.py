"""Блок «Fill free» в РНП B2C."""

from __future__ import annotations

import pandas as pd
import streamlit as st

FILL_FREE_TABLE_ROW_HEIGHT_PX = 35


def render_fill_free_products_block(
    *,
    focus_fill_free: pd.DataFrame | None = None,
    embedded: bool = False,
) -> None:
    """Отображает загруженные данные Fill free."""
    if not embedded:
        st.markdown("---")
        st.subheader("Fill free")
    else:
        st.markdown("**Fill free**")

    if focus_fill_free is None or focus_fill_free.empty:
        st.info("Загрузите файл Fill free.")
        return

    table = focus_fill_free.copy()
    table.columns = table.columns.astype(str).str.strip()
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        row_height=FILL_FREE_TABLE_ROW_HEIGHT_PX,
    )
