"""Вес угля для Общего РНП: килограммы = количество упаковок × вес из листа Ves."""

from __future__ import annotations

import pandas as pd

from config.constants import CATEGORY_COLUMN_GENERAL

COAL_KG_CATEGORY = "Уголь в кг"
COAL_PIECE_CATEGORY = "Уголь"
COL_SKU = "Товар ур.4"
COL_WEIGHT = "Вес в кг"
COL_QTY = "Количество"

_SKU_COLUMN_CANDIDATES = (COL_SKU, "Товар4", "Товар 4")
_WEIGHT_COLUMN_CANDIDATES = (COL_WEIGHT, "Вес, кг", "Вес кг")


def is_coal_kg_category(name: object) -> bool:
    """Строка порядка категорий, которую считаем в килограммах, а не в штуках."""
    return _norm_label(name) == _norm_label(COAL_KG_CATEGORY)


def parse_weight_map(weights_df: pd.DataFrame | None) -> dict[str, float]:
    """Ключ «Товар ур.4» → вес одной упаковки в кг. Пустой справочник → пустой словарь."""
    if weights_df is None or weights_df.empty:
        return {}
    df = weights_df.copy()
    df.columns = df.columns.astype(str).str.strip()
    sku_col = _find_column(df, _SKU_COLUMN_CANDIDATES)
    weight_col = _find_column(df, _WEIGHT_COLUMN_CANDIDATES)
    if sku_col is None or weight_col is None:
        return {}

    weights: dict[str, float] = {}
    for sku_raw, weight_raw in zip(df[sku_col].tolist(), df[weight_col].tolist()):
        key = sku_key(sku_raw)
        weight = _parse_weight(weight_raw)
        if not key or weight is None or key in weights:
            continue
        weights[key] = weight
    return weights


def format_coal_kg(
    sales_df: pd.DataFrame | None,
    weights_df: pd.DataFrame | None,
) -> str:
    """Сумма кг за переданный срез продаж. Без справочника Ves — пустая ячейка."""
    weights = parse_weight_map(weights_df)
    if not weights or sales_df is None:
        return ""
    total = sum_coal_kg(sales_df, weights)
    return f"{total:.1f}".replace(".", ",")


def sum_coal_kg(sales_df: pd.DataFrame, weights: dict[str, float]) -> float:
    """Сумма кг по SKU, которые есть в Ves. Остальные продажи в сумму не входят."""
    if sales_df.empty or COL_SKU not in sales_df.columns or COL_QTY not in sales_df.columns:
        return 0.0
    keys = sales_df[COL_SKU].map(sku_key)
    qty = pd.to_numeric(sales_df[COL_QTY], errors="coerce").fillna(0.0)
    unit_weight = keys.map(weights)
    matched = unit_weight.notna()
    if not matched.any():
        return 0.0
    return float((qty.loc[matched] * unit_weight.loc[matched].astype(float)).sum())


def missing_coal_skus(
    sales_df: pd.DataFrame | None,
    weights: dict[str, float],
) -> list[str]:
    """Уголь категории «Уголь» с ненулевыми штуками, которого нет в Ves."""
    if (
        sales_df is None
        or sales_df.empty
        or not weights
        or COL_SKU not in sales_df.columns
        or COL_QTY not in sales_df.columns
        or CATEGORY_COLUMN_GENERAL not in sales_df.columns
    ):
        return []

    category = sales_df[CATEGORY_COLUMN_GENERAL].map(_norm_label)
    coal = category == _norm_label(COAL_PIECE_CATEGORY)
    qty = pd.to_numeric(sales_df[COL_QTY], errors="coerce").fillna(0.0)
    keys = sales_df[COL_SKU].map(sku_key)
    missing_mask = coal & qty.ne(0) & ~keys.isin(weights) & keys.ne("")
    if not missing_mask.any():
        return []

    names: list[str] = []
    seen: set[str] = set()
    for raw in sales_df.loc[missing_mask, COL_SKU].tolist():
        key = sku_key(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(str(raw).strip())
    return names


def coal_kg_warnings(
    sales_df: pd.DataFrame | None,
    weights_df: pd.DataFrame | None,
    category_order_general: list[str] | None,
) -> list[str]:
    """Предупреждения, если строка «Уголь в кг» есть в порядке, а вес посчитать нельзя."""
    if not category_order_general or not any(
        is_coal_kg_category(name) for name in category_order_general
    ):
        return []
    weights = parse_weight_map(weights_df)
    if not weights:
        return [
            "Лист Ves не загружен или в нём нет столбцов «Товар ур.4» и «Вес в кг». "
            "Строка «Уголь в кг» пустая."
        ]
    missing = missing_coal_skus(sales_df, weights)
    if not missing:
        return []
    shown = missing[:12]
    tail = len(missing) - len(shown)
    names = ", ".join(shown)
    if tail:
        names = f"{names} и ещё {tail}"
    return [f"Нет веса в Ves, эти продажи не вошли в килограммы: {names}"]


def sku_key(value: object) -> str:
    """Ключ сопоставления SKU: без регистра и лишних пробелов."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = " ".join(str(value).strip().split())
    if text.casefold() in ("", "nan", "none"):
        return ""
    return text.casefold()


def _norm_label(value: object) -> str:
    return sku_key(value)


def _find_column(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    folded = {str(column).strip().casefold(): str(column) for column in df.columns}
    for name in candidates:
        found = folded.get(name.casefold())
        if found is not None:
            return found
    return None


def _parse_weight(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number > 0 else None
    text = (
        str(value)
        .replace("\xa0", "")
        .replace(" ", "")
        .strip()
        .replace(",", ".")
    )
    if not text or text.casefold() in ("nan", "none"):
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if number > 0 else None
