"""Подготовка датафрейма продаж и списки несопоставленных магазинов/товаров."""

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from config.constants import UNKNOWN_SHOP_GROUP
from data.loaders import AppData
from features.categories import (
    apply_category_reference,
    apply_group_mapping,
    reference_product_keys,
)
from features.reference_update import _product_dup_key, category_triple_keys_set

# (ур.2, ур.3, уникальные ур.4 из «проблемных» строк) — в UI одна строка, в справочник — по каждому ур.4.
# Новые товары собираются только из файла продаж (см. prepare_sales_dataset).
UnmatchedProductGroup = tuple[str, str, tuple[str, ...]]


@dataclass
class PreparedSalesResult:
    df: pd.DataFrame
    new_shops: list[str]
    unmatched_products: list[UnmatchedProductGroup]


def collect_new_shops(sales_df: pd.DataFrame, groups_df: pd.DataFrame) -> list[str]:
    """Магазины из продаж, которых нет в справочнике групп (без учёта регистра)."""
    if sales_df is None or groups_df is None:
        return []
    if "Магазин" not in sales_df.columns or "Магазин" not in groups_df.columns:
        return []
    known = set(
        groups_df["Магазин"].dropna().astype(str).str.strip().str.lower().unique()
    )
    shops = sales_df["Магазин"].dropna().astype(str).str.strip()
    new = sorted({s for s in shops.unique() if s.lower() not in known})
    return new


def _sort_u4_values(u4s: set[str]) -> tuple[str, ...]:
    return tuple(sorted(u4s, key=lambda s: (s == "", str(s).lower())))


def collect_unmatched_products(
    sales_df: pd.DataFrame,
    category_df: Optional[pd.DataFrame],
) -> list[UnmatchedProductGroup]:
    """
    Уникальные пары (ур.2, ур.3) для формы; третий элемент — уникальные ур.4 из строк,
    где тройки ещё нет в файле категорий и (нет ключа в справочнике ИЛИ категория «Прочие товары»).
    Ключи ур.2–4 сопоставляются с справочником без учёта регистра, как при записи в Excel.
    """
    if "Товар ур.2" not in sales_df.columns or "Товар ур.3" not in sales_df.columns:
        return []

    work = pd.DataFrame(index=sales_df.index)
    work["u2"] = sales_df["Товар ур.2"].astype(str).str.strip()
    work["u3"] = sales_df["Товар ур.3"].astype(str).str.strip()
    if "Товар ур.4" in sales_df.columns:
        work["u4"] = sales_df["Товар ур.4"].astype(str).str.strip()
    else:
        work["u4"] = ""
    if "Категория" in sales_df.columns:
        work["cat"] = sales_df["Категория"].astype(str).str.strip()
    else:
        work["cat"] = ""

    work = work.loc[work["u2"].ne("") & work["u3"].ne("")]
    if work.empty:
        return []

    work["u2_lower"] = work["u2"].str.lower()
    work["u3_lower"] = work["u3"].str.lower()
    work["triple_k"] = (
        work["u2_lower"] + "|||" + work["u3_lower"] + "|||" + work["u4"].str.lower()
    )

    if category_df is None:
        flagged = work
        ref_filter: set[str] = set()
    else:
        keys = reference_product_keys(category_df)
        ref_triples = category_triple_keys_set(category_df)
        key4 = work["u2_lower"] + "||" + work["u3_lower"] + "||" + work["u4"].str.lower()
        key3 = work["u2_lower"] + "||" + work["u3_lower"]
        key2 = work["u2_lower"]
        matchable = key4.isin(keys) | key3.isin(keys) | key2.isin(keys)
        need_raw = (~matchable) | (work["cat"] == "Прочие товары")
        flagged = work.loc[need_raw & (~work["triple_k"].isin(ref_triples))]
        ref_filter = ref_triples

    if flagged.empty:
        return []

    result: list[UnmatchedProductGroup] = []
    for _, group in flagged.groupby(["u2_lower", "u3_lower"], sort=False):
        u2 = str(group["u2"].iloc[0])
        u3 = str(group["u3"].iloc[0])
        u4s = _sort_u4_values(set(group["u4"].tolist()))
        if ref_filter:
            u4s = tuple(
                u for u in u4s if _product_dup_key(u2, u3, u) not in ref_filter
            )
        if u4s:
            result.append((u2, u3, u4s))
    return result


def prepare_sales_dataset(data: AppData) -> Optional[PreparedSalesResult]:
    if data.sales is None or data.groups is None:
        return None
    new_shops = collect_new_shops(data.sales, data.groups)
    df = apply_group_mapping(data.sales, data.groups)
    df["Группа"] = df["Группа"].fillna(UNKNOWN_SHOP_GROUP)
    if data.categories is not None:
        df = apply_category_reference(df, data.categories)
    else:
        df["Категория"] = "Прочие товары"
        if "Товар ур.4" not in df.columns:
            df["Товар ур.4"] = ""
    unmatched = collect_unmatched_products(df, data.categories)
    return PreparedSalesResult(df=df, new_shops=new_shops, unmatched_products=unmatched)


def sales_week_numbers(df: pd.DataFrame) -> list[int]:
    """Уникальные номера недель в продажах (по возрастанию)."""
    if df is None or "Неделя" not in df.columns:
        return []
    weeks = pd.to_numeric(df["Неделя"], errors="coerce").dropna()
    return sorted(int(w) for w in weeks.unique())


def filter_sales_by_report_week(df: pd.DataFrame, report_week: int) -> pd.DataFrame:
    """Строки только с указанной отчётной неделей."""
    if "Неделя" not in df.columns:
        return df
    week_col = pd.to_numeric(df["Неделя"], errors="coerce")
    return df.loc[week_col == report_week].copy()


def filter_sales_cumulative_to_week(df: pd.DataFrame, report_week: int) -> pd.DataFrame:
    """Строки с неделей <= отчётной (накопительно). Без колонки «Неделя» — весь датафрейм."""
    if "Неделя" not in df.columns:
        return df.copy()
    week_col = pd.to_numeric(df["Неделя"], errors="coerce")
    return df.loc[week_col <= report_week].copy()


def default_lfl_and_report_weeks(weeks: list[int]) -> tuple[int, int]:
    """Меньшая неделя — LFL, большая — отчётная."""
    if not weeks:
        raise ValueError("Список недель пуст.")
    return weeks[0], weeks[-1]
