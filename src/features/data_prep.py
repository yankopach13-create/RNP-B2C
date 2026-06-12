"""Подготовка датафрейма продаж и списки несопоставленных магазинов/товаров."""

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from config.constants import UNKNOWN_SHOP_GROUP
from data.loaders import AppData
from features.categories import (
    apply_category_reference,
    apply_group_mapping,
    product_matchable,
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

    def _row_triple(row) -> tuple[str, str, str]:
        u2 = str(row.get("Товар ур.2", "") or "").strip()
        u3 = str(row.get("Товар ур.3", "") or "").strip()
        u4 = str(row.get("Товар ур.4", "") or "").strip()
        return (u2, u3, u4)

    def _pair_key(u2: str, u3: str) -> tuple[str, str]:
        return (u2.lower(), u3.lower())

    def _sort_u4(u4s: set[str]) -> tuple[str, ...]:
        return tuple(sorted(u4s, key=lambda s: (s == "", str(s).lower())))

    # pk -> (display u2, display u3, set of u4)
    buckets: dict[tuple[str, str], tuple[str, str, set[str]]] = {}
    order: list[tuple[str, str]] = []

    def _add_u4(u2: str, u3: str, u4: str) -> None:
        pk = _pair_key(u2, u3)
        if pk not in buckets:
            buckets[pk] = (u2, u3, set())
            order.append(pk)
        buckets[pk][2].add(u4)

    if category_df is None:
        for _, row in sales_df.iterrows():
            u2, u3, u4 = _row_triple(row)
            if not u2 or not u3:
                continue
            _add_u4(u2, u3, u4)
    else:
        keys = reference_product_keys(category_df)
        ref_triples = category_triple_keys_set(category_df)
        for _, row in sales_df.iterrows():
            u2, u3, u4 = _row_triple(row)
            if not u2 or not u3:
                continue
            cat = str(row.get("Категория", "") or "").strip()
            triple_k = _product_dup_key(u2, u3, u4)
            need_raw = (not product_matchable(u2, u3, u4, keys)) or (cat == "Прочие товары")
            need = need_raw and triple_k not in ref_triples
            if not need:
                continue
            _add_u4(u2, u3, u4)

    result: list[UnmatchedProductGroup] = []
    ref_filter = category_triple_keys_set(category_df) if category_df is not None else set()
    for pk in order:
        u2, u3, u4s = buckets[pk][0], buckets[pk][1], buckets[pk][2]
        if ref_filter:
            filtered = tuple(
                u for u in _sort_u4(u4s) if _product_dup_key(u2, u3, u) not in ref_filter
            )
        else:
            filtered = _sort_u4(u4s)
        if filtered:
            result.append((u2, u3, filtered))
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
