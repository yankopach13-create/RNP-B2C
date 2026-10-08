"""Блок «План факт категории»: факт продаж в штуках по магазинам."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config.constants import CATEGORY_COLUMN_GENERAL
from features.categories import apply_category_reference
from features.metrics import (
    FINANCIAL_TABLE_ROW_HEIGHT_PX,
    _build_shop_group_map,
    _filter_groups_for_shop_economy,
    _financial_dataframe_height,
    _fmt_int,
    _normalize_shop_key,
    _shops_by_group_from_order,
)
from features.reference_orders import resolve_groups_order, resolve_shops_order
from features.table_layout import STACKED_ORDER_TABLE_VISIBLE_ROWS

COL_GROUP = "Группа"
COL_SHOP = "Магазин"
COL_WEEK = "Неделя"
COL_QTY = "Количество"
_GROUP_COL_WIDTH_PX = 96
_SHOP_COL_WIDTH_PX = 140
_WEEK_COL_WIDTH_PX = 72
_CATEGORY_COL_WIDTH_PX = 96

# Колонка в таблице → ключи категории.
# Уголь, аксессуары и кальяны в справочнике лежат как «Прочие товары/<правая часть>».
PLANFACT_CATEGORY_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ОЭС 2 мл", ("ОЭС 2 мл",)),
    ("ОЭС 4 мл", ("ОЭС 4 мл",)),
    ("ОЭС 10 мл", ("ОЭС 10 мл",)),
    ("Жидк. 25 мл", ("Жидкость 25 мл",)),
    ("Жидк. 13 мл", ("Жидкость 13 мл",)),
    ("Поды", ("Под-системы",)),
    ("Расходники", ("Расходники",)),
    ("Карт. с жидк.", ("Картриджи с жидкостью",)),
    ("Паучи", ("Никотиновые паучи",)),
    ("БКС и ТКС", ("Кальянные смеси", "БКС")),
    ("Уголь", ("Прочие товары/Уголь", "Уголь")),
    ("Аксессуары", ("Прочие товары/Аксессуары", "Аксессуары")),
    ("Кальяны", ("Прочие товары/Кальян", "Кальяны", "Кальян")),
    (
        "Прочие",
        (
            "Прочие товары/Прочие товары",
            "OXVA Stick",
            "OXVA Stick картриджи",
        ),
    ),
)

_RNP_OTHER = "прочие товары"
# Правая часть пары «Прочие товары/…» → ключ колонки план-факта.
_OTHER_GENERAL_KEYS = {
    "уголь": "прочие товары/уголь",
    "аксессуары": "прочие товары/аксессуары",
    "кальян": "прочие товары/кальян",
    "кальяны": "прочие товары/кальян",
    "прочие товары": "прочие товары/прочие товары",
}


def _norm_category_key(value: object) -> str:
    return str(value or "").strip().casefold()


def _category_alias_keys(aliases: tuple[str, ...]) -> frozenset[str]:
    return frozenset(_norm_category_key(name) for name in aliases if str(name).strip())


def _planfact_match_key(rnp: object, general: object) -> str:
    """Ключ сопоставления: для «Прочие товары/…» берём правую часть справочника."""
    rnp_key = _norm_category_key(rnp)
    general_key = _norm_category_key(general)
    if rnp_key == _RNP_OTHER and general_key in _OTHER_GENERAL_KEYS:
        return _OTHER_GENERAL_KEYS[general_key]
    return rnp_key


def build_planfact_categories_table(
    sales_df: pd.DataFrame | None,
    groups_df: pd.DataFrame | None = None,
    shops_order: list[str] | None = None,
    groups_order_rnp: list[str] | None = None,
    report_week: int | None = None,
    categories_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Одна строка на магазин: факт количества по категориям за отчётную неделю."""
    columns = [COL_GROUP, COL_SHOP, COL_WEEK] + [
        title for title, _ in PLANFACT_CATEGORY_COLUMNS
    ]
    shop_rows = _shop_rows(shops_order, groups_order_rnp, groups_df, sales_df)
    if not shop_rows:
        return pd.DataFrame(columns=columns)

    qty_by_shop_cat = _qty_by_shop_and_category(sales_df, categories_df)
    week_label = "" if report_week is None else str(int(report_week))

    rows: list[dict[str, str]] = []
    for group, shop in shop_rows:
        shop_key = _normalize_shop_key(shop)
        row: dict[str, str] = {
            COL_GROUP: group,
            COL_SHOP: shop,
            COL_WEEK: week_label,
        }
        for title, aliases in PLANFACT_CATEGORY_COLUMNS:
            total = 0.0
            for cat_key in _category_alias_keys(aliases):
                total += float(qty_by_shop_cat.get((shop_key, cat_key), 0.0) or 0.0)
            row[title] = _fmt_int(total)
        rows.append(row)

    return pd.DataFrame(rows, columns=columns)


def render_planfact_categories_block(
    *,
    sales_df: pd.DataFrame | None = None,
    groups_df: pd.DataFrame | None = None,
    shops_order: list[str] | None = None,
    groups_order_rnp: list[str] | None = None,
    categories_df: pd.DataFrame | None = None,
    report_week: int | None = None,
    embedded: bool = False,
) -> None:
    """Таблица факта продаж в штуках по магазинам и категориям."""
    if not embedded:
        st.markdown("---")
        st.subheader("План факт категории")
    else:
        st.markdown("**План факт категории**")

    table = build_planfact_categories_table(
        sales_df,
        groups_df,
        shops_order,
        groups_order_rnp,
        report_week,
        categories_df,
    )
    if table.empty:
        st.info("Нет данных для план-факта категорий.")
        return

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        height=_financial_dataframe_height(STACKED_ORDER_TABLE_VISIBLE_ROWS),
        row_height=FINANCIAL_TABLE_ROW_HEIGHT_PX,
        column_config=_planfact_column_config(table),
    )


def _planfact_column_config(table: pd.DataFrame) -> dict:
    """Фиксированные ширины, как у факторного анализа: узкие показатели, шире названия."""
    label_widths = {
        COL_GROUP: _GROUP_COL_WIDTH_PX,
        COL_SHOP: _SHOP_COL_WIDTH_PX,
        COL_WEEK: _WEEK_COL_WIDTH_PX,
    }
    return {
        column: st.column_config.TextColumn(
            column,
            width=label_widths.get(column, _CATEGORY_COL_WIDTH_PX),
        )
        for column in table.columns
    }


def _shop_rows(
    shops_order: list[str] | None,
    groups_order_rnp: list[str] | None,
    groups_df: pd.DataFrame | None,
    sales_df: pd.DataFrame | None,
) -> list[tuple[str, str]]:
    display_order = resolve_shops_order(shops_order)
    if not display_order:
        display_order = _shops_from_sales(sales_df)
    if not display_order:
        return []

    shop_group_map = _build_shop_group_map(groups_df)
    shops_by_group = _shops_by_group_from_order(display_order, shop_group_map)
    group_cols = _filter_groups_for_shop_economy(resolve_groups_order(groups_order_rnp))
    if not group_cols:
        group_cols = list(shops_by_group.keys())

    rows: list[tuple[str, str]] = []
    for group in group_cols:
        for shop in shops_by_group.get(group, []):
            rows.append((group, shop))
    return rows


def _shops_from_sales(sales_df: pd.DataFrame | None) -> list[str]:
    if sales_df is None or sales_df.empty or COL_SHOP not in sales_df.columns:
        return []
    names = sales_df[COL_SHOP].astype(str).str.strip()
    return [name for name in names.unique().tolist() if name and name.lower() not in ("nan", "none")]


def _qty_by_shop_and_category(
    sales_df: pd.DataFrame | None,
    categories_df: pd.DataFrame | None,
) -> dict[tuple[str, str], float]:
    df = _prepare_sales(sales_df, categories_df)
    if df is None or df.empty:
        return {}
    work = df[[COL_SHOP, "Категория", COL_QTY]].copy()
    if CATEGORY_COLUMN_GENERAL in df.columns:
        general = df[CATEGORY_COLUMN_GENERAL]
    else:
        general = pd.Series("", index=df.index)
    work["_shop"] = work[COL_SHOP].map(_normalize_shop_key)
    work["_cat"] = [
        _planfact_match_key(rnp, gen)
        for rnp, gen in zip(work["Категория"].tolist(), general.tolist())
    ]
    work[COL_QTY] = pd.to_numeric(work[COL_QTY], errors="coerce").fillna(0.0)
    work = work.loc[work["_shop"].ne("") & work["_cat"].ne("")]
    if work.empty:
        return {}
    agg = work.groupby(["_shop", "_cat"], sort=False)[COL_QTY].sum()
    return {(str(shop), str(cat)): float(qty) for (shop, cat), qty in agg.items()}


def _prepare_sales(
    sales_df: pd.DataFrame | None,
    categories_df: pd.DataFrame | None,
) -> pd.DataFrame | None:
    if sales_df is None or sales_df.empty:
        return None
    df = sales_df.copy()
    df.columns = df.columns.astype(str).str.strip()
    if COL_QTY not in df.columns or COL_SHOP not in df.columns:
        return None
    if "Категория" not in df.columns:
        if categories_df is None or categories_df.empty:
            return None
        try:
            df = apply_category_reference(df, categories_df)
        except ValueError:
            return None
    if "Категория" not in df.columns:
        return None
    return df
