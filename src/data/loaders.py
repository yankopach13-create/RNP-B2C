from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from config.constants import (
    CATEGORY_ORDER_COLUMN_GENERAL,
    CATEGORY_ORDER_COLUMN_RNP,
    GROUPS_ORDER_COLUMN_CANDIDATES,
    GROUPS_ORDER_COLUMN_SHOPS_CANDIDATES,
    REFERENCE_CATEGORIES_FILENAME,
    REFERENCE_CATEGORY_ORDER_FILENAMES,
    REFERENCE_DIR,
    REFERENCE_FOCUS_FILENAME,
    REFERENCE_GROUPS_FILENAMES,
    REFERENCE_GROUPS_ORDER_FILENAMES,
    REQUIRED_CATEGORY_COLS,
)

@dataclass
class AppData:
    sales: Optional[pd.DataFrame]
    groups: Optional[pd.DataFrame]
    categories: Optional[pd.DataFrame]
    checks_clients: Optional[pd.DataFrame]
    client_segments: Optional[pd.DataFrame]
    focus: Optional[pd.DataFrame]
    lfl: Optional[pd.DataFrame]
    turnover_week: Optional[pd.DataFrame]
    turnover_90: Optional[pd.DataFrame]
    groups_order_rnp: Optional[list[str]]
    category_order_rnp: Optional[list[str]]
    category_order_general: Optional[list[str]]
    shops_order: Optional[list[str]]

def _read_excel(file, **kwargs) -> pd.DataFrame:
    return pd.read_excel(file, **kwargs)


def _groups_reference_path() -> Optional[Path]:
    for name in REFERENCE_GROUPS_FILENAMES:
        path = REFERENCE_DIR / name
        if path.is_file():
            return path
    return None


def get_groups_reference_path() -> Optional[Path]:
    """Публичный путь к файлу групп магазинов (для записи справочника)."""
    return _groups_reference_path()


def get_groups_order_reference_path() -> Optional[Path]:
    """Путь к groups_order.xlsx (порядок групп и магазинов)."""
    return _reference_path(REFERENCE_GROUPS_ORDER_FILENAMES)


def get_category_order_reference_path() -> Optional[Path]:
    """Путь к category_order.xlsx (порядок категорий РНП и Общего РНП)."""
    return _reference_path(REFERENCE_CATEGORY_ORDER_FILENAMES)


def _coerce_numeric_columns(df: pd.DataFrame, columns: list[str]) -> None:
    """Приводит столбцы к числу; поддерживает строки с десятичной запятой."""
    for col in columns:
        if col not in df.columns:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        s = (
            df[col]
            .astype(str)
            .str.replace("\xa0", "", regex=False)
            .str.replace(" ", "", regex=False)
            .str.strip()
            .str.replace(",", ".", regex=False)
        )
        df[col] = pd.to_numeric(s, errors="coerce")


def _load_categories_reference() -> Optional[pd.DataFrame]:
    path = REFERENCE_DIR / REFERENCE_CATEGORIES_FILENAME
    if not path.is_file():
        return None
    categories_df = _read_excel(path)
    if not REQUIRED_CATEGORY_COLS.issubset(set(categories_df.columns)):
        raise ValueError(
            f"В справочнике категорий ({path.name}) отсутствуют необходимые столбцы "
            f"({', '.join(sorted(REQUIRED_CATEGORY_COLS))})."
        )
    return categories_df


def _load_focus_reference() -> Optional[pd.DataFrame]:
    path = REFERENCE_DIR / REFERENCE_FOCUS_FILENAME
    if not path.is_file():
        return None
    return _read_excel(path)


def _reference_path(filenames: tuple[str, ...]) -> Optional[Path]:
    for name in filenames:
        path = REFERENCE_DIR / name
        if path.is_file():
            return path
    return None


def _column_names_from_reference(df: pd.DataFrame, column: str) -> list[str]:
    names: list[str] = []
    for val in df[column]:
        if pd.isna(val):
            continue
        name = str(val).strip()
        if name and name.lower() not in ("nan", "none"):
            names.append(name)
    return names


def _resolve_groups_order_column(order_df: pd.DataFrame) -> str:
    for col in GROUPS_ORDER_COLUMN_CANDIDATES:
        if col in order_df.columns:
            return col
    if len(order_df.columns) >= 1:
        return str(order_df.columns[0])
    raise ValueError("В справочнике groups_order нет столбцов с группами.")


def _resolve_shops_order_column(order_df: pd.DataFrame) -> str | None:
    for col in GROUPS_ORDER_COLUMN_SHOPS_CANDIDATES:
        if col in order_df.columns:
            return col
    return None


def _load_groups_order_rnp() -> Optional[list[str]]:
    """Порядок и список групп РНП для отчёта и формы новых магазинов."""
    path = get_groups_order_reference_path()
    if not path:
        return None
    order_df = _read_excel(path)
    order_df.columns = order_df.columns.str.strip()
    col = _resolve_groups_order_column(order_df)
    return _column_names_from_reference(order_df, col)


def _load_shops_order() -> Optional[list[str]]:
    """Порядок магазинов для блока «Экономика магазинов»."""
    path = get_groups_order_reference_path()
    if not path:
        return None
    order_df = _read_excel(path)
    order_df.columns = order_df.columns.str.strip()
    col = _resolve_shops_order_column(order_df)
    if col is None:
        return None
    return _column_names_from_reference(order_df, col)


def _load_category_order() -> tuple[Optional[list[str]], Optional[list[str]]]:
    """category_order.xlsx: «РНП» (обяз.), «Общий РНП» (опц.). Возвращает (rnp, general)."""
    path = _reference_path(REFERENCE_CATEGORY_ORDER_FILENAMES)
    if not path:
        return None, None
    order_df = _read_excel(path)
    order_df.columns = order_df.columns.str.strip()
    if CATEGORY_ORDER_COLUMN_RNP not in order_df.columns:
        raise ValueError(
            f"В справочнике порядка категорий ({path.name}) отсутствует столбец "
            f"«{CATEGORY_ORDER_COLUMN_RNP}»."
        )
    rnp = _column_names_from_reference(order_df, CATEGORY_ORDER_COLUMN_RNP)
    general = None
    if CATEGORY_ORDER_COLUMN_GENERAL in order_df.columns:
        general = _column_names_from_reference(order_df, CATEGORY_ORDER_COLUMN_GENERAL)
    return rnp, general


def load_all_data(files) -> AppData:
    # Все файлы теперь опциональны
    sales_df = _read_excel(files.sales) if files.sales else None
    if sales_df is not None:
        sales_df = sales_df.copy()
        sales_df.columns = sales_df.columns.str.strip()
        _coerce_numeric_columns(
            sales_df,
            ["Продажи с НДС", "Маржа", "Количество", "Неделя"],
        )

    groups_path = _groups_reference_path()
    groups_df = _read_excel(groups_path) if groups_path else None
    categories_df = _load_categories_reference()
    focus_df = _load_focus_reference()
    groups_order_rnp = _load_groups_order_rnp()
    shops_order = _load_shops_order()
    category_order_rnp, category_order_general = _load_category_order()

    lfl_df = None
    if getattr(files, "lfl", None):
        lfl_df = _read_excel(files.lfl)
        lfl_df.columns = lfl_df.columns.str.strip()
        _coerce_numeric_columns(
            lfl_df,
            ["Продажи с НДС", "Маржа", "Количество", "Неделя"],
        )
    elif sales_df is not None and "Неделя" in sales_df.columns:
        lfl_df = sales_df

    turnover_week_df = _read_excel(files.turnover_week) if files.turnover_week else None
    turnover_90_df = _read_excel(files.turnover_90) if files.turnover_90 else None
    for tdf in (turnover_week_df, turnover_90_df):
        if tdf is not None:
            tdf.columns = tdf.columns.str.strip()
            _coerce_numeric_columns(
                tdf,
                ["Остаток сред.дн. (Q)", "Продажи (Q)", "Продажи с НДС", "Маржа"],
            )
    checks_clients_df = (
        _read_excel(files.checks_clients) if files.checks_clients else None
    )
    if checks_clients_df is not None:
        checks_clients_df.columns = checks_clients_df.columns.str.strip()
        _coerce_numeric_columns(
            checks_clients_df,
            [
                "Неделя",
                "Количество чеков",
                "Продажи",
                "Начислено бонусов",
                "Списано бонусов",
            ],
        )
    client_segments_df = (
        _read_excel(files.client_segments) if files.client_segments else None
    )
    if client_segments_df is not None:
        client_segments_df.columns = client_segments_df.columns.str.strip()
        _coerce_numeric_columns(
            client_segments_df,
            ["Неделя", "Продажи"],
        )

    return AppData(
        sales=sales_df,
        groups=groups_df,
        categories=categories_df,
        checks_clients=checks_clients_df,
        client_segments=client_segments_df,
        focus=focus_df,
        lfl=lfl_df,
        turnover_week=turnover_week_df,
        turnover_90=turnover_90_df,
        groups_order_rnp=groups_order_rnp,
        category_order_rnp=category_order_rnp,
        category_order_general=category_order_general,
        shops_order=shops_order,
    )