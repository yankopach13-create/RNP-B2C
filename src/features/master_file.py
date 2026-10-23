"""Блок «Мастер файл»: магазин, месяц, неделя и категория Мастер."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from features.categories import (
    NO_MASTER_CATEGORY,
    _master_part,
    apply_category_reference,
    master_category_levels,
    resolve_master_category,
)
from features.data_prep import safe_int_week
from features.excise_liquid import CATEGORY_LIQUID_25ML, WeekCalculationConfig
from features.liquid_margin import (
    VAT_NET_DIVISOR,
    _normalize_sku,
    _normalize_text,
    recalculate_liquid_margins,
)

COL_SHOP = "Магазин"
COL_PAD_LEFT = "\u00a0"
COL_PAD_RIGHT = "\u00a0\u00a0"
COL_MONTH = "Месяц"
COL_WEEK = "Неделя"
COL_REVENUE = "Выручка"
COL_MARGIN = "Маржа"
COL_MARGIN_DELTA = "Изм. % маржи"
COL_QTY = "Количество"
COL_CATEGORY = "Категория"
COL_U2 = "Товар ур.2"
COL_U4 = "Товар ур.4"
COL_SALES_REVENUE = "Продажи с НДС"
COL_SALES_CATEGORY = "Категория"
_MARGIN_FILE = "_margin_file"

TABLE_COLUMNS = [
    COL_SHOP,
    COL_MONTH,
    COL_WEEK,
    COL_REVENUE,
    COL_MARGIN,
    COL_MARGIN_DELTA,
    COL_QTY,
    COL_CATEGORY,
]
DISPLAY_COLUMNS = [
    COL_SHOP,
    COL_PAD_LEFT,
    COL_PAD_RIGHT,
    COL_MONTH,
    COL_WEEK,
    COL_REVENUE,
    COL_MARGIN,
    COL_MARGIN_DELTA,
    COL_QTY,
    COL_CATEGORY,
]


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


def _shop_key(value) -> str:
    return _normalize_text(value).casefold()


def _sku_key(value) -> str:
    return _normalize_sku(value).casefold()


def _margin_pct(margin: float, revenue_vat: float) -> float | None:
    """Маржа % = маржа / (выручка с НДС / 1,2), как в РНП."""
    if revenue_vat == 0:
        return None
    return float(margin) / (float(revenue_vat) / VAT_NET_DIVISOR) * 100


def _fmt_margin_delta(value) -> str:
    """Сдвиг процента маржи в процентных пунктах. Ноль не показываем."""
    if value is None or pd.isna(value) or abs(float(value)) < 0.05:
        return ""
    number = float(value)
    sign = "+" if number > 0 else "−"
    return f"{sign}{abs(number):.1f} п.п.".replace(".", ",")


def sales_u3_by_product(sales_df: pd.DataFrame | None) -> dict[tuple[str, str], str]:
    """Товар ур.3 из продаж для пары ур.2 + ур.4. Мастер-файл этот уровень не содержит."""
    if sales_df is None or sales_df.empty:
        return {}
    if COL_U2 not in sales_df.columns or COL_U4 not in sales_df.columns:
        return {}
    if "Товар ур.3" not in sales_df.columns:
        return {}
    found: dict[tuple[str, str], str] = {}
    for u2, u3, u4 in zip(
        sales_df[COL_U2].tolist(),
        sales_df["Товар ур.3"].tolist(),
        sales_df[COL_U4].tolist(),
    ):
        middle = _master_part(u3)
        key = (_master_part(u2), _master_part(u4))
        if not key[0] or not key[1] or not middle:
            continue
        found.setdefault(key, middle)
    return found


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


def _liquid_margin_from_sales(
    sales_df: pd.DataFrame | None,
    *,
    week: int,
    lfl_week: int | None,
    report_week: int | None,
    cost_df: pd.DataFrame | None,
    excise_lfl: pd.DataFrame | None,
    excise_report: pd.DataFrame | None,
    excise_from_sales_skus: frozenset[str] | None,
) -> dict[tuple[str, str], float]:
    """Маржа «Жидкость 25 мл» после той же правки, что в РНП: магазин + SKU."""
    if sales_df is None or sales_df.empty or COL_SALES_CATEGORY not in sales_df.columns:
        return {}
    if COL_SHOP not in sales_df.columns or COL_U4 not in sales_df.columns:
        return {}
    if COL_WEEK not in sales_df.columns or COL_MARGIN not in sales_df.columns:
        return {}
    adjusted = recalculate_liquid_margins(
        sales_df,
        cost_df,
        excise_lfl,
        excise_report,
        lfl_week=lfl_week,
        report_week=report_week,
        excise_from_sales_skus=excise_from_sales_skus,
    )
    week_num = adjusted[COL_WEEK].map(safe_int_week)
    mask = (week_num == week) & (
        adjusted[COL_SALES_CATEGORY].astype(str).str.strip() == CATEGORY_LIQUID_25ML
    )
    if not mask.any():
        return {}
    part = adjusted.loc[mask, [COL_SHOP, COL_U4, COL_MARGIN]].copy()
    part["_shop"] = part[COL_SHOP].map(_shop_key)
    part["_sku"] = part[COL_U4].map(_sku_key)
    part[COL_MARGIN] = pd.to_numeric(part[COL_MARGIN], errors="coerce").fillna(0.0)
    part = part.loc[(part["_shop"] != "") & (part["_sku"] != "")]
    if part.empty:
        return {}
    totals = part.groupby(["_shop", "_sku"], as_index=False)[COL_MARGIN].sum()
    return {
        (row["_shop"], row["_sku"]): float(row[COL_MARGIN])
        for _, row in totals.iterrows()
    }


def _use_sales_liquid_margin(
    grouped: pd.DataFrame,
    margin_by_shop_sku: dict[tuple[str, str], float],
) -> pd.DataFrame:
    """Подставляет в мастер-файл уже пересчитанную маржу продаж по магазину и SKU."""
    grouped = grouped.copy()
    grouped[_MARGIN_FILE] = grouped[COL_MARGIN]
    if not margin_by_shop_sku:
        return grouped
    grouped["_shop"] = grouped[COL_SHOP].map(_shop_key)
    grouped["_sku"] = grouped[COL_U4].map(_sku_key)
    for (shop, sku), total in margin_by_shop_sku.items():
        mask = (grouped["_shop"] == shop) & (grouped["_sku"] == sku)
        if not mask.any():
            continue
        qty_sum = float(grouped.loc[mask, COL_QTY].sum())
        if qty_sum > 0:
            grouped.loc[mask, COL_MARGIN] = total * grouped.loc[mask, COL_QTY] / qty_sum
        else:
            count = int(mask.sum())
            grouped.loc[mask, COL_MARGIN] = total / count if count else total
    return grouped.drop(columns=["_shop", "_sku"])


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

    Выручка и штуки — из мастер-файла. Маржа «Жидкость 25 мл» берётся из продаж
    после той же правки себестоимости и акциза, что в РНП.
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

    levels = master_category_levels(categories_df)
    sales_ready = _sales_with_rnp_category(sales_df, categories_df)
    u3_by_product = sales_u3_by_product(sales_ready if sales_ready is not None else sales_df)
    work["_month"] = work[COL_MONTH].map(_month_label)
    work["_category"] = [
        resolve_master_category(
            u2,
            u4,
            u3_by_product.get((_master_part(u2), _master_part(u4)), ""),
            levels,
        )
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
    grouped = _use_sales_liquid_margin(
        grouped,
        _liquid_margin_from_sales(
            sales_ready,
            week=week,
            lfl_week=lfl_week,
            report_week=report_week if report_week is not None else week,
            cost_df=cost_df,
            excise_lfl=excise_lfl,
            excise_report=excise_report,
            excise_from_sales_skus=excise_from_sales_skus,
        ),
    )

    table = (
        grouped.groupby([COL_SHOP, "_month", COL_WEEK, "_category"], dropna=False, as_index=False)
        .agg(
            {
                COL_SALES_REVENUE: "sum",
                COL_MARGIN: "sum",
                COL_QTY: "sum",
                _MARGIN_FILE: "sum",
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
    table[COL_MARGIN_DELTA] = [
        None
        if _margin_pct(new_margin, revenue) is None or _margin_pct(file_margin, revenue) is None
        else _margin_pct(new_margin, revenue) - _margin_pct(file_margin, revenue)
        for new_margin, file_margin, revenue in zip(
            table[COL_MARGIN].tolist(),
            table[_MARGIN_FILE].tolist(),
            table[COL_REVENUE].tolist(),
        )
    ]
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
    visible[COL_PAD_LEFT] = ""
    visible[COL_PAD_RIGHT] = ""
    visible[COL_REVENUE] = visible[COL_REVENUE].map(_fmt_money)
    visible[COL_MARGIN] = visible[COL_MARGIN].map(_fmt_money)
    visible[COL_MARGIN_DELTA] = visible[COL_MARGIN_DELTA].map(_fmt_margin_delta)
    visible[COL_QTY] = visible[COL_QTY].map(_fmt_qty)
    visible = visible[DISPLAY_COLUMNS]
    st.caption(
        f"Отчётная неделя {week}. Категория — «Категория товара Мастер». "
        "«Изм. % маржи» — сдвиг после правки жидкости, в процентных пунктах."
    )
    st.dataframe(
        visible,
        use_container_width=True,
        hide_index=True,
        column_config={
            COL_PAD_LEFT: st.column_config.TextColumn(COL_PAD_LEFT, width=28),
            COL_PAD_RIGHT: st.column_config.TextColumn(COL_PAD_RIGHT, width=28),
            COL_MARGIN_DELTA: st.column_config.TextColumn(COL_MARGIN_DELTA, width=120),
        },
    )
