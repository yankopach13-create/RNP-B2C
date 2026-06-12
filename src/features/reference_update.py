"""Запись правок в локальные Excel-справочники (без Streamlit)."""

from __future__ import annotations

import pandas as pd

from config.constants import (
    CATEGORY_COLUMN_GENERAL,
    CATEGORY_COLUMN_RNP,
    CATEGORY_ORDER_COLUMN_GENERAL,
    CATEGORY_ORDER_COLUMN_RNP,
    GROUPS_ORDER_COLUMN_CANDIDATES,
    GROUPS_ORDER_COLUMN_SHOPS,
    GROUPS_ORDER_COLUMN_SHOPS_CANDIDATES,
    REFERENCE_CATEGORIES_FILENAME,
    REFERENCE_CATEGORY_ORDER_FILENAMES,
    REFERENCE_DIR,
    SHOP_GROUP_COLUMN_GENERAL,
)
from data.loaders import (
    get_category_order_reference_path,
    get_groups_order_reference_path,
    get_groups_reference_path,
)
from features.categories import format_category_pair, parse_category_pair


def add_shop_to_reference(
    shop_name: str,
    group_name: str,
    group_general: str | None = None,
) -> tuple[bool, str]:
    """
    Добавляет или обновляет магазин в файле групп.
    Если group_general is None — колонка «Группа Общий РНП:» не меняется (только «Группа»).
    Если передана строка (в т.ч. пустая) — записывается и общий РНП.
    """
    shop_name = str(shop_name).strip()
    group_name = str(group_name).strip()
    touch_general = group_general is not None
    group_general_val = str(group_general or "").strip() if touch_general else ""
    if not shop_name or not group_name:
        return False, "Укажите магазин и группу РНП."
    path = get_groups_reference_path()
    if path is None:
        return False, "Не найден файл shop_groups.xlsx или groups.xlsx в data/reference."
    df = pd.read_excel(path)
    df.columns = df.columns.str.strip()
    if "Магазин" not in df.columns or "Группа" not in df.columns:
        return False, "В файле групп должны быть столбцы «Магазин» и «Группа»."
    if SHOP_GROUP_COLUMN_GENERAL not in df.columns:
        df[SHOP_GROUP_COLUMN_GENERAL] = ""
    key = shop_name.lower()
    mask = df["Магазин"].astype(str).str.strip().str.lower() == key
    is_new_shop = not mask.any()
    if mask.any():
        df.loc[mask, "Группа"] = group_name
        if touch_general:
            df.loc[mask, SHOP_GROUP_COLUMN_GENERAL] = group_general_val
    else:
        gen_cell = group_general_val if touch_general else ""
        row = {"Магазин": shop_name, "Группа": group_name, SHOP_GROUP_COLUMN_GENERAL: gen_cell}
        for c in df.columns:
            if c not in row:
                row[c] = ""
        df = pd.concat([df, pd.DataFrame([{c: row.get(c, "") for c in df.columns}])], ignore_index=True)
    df.to_excel(path, index=False)
    if is_new_shop:
        append_shop_to_groups_order(shop_name)
    return True, "Справочник магазинов обновлён."


def _resolve_shops_order_column(order_df: pd.DataFrame) -> str | None:
    for col in GROUPS_ORDER_COLUMN_SHOPS_CANDIDATES:
        if col in order_df.columns:
            return col
    return None


def _resolve_groups_order_column_for_file(order_df: pd.DataFrame) -> str | None:
    for col in GROUPS_ORDER_COLUMN_CANDIDATES:
        if col in order_df.columns:
            return col
    return None


def append_shop_to_groups_order(shop_name: str) -> tuple[bool, str]:
    """Добавляет магазин в конец столбца «Порядок магазинов» в groups_order.xlsx."""
    shop_name = str(shop_name).strip()
    if not shop_name:
        return False, "Пустое название магазина."
    path = get_groups_order_reference_path()
    if path is None:
        return False, "Не найден файл groups_order.xlsx в data/reference."
    key = shop_name.lower()
    if path.is_file():
        df = pd.read_excel(path)
    else:
        df = pd.DataFrame(columns=list(GROUPS_ORDER_COLUMN_CANDIDATES) + [GROUPS_ORDER_COLUMN_SHOPS])
    df.columns = df.columns.str.strip()
    shops_col = _resolve_shops_order_column(df)
    if shops_col is None:
        df[GROUPS_ORDER_COLUMN_SHOPS] = ""
        shops_col = GROUPS_ORDER_COLUMN_SHOPS
    groups_col = _resolve_groups_order_column_for_file(df)
    if groups_col is None and GROUPS_ORDER_COLUMN_CANDIDATES:
        df[GROUPS_ORDER_COLUMN_CANDIDATES[0]] = ""
        groups_col = GROUPS_ORDER_COLUMN_CANDIDATES[0]
    existing = {
        str(v).strip().lower()
        for v in df[shops_col].dropna()
        if str(v).strip()
    }
    if key in existing:
        return True, "Магазин уже есть в порядке магазинов."
    row: dict = {c: "" for c in df.columns}
    row[shops_col] = shop_name
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_excel(path, index=False)
    return True, "Магазин добавлен в конец списка «Порядок магазинов»."


def category_triple_keys_set(category_df: pd.DataFrame) -> set[str]:
    """Ключи троек ур.2–4, уже присутствующих в справочнике (как при проверке дубликатов)."""
    df = category_df.copy()
    df.columns = df.columns.str.strip()
    if "Товар ур.4" not in df.columns:
        df["Товар ур.4"] = ""
    out: set[str] = set()
    for _, row in df.iterrows():
        u2 = str(row.get("Товар ур.2", "") or "").strip()
        u3 = str(row.get("Товар ур.3", "") or "").strip()
        u4 = str(row.get("Товар ур.4", "") or "").strip()
        out.add(_product_dup_key(u2, u3, u4))
    return out


def _product_dup_key(u2: str, u3: str, u4: str) -> str:
    return "|||".join(
        [str(u2).strip().lower(), str(u3).strip().lower(), str(u4).strip().lower()]
    )


_POSITION_START = "__START__"


def _order_column_values(series: pd.Series) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in series.dropna():
        name = str(v).strip()
        if not name or name.lower() in ("nan", "none"):
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _name_in_list(name: str, items: list[str]) -> bool:
    key = name.casefold()
    return any(x.casefold() == key for x in items)


def _insert_in_ordered_list(
    items: list[str],
    name: str,
    *,
    after: str | None = None,
) -> list[str]:
    """after=None — в конец; after=__START__ — в начало; иначе — сразу после указанной категории."""
    name = str(name).strip()
    if not name or _name_in_list(name, items):
        return items
    if after is None:
        return items + [name]
    if after == _POSITION_START:
        return [name] + items
    anchor = str(after).strip()
    result: list[str] = []
    inserted = False
    for item in items:
        result.append(item)
        if item.casefold() == anchor.casefold():
            result.append(name)
            inserted = True
    if not inserted:
        result.append(name)
    return result


def _order_lists_to_dataframe(
    rnp_list: list[str],
    general_list: list[str],
    columns: list[str],
    rnp_col: str,
    gen_col: str,
) -> pd.DataFrame:
    n = max(len(rnp_list), len(general_list), 1)
    rows: list[dict] = []
    for i in range(n):
        row = {c: "" for c in columns}
        if i < len(rnp_list):
            row[rnp_col] = rnp_list[i]
        if i < len(general_list):
            row[gen_col] = general_list[i]
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def insert_categories_to_order(
    rnp: str,
    general: str,
    *,
    rnp_after: str | None = None,
    general_after: str | None = None,
) -> tuple[bool, str]:
    """
    Добавляет новые имена в category_order.xlsx в выбранную позицию
    (столбцы «РНП» и «Общий РНП» независимы).
    rnp_after / general_after: None — в конец, __START__ — в начало, иначе — после категории.
    """
    rnp = str(rnp or "").strip()
    general = str(general or "").strip()
    if not rnp and not general:
        return False, "Пустые названия категорий."

    path = get_category_order_reference_path()
    if path is None:
        path = REFERENCE_DIR / REFERENCE_CATEGORY_ORDER_FILENAMES[0]
    if path.is_file():
        df = pd.read_excel(path)
    else:
        df = pd.DataFrame(
            columns=[CATEGORY_ORDER_COLUMN_RNP, CATEGORY_ORDER_COLUMN_GENERAL]
        )
    df.columns = df.columns.str.strip()
    if CATEGORY_ORDER_COLUMN_RNP not in df.columns:
        df[CATEGORY_ORDER_COLUMN_RNP] = ""
    if CATEGORY_ORDER_COLUMN_GENERAL not in df.columns:
        df[CATEGORY_ORDER_COLUMN_GENERAL] = ""

    rnp_col = CATEGORY_ORDER_COLUMN_RNP
    gen_col = CATEGORY_ORDER_COLUMN_GENERAL
    rnp_list = _order_column_values(df[rnp_col])
    gen_list = _order_column_values(df[gen_col])

    added: list[str] = []
    if rnp and not _name_in_list(rnp, rnp_list):
        rnp_list = _insert_in_ordered_list(rnp_list, rnp, after=rnp_after)
        pos = _position_label(rnp_after, rnp_list, rnp)
        added.append(f"РНП «{rnp}» ({pos})")
    if general and not _name_in_list(general, gen_list):
        gen_list = _insert_in_ordered_list(gen_list, general, after=general_after)
        pos = _position_label(general_after, gen_list, general)
        added.append(f"Общий РНП «{general}» ({pos})")

    if not added:
        return True, "Категории уже есть в порядке отчёта."

    df = _order_lists_to_dataframe(rnp_list, gen_list, list(df.columns), rnp_col, gen_col)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, index=False)
    return True, "Добавлено в category_order: " + ", ".join(added)


def _position_label(after: str | None, items: list[str], name: str) -> str:
    if after is None:
        return "в конец"
    if after == _POSITION_START:
        return "в начало"
    try:
        idx = next(i for i, x in enumerate(items) if x.casefold() == name.casefold())
        return f"позиция {idx + 1}"
    except StopIteration:
        return "в список"


def append_categories_to_order(rnp: str, general: str) -> tuple[bool, str]:
    """Добавляет категории в конец списков (обратная совместимость)."""
    return insert_categories_to_order(rnp, general)


def add_product_to_reference(
    ur2: str,
    ur3: str,
    ur4: str,
    category_pair: str,
    slice1: str = "",
    slice2: str = "",
) -> tuple[bool, str]:
    """Добавляет строку в categories.xlsx (категория — «РНП/Общий РНП»), если тройки ещё нет."""
    ur2, ur3, ur4 = str(ur2).strip(), str(ur3).strip(), str(ur4).strip()
    rnp, general = parse_category_pair(category_pair)
    if not ur2 or not ur3:
        return False, "Укажите товар ур.2 и ур.3."
    if not rnp:
        return False, "Укажите категорию (формат: РНП/Общий РНП)."
    stored = format_category_pair(rnp, general)
    path = REFERENCE_DIR / REFERENCE_CATEGORIES_FILENAME
    if not path.is_file():
        return False, f"Не найден файл {path.name}."
    df = pd.read_excel(path)
    df.columns = df.columns.str.strip()
    for col in (CATEGORY_COLUMN_RNP, "Товар ур.2", "Товар ур.3"):
        if col not in df.columns:
            return False, f"В справочнике категорий нет столбца «{col}»."
    if "Товар ур.4" not in df.columns:
        df["Товар ур.4"] = ""
    if "Разрез 1" not in df.columns:
        df["Разрез 1"] = ""
    if "Разрез 2" not in df.columns:
        df["Разрез 2"] = ""

    new_key = _product_dup_key(ur2, ur3, ur4)
    existing = (
        df["Товар ур.2"].astype(str).str.strip().str.lower()
        + "|||"
        + df["Товар ур.3"].astype(str).str.strip().str.lower()
        + "|||"
        + df["Товар ур.4"].astype(str).str.strip().str.lower()
    )
    if (existing == new_key).any():
        return False, "Такая тройка товара уже есть в справочнике."

    row = {
        CATEGORY_COLUMN_RNP: stored,
        "Товар ур.2": ur2,
        "Товар ур.3": ur3,
        "Товар ур.4": ur4,
        "Разрез 1": str(slice1 or "").strip(),
        "Разрез 2": str(slice2 or "").strip(),
    }
    if CATEGORY_COLUMN_GENERAL in df.columns:
        row[CATEGORY_COLUMN_GENERAL] = ""
    for c in df.columns:
        if c not in row:
            row[c] = ""
    new_row = pd.DataFrame([{c: row.get(c, "") for c in df.columns}])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_excel(path, index=False)
    return True, "Справочник категорий обновлён."
