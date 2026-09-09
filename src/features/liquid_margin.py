"""Расчёт маржи категории «Жидкость 25 мл» из себестоимости и акциза."""

from __future__ import annotations

import re
from io import BytesIO

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

METHOD_FROM_SALES_NO_COST = "из продаж (нет себестоимости)"
METHOD_FROM_SALES_NO_EXCISE = "из продаж (нет акциза)"
METHOD_FULL = "полный расчёт"
METHOD_FALLBACK_ONLY = "только fallback (из продаж)"

_COST_SHOP = "Склад"
_COST_SKU = "Товар4"
_COST_YEAR_WEEK = "Год-Неделя"
_COST_QTY = "Продажи (Q)"
_COST_SUM = "Продажи (Σ)"

# Qlik/Excel: ∑ U+2211, Σ U+03A3, Ʃ U+0199 (African D), E/Е и варианты без пробелов.
_COST_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    _COST_SHOP: (_COST_SHOP, "склад"),
    _COST_SKU: (_COST_SKU, "товар4", "Товар 4", "Товар ур.4"),
    _COST_YEAR_WEEK: (_COST_YEAR_WEEK, "год-неделя", "Год неделя"),
    _COST_QTY: (_COST_QTY, "продажи (q)", "Продажи(Q)"),
    _COST_SUM: (
        _COST_SUM,
        "Продажи (∑)",
        "Продажи (Ʃ)",
        "Продажи(Σ)",
        "Продажи(∑)",
        "Продажи(Ʃ)",
        "Продажи (E)",
        "Продажи (Е)",
        "Продажи(E)",
        "Продажи(Е)",
        "продажи (σ)",
        "продажи (∑)",
        "продажи (Ʃ)",
    ),
}

_COST_SUM_FALLBACK = re.compile(r"^продажи\([^q)]+\)$")

_EXCISE_SKU_COL = 1
_EXCISE_QTY_COL = 8
_EXCISE_SUM_COL = 9
_EXCISE_SKU_SCAN_COLS = 6

_RETAIL_ANCHOR = "Розница"
_WHOLESALE_ANCHOR = "Опт"
_WRITEOFF_ANCHOR = "Списание за период"
_EXCISE_ANCHORS = (_RETAIL_ANCHOR, _WHOLESALE_ANCHOR, _WRITEOFF_ANCHOR)
_EXCISE_DETAIL_RECEIPT_RE = re.compile(r"чек\s*ккм", re.IGNORECASE)
_EXCISE_DETAIL_DOC_TYPES = frozenset({"продажа", "возврат"})

AUDIT_DETAIL_COLUMNS = [
    "Товар ур.4",
    "Магазин",
    "Неделя",
    "Кол-во",
    "Продажи с НДС",
    "Маржа из продаж",
    "Средняя маржа/шт (SKU)",
    "Бух. себес (магазин)",
    "Акциз шт (SKU)",
    "Акциз сумма (SKU)",
    "Шт с акцизом (строка)",
    "Шт fallback (строка)",
    "Выручка без НДС (акциз)",
    "Себес (акциз)",
    "Акциз (строка)",
    "Маржа fallback",
    "Маржа расчётная",
    "Маржа в отчёте",
    "Метод",
]

AUDIT_SKU_COLUMNS = [
    "Товар ур.4",
    "Неделя",
    "Кол-во",
    "Продажи с НДС",
    "Маржа из продаж",
    "Маржа расчётная",
    "Маржа в отчёте",
    "Разница",
    "Метод",
]


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
    text = str(value).replace("\xa0", " ")
    return " ".join(text.split())


_SKU_SUFFIX_RE = re.compile(r"\s*(?:РБ|СТ)\s*$")


def _normalize_sku(value) -> str:
    """Единый ключ SKU: пробелы + снятие суффиксов «РБ»/«СТ» в конце названия."""
    text = _normalize_text(value)
    if not text:
        return ""
    return _SKU_SUFFIX_RE.sub("", text).rstrip()


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
        if actual is None and canonical == _COST_SUM:
            for col in columns:
                if _COST_SUM_FALLBACK.match(_normalize_column_key(col)):
                    actual = col
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
            "sku": df[cols[_COST_SKU]].map(_normalize_sku),
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


def _is_excise_anchor(text: str) -> bool:
    folded = text.casefold()
    return any(anchor.casefold() in folded for anchor in _EXCISE_ANCHORS)


def _looks_like_sku_text(text: str) -> bool:
    if not text or _is_excise_anchor(text):
        return False
    if _coerce_number(text) is not None and len(text.replace(" ", "")) <= 12:
        return False
    return True


def _detect_excise_qty_sum_cols(row: pd.Series) -> tuple[int, int]:
    """По строке «Розница» находит столбцы шт и суммы (последние два числа в строке)."""
    numeric_cols: list[int] = []
    for idx, value in enumerate(row):
        number = _coerce_number(value)
        if number is not None and number > 0:
            numeric_cols.append(idx)
    if len(numeric_cols) >= 2:
        return numeric_cols[-2], numeric_cols[-1]
    return _EXCISE_QTY_COL, _EXCISE_SUM_COL


def _row_is_wholesale_section(row: pd.Series) -> bool:
    """Строка-якорь секции «Опт» (не путать с «Евроопт» в названиях)."""
    for value in row:
        text = _normalize_text(value)
        if text.casefold() == _WHOLESALE_ANCHOR.casefold():
            return True
    return False


def _is_excise_subgroup_header(sku: str, next_row: pd.Series | None, *, qty_col: int) -> bool:
    """
    Промежуточная подгруппа внутри «Розница» (бренд/линейка).
    Следующая строка — более длинное название того же SKU-дерева, не чек.
    """
    if not sku or next_row is None or _is_excise_detail_row(next_row):
        return False
    next_sku = _extract_excise_sku(next_row, before_col=qty_col)
    if not next_sku:
        return False
    sku_key = _normalize_sku(sku)
    next_key = _normalize_sku(next_sku)
    if sku_key == next_key:
        return False
    return len(next_key) > len(sku_key) and next_key.startswith(sku_key)


def _is_excise_detail_row(row: pd.Series) -> bool:
    """
    Строка детализации (чек) внутри группы SKU.
    Такие строки дублируют итог группы — их не суммируем.
    """
    for value in row:
        if pd.isna(value):
            continue
        text = _normalize_text(value)
        if not text:
            continue
        if _EXCISE_DETAIL_RECEIPT_RE.search(text):
            return True
        if text.casefold() in _EXCISE_DETAIL_DOC_TYPES:
            return True
    return False


def _extract_excise_sku(row: pd.Series, *, before_col: int) -> str:
    """
    SKU из первых столбцов строки.
    Учитывает объединённые ячейки: название может быть в col 1 (index 0), а col 2 пуст.
    """
    limit = min(max(before_col, 1), _EXCISE_SKU_SCAN_COLS, len(row))
    candidates: list[tuple[int, str]] = []
    for idx in range(limit):
        text = _normalize_text(row.iloc[idx])
        if _looks_like_sku_text(text):
            candidates.append((len(text), text))

    if not candidates:
        return ""

    candidates.sort(reverse=True)
    return candidates[0][1]


def format_excise_parse_status(df: pd.DataFrame | None, label: str) -> str | None:
    """Краткий статус парсинга акциза для UI после загрузки."""
    if df is None:
        return None
    sku_count = len(df)
    if sku_count == 0:
        return (
            f"⚠ {label}: из блока «Розница» не загружено ни одного SKU. "
            "Проверьте объединённые ячейки в столбце с названием товара."
        )
    qty_total = float(df["qty"].sum())
    sum_total = float(df["excise_sum"].sum())
    return f"✓ {label}: {sku_count} SKU, {qty_total:.0f} шт., сумма акциза {sum_total:,.2f}".replace(
        ",", " "
    )


def parse_excise_retail_block(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Парсит блок «Розница» из файла акциза.
    SKU — в первых столбцах (col 1–2 Excel, с учётом merge), шт/сумма — по строке «Розница».
    """
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["sku", "qty", "excise_sum"])

    df = raw.copy()
    df = df.reset_index(drop=True)

    retail_idx = None
    writeoff_idx = None
    wholesale_idx = None
    for idx, row in df.iterrows():
        if retail_idx is None and _row_contains_anchor(row, _RETAIL_ANCHOR):
            retail_idx = idx
            continue
        if retail_idx is None:
            continue
        if writeoff_idx is None and _row_contains_anchor(row, _WRITEOFF_ANCHOR):
            writeoff_idx = idx
        if wholesale_idx is None and _row_is_wholesale_section(row):
            wholesale_idx = idx
        if writeoff_idx is not None:
            break

    if retail_idx is None:
        raise ValueError(
            f'В файле акциза не найдена строка-якорь «{_RETAIL_ANCHOR}».'
        )
    end_idx = writeoff_idx if writeoff_idx is not None else len(df)
    if wholesale_idx is not None:
        end_idx = min(end_idx, wholesale_idx)

    anchor_row = df.iloc[retail_idx]
    qty_col, sum_col = _detect_excise_qty_sum_cols(anchor_row)
    block = df.iloc[retail_idx + 1 : end_idx].copy()

    rows: list[dict[str, float | str]] = []
    last_sku = ""
    block_items = list(block.iterrows())
    for i, (_, row) in enumerate(block_items):
        if _is_excise_detail_row(row):
            continue

        sku = _extract_excise_sku(row, before_col=qty_col)
        if sku:
            last_sku = sku
        elif last_sku:
            sku = last_sku

        next_row = block_items[i + 1][1] if i + 1 < len(block_items) else None
        if _is_excise_subgroup_header(sku, next_row, qty_col=qty_col):
            continue

        qty = _coerce_number(row.iloc[qty_col] if len(row) > qty_col else None)
        excise_sum = _coerce_number(row.iloc[sum_col] if len(row) > sum_col else None)
        if not sku or qty is None or excise_sum is None:
            continue
        if qty <= 0:
            continue
        rows.append({"sku": _normalize_sku(sku), "qty": qty, "excise_sum": excise_sum})

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
    sku_key = _normalize_sku(sku)
    mask = (cost_df["sku"] == sku_key) & (cost_df["week"] == week)
    return bool(mask.any())


def _shop_cost(cost_df: pd.DataFrame, shop: str, sku: str, week: int) -> float:
    if cost_df is None or cost_df.empty:
        return 0.0
    sku_key = _normalize_sku(sku)
    rows = cost_df.loc[
        (cost_df["shop"] == shop) & (cost_df["sku"] == sku_key) & (cost_df["week"] == week)
    ]
    if rows.empty:
        return 0.0
    return float(rows["buh_cost"].sum())


def _excise_row(excise_df: pd.DataFrame | None, sku: str) -> tuple[float, float]:
    if excise_df is None or excise_df.empty:
        return 0.0, 0.0
    sku_key = _normalize_sku(sku)
    rows = excise_df.loc[excise_df["sku"] == sku_key]
    if rows.empty:
        return 0.0, 0.0
    qty = float(rows["qty"].sum())
    excise_sum = float(rows["excise_sum"].sum())
    return qty, excise_sum


def _prepare_liquid_sales(sales_df: pd.DataFrame) -> pd.DataFrame | None:
    if sales_df is None or sales_df.empty:
        return None
    if COL_CATEGORY not in sales_df.columns or COL_MARGIN not in sales_df.columns:
        return None

    df = sales_df.copy()
    if COL_SKU not in df.columns:
        df[COL_SKU] = ""
    df[COL_SKU] = df[COL_SKU].map(_normalize_text)
    if COL_WEEK in df.columns:
        df["_week_num"] = pd.to_numeric(df[COL_WEEK], errors="coerce")
    else:
        df["_week_num"] = pd.NA

    liquid_mask = df[COL_CATEGORY].astype(str).str.strip() == CATEGORY_LIQUID_25ML
    liquid = df.loc[liquid_mask].copy()
    if liquid.empty:
        return None
    return liquid


def _calculate_row_margin(
    *,
    qty: float,
    rev: float,
    orig_margin: float,
    sales_qty: float,
    avg_margin: float,
    excise_qty: float,
    excise_sum: float,
    shop_buh_cost: float,
) -> tuple[float, str, dict[str, float]]:
    share = qty / sales_qty if sales_qty > 0 else 0.0
    row_excise_qty = excise_qty * share
    row_fallback_qty = qty - row_excise_qty

    rev_net_excise = cost_excise = excise_part = margin_fallback = margin_excise = 0.0

    if row_excise_qty > 0 and excise_qty > 0:
        excise_share = row_excise_qty / excise_qty
        rev_net_excise = (rev / VAT_NET_DIVISOR) * (row_excise_qty / qty)
        cost_excise = shop_buh_cost * (row_excise_qty / qty)
        excise_part = excise_sum * excise_share
        margin_excise = rev_net_excise - cost_excise - excise_part

    if row_fallback_qty > 0:
        margin_fallback = avg_margin * row_fallback_qty

    calculated = margin_excise + margin_fallback
    if row_excise_qty <= 0 and row_fallback_qty > 0:
        method = METHOD_FALLBACK_ONLY
    else:
        method = METHOD_FULL

    details = {
        "Шт с акцизом (строка)": row_excise_qty,
        "Шт fallback (строка)": row_fallback_qty,
        "Выручка без НДС (акциз)": rev_net_excise,
        "Себес (акциз)": cost_excise,
        "Акциз (строка)": excise_part,
        "Маржа fallback": margin_fallback,
    }
    return calculated, method, details


def build_liquid_margin_audit(
    sales_df: pd.DataFrame,
    sales_adjusted_df: pd.DataFrame | None,
    cost_df: pd.DataFrame | None,
    excise_lfl: pd.DataFrame | None,
    excise_report: pd.DataFrame | None,
    *,
    lfl_week: int | None,
    report_week: int | None,
) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Детализация расчёта маржи жидкости по строкам и сводка по SKU."""
    liquid = _prepare_liquid_sales(sales_df)
    if liquid is None:
        return None

    adjusted = sales_adjusted_df if sales_adjusted_df is not None else sales_df
    adjusted_margins: dict[int, float] = {}
    if adjusted is not None and COL_MARGIN in adjusted.columns:
        for idx, row in adjusted.iterrows():
            if (
                str(row.get(COL_CATEGORY, "")).strip() == CATEGORY_LIQUID_25ML
                and pd.notna(row.get(COL_MARGIN))
            ):
                adjusted_margins[int(idx)] = float(row[COL_MARGIN])

    rows: list[dict[str, object]] = []
    group_keys = [COL_SKU, "_week_num"]

    for (sku, week_val), group in liquid.groupby(group_keys, dropna=False):
        if not sku or pd.isna(week_val):
            continue
        week = int(week_val)
        sales_qty = float(group[COL_QTY].sum())
        if sales_qty <= 0:
            continue

        sales_margin_total = float(group[COL_MARGIN].sum())
        avg_margin = sales_margin_total / sales_qty

        if cost_df is None or cost_df.empty or not _sku_in_cost(cost_df, sku, week):
            for idx, row in group.iterrows():
                orig = float(row[COL_MARGIN])
                rows.append(
                    {
                        "_row_index": int(idx),
                        "Товар ур.4": sku,
                        "Магазин": _normalize_text(row.get(COL_SHOP, "")),
                        "Неделя": week,
                        "Кол-во": float(row[COL_QTY]),
                        "Продажи с НДС": float(row[COL_REVENUE]),
                        "Маржа из продаж": orig,
                        "Средняя маржа/шт (SKU)": avg_margin,
                        "Бух. себес (магазин)": 0.0,
                        "Акциз шт (SKU)": 0.0,
                        "Акциз сумма (SKU)": 0.0,
                        "Шт с акцизом (строка)": 0.0,
                        "Шт fallback (строка)": float(row[COL_QTY]),
                        "Выручка без НДС (акциз)": 0.0,
                        "Себес (акциз)": 0.0,
                        "Акциз (строка)": 0.0,
                        "Маржа fallback": orig,
                        "Маржа расчётная": orig,
                        "Маржа в отчёте": adjusted_margins.get(int(idx), orig),
                        "Метод": METHOD_FROM_SALES_NO_COST,
                    }
                )
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
            for idx, row in group.iterrows():
                orig = float(row[COL_MARGIN])
                rows.append(
                    {
                        "_row_index": int(idx),
                        "Товар ур.4": sku,
                        "Магазин": _normalize_text(row.get(COL_SHOP, "")),
                        "Неделя": week,
                        "Кол-во": float(row[COL_QTY]),
                        "Продажи с НДС": float(row[COL_REVENUE]),
                        "Маржа из продаж": orig,
                        "Средняя маржа/шт (SKU)": avg_margin,
                        "Бух. себес (магазин)": _shop_cost(
                            cost_df,
                            _normalize_text(row.get(COL_SHOP, "")),
                            sku,
                            week,
                        ),
                        "Акциз шт (SKU)": 0.0,
                        "Акциз сумма (SKU)": 0.0,
                        "Шт с акцизом (строка)": 0.0,
                        "Шт fallback (строка)": float(row[COL_QTY]),
                        "Выручка без НДС (акциз)": 0.0,
                        "Себес (акциз)": 0.0,
                        "Акциз (строка)": 0.0,
                        "Маржа fallback": orig,
                        "Маржа расчётная": orig,
                        "Маржа в отчёте": adjusted_margins.get(int(idx), orig),
                        "Метод": METHOD_FROM_SALES_NO_EXCISE,
                    }
                )
            continue

        excise_qty = min(raw_excise_qty, sales_qty)
        if raw_excise_qty > sales_qty:
            excise_sum = excise_sum * (excise_qty / raw_excise_qty)

        for idx, row in group.iterrows():
            qty = float(row[COL_QTY])
            if qty <= 0:
                continue
            rev = float(row[COL_REVENUE])
            orig = float(row[COL_MARGIN])
            shop = _normalize_text(row.get(COL_SHOP, ""))
            shop_buh_cost = _shop_cost(cost_df, shop, sku, week)

            calculated, method, details = _calculate_row_margin(
                qty=qty,
                rev=rev,
                orig_margin=orig,
                sales_qty=sales_qty,
                avg_margin=avg_margin,
                excise_qty=excise_qty,
                excise_sum=excise_sum,
                shop_buh_cost=shop_buh_cost,
            )

            rows.append(
                {
                    "_row_index": int(idx),
                    "Товар ур.4": sku,
                    "Магазин": shop,
                    "Неделя": week,
                    "Кол-во": qty,
                    "Продажи с НДС": rev,
                    "Маржа из продаж": orig,
                    "Средняя маржа/шт (SKU)": avg_margin,
                    "Бух. себес (магазин)": shop_buh_cost,
                    "Акциз шт (SKU)": excise_qty,
                    "Акциз сумма (SKU)": excise_sum,
                    **details,
                    "Маржа расчётная": calculated,
                    "Маржа в отчёте": adjusted_margins.get(int(idx), calculated),
                    "Метод": method,
                }
            )

    if not rows:
        return None

    detail_df = pd.DataFrame(rows)
    detail_df = detail_df[["_row_index", *AUDIT_DETAIL_COLUMNS]]
    summary_df = (
        detail_df.groupby(["Товар ур.4", "Неделя"], as_index=False)
        .agg(
            {
                "Кол-во": "sum",
                "Продажи с НДС": "sum",
                "Маржа из продаж": "sum",
                "Маржа расчётная": "sum",
                "Маржа в отчёте": "sum",
                "Метод": lambda s: ", ".join(sorted(set(str(v) for v in s))),
            }
        )
        .rename(columns={"Метод": "Метод"})
    )
    summary_df["Разница"] = summary_df["Маржа в отчёте"] - summary_df["Маржа расчётная"]
    summary_df = summary_df[AUDIT_SKU_COLUMNS]
    return detail_df, summary_df


def export_liquid_margin_audit_bytes(
    detail_df: pd.DataFrame,
    summary_df: pd.DataFrame,
) -> bytes:
    buffer = BytesIO()
    export_detail = detail_df.drop(columns=["_row_index"], errors="ignore")
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        export_detail.to_excel(writer, sheet_name="По строкам", index=False)
        summary_df.to_excel(writer, sheet_name="По SKU", index=False)
    return buffer.getvalue()


def liquid_margin_audit_filename(report_week: int | None) -> str:
    suffix = f"_неделя_{report_week}" if report_week is not None else ""
    return f"Проверка_себестоимости_жидкость{suffix}.xlsx"


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
    audit = build_liquid_margin_audit(
        sales_df,
        sales_df,
        cost_df,
        excise_lfl,
        excise_report,
        lfl_week=lfl_week,
        report_week=report_week,
    )
    if audit is None:
        return sales_df

    detail_df, _ = audit
    if detail_df.empty:
        return sales_df

    df = sales_df.copy()
    if COL_SKU not in df.columns:
        df[COL_SKU] = ""
    df[COL_SKU] = df[COL_SKU].map(_normalize_text)

    liquid_mask = df[COL_CATEGORY].astype(str).str.strip() == CATEGORY_LIQUID_25ML
    if not liquid_mask.any():
        return df

    for _, audit_row in detail_df.iterrows():
        if audit_row["Метод"] in (METHOD_FROM_SALES_NO_COST, METHOD_FROM_SALES_NO_EXCISE):
            continue
        row_idx = int(audit_row["_row_index"])
        if row_idx in df.index:
            df.at[row_idx, COL_MARGIN] = float(audit_row["Маржа расчётная"])

    return df
