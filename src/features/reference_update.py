"""Запись правок в справочники (Google Sheets или локальные xlsx)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from config.constants import (
    CATEGORY_COLUMN_GENERAL,
    CATEGORY_COLUMN_RNP,
    CATEGORY_ORDER_COLUMN_GENERAL,
    CATEGORY_ORDER_COLUMN_RNP,
    GROUPS_ORDER_COLUMN_CANDIDATES,
    GROUPS_ORDER_COLUMN_SHOPS,
    GROUPS_ORDER_COLUMN_SHOPS_CANDIDATES,
    SHOP_GROUP_COLUMN_GENERAL,
)
from data.references import (
    REF_CATEGORIES,
    REF_CATEGORY_ORDER,
    REF_GROUPS_ORDER,
    REF_SHOP_GROUPS,
    append_reference_rows,
    get_reference_label,
    get_reference_storage_hint,
    load_all_references,
    load_reference,
    reference_exists,
    save_reference,
    save_references_batch,
)
from features.categories import format_category_pair, parse_category_pair


@dataclass
class QuickCategoryOrderEntry:
    rnp: str
    general: str
    rnp_after: str | None = None
    general_after: str | None = None


@dataclass
class QuickProductEntry:
    u2: str
    u3: str
    u4_variants: list[str]
    category_pair: str
    new_category: QuickCategoryOrderEntry | None = None


def _try_load_reference(key: str) -> tuple[pd.DataFrame | None, str | None]:
    try:
        return load_reference(key), None
    except Exception as exc:  # noqa: BLE001
        return None, f"Не удалось прочитать справочник ({get_reference_label(key)}): {exc}"


def _try_save_reference(key: str, df: pd.DataFrame) -> tuple[bool, str | None]:
    try:
        save_reference(key, df)
    except Exception as exc:  # noqa: BLE001
        return False, (
            f"Не удалось записать в {get_reference_storage_hint(key)}: {exc}"
        )
    return True, None


def _load_or_empty(key: str, default_columns: list[str]) -> tuple[pd.DataFrame | None, str | None]:
    if not reference_exists(key):
        return None, None
    df, err = _try_load_reference(key)
    if err:
        return None, err
    df.columns = df.columns.str.strip()
    if df.empty and not list(df.columns):
        return pd.DataFrame(columns=default_columns), None
    return df, None


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


def _mutate_shop_groups(
    df: pd.DataFrame,
    shop_name: str,
    group_name: str,
    group_general: str | None = None,
) -> tuple[pd.DataFrame, bool, str | None]:
    """Возвращает (df, is_new_shop, error)."""
    shop_name = str(shop_name).strip()
    group_name = str(group_name).strip()
    touch_general = group_general is not None
    group_general_val = str(group_general or "").strip() if touch_general else ""
    if not shop_name or not group_name:
        return df, False, "Укажите магазин и группу РНП."

    df = df.copy()
    df.columns = df.columns.str.strip()
    if "Магазин" not in df.columns or "Группа" not in df.columns:
        return df, False, "В справочнике групп должны быть столбцы «Магазин» и «Группа»."
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
    return df, is_new_shop, None


def _mutate_groups_order_append_shop(
    df: pd.DataFrame,
    shop_name: str,
) -> tuple[pd.DataFrame, bool, str | None]:
    """Возвращает (df, was_added, error). was_added=False если магазин уже в списке."""
    shop_name = str(shop_name).strip()
    if not shop_name:
        return df, False, "Пустое название магазина."

    df = df.copy()
    df.columns = df.columns.str.strip()
    shops_col = _resolve_shops_order_column(df)
    if shops_col is None:
        df[GROUPS_ORDER_COLUMN_SHOPS] = ""
        shops_col = GROUPS_ORDER_COLUMN_SHOPS
    groups_col = _resolve_groups_order_column_for_file(df)
    if groups_col is None and GROUPS_ORDER_COLUMN_CANDIDATES:
        df[GROUPS_ORDER_COLUMN_CANDIDATES[0]] = ""
    key = shop_name.lower()
    existing = {
        str(v).strip().lower()
        for v in df[shops_col].dropna()
        if str(v).strip()
    }
    if key in existing:
        return df, False, None
    row: dict = {c: "" for c in df.columns}
    row[shops_col] = shop_name
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    return df, True, None


def _mutate_category_order_insert(
    df: pd.DataFrame,
    rnp: str,
    general: str,
    *,
    rnp_after: str | None = None,
    general_after: str | None = None,
) -> tuple[pd.DataFrame, list[str], str | None]:
    """Возвращает (df, added_descriptions, error)."""
    rnp = str(rnp or "").strip()
    general = str(general or "").strip()
    if not rnp and not general:
        return df, [], "Пустые названия категорий."

    df = df.copy()
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
        return df, [], None

    df = _order_lists_to_dataframe(rnp_list, gen_list, list(df.columns), rnp_col, gen_col)
    return df, added, None


def _mutate_categories_add_product(
    df: pd.DataFrame,
    ur2: str,
    ur3: str,
    ur4: str,
    category_pair: str,
    slice1: str = "",
    slice2: str = "",
) -> tuple[pd.DataFrame, bool, str | None]:
    """Возвращает (df, was_added, error). was_added=False при дубликате."""
    ur2, ur3, ur4 = str(ur2).strip(), str(ur3).strip(), str(ur4).strip()
    rnp, general = parse_category_pair(category_pair)
    if not ur2 or not ur3:
        return df, False, "Укажите товар ур.2 и ур.3."
    if not rnp:
        return df, False, "Укажите категорию (формат: РНП/Общий РНП)."
    stored = format_category_pair(rnp, general)

    df = df.copy()
    df.columns = df.columns.str.strip()
    for col in (CATEGORY_COLUMN_RNP, "Товар ур.2", "Товар ур.3"):
        if col not in df.columns:
            return df, False, f"В справочнике категорий нет столбца «{col}»."
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
        return df, False, "Такая тройка товара уже есть в справочнике."

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
    return df, True, None


def _default_shop_groups() -> pd.DataFrame:
    return pd.DataFrame(columns=["Магазин", "Группа", SHOP_GROUP_COLUMN_GENERAL])


def _default_groups_order() -> pd.DataFrame:
    return pd.DataFrame(columns=list(GROUPS_ORDER_COLUMN_CANDIDATES) + [GROUPS_ORDER_COLUMN_SHOPS])


def _default_category_order() -> pd.DataFrame:
    return pd.DataFrame(columns=[CATEGORY_ORDER_COLUMN_RNP, CATEGORY_ORDER_COLUMN_GENERAL])


def _load_batch_refs() -> tuple[dict[str, pd.DataFrame], str | None]:
    """Загружает справочники для пакетного обновления."""
    keys = [REF_SHOP_GROUPS, REF_GROUPS_ORDER, REF_CATEGORIES, REF_CATEGORY_ORDER]
    refs: dict[str, pd.DataFrame] = {}

    try:
        refs = load_all_references(keys)
    except Exception:
        for key in keys:
            if not reference_exists(key):
                continue
            df, err = _try_load_reference(key)
            if err:
                return {}, err
            refs[key] = df

    if REF_CATEGORIES not in refs:
        if reference_exists(REF_CATEGORIES):
            df, err = _try_load_reference(REF_CATEGORIES)
            if err:
                return {}, err
            refs[REF_CATEGORIES] = df
        else:
            return {}, (
                f"Не найден справочник категорий ({get_reference_label(REF_CATEGORIES)})."
            )

    if REF_SHOP_GROUPS not in refs:
        refs[REF_SHOP_GROUPS] = _default_shop_groups()
    if REF_GROUPS_ORDER not in refs:
        refs[REF_GROUPS_ORDER] = _default_groups_order()
    if REF_CATEGORY_ORDER not in refs:
        refs[REF_CATEGORY_ORDER] = _default_category_order()

    for key in refs:
        refs[key].columns = refs[key].columns.str.strip()
    return refs, None


def apply_reference_updates_batch(
    shop_entries: list[tuple[str, str]],
    product_entries: list[QuickProductEntry],
) -> tuple[bool, list[str]]:
    """
    Пакетное обновление справочников: одна загрузка, правки в памяти, одна запись на лист.
  """
    messages: list[str] = []
    ok_any = False

    refs, load_err = _load_batch_refs()
    if load_err:
        return False, [load_err]

    dirty: set[str] = set()
    shops_updated = 0
    products_added = 0
    category_order_msgs: list[str] = []

    for shop_name, group_name in shop_entries:
        shop_name = str(shop_name).strip()
        group_name = str(group_name).strip()
        if not shop_name or not group_name:
            messages.append(f"«{shop_name or '?'}»: выберите группу РНП.")
            continue

        refs[REF_SHOP_GROUPS], is_new, err = _mutate_shop_groups(
            refs[REF_SHOP_GROUPS], shop_name, group_name, None
        )
        if err:
            messages.append(f"«{shop_name}»: {err}")
            continue

        dirty.add(REF_SHOP_GROUPS)
        shops_updated += 1

        if is_new:
            refs[REF_GROUPS_ORDER], added, err = _mutate_groups_order_append_shop(
                refs[REF_GROUPS_ORDER], shop_name
            )
            if err:
                messages.append(f"«{shop_name}»: {err}")
            elif added:
                dirty.add(REF_GROUPS_ORDER)

    for entry in product_entries:
        label = f"«{entry.u2} \\ {entry.u3}»"
        if entry.new_category:
            nc = entry.new_category
            refs[REF_CATEGORY_ORDER], added, err = _mutate_category_order_insert(
                refs[REF_CATEGORY_ORDER],
                nc.rnp,
                nc.general,
                rnp_after=nc.rnp_after,
                general_after=nc.general_after,
            )
            if err:
                messages.append(f"{label}: {err}")
            elif added:
                dirty.add(REF_CATEGORY_ORDER)
                hint = get_reference_storage_hint(REF_CATEGORY_ORDER)
                category_order_msgs.append(
                    f"Добавлено в category_order ({hint}): " + ", ".join(added)
                )

        n_dup = 0
        n_added = 0
        for u4 in entry.u4_variants:
            refs[REF_CATEGORIES], was_added, err = _mutate_categories_add_product(
                refs[REF_CATEGORIES],
                entry.u2,
                entry.u3,
                u4,
                entry.category_pair,
            )
            if err:
                if "уже есть" in err.lower():
                    n_dup += 1
                else:
                    messages.append(f"{label}: {err}")
            elif was_added:
                n_added += 1
                dirty.add(REF_CATEGORIES)

        if n_added:
            products_added += n_added
            ok_any = True
        if n_dup:
            messages.append(
                f"{label}: {n_dup} поз. уже есть в справочнике — при необходимости "
                "обновите справочник и снова нажмите «Загрузить данные»."
            )

    if shops_updated:
        ok_any = True

    if not dirty:
        return ok_any, messages + category_order_msgs

    updates = {key: refs[key] for key in dirty}
    try:
        save_references_batch(updates)
    except Exception as exc:  # noqa: BLE001
        return False, messages + [f"Не удалось сохранить справочники: {exc}"]

    if shops_updated:
        hint = get_reference_storage_hint(REF_SHOP_GROUPS)
        messages.append(
            f"Справочник магазинов: обновлено {shops_updated} ({hint})."
        )
    if products_added:
        hint = get_reference_storage_hint(REF_CATEGORIES)
        messages.append(
            f"Справочник категорий: добавлено {products_added} поз. ({hint})."
        )
    messages.extend(category_order_msgs)
    return ok_any, messages


def add_shop_to_reference(
    shop_name: str,
    group_name: str,
    group_general: str | None = None,
) -> tuple[bool, str]:
    """
    Добавляет или обновляет магазин в справочнике групп.
    Если group_general is None — колонка «Группа Общий РНП:» не меняется (только «Группа»).
    Если передана строка (в т.ч. пустая) — записывается и общий РНП.
    """
    default_cols = ["Магазин", "Группа", SHOP_GROUP_COLUMN_GENERAL]
    df, err = _load_or_empty(REF_SHOP_GROUPS, default_cols)
    if err:
        return False, err
    if df is None:
        return False, f"Не найден справочник магазинов ({get_reference_label(REF_SHOP_GROUPS)})."

    df, is_new_shop, err = _mutate_shop_groups(df, shop_name, group_name, group_general)
    if err:
        return False, err

    if is_new_shop:
        try:
            append_reference_rows(REF_SHOP_GROUPS, df.tail(1))
        except Exception as exc:  # noqa: BLE001
            return False, (
                f"Не удалось записать в {get_reference_storage_hint(REF_SHOP_GROUPS)}: {exc}"
            )
        order_df, order_err = _load_or_empty(
            REF_GROUPS_ORDER,
            list(GROUPS_ORDER_COLUMN_CANDIDATES) + [GROUPS_ORDER_COLUMN_SHOPS],
        )
        if order_err:
            return False, order_err
        if order_df is None:
            order_df = _default_groups_order()
        order_df, was_added, order_mut_err = _mutate_groups_order_append_shop(
            order_df, shop_name
        )
        if order_mut_err:
            return False, order_mut_err
        if was_added:
            try:
                append_reference_rows(REF_GROUPS_ORDER, order_df.tail(1))
            except Exception as exc:  # noqa: BLE001
                return False, (
                    f"Не удалось записать в {get_reference_storage_hint(REF_GROUPS_ORDER)}: {exc}"
                )
    else:
        ok, err = _try_save_reference(REF_SHOP_GROUPS, df)
        if not ok:
            return False, err or "Ошибка записи справочника магазинов."

    hint = get_reference_storage_hint(REF_SHOP_GROUPS)
    return True, f"Справочник магазинов обновлён ({hint})."


def append_shop_to_groups_order(shop_name: str) -> tuple[bool, str]:
    """Добавляет магазин в конец столбца «Порядок магазинов»."""
    shop_name = str(shop_name).strip()
    if not shop_name:
        return False, "Пустое название магазина."

    default_cols = list(GROUPS_ORDER_COLUMN_CANDIDATES) + [GROUPS_ORDER_COLUMN_SHOPS]
    if reference_exists(REF_GROUPS_ORDER):
        df, err = _try_load_reference(REF_GROUPS_ORDER)
        if err:
            return False, err
    else:
        df = _default_groups_order()

    df, was_added, err = _mutate_groups_order_append_shop(df, shop_name)
    if err:
        return False, err
    if not was_added:
        return True, "Магазин уже есть в порядке магазинов."

    ok, err = _try_save_reference(REF_GROUPS_ORDER, df)
    if not ok:
        return False, err or "Ошибка записи порядка магазинов."
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


def insert_categories_to_order(
    rnp: str,
    general: str,
    *,
    rnp_after: str | None = None,
    general_after: str | None = None,
) -> tuple[bool, str]:
    """
    Добавляет новые имена в category_order в выбранную позицию
    (столбцы «РНП» и «Общий РНП» независимы).
    rnp_after / general_after: None — в конец, __START__ — в начало, иначе — после категории.
    """
    if reference_exists(REF_CATEGORY_ORDER):
        df, err = _try_load_reference(REF_CATEGORY_ORDER)
        if err:
            return False, err
    else:
        df = _default_category_order()

    df, added, err = _mutate_category_order_insert(
        df, rnp, general, rnp_after=rnp_after, general_after=general_after
    )
    if err:
        return False, err
    if not added:
        return True, "Категории уже есть в порядке отчёта."

    ok, err = _try_save_reference(REF_CATEGORY_ORDER, df)
    if not ok:
        return False, err or "Ошибка записи порядка категорий."
    hint = get_reference_storage_hint(REF_CATEGORY_ORDER)
    return True, f"Добавлено в category_order ({hint}): " + ", ".join(added)


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
    """Добавляет строку в categories (категория — «РНП/Общий РНП»), если тройки ещё нет."""
    if not reference_exists(REF_CATEGORIES):
        return False, f"Не найден справочник категорий ({get_reference_label(REF_CATEGORIES)})."

    df, err = _try_load_reference(REF_CATEGORIES)
    if err:
        return False, err

    df, was_added, err = _mutate_categories_add_product(
        df, ur2, ur3, ur4, category_pair, slice1, slice2
    )
    if err:
        return False, err
    if not was_added:
        return False, "Такая тройка товара уже есть в справочнике."

    try:
        new_row = df.tail(1)
        append_reference_rows(REF_CATEGORIES, new_row)
    except Exception as exc:  # noqa: BLE001
        return False, (
            f"Не удалось записать в {get_reference_storage_hint(REF_CATEGORIES)}: {exc}"
        )
    hint = get_reference_storage_hint(REF_CATEGORIES)
    return True, f"Справочник категорий обновлён ({hint})."
