import pandas as pd

from config.constants import CATEGORY_COLUMN_GENERAL, CATEGORY_COLUMN_RNP
from features.categories import parse_category_pair

TURNOVER_PRODUCT_COL = "Товар ур.3"
TURNOVER_PRODUCT_COL_ALT = "Товар3"
TURNOVER_STOCK_DAYS_COL = "Запасы (дней) (Q)"
TURNOVER_UNKNOWN_CATEGORY = "Прочие товары"


def _norm_turnover_cell(value) -> str:
    if pd.isna(value):
        return ""
    s = str(value).strip()
    if s.lower() in ("", "nan", "none"):
        return ""
    return s


def _build_turnover_map_by_u3(category_ref: pd.DataFrame) -> dict[str, str]:
    """Справочник categories: Товар ур.3 → категория РНП (ключ без учёта регистра)."""
    ref = category_ref.copy()
    ref.columns = ref.columns.str.strip()
    mapping: dict[str, str] = {}

    if "Товар ур.3" not in ref.columns:
        return mapping

    has_general = CATEGORY_COLUMN_GENERAL in ref.columns
    for _, row in ref.iterrows():
        u3 = _norm_turnover_cell(row.get("Товар ур.3"))
        override = (
            _norm_turnover_cell(row.get(CATEGORY_COLUMN_GENERAL)) if has_general else ""
        )
        rnp, _ = parse_category_pair(
            row.get(CATEGORY_COLUMN_RNP, ""), general_override=override
        )
        if not u3 or not rnp:
            continue
        mapping[u3.casefold()] = rnp

    return mapping


def _resolve_turnover_product_column(df: pd.DataFrame) -> str:
    """Возвращает имя столбца товара ур.3 в файле оборачиваемости."""
    if TURNOVER_PRODUCT_COL in df.columns:
        return TURNOVER_PRODUCT_COL
    if TURNOVER_PRODUCT_COL_ALT in df.columns:
        df[TURNOVER_PRODUCT_COL] = df[TURNOVER_PRODUCT_COL_ALT].map(_norm_turnover_cell)
        return TURNOVER_PRODUCT_COL
    raise ValueError(
        f"В файле оборачиваемости нет столбца «{TURNOVER_PRODUCT_COL}» "
        f"или «{TURNOVER_PRODUCT_COL_ALT}»."
    )


def _is_turnover_excluded_by_stock_days(value) -> bool:
    """Строки с «-» в запасах не участвуют в расчёте оборачиваемости."""
    if pd.isna(value):
        return False
    return str(value).strip() == "-"


def _is_turnover_excluded_product(value) -> bool:
    """Строки с «-» или пустым товаром ур.3 не участвуют в расчёте."""
    s = _norm_turnover_cell(value)
    return s == "-" or s == ""


def _turnover_lookup_category(u3: str, map_u3: dict[str, str]) -> str:
    key = _norm_turnover_cell(u3).casefold()
    if not key:
        return TURNOVER_UNKNOWN_CATEGORY
    return map_u3.get(key, TURNOVER_UNKNOWN_CATEGORY)


def prepare_turnover_table(
    df_inventory: pd.DataFrame,
    categories_df: pd.DataFrame,
    period_days: int,
) -> pd.DataFrame:
    """
    Рассчитывает оборачиваемость (в днях) по категориям.

    Оборачиваемость = Средний остаток / (Продажи / период_в_днях)

    Файл оборачиваемости — в разрезе **Товар ур.3** (или «Товар3»);
    категория берётся из справочника categories по столбцу «Товар ур.3».
    Строки, где «Запасы (дней) (Q)» = «-» или «Товар ур.3» / «Товар3» = «-»
    (или пусто), не участвуют в расчёте.
    """
    if df_inventory is None or df_inventory.empty:
        return pd.DataFrame(columns=["Категория", "Оборачиваемость, дни"])

    df = df_inventory.copy()
    df.columns = df.columns.str.strip()

    category_ref = categories_df.copy()
    category_ref.columns = category_ref.columns.str.strip()
    map_u3 = _build_turnover_map_by_u3(category_ref)

    product_col = _resolve_turnover_product_column(df)
    df[product_col] = df[product_col].map(_norm_turnover_cell)
    df = df.loc[~df[product_col].map(_is_turnover_excluded_product)].copy()
    if df.empty:
        return pd.DataFrame(columns=["Категория", "Оборачиваемость, дни"])

    if TURNOVER_STOCK_DAYS_COL in df.columns:
        df = df.loc[
            ~df[TURNOVER_STOCK_DAYS_COL].map(_is_turnover_excluded_by_stock_days)
        ].copy()
        if df.empty:
            return pd.DataFrame(columns=["Категория", "Оборачиваемость, дни"])

    df["Категория"] = df[product_col].map(
        lambda u3: _turnover_lookup_category(u3, map_u3)
    )

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
