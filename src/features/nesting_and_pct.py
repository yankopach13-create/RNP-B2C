"""Объединённый блок «Вложенность и % без БК»."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config.constants import (
    PCT_NO_BK_COLUMN_GROUPS,
    PCT_NO_BK_COLUMN_SELLERS,
    PCT_NO_BK_COLUMN_SHOPS,
)
from data.references import REF_PCT_NO_BK, get_reference_label
from features.checks_no_bk import (
    COL_PCT_NO_BK,
    _build_shop_group_map,
    _prepare_upload_for_sellers as _prepare_no_bk_upload,
    _resolve_reference_sellers_column,
    build_groups_no_bk_table,
    build_sellers_no_bk_table,
    build_shops_no_bk_table,
)
from features.consumables_nesting import (
    COL_NESTING,
    _prepare_upload_for_sellers as _prepare_nesting_upload,
    build_groups_nesting_table,
    build_sellers_nesting_table,
    build_shops_nesting_table,
    load_pct_no_bk_reference,
)
from features.metrics import (
    FINANCIAL_TABLE_ROW_HEIGHT_PX,
    _financial_dataframe_height,
)
from features.table_layout import (
    STACKED_ORDER_NAME_COL,
    STACKED_ORDER_TABLE_VISIBLE_ROWS,
    merge_named_metric_tables,
    stack_named_metric_tables,
)

_NAME_COL_WIDTH_PX = 200
_VALUE_COL_WIDTH_PX = 90
BLOCK_TITLE = "Вложенность и % без БК"


def build_nesting_and_pct_table(
    reference_df: pd.DataFrame | None = None,
    nesting_upload: pd.DataFrame | None = None,
    no_bk_upload: pd.DataFrame | None = None,
    groups_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Группы, магазины, продавцы: Название, вложенность и % без БК."""
    sections = [
        merge_named_metric_tables(
            build_groups_nesting_table(reference_df, nesting_upload, groups_df),
            build_groups_no_bk_table(reference_df, no_bk_upload, groups_df),
            left_value=COL_NESTING,
            right_value=COL_PCT_NO_BK,
        ),
        merge_named_metric_tables(
            build_shops_nesting_table(reference_df, nesting_upload),
            build_shops_no_bk_table(reference_df, no_bk_upload),
            left_value=COL_NESTING,
            right_value=COL_PCT_NO_BK,
        ),
        merge_named_metric_tables(
            build_sellers_nesting_table(reference_df, nesting_upload),
            build_sellers_no_bk_table(reference_df, no_bk_upload),
            left_value=COL_NESTING,
            right_value=COL_PCT_NO_BK,
        ),
    ]
    return stack_named_metric_tables(
        sections,
        value_column=(COL_NESTING, COL_PCT_NO_BK),
    )


def render_nesting_and_pct_block(
    *,
    nesting_upload: pd.DataFrame | None = None,
    no_bk_upload: pd.DataFrame | None = None,
    groups_df: pd.DataFrame | None = None,
    embedded: bool = False,
) -> None:
    """Одна таблица: название, вложенность расходников и % чеков без БК."""
    try:
        _render_nesting_and_pct_block_impl(
            nesting_upload=nesting_upload,
            no_bk_upload=no_bk_upload,
            groups_df=groups_df,
            embedded=embedded,
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"Ошибка в блоке «{BLOCK_TITLE}».")
        st.exception(exc)


def _render_nesting_and_pct_block_impl(
    *,
    nesting_upload: pd.DataFrame | None,
    no_bk_upload: pd.DataFrame | None,
    groups_df: pd.DataFrame | None,
    embedded: bool,
) -> None:
    if not embedded:
        st.markdown("---")
        st.subheader(BLOCK_TITLE)
    else:
        st.markdown(f"**{BLOCK_TITLE}**")

    if nesting_upload is not None and nesting_upload.empty:
        st.warning("Загруженный файл «Вложенность расходников» не содержит данных.")
        nesting_upload = None
    if no_bk_upload is not None and no_bk_upload.empty:
        st.warning("Загруженный файл «% чеков без БК» не содержит данных.")
        no_bk_upload = None

    reference_df = load_pct_no_bk_reference()
    if reference_df is None:
        st.warning(
            f"Справочник «% без БК» не найден ({get_reference_label(REF_PCT_NO_BK)}). "
            "Таблица будет пустой."
        )
    else:
        reference_df = reference_df.copy()
        reference_df.columns = reference_df.columns.astype(str).str.strip()
        sellers_col = _resolve_reference_sellers_column(reference_df)
        required_cols = [PCT_NO_BK_COLUMN_SHOPS, PCT_NO_BK_COLUMN_GROUPS]
        required_cols.insert(0, sellers_col or PCT_NO_BK_COLUMN_SELLERS)
        missing = [col for col in required_cols if col not in reference_df.columns]
        if missing:
            st.warning(
                "В справочнике «%_bk» отсутствуют столбцы: "
                + ", ".join(f"«{col}»" for col in missing)
                + "."
            )

    if nesting_upload is not None:
        try:
            _prepare_nesting_upload(nesting_upload)
        except ValueError as exc:
            st.error(str(exc))
            nesting_upload = None
    if no_bk_upload is not None:
        try:
            _prepare_no_bk_upload(no_bk_upload)
        except ValueError as exc:
            st.error(str(exc))
            no_bk_upload = None

    if (
        (nesting_upload is not None or no_bk_upload is not None)
        and _build_shop_group_map(groups_df) == {}
    ):
        st.info(
            "Справочник магазинов недоступен — строки групп не будут рассчитаны."
        )

    _render_table(
        build_nesting_and_pct_table(
            reference_df,
            nesting_upload,
            no_bk_upload,
            groups_df,
        )
    )


def _render_table(table: pd.DataFrame) -> None:
    table_height = _financial_dataframe_height(STACKED_ORDER_TABLE_VISIBLE_ROWS)
    kwargs = {
        "use_container_width": True,
        "hide_index": True,
        "height": table_height,
    }
    if table.empty:
        st.dataframe(table, **kwargs)
        return
    st.dataframe(
        table,
        **kwargs,
        row_height=FINANCIAL_TABLE_ROW_HEIGHT_PX,
        column_config={
            STACKED_ORDER_NAME_COL: st.column_config.TextColumn(
                STACKED_ORDER_NAME_COL,
                width=_NAME_COL_WIDTH_PX,
            ),
            COL_NESTING: st.column_config.TextColumn(
                COL_NESTING,
                width=_VALUE_COL_WIDTH_PX,
            ),
            COL_PCT_NO_BK: st.column_config.TextColumn(
                COL_PCT_NO_BK,
                width=_VALUE_COL_WIDTH_PX,
            ),
        },
    )
