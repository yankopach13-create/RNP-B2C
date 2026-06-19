"""Блок «Кальянная продукция» в РНП B2C."""

from __future__ import annotations

import pandas as pd
import streamlit as st

COL_METRIC = "Метрика"
COL_VALUE = "Значение"
HOOKAH_TABLE_ROW_HEIGHT_PX = 35
HOOKAH_METRIC_COL_WIDTH_PX = 210
HOOKAH_VALUE_COL_WIDTH_PX = 68

_HOOKAH_METRIC_ROWS: tuple[str | None, ...] = (
    "1.1 Бестабачная Смесь",
    "1.2 Уголь для кальяна",
    "1.3 Аксессуары для Кальяна",
    "1.4 Кальяны",
    "1.5 Табачная Смесь",
    None,
    "Кол-во чеков всей категории",
    "Кол-во чеков с кулером",
    "Кол-во чеков с углём",
    None,
    "% чеков с кулером",
    "% чеков с углём",
    "Вложенность",
    "АКБ всей категории",
    None,
    None,
    None,
    "Восток",
    "Юг",
    "Север",
    "Запад",
    "Норд-Вест",
    "Центр",
    "Минская область",
    "Гомель",
    "Витебская область",
    "Могилёв",
    "Брест",
    "Гродно",
)


def build_hookah_products_table() -> pd.DataFrame:
    """Таблица метрик кальянной продукции; значения заполняются позже."""
    rows = [
        [label or "", ""]
        for label in _HOOKAH_METRIC_ROWS
    ]
    return pd.DataFrame(rows, columns=[COL_METRIC, COL_VALUE])


def render_hookah_products_block(*, embedded: bool = False) -> None:
    """Метрики слева, значения справа (пока пустые)."""
    if not embedded:
        st.markdown("---")
        st.subheader("Кальянная продукция")
    else:
        st.markdown("**Кальянная продукция**")

    table = build_hookah_products_table()
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        row_height=HOOKAH_TABLE_ROW_HEIGHT_PX,
        column_config={
            COL_METRIC: st.column_config.TextColumn(
                COL_METRIC, width=HOOKAH_METRIC_COL_WIDTH_PX
            ),
            COL_VALUE: st.column_config.TextColumn(
                COL_VALUE, width=HOOKAH_VALUE_COL_WIDTH_PX
            ),
        },
    )
