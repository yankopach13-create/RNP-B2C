"""Блок «Кальянная продукция» в РНП B2C."""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from features.data_prep import filter_sales_by_report_week

COL_METRIC = "Метрика"
COL_VALUE = "Значение"
HOOKAH_TABLE_ROW_HEIGHT_PX = 35
HOOKAH_METRIC_COL_WIDTH_PX = 210
HOOKAH_VALUE_COL_WIDTH_PX = 68

COL_SHOP = "Магазин"
COL_CHECKS = "количество чеков"
COL_PRODUCT_QTY = "количество товара"
COL_SALES_U2 = "Товар ур.2"
COL_SALES_QTY = "Количество"

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

_SALES_CATEGORY_BY_METRIC: dict[str, str] = {
    "1.1 Бестабачная Смесь": "Бестабачная Смесь",
    "1.2 Уголь для кальяна": "Уголь для кальяна",
    "1.3 Аксессуары для Кальяна": "Аксессуары для Кальяна",
    "1.4 Кальяны": "Кальяны",
    "1.5 Табачная Смесь": "Табачная Смесь",
}

# Допустимые варианты написания в «Товар ур.2» (без учёта регистра).
_SALES_CATEGORY_ALIASES: dict[str, tuple[str, ...]] = {
    "Бестабачная Смесь": ("бестабачная смесь", "бкс", "бестабачные смеси"),
    "Уголь для кальяна": ("уголь для кальяна",),
    "Аксессуары для Кальяна": ("аксессуары для кальяна",),
    "Кальяны": ("кальяны",),
    "Табачная Смесь": ("табачная смесь", "табачные смеси"),
}

_HOOKAH_GROUP_ROWS: tuple[str, ...] = _HOOKAH_METRIC_ROWS[-12:]  # type: ignore[assignment]

_GROUP_LABEL_TO_REF: dict[str, str] = {
    "Витебская область": "Витебск",
}

_HOOKAH_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    COL_SHOP: (COL_SHOP, "магазин"),
    COL_CHECKS: (COL_CHECKS, "Количество чеков"),
    COL_PRODUCT_QTY: (COL_PRODUCT_QTY, "Количество товара"),
}

_SALES_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    COL_SALES_U2: (COL_SALES_U2, "Товар Ур.2", "товар ур.2", "Товар2", "Товар 2"),
    COL_SALES_QTY: (COL_SALES_QTY, "количество", "Кол-во", "Кол-во, шт"),
}


def build_hookah_products_table(
    sales_df: pd.DataFrame | None = None,
    focus_hookah: pd.DataFrame | None = None,
    groups_df: pd.DataFrame | None = None,
    report_week: int | None = None,
) -> pd.DataFrame:
    """Таблица метрик кальянной продукции."""
    values = _compute_hookah_metrics(
        sales_df=sales_df,
        focus_hookah=focus_hookah,
        groups_df=groups_df,
        report_week=report_week,
    )
    rows = [
        [label or "", values.get(label, "") if label else ""]
        for label in _HOOKAH_METRIC_ROWS
    ]
    return pd.DataFrame(rows, columns=[COL_METRIC, COL_VALUE])


def render_hookah_products_block(
    *,
    sales_df: pd.DataFrame | None = None,
    focus_hookah: pd.DataFrame | None = None,
    groups_df: pd.DataFrame | None = None,
    report_week: int | None = None,
    embedded: bool = False,
) -> None:
    """Метрики слева, значения справа."""
    if not embedded:
        st.markdown("---")
        st.subheader("Кальянная продукция")
    else:
        st.markdown("**Кальянная продукция**")

    table = build_hookah_products_table(
        sales_df=sales_df,
        focus_hookah=focus_hookah,
        groups_df=groups_df,
        report_week=report_week,
    )
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


def _compute_hookah_metrics(
    *,
    sales_df: pd.DataFrame | None,
    focus_hookah: pd.DataFrame | None,
    groups_df: pd.DataFrame | None,
    report_week: int | None,
) -> dict[str, str]:
    out: dict[str, str] = {}

    sales_week = _prepare_sales_for_hookah(sales_df, report_week)
    for metric, category in _SALES_CATEGORY_BY_METRIC.items():
        out[metric] = _sales_category_qty(sales_week, category)

    if focus_hookah is not None and not focus_hookah.empty:
        out["Кол-во чеков всей категории"] = _category_checks_total(focus_hookah)

    hookah_shops = _prepare_hookah_shops(focus_hookah)
    if hookah_shops is not None:
        shop_group_map = _build_shop_group_map(groups_df)
        for group_label in _HOOKAH_GROUP_ROWS:
            ref_group = _GROUP_LABEL_TO_REF.get(group_label, group_label)
            out[group_label] = _group_nesting(
                hookah_shops, shop_group_map, ref_group
            )

    return out


def _prepare_sales_for_hookah(
    sales_df: pd.DataFrame | None,
    report_week: int | None,
) -> pd.DataFrame | None:
    if sales_df is None or sales_df.empty:
        return None
    try:
        df = _resolve_columns(sales_df, _SALES_COLUMN_ALIASES)
    except ValueError:
        return None
    if report_week is not None:
        df = filter_sales_by_report_week(df, report_week)
    return df


def _sales_category_qty(sales_df: pd.DataFrame | None, category: str) -> str:
    if sales_df is None or sales_df.empty:
        return ""
    if COL_SALES_U2 not in sales_df.columns:
        return ""
    aliases = _SALES_CATEGORY_ALIASES.get(category, (_normalize_label(category),))
    alias_set = {_normalize_label(name) for name in aliases}
    u2 = sales_df[COL_SALES_U2].map(_normalize_label)
    mask = u2.isin(alias_set)
    subset = sales_df.loc[mask]
    if subset.empty:
        return ""
    qty = float(subset[COL_SALES_QTY].sum()) if COL_SALES_QTY in subset.columns else 0.0
    return _fmt_int(qty)


def _prepare_hookah_shops(raw: pd.DataFrame | None) -> pd.DataFrame | None:
    if raw is None or raw.empty:
        return None
    try:
        df = _resolve_columns(raw, _HOOKAH_COLUMN_ALIASES)
    except ValueError:
        return None

    shop_series = df[COL_SHOP]
    shop_mask = ~shop_series.map(_is_totals_row)
    shops = df.loc[shop_mask].copy()
    shops[COL_SHOP] = shops[COL_SHOP].astype(str).str.strip()
    shops = shops.loc[shops[COL_SHOP].ne("")]
    if shops.empty:
        return None

    for col in (COL_CHECKS, COL_PRODUCT_QTY):
        shops[col] = pd.to_numeric(shops[col], errors="coerce").fillna(0)
    return shops


def _category_checks_total(raw: pd.DataFrame) -> str:
    """Кол-во чеков всей категории — вторая строка загруженного файла (после заголовка)."""
    try:
        df = _resolve_columns(raw, _HOOKAH_COLUMN_ALIASES)
    except ValueError:
        return ""
    if df.empty:
        return ""
    value = pd.to_numeric(df.iloc[0][COL_CHECKS], errors="coerce")
    if pd.isna(value):
        return ""
    return _fmt_int(value)


def _group_nesting(
    hookah_shops: pd.DataFrame,
    shop_group_map: dict[str, str],
    ref_group: str,
) -> str:
    ref_norm = _normalize_label(ref_group)
    group_shops = hookah_shops.loc[
        hookah_shops[COL_SHOP].map(_normalize_shop_key).map(shop_group_map).map(
            _normalize_label
        )
        == ref_norm
    ]
    total_checks = float(group_shops[COL_CHECKS].sum())
    total_qty = float(group_shops[COL_PRODUCT_QTY].sum())
    if total_checks <= 0:
        return ""
    return _fmt_decimal(total_qty / total_checks, 3)


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
        if found is None and canonical == COL_SALES_U2:
            found = _find_product_level2_column(df.columns)
        if found is None:
            raise ValueError(f"Отсутствует столбец «{canonical}»")
        resolved[canonical] = found

    rename = {src: dst for dst, src in resolved.items() if src != dst}
    if rename:
        df = df.rename(columns=rename)
    return df


def _find_product_level2_column(columns) -> str | None:
    for col in columns:
        name = str(col).strip().casefold()
        if "товар" in name and "2" in name:
            return str(col).strip()
    return None


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


def _is_totals_row(value: object) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return True
    text = str(value).strip()
    if not text or text.lower() in ("nan", "none", "<na>"):
        return True
    return "итог" in text.casefold()


def _normalize_label(value: object) -> str:
    text = str(value or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip().casefold()


def _normalize_shop_key(value: object) -> str:
    return _normalize_label(value)


def _fmt_int(value: float | int) -> str:
    try:
        return f"{int(round(float(value))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def _fmt_decimal(value: float, decimals: int) -> str:
    try:
        return f"{float(value):.{decimals}f}".replace(".", ",")
    except (TypeError, ValueError):
        return ""
