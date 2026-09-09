"""Расчёт маржи категории «Жидкость 25 мл» из себестоимости и акциза."""

from __future__ import annotations

import pandas as pd

from features.excise_liquid import CATEGORY_LIQUID_25ML

VAT_NET_DIVISOR = 1.2

COL_SHOP = "Магазин"
COL_SKU = "Товар ур.4"
COL_WEEK = "Неделя"
COL_QTY = "Количество"
COL_REVENUE = "Продажи с НДС"
COL_MARGIN = "Маржа"
COL_CATEGORY = "Категория"

_COST_SHOP = "Склад"
_COST_SKU = "Товар4"
_COST_YEAR_WEEK = "Год-Неделя"
_COST_QTY = "Продажи (Q)"
_COST_SUM = "Продажи (Σ)"

# Qlik/Excel могут отдавать ∑ (U+2211), Σ (U+03A3), латинскую E и варианты без пробелов.
_COST_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    _COST_SHOP: (_COST_SHOP, "склад"),
    _COST_SKU: (_COST_SKU, "товар4", "Товар 4", "Товар ур.4"),
    _COST_YEAR_WEEK: (_COST_YEAR_WEEK, "год-неделя", "Год неделя"),
    _COST_QTY: (_COST_QTY, "продажи (q)", "Продажи(Q)"),
    _COST_SUM: (
        _COST_SUM,
        "Продажи (∑)",
        "Продажи(Σ)",
        "Продажи(∑)",
        "Продажи (E)",
        "Продажи (Е)",
        "Продажи(E)",
        "Продажи(Е)",
        "продажи (σ)",
        "продажи (∑)",
    ),
}

_EXCISE_SKU_COL = 1
_EXCISE_QTY_COL = 8
_EXCISE_SUM_COL = 9

_RETAIL_ANCHOR = "Розница"
_WRITEOFF_ANCHOR = "Списание за период"


def parse_year_week(value) -> int | None:
    """«2026/32» → 32; иначе целое число недели."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    if "/" in text:
        text = text.rsplit("/", 1)[-1].strip()
    try:
        return int(float(text))
    except (ValueError, TypeError):
        return None


def _normalize_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _coerce_number(value) -> float | None:
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = (
        str(value)
        .replace("\xa0", "")
        .replace(" ", "")
        .strip()
        .replace(",", ".")
    )
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_column_key(name: str) -> str:
    return str(name).strip().casefold().replace(" ", "")


def _resolve_cost_columns(columns: list[str]) -> dict[str, str]:
    """Сопоставляет канонические имена столбцов с фактическими заголовками файла."""
    normalized = {_normalize_column_key(col): col for col in columns}
    resolved: dict[str, str] = {}
    missing: list[str] = []

    for canonical, aliases in _COST_COLUMN_ALIASES.items():
        actual = None
        for alias in aliases:
            key = _normalize_column_key(alias)
            if key in normalized:
                actual = normalized[key]
                break
        if actual is None:
            missing.append(canonical)
        else:
            resolved[canonical] = actual

    if missing:
        raise ValueError(
            "В файле себестоимости жидкости отсутствуют столбцы: "
            + ", ".join(sorted(missing))
            + ". Найденные заголовки: "
            + ", ".join(columns)
        )
    return resolved


def parse_liquid_cost(raw: pd.DataFrame) -> pd.DataFrame:
    """Нормализует файл бух. себестоимости жидкости."""
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["shop", "sku", "week", "qty", "buh_cost"])

    df = raw.copy()
    df.columns = df.columns.astype(str).str.strip()
    cols = _resolve_cost_columns(list(df.columns))

    out = pd.DataFrame(
        {
            "shop": df[cols[_COST_SHOP]].map(_normalize_text),
            "sku": df[cols[_COST_SKU]].map(_normalize_text),
            "week": df[cols[_COST_YEAR_WEEK]].map(parse_year_week),
            "qty": df[cols[_COST_QTY]].map(_coerce_number),
            "buh_cost": df[cols[_COST_SUM]].map(_coerce_number),
        }
    )
    out = out.loc[
        out["shop"].ne("")
        & out["sku"].ne("")
        & out["week"].notna()
        & out["qty"].notna()
        & out["buh_cost"].notna()
    ].copy()
    out["week"] = out["week"].astype(int)
    return out.reset_index(drop=True)


def _row_contains_anchor(row: pd.Series, anchor: str) -> bool:
    target = anchor.casefold()
    for value in row:
        if pd.isna(value):
            continue
        if target in str(value).strip().casefold():
            return True
    return False


def parse_excise_retail_block(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Парсит блок «Розница» из файла акциза.
    Столбец 2 (index 1) — SKU (= Товар ур.4), 9 — шт, 10 — сумма акциза.
    """
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["sku", "qty", "excise_sum"])

    df = raw.copy()
    if not isinstance(df.columns[0], int):
        # Если файл прочитан с заголовком — перечитываем как матрицу без шапки.
        pass
    df = df.reset_index(drop=True)

    retail_idx = None
    writeoff_idx = None
    for idx, row in df.iterrows():
        if retail_idx is None and _row_contains_anchor(row, _RETAIL_ANCHOR):
            retail_idx = idx
            continue
        if retail_idx is not None and _row_contains_anchor(row, _WRITEOFF_ANCHOR):
            writeoff_idx = idx
            break

    if retail_idx is None:
        raise ValueError(
            f'В файле акциза не найдена строка-якорь «{_RETAIL_ANCHOR}».'
        )
    if writeoff_idx is None:
        writeoff_idx = len(df)

    block = df.iloc[retail_idx + 1 : writeoff_idx].copy()
    rows: list[dict[str, float | str]] = []
    for _, row in block.iterrows():
        sku = _normalize_text(row.iloc[_EXCISE_SKU_COL] if len(row) > _EXCISE_SKU_COL else "")
        qty = _coerce_number(row.iloc[_EXCISE_QTY_COL] if len(row) > _EXCISE_QTY_COL else None)
        excise_sum = _coerce_number(
            row.iloc[_EXCISE_SUM_COL] if len(row) > _EXCISE_SUM_COL else None
        )
        if not sku or qty is None or excise_sum is None:
            continue
        if qty <= 0:
            continue
        rows.append({"sku": sku, "qty": qty, "excise_sum": excise_sum})

    if not rows:
        return pd.DataFrame(columns=["sku", "qty", "excise_sum"])

    parsed = pd.DataFrame(rows)
    return (
        parsed.groupby("sku", as_index=False)
        .agg({"qty": "sum", "excise_sum": "sum"})
        .reset_index(drop=True)
    )


def _excise_for_week(
    week: int,
    *,
    lfl_week: int | None,
    report_week: int | None,
    excise_lfl: pd.DataFrame | None,
    excise_report: pd.DataFrame | None,
) -> pd.DataFrame | None:
    if lfl_week is not None and week == int(lfl_week):
        return excise_lfl
    if report_week is not None and week == int(report_week):
        return excise_report
    return None


def _sku_in_cost(cost_df: pd.DataFrame, sku: str, week: int) -> bool:
    if cost_df is None or cost_df.empty:
        return False
    mask = (cost_df["sku"] == sku) & (cost_df["week"] == week)
    return bool(mask.any())


def _shop_cost(cost_df: pd.DataFrame, shop: str, sku: str, week: int) -> float:
    if cost_df is None or cost_df.empty:
        return 0.0
    rows = cost_df.loc[
        (cost_df["shop"] == shop) & (cost_df["sku"] == sku) & (cost_df["week"] == week)
    ]
    if rows.empty:
        return 0.0
    return float(rows["buh_cost"].sum())


def _excise_row(excise_df: pd.DataFrame | None, sku: str) -> tuple[float, float]:
    if excise_df is None or excise_df.empty:
        return 0.0, 0.0
    rows = excise_df.loc[excise_df["sku"] == sku]
    if rows.empty:
        return 0.0, 0.0
    qty = float(rows["qty"].sum())
    excise_sum = float(rows["excise_sum"].sum())
    return qty, excise_sum


def recalculate_liquid_margins(
    sales_df: pd.DataFrame,
    cost_df: pd.DataFrame | None,
    excise_lfl: pd.DataFrame | None,
    excise_report: pd.DataFrame | None,
    *,
    lfl_week: int | None,
    report_week: int | None,
) -> pd.DataFrame:
    """
    Пересчитывает «Маржа» только для «Жидкость 25 мл».
    Без файла себестоимости исходные значения не меняются.
    """
    if sales_df is None or sales_df.empty:
        return sales_df
    if COL_CATEGORY not in sales_df.columns or COL_MARGIN not in sales_df.columns:
        return sales_df
    if cost_df is None or cost_df.empty:
        return sales_df

    df = sales_df.copy()
    if COL_SKU not in df.columns:
        df[COL_SKU] = ""
    df[COL_SKU] = df[COL_SKU].map(_normalize_text)

    liquid_mask = df[COL_CATEGORY].astype(str).str.strip() == CATEGORY_LIQUID_25ML
    if not liquid_mask.any():
        return df

    if COL_WEEK in df.columns:
        df["_week_num"] = pd.to_numeric(df[COL_WEEK], errors="coerce")
    else:
        df["_week_num"] = pd.NA

    liquid = df.loc[liquid_mask].copy()
    group_keys = [COL_SKU, "_week_num"]

    for (sku, week_val), group in liquid.groupby(group_keys, dropna=False):
        if not sku or pd.isna(week_val):
            continue
        week = int(week_val)

        if not _sku_in_cost(cost_df, sku, week):
            continue

        excise_df = _excise_for_week(
            week,
            lfl_week=lfl_week,
            report_week=report_week,
            excise_lfl=excise_lfl,
            excise_report=excise_report,
        )
        raw_excise_qty, excise_sum = _excise_row(excise_df, sku)
        if raw_excise_qty <= 0:
            continue

        sales_qty = float(group[COL_QTY].sum())
        if sales_qty <= 0:
            continue

        sales_margin = float(group[COL_MARGIN].sum())
        avg_margin = sales_margin / sales_qty

        excise_qty = min(raw_excise_qty, sales_qty)
        if raw_excise_qty > sales_qty:
            excise_sum = excise_sum * (excise_qty / raw_excise_qty)

        for idx, row in group.iterrows():
            qty = float(row[COL_QTY])
            if qty <= 0:
                continue
            rev = float(row[COL_REVENUE])
            shop = _normalize_text(row.get(COL_SHOP, ""))

            share = qty / sales_qty
            row_excise_qty = excise_qty * share
            row_fallback_qty = qty - row_excise_qty
            shop_buh_cost = _shop_cost(cost_df, shop, sku, week)

            if row_excise_qty <= 0:
                continue

            excise_share = row_excise_qty / excise_qty if excise_qty > 0 else 0.0
            margin_excise = (
                (rev / VAT_NET_DIVISOR) * (row_excise_qty / qty)
                - shop_buh_cost * (row_excise_qty / qty)
                - excise_sum * excise_share
            )
            margin_fallback = avg_margin * row_fallback_qty
            df.at[idx, COL_MARGIN] = margin_excise + margin_fallback

    df.drop(columns=["_week_num"], inplace=True, errors="ignore")
    return df
