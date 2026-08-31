import pandas as pd

from config.constants import CATEGORY_COLUMN_GENERAL, CATEGORY_COLUMN_RNP
from features.categories import parse_category_pair

TURNOVER_PRODUCT_COL_L4 = "Товар ур.4"
TURNOVER_PRODUCT_COL_L4_ALT = "Товар4"
TURNOVER_PRODUCT_COL_L3 = "Товар ур.3"
TURNOVER_PRODUCT_COL_L3_ALT = "Товар3"
TURNOVER_STOCK_DAYS_COL = "Запасы (дней) (Q)"
TURNOVER_UNKNOWN_CATEGORY = "Прочие товары"


def _norm_turnover_cell(value) -> str:
    if pd.isna(value):
        return ""
    s = str(value).strip()
    if s.lower() in ("", "nan", "none"):
        return ""
    return s


def _ensure_canonical_column(df: pd.DataFrame, canonical: str, alt: str) -> bool:
    """Приводит альтернативное имя столбца к каноническому. True, если столбец есть."""
    if canonical in df.columns:
        return True
    if alt in df.columns:
        df[canonical] = df[alt].map(_norm_turnover_cell)
        return True
    return False


def _build_turnover_product_maps(
    category_ref: pd.DataFrame,
) -> tuple[dict[str, str], dict[str, str]]:
    """
    Справочник categories: Товар ур.4 / ур.3 → категория РНП.

    Ключи без учёта регистра. Строки без категории пропускаются.
    """
    ref = category_ref.copy()
    ref.columns = ref.columns.str.strip()
    map_u4: dict[str, str] = {}
    map_u3: dict[str, str] = {}

    has_u4 = "Товар ур.4" in ref.columns
    has_u3 = "Товар ур.3" in ref.columns
    if not has_u4 and not has_u3:
        return map_u4, map_u3

    has_general = CATEGORY_COLUMN_GENERAL in ref.columns
    for _, row in ref.iterrows():
        override = (
            _norm_turnover_cell(row.get(CATEGORY_COLUMN_GENERAL)) if has_general else ""
        )
        rnp, _ = parse_category_pair(
            row.get(CATEGORY_COLUMN_RNP, ""), general_override=override
        )
        if not rnp:
            continue
        if has_u4:
            u4 = _norm_turnover_cell(row.get("Товар ур.4"))
            if u4 and u4 != "-":
                map_u4[u4.casefold()] = rnp
        if has_u3:
            u3 = _norm_turnover_cell(row.get("Товар ур.3"))
            if u3 and u3 != "-":
                map_u3[u3.casefold()] = rnp

    return map_u4, map_u3


def _resolve_turnover_product_columns(df: pd.DataFrame) -> tuple[str, str | None]:
    """
    Возвращает (основной столбец товара, запасной).

    Приоритет — ур.4 (или «Товар4»); если его нет — ур.3 / «Товар3».
    """
    has_l4 = _ensure_canonical_column(
        df, TURNOVER_PRODUCT_COL_L4, TURNOVER_PRODUCT_COL_L4_ALT
    )
    has_l3 = _ensure_canonical_column(
        df, TURNOVER_PRODUCT_COL_L3, TURNOVER_PRODUCT_COL_L3_ALT
    )
    if has_l4:
        return TURNOVER_PRODUCT_COL_L4, TURNOVER_PRODUCT_COL_L3 if has_l3 else None
    if has_l3:
        return TURNOVER_PRODUCT_COL_L3, None
    raise ValueError(
        "В файле оборачиваемости нет столбца «Товар ур.4» / «Товар4» "
        "или «Товар ур.3» / «Товар3»."
    )


def _is_turnover_excluded_by_stock_days(value) -> bool:
    """Строки с «-» в запасах не участвуют в расчёте оборачиваемости."""
    if pd.isna(value):
        return False
    return str(value).strip() == "-"


def _is_turnover_excluded_product(value) -> bool:
    """Строки с «-» или пустым товаром не участвуют в расчёте."""
    s = _norm_turnover_cell(value)
    return s == "-" or s == ""


def _assign_turnover_categories(
    df: pd.DataFrame,
    product_col: str,
    fallback_col: str | None,
    map_u4: dict[str, str],
    map_u3: dict[str, str],
) -> None:
    """Пишет столбец «Категория»: сначала ур.4, при промахе — ур.3."""
    primary_map = map_u4 if product_col == TURNOVER_PRODUCT_COL_L4 else map_u3
    keys_primary = df[product_col].map(_norm_turnover_cell).str.casefold()
    df["Категория"] = keys_primary.map(primary_map)

    if product_col == TURNOVER_PRODUCT_COL_L4 and fallback_col is not None:
        keys_u3 = df[fallback_col].map(_norm_turnover_cell).str.casefold()
        df["Категория"] = df["Категория"].fillna(keys_u3.map(map_u3))

    df["Категория"] = df["Категория"].fillna(TURNOVER_UNKNOWN_CATEGORY)


def prepare_turnover_table(
    df_inventory: pd.DataFrame,
    categories_df: pd.DataFrame,
    period_days: int,
) -> pd.DataFrame:
    """
    Рассчитывает оборачиваемость (в днях) по категориям.

    Оборачиваемость = Средний остаток / (Продажи / период_в_днях)

    Файл оборачиваемости — в разрезе **Товар ур.4** (или «Товар4»);
    категория берётся из справочника categories по «Товар ур.4».
    Если ур.4 в справочнике нет, а в файле есть «Товар ур.3» — запасной
    поиск по ур.3. Старые файлы только с ур.3 / «Товар3» поддерживаются.
    Строки, где «Запасы (дней) (Q)» = «-» или товар пустой / «-»,
    не участвуют в расчёте.
    """
    if df_inventory is None or df_inventory.empty:
        return pd.DataFrame(columns=["Категория", "Оборачиваемость, дни"])

    df = df_inventory.copy()
    df.columns = df.columns.str.strip()

    category_ref = categories_df.copy()
    category_ref.columns = category_ref.columns.str.strip()
    map_u4, map_u3 = _build_turnover_product_maps(category_ref)

    product_col, fallback_col = _resolve_turnover_product_columns(df)
    df[product_col] = df[product_col].map(_norm_turnover_cell)
    if fallback_col is not None:
        df[fallback_col] = df[fallback_col].map(_norm_turnover_cell)

    df = df.loc[~df[product_col].map(_is_turnover_excluded_product)].copy()
    if df.empty:
        return pd.DataFrame(columns=["Категория", "Оборачиваемость, дни"])

    if TURNOVER_STOCK_DAYS_COL in df.columns:
        df = df.loc[
            ~df[TURNOVER_STOCK_DAYS_COL].map(_is_turnover_excluded_by_stock_days)
        ].copy()
        if df.empty:
            return pd.DataFrame(columns=["Категория", "Оборачиваемость, дни"])

    _assign_turnover_categories(df, product_col, fallback_col, map_u4, map_u3)

    for col in ["Остаток сред.дн. (Q)", "Продажи (Q)"]:
        if col not in df.columns:
            raise ValueError(f"В файле оборачиваемости отсутствует столбец '{col}'.")
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    agg = (
        df.groupby("Категория")[["Остаток сред.дн. (Q)", "Продажи (Q)"]]
        .sum()
        .reset_index()
    )

    agg["Оборачиваемость, дни"] = agg.apply(
        lambda row: _calc_turnover(
            row["Остаток сред.дн. (Q)"], row["Продажи (Q)"], period_days
        ),
        axis=1,
    )

    agg["Оборачиваемость, дни"] = agg["Оборачиваемость, дни"].apply(
        lambda x: "" if pd.isna(x) else str(int(round(x)))
    )
    return agg[["Категория", "Оборачиваемость, дни"]]


def _calc_turnover(avg_stock: float, total_sales: float, period_days: int):
    if period_days <= 0:
        return pd.NA
    if total_sales <= 0:
        return pd.NA
    daily_sales = total_sales / period_days
    if daily_sales <= 0:
        return pd.NA
    if avg_stock <= 0:
        return 0
    return avg_stock / daily_sales
