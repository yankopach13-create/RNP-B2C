import io
from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

from config.constants import (
    CATEGORY_ORDER_COLUMN_GENERAL,
    CATEGORY_ORDER_COLUMN_RNP,
    GROUPS_ORDER_COLUMN_CANDIDATES,
    GROUPS_ORDER_COLUMN_SHOPS_CANDIDATES,
    REQUIRED_CATEGORY_COLS,
    TURNOVER_CATEGORIES_COLUMN,
)


def _references():
    from data import references

    return references


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
    focus_hookah: Optional[pd.DataFrame]
    focus_fill_free: Optional[pd.DataFrame]
    groups_order_rnp: Optional[list[str]]
    category_order_rnp: Optional[list[str]]
    category_order_general: Optional[list[str]]
    turnover_categories: Optional[list[str]]
    shops_order: Optional[list[str]]

_APP_DATA_OPTIONAL_FIELDS = ("focus_hookah", "focus_fill_free", "turnover_categories")


def normalize_app_data(data: AppData | None) -> AppData | None:
    """Дополняет AppData из session_state полями, добавленными в новых версиях."""
    if data is None:
        return None
    if all(hasattr(data, field) for field in _APP_DATA_OPTIONAL_FIELDS):
        return data
    return AppData(
        sales=data.sales,
        groups=data.groups,
        categories=data.categories,
        checks_clients=data.checks_clients,
        client_segments=data.client_segments,
        focus=data.focus,
        lfl=data.lfl,
        turnover_week=data.turnover_week,
        turnover_90=data.turnover_90,
        focus_hookah=getattr(data, "focus_hookah", None),
        focus_fill_free=getattr(data, "focus_fill_free", None),
        groups_order_rnp=data.groups_order_rnp,
        category_order_rnp=data.category_order_rnp,
        category_order_general=data.category_order_general,
        turnover_categories=getattr(data, "turnover_categories", None),
        shops_order=data.shops_order,
    )

def _excel_file_label(file: Any, fallback: str) -> str:
    name = getattr(file, "name", None)
    if name:
        return str(name).strip()
    return fallback


def _excel_buffer(file: Any) -> io.BytesIO:
    if hasattr(file, "seek"):
        file.seek(0)
    if hasattr(file, "read"):
        content = file.read()
        if not content:
            raise ValueError("Файл пустой.")
        return io.BytesIO(content)
    return file


def _read_excel(file, *, label: str = "Excel", **kwargs) -> pd.DataFrame:
    """Читает загруженный xlsx; устойчив к повторному чтению и «битым» read_only."""
    file_label = _excel_file_label(file, label)
    try:
        buffer = _excel_buffer(file)
    except ValueError as exc:
        raise ValueError(f"Файл «{file_label}» пустой.") from exc

    attempts: list[tuple[str, dict[str, Any]]] = [
        (
            "openpyxl",
            {"engine": "openpyxl", "engine_kwargs": {"read_only": False, "data_only": True}},
        ),
        ("openpyxl (read_only)", {"engine": "openpyxl"}),
    ]

    last_error: Exception | None = None
    for _, read_kwargs in attempts:
        buffer.seek(0)
        try:
            return pd.read_excel(buffer, **read_kwargs, **kwargs)
        except Exception as exc:
            last_error = exc

    raise ValueError(
        f"Не удалось прочитать файл «{file_label}». "
        "Файл повреждён или имеет неподдерживаемый формат Excel. "
        "Скачайте отчёт из Qlik в формате .xlsx без форматирования и загрузите снова."
    ) from last_error


def _safe_load_reference(key: str) -> Optional[pd.DataFrame]:
    try:
        return _references().load_reference(key)
    except FileNotFoundError:
        return None


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


def _load_categories_from_batch(
    batch: dict[str, pd.DataFrame],
) -> Optional[pd.DataFrame]:
    refs = _references()
    categories_df = batch.get(refs.REF_CATEGORIES)
    if categories_df is None:
        return None
    categories_df = categories_df.copy()
    categories_df.columns = categories_df.columns.str.strip()
    if not REQUIRED_CATEGORY_COLS.issubset(set(categories_df.columns)):
        raise ValueError(
            f"В справочнике категорий ({refs.get_reference_label(refs.REF_CATEGORIES)}) "
            f"отсутствуют необходимые столбцы ({', '.join(sorted(REQUIRED_CATEGORY_COLS))})."
        )
    return categories_df


def _load_reference_batch() -> dict[str, pd.DataFrame]:
    """Все справочники за один batchGet / один проход кэша."""
    refs = _references()
    keys = [
        refs.REF_SHOP_GROUPS,
        refs.REF_CATEGORIES,
        refs.REF_GROUPS_ORDER,
        refs.REF_CATEGORY_ORDER,
        refs.REF_FOCUS,
        refs.REF_TURNOVER_CATEGORIES,
    ]
    try:
        return refs.load_all_references(keys)
    except FileNotFoundError:
        batch: dict[str, pd.DataFrame] = {}
        for key in keys:
            df = _safe_load_reference(key)
            if df is not None:
                batch[key] = df
        return batch


def _groups_order_from_batch(
    batch: dict[str, pd.DataFrame],
) -> tuple[Optional[list[str]], Optional[list[str]]]:
    refs = _references()
    order_df = batch.get(refs.REF_GROUPS_ORDER)
    if order_df is None:
        return None, None
    order_df = order_df.copy()
    order_df.columns = order_df.columns.str.strip()
    groups_col = _resolve_groups_order_column(order_df)
    groups_order = _column_names_from_reference(order_df, groups_col)
    shops_col = _resolve_shops_order_column(order_df)
    shops_order = (
        _column_names_from_reference(order_df, shops_col) if shops_col else None
    )
    return groups_order, shops_order


def _category_order_from_batch(
    batch: dict[str, pd.DataFrame],
) -> tuple[Optional[list[str]], Optional[list[str]]]:
    refs = _references()
    order_df = batch.get(refs.REF_CATEGORY_ORDER)
    if order_df is None:
        return None, None
    order_df = order_df.copy()
    order_df.columns = order_df.columns.str.strip()
    if CATEGORY_ORDER_COLUMN_RNP not in order_df.columns:
        raise ValueError(
            f"В справочнике порядка категорий ({refs.get_reference_label(refs.REF_CATEGORY_ORDER)}) "
            f"отсутствует столбец «{CATEGORY_ORDER_COLUMN_RNP}»."
        )
    rnp = _column_names_from_reference(order_df, CATEGORY_ORDER_COLUMN_RNP)
    general = None
    if CATEGORY_ORDER_COLUMN_GENERAL in order_df.columns:
        general = _column_names_from_reference(order_df, CATEGORY_ORDER_COLUMN_GENERAL)
    return rnp, general


def _turnover_categories_from_batch(
    batch: dict[str, pd.DataFrame],
) -> Optional[list[str]]:
    refs = _references()
    turnover_df = batch.get(refs.REF_TURNOVER_CATEGORIES)
    if turnover_df is None:
        return None
    turnover_df = turnover_df.copy()
    turnover_df.columns = turnover_df.columns.str.strip()
    if TURNOVER_CATEGORIES_COLUMN not in turnover_df.columns:
        return None
    categories = _column_names_from_reference(turnover_df, TURNOVER_CATEGORIES_COLUMN)
    return categories or None


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


def _load_groups_order_data() -> tuple[Optional[list[str]], Optional[list[str]]]:
    """Порядок групп РНП и магазинов — один запрос к справочнику groups_order."""
    batch = _load_reference_batch()
    return _groups_order_from_batch(batch)


def _load_category_order() -> tuple[Optional[list[str]], Optional[list[str]]]:
    """category_order: «РНП» (обяз.), «Общий РНП» (опц.). Возвращает (rnp, general)."""
    batch = _load_reference_batch()
    return _category_order_from_batch(batch)


def load_all_data(files) -> AppData:
    # Все файлы теперь опциональны
    sales_df = _read_excel(files.sales, label="Продажи") if files.sales else None
    if sales_df is not None:
        sales_df = sales_df.copy()
        sales_df.columns = sales_df.columns.str.strip()
        _coerce_numeric_columns(
            sales_df,
            ["Продажи с НДС", "Маржа", "Количество", "Неделя"],
        )

    ref_batch = _load_reference_batch()
    refs = _references()

    groups_df = ref_batch.get(refs.REF_SHOP_GROUPS)
    if groups_df is not None:
        groups_df = groups_df.copy()
        groups_df.columns = groups_df.columns.str.strip()

    categories_df = _load_categories_from_batch(ref_batch)
    focus_df = ref_batch.get(refs.REF_FOCUS)
    if focus_df is not None:
        focus_df = focus_df.copy()
        focus_df.columns = focus_df.columns.str.strip()

    groups_order_rnp, shops_order = _groups_order_from_batch(ref_batch)
    category_order_rnp, category_order_general = _category_order_from_batch(ref_batch)
    turnover_categories = _turnover_categories_from_batch(ref_batch)

    lfl_df = None
    if getattr(files, "lfl", None):
        lfl_df = _read_excel(files.lfl, label="LFL")
        lfl_df.columns = lfl_df.columns.str.strip()
        _coerce_numeric_columns(
            lfl_df,
            ["Продажи с НДС", "Маржа", "Количество", "Неделя"],
        )
    elif sales_df is not None and "Неделя" in sales_df.columns:
        lfl_df = sales_df

    turnover_week_df = (
        _read_excel(files.turnover_week, label="Оборачиваемость (7 дней)")
        if files.turnover_week
        else None
    )
    turnover_90_df = (
        _read_excel(files.turnover_90, label="Оборачиваемость (90 дней)")
        if files.turnover_90
        else None
    )
    for tdf in (turnover_week_df, turnover_90_df):
        if tdf is not None:
            tdf.columns = tdf.columns.str.strip()
            _coerce_numeric_columns(
                tdf,
                ["Остаток сред.дн. (Q)", "Продажи (Q)", "Продажи с НДС", "Маржа"],
            )
    checks_clients_df = (
        _read_excel(files.checks_clients, label="Чеки и клиенты")
        if files.checks_clients
        else None
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
        _read_excel(files.client_segments, label="Сегменты покупателей")
        if files.client_segments
        else None
    )
    if client_segments_df is not None:
        client_segments_df.columns = client_segments_df.columns.str.strip()
        _coerce_numeric_columns(
            client_segments_df,
            ["Неделя", "Продажи"],
        )

    focus_hookah_df = (
        _read_excel(files.focus_hookah, label="Кальянная продукция")
        if getattr(files, "focus_hookah", None)
        else None
    )
    if focus_hookah_df is not None:
        focus_hookah_df.columns = focus_hookah_df.columns.str.strip()
        _coerce_numeric_columns(
            focus_hookah_df,
            ["количество чеков", "количество товара", "Количество чеков", "Количество товара"],
        )

    focus_fill_free_df = (
        _read_excel(files.focus_fill_free, label="Fill free")
        if getattr(files, "focus_fill_free", None)
        else None
    )
    if focus_fill_free_df is not None:
        focus_fill_free_df.columns = focus_fill_free_df.columns.str.strip()
        _coerce_numeric_columns(
            focus_fill_free_df,
            ["Неделя", "неделя", "Клиентов", "клиентов"],
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
        focus_hookah=focus_hookah_df,
        focus_fill_free=focus_fill_free_df,
        groups_order_rnp=groups_order_rnp,
        category_order_rnp=category_order_rnp,
        category_order_general=category_order_general,
        turnover_categories=turnover_categories,
        shops_order=shops_order,
    )
