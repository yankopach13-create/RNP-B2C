"""Блок «Мастер файл»: магазин, месяц, неделя и категория Мастер."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from features.categories import (
    NO_MASTER_CATEGORY,
    apply_category_reference,
    master_category_by_product,
)
from features.data_prep import safe_int_week
from features.excise_liquid import CATEGORY_LIQUID_25ML, WeekCalculationConfig
from features.liquid_margin import recalculate_liquid_margins

COL_SHOP = "Магазин"
COL_MONTH = "Месяц"
COL_WEEK = "Неделя"
COL_REVENUE = "Выручка"
COL_MARGIN = "Маржа"
COL_QTY = "Количество"
COL_CATEGORY = "Категория"
COL_U2 = "Товар ур.2"
COL_U4 = "Товар ур.4"
COL_SALES_REVENUE = "Продажи с НДС"
COL_SALES_CATEGORY = "Категория"

TABLE_COLUMNS = [
    COL_SHOP,
    COL_MONTH,
    COL_WEEK,
    COL_REVENUE,
    COL_MARGIN,
    COL_QTY,
    COL_CATEGORY,
]


def _norm_key(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return " ".join(str(value).replace("\xa0", " ").split()).casefold()


def _month_label(value) -> str:
    """Месяц для группировки: число, дата Excel или текст как в файле."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime("%m.%Y")
    number = pd.to_numeric(value, errors="coerce")
    if pd.notna(number) and float(number).is_integer():
        return str(int(number))
    return " ".join(str(value).replace("\xa0", " ").split())


def _fmt_money(value: float) -> str:
    return f"{float(value):,.2f}".replace(",", " ").replace(".", ",")


def _fmt_qty(value: float) -> str:
    number = float(value)
    if number.is_integer():
        return f"{int(number):,}".replace(",", " ")
    return f"{number:.2f}".replace(".", ",")


def liquid_product_keys(sales_df: pd.DataFrame | None) -> set[tuple[str, str]]:
    """Пары (товар ур.2, товар ур.4), у которых категория РНП — «Жидкость 25 мл»."""
    if sales_df is None or sales_df.empty:
        return set()
    if COL_SALES_CATEGORY not in sales_df.columns:
        return set()
    if COL_U2 not in sales_df.columns or COL_U4 not in sales_df.columns:
        return set()
    mask = sales_df[COL_SALES_CATEGORY].astype(str).str.strip() == CATEGORY_LIQUID_25ML
    keys: set[tuple[str, str]] = set()
    for u2, u4 in zip(
        sales_df.loc[mask, COL_U2].tolist(),
        sales_df.loc[mask, COL_U4].tolist(),
    ):
        left, right = _norm_key(u2), _norm_key(u4)
        if left and right:
            keys.add((left, right))
    return keys


def _sales_with_rnp_category(
    sales_df: pd.DataFrame | None,
    categories_df: pd.DataFrame | None,
) -> pd.DataFrame | None:
    if sales_df is None or sales_df.empty:
        return None
    if COL_SALES_CATEGORY in sales_df.columns:
        return sales_df
    if categories_df is None or categories_df.empty:
        return sales_df
    return apply_category_reference(sales_df, categories_df)


def resolve_master_week(
    master_df: pd.DataFrame,
    report_week: int | None,
) -> int | None:
    """Отчётная неделя. Без выбора в интерфейсе — единственная или последняя неделя файла."""
    if report_week is not None:
        return int(report_week)
    weeks = sorted(
        {
            week
            for week in (safe_int_week(value) for value in master_df[COL_WEEK].tolist())
            if week is not None
        }
    )
    if not weeks:
        return None
    return weeks[-1]


def _apply_liquid_margins(
    grouped: pd.DataFrame,
    liquid_keys: set[tuple[str, str]],
    cost_df: pd.DataFrame | None,
    excise_lfl: pd.DataFrame | None,
    excise_report: pd.DataFrame | None,
    *,
    lfl_week: int | None,
    report_week: int | None,
    excise_from_sales_skus: frozenset[str] | None,
) -> pd.DataFrame:
    """Правит маржу жидкости на строке магазин + SKU, чтобы себестоимость не задвоилась."""
    if grouped.empty or not liquid_keys:
        return grouped
    frame = grouped.copy()
    frame[COL_SALES_CATEGORY] = [
        CATEGORY_LIQUID_25ML
        if (_norm_key(u2), _norm_key(u4)) in liquid_keys
        else ""
        for u2, u4 in zip(frame[COL_U2].tolist(), frame[COL_U4].tolist())
    ]
    if not (frame[COL_SALES_CATEGORY] == CATEGORY_LIQUID_25ML).any():
        return grouped
    adjusted = recalculate_liquid_margins(
        frame,
        cost_df,
        excise_lfl,
        excise_report,
        lfl_week=lfl_week,
        report_week=report_week,
        excise_from_sales_skus=excise_from_sales_skus,
    )
    grouped = grouped.copy()
    grouped[COL_MARGIN] = adjusted[COL_MARGIN].to_numpy()
    return grouped


def build_master_file_table(
    master_df: pd.DataFrame | None,
    categories_df: pd.DataFrame | None,
    sales_df: pd.DataFrame | None = None,
    *,
    report_week: int | None = None,
    lfl_week: int | None = None,
    cost_df: pd.DataFrame | None = None,
    excise_lfl: pd.DataFrame | None = None,
    excise_report: pd.DataFrame | None = None,
    excise_from_sales_skus: frozenset[str] | None = None,
    shops_order: list[str] | None = None,
) -> pd.DataFrame:
    """Магазин / месяц / неделя / категория: выручка, маржа и количество.

    Выручка и штуки — из мастер-файла. Маржа «Жидкость 25 мл» пересчитывается
    по себестоимости и акцизу до суммирования в категорию Мастер.
    """
    empty = pd.DataFrame(columns=TABLE_COLUMNS)
    if master_df is None or master_df.empty:
        return empty

    week = resolve_master_week(master_df, report_week)
    if week is None:
        return empty
    week_num = master_df[COL_WEEK].map(safe_int_week)
    work = master_df.loc[week_num == week].copy()
    if work.empty:
        return empty

    category_map = master_category_by_product(categories_df)
    work["_month"] = work[COL_MONTH].map(_month_label)
    work["_category"] = [
        category_map.get((_norm_key(u2), _norm_key(u4)), NO_MASTER_CATEGORY)
        for u2, u4 in zip(work[COL_U2].tolist(), work[COL_U4].tolist())
    ]
    work[COL_SALES_REVENUE] = pd.to_numeric(work[COL_SALES_REVENUE], errors="coerce").fillna(0.0)
    work[COL_MARGIN] = pd.to_numeric(work[COL_MARGIN], errors="coerce").fillna(0.0)
    work[COL_QTY] = pd.to_numeric(work[COL_QTY], errors="coerce").fillna(0.0)

    grouped = (
        work.groupby([COL_SHOP, "_month", COL_U2, COL_U4, "_category"], dropna=False, as_index=False)
        .agg(
            {
                COL_SALES_REVENUE: "sum",
                COL_MARGIN: "sum",
                COL_QTY: "sum",
            }
        )
    )
    grouped[COL_WEEK] = week

    sales_ready = _sales_with_rnp_category(sales_df, categories_df)
    grouped = _apply_liquid_margins(
        grouped,
        liquid_product_keys(sales_ready),
        cost_df,
        excise_lfl,
        excise_report,
        lfl_week=lfl_week,
        report_week=week,
        excise_from_sales_skus=excise_from_sales_skus,
    )

    table = (
        grouped.groupby([COL_SHOP, "_month", COL_WEEK, "_category"], dropna=False, as_index=False)
        .agg(
            {
                COL_SALES_REVENUE: "sum",
                COL_MARGIN: "sum",
                COL_QTY: "sum",
            }
        )
        .rename(
            columns={
                "_month": COL_MONTH,
                "_category": COL_CATEGORY,
                COL_SALES_REVENUE: COL_REVENUE,
            }
        )
    )
    table = table[TABLE_COLUMNS]
    return _sort_table(table, shops_order)


def _sort_table(table: pd.DataFrame, shops_order: list[str] | None) -> pd.DataFrame:
    if table.empty:
        return table
    shop_rank = {
        str(name).strip().casefold(): index
        for index, name in enumerate(shops_order or [])
    }

    def shop_key(name: str) -> tuple[int, str]:
        label = str(name).strip()
        return (shop_rank.get(label.casefold(), len(shop_rank)), label.casefold())

    def category_key(name: str) -> tuple[int, str]:
        label = str(name).strip()
        return (1 if label == NO_MASTER_CATEGORY else 0, label.casefold())

    ordered = table.copy()
    ordered["_shop"] = ordered[COL_SHOP].map(shop_key)
    ordered["_cat"] = ordered[COL_CATEGORY].map(category_key)
    ordered = ordered.sort_values(["_shop", COL_MONTH, COL_WEEK, "_cat"], kind="mergesort")
    return ordered.drop(columns=["_shop", "_cat"]).reset_index(drop=True)


def render_master_file_block(
    master_df: pd.DataFrame | None,
    categories_df: pd.DataFrame | None,
    sales_df: pd.DataFrame | None,
    *,
    week_config: WeekCalculationConfig | None,
    cost_df: pd.DataFrame | None,
    excise_lfl: pd.DataFrame | None,
    excise_report: pd.DataFrame | None,
    excise_from_sales_skus: frozenset[str] | None,
    shops_order: list[str] | None,
) -> None:
    """Таблица мастер-файла внутри раскрывающегося блока."""
    if master_df is None or master_df.empty:
        st.info("Загрузите файл «Мастер файл» и нажмите «Загрузить данные».")
        return

    report_week = week_config.report_week if week_config else None
    lfl_week = week_config.lfl_week if week_config else None
    week = resolve_master_week(master_df, report_week)
    table = build_master_file_table(
        master_df,
        categories_df,
        sales_df,
        report_week=report_week,
        lfl_week=lfl_week,
        cost_df=cost_df,
        excise_lfl=excise_lfl,
        excise_report=excise_report,
        excise_from_sales_skus=excise_from_sales_skus,
        shops_order=shops_order,
    )
    if table.empty:
        st.warning(f"В мастер-файле нет строк отчётной недели {week}.")
        return

    if sales_df is None or sales_df.empty:
        st.caption(
            "Файл продаж не загружен: маржа «Жидкость 25 мл» показана как в мастер-файле."
        )
    elif cost_df is None or getattr(cost_df, "empty", True):
        st.caption(
            "Файл себестоимости не загружен: маржа «Жидкость 25 мл» показана как в мастер-файле."
        )

    visible = table.copy()
    visible[COL_REVENUE] = visible[COL_REVENUE].map(_fmt_money)
    visible[COL_MARGIN] = visible[COL_MARGIN].map(_fmt_money)
    visible[COL_QTY] = visible[COL_QTY].map(_fmt_qty)
    st.caption(f"Отчётная неделя {week}. Категория — «Категория товара Мастер».")
    st.dataframe(visible, use_container_width=True, hide_index=True)
