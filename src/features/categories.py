"""Сопоставление товаров со справочником категорий (РНП / Общий РНП)."""

from __future__ import annotations

import pandas as pd

from config.constants import CATEGORY_COLUMN_GENERAL, CATEGORY_COLUMN_RNP

# Разделитель пары «категория РНП / категория Общего РНП» в одной ячейке справочника.
CATEGORY_PAIR_SEPARATOR = "/"

_LEVEL_MAPS_CACHE: dict[int, tuple[dict, dict, dict]] = {}


def clear_category_maps_cache() -> None:
    """Сброс кэша карт категорий (после обновления справочника)."""
    _LEVEL_MAPS_CACHE.clear()


def _norm_cell(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _is_empty_level(value) -> bool:
    s = _norm_cell(value)
    return s == "" or s.lower() in ("nan", "none")


def parse_category_pair(
    raw: str,
    *,
    general_override: str = "",
) -> tuple[str, str]:
    """
    Разбирает категорию из справочника.
    Формат: «РНП/Общий РНП». Без «/» — одна категория для обоих отчётов.
    Если задан general_override (отдельный столбец в старом файле) — правая часть из него.
    """
    cell = _norm_cell(raw)
    override = _norm_cell(general_override)
    if CATEGORY_PAIR_SEPARATOR in cell:
        left, _, right = cell.partition(CATEGORY_PAIR_SEPARATOR)
        rnp = left.strip()
        general = right.strip() if right.strip() else (override or rnp)
        if override:
            general = override
        return rnp, general
    if not cell:
        return "", override
    return cell, override if override else cell


def format_category_pair(rnp: str, general: str) -> str:
    """Каноническая запись в categories: «РНП/Общий РНП»."""
    rnp = _norm_cell(rnp)
    general = _norm_cell(general)
    if not rnp:
        return ""
    if not general or general == rnp:
        return f"{rnp}{CATEGORY_PAIR_SEPARATOR}{general or rnp}"
    return f"{rnp}{CATEGORY_PAIR_SEPARATOR}{general}"


def category_pair_label(rnp: str, general: str) -> str:
    """Подпись для select в UI."""
    rnp, general = _norm_cell(rnp), _norm_cell(general)
    if not general or general == rnp:
        return rnp
    return f"{rnp} / {general}"


def unique_category_pairs(category_df: pd.DataFrame) -> list[tuple[str, str, str]]:
    """
    Уникальные пары из справочника: (rnp, general, stored_value).
    stored_value — строка для записи в Excel и значения select.
    """
    if category_df is None or category_df.empty:
        return []
    df = category_df.copy()
    df.columns = df.columns.str.strip()
    if CATEGORY_COLUMN_RNP not in df.columns:
        return []

    has_general_col = CATEGORY_COLUMN_GENERAL in df.columns
    rnp_col = df[CATEGORY_COLUMN_RNP].map(_norm_cell)
    if has_general_col:
        gen_col = df[CATEGORY_COLUMN_GENERAL].map(_norm_cell)
    else:
        gen_col = pd.Series("", index=df.index)

    pairs_df = pd.DataFrame({"rnp_raw": rnp_col, "gen_override": gen_col})
    pairs_df = pairs_df.loc[pairs_df["rnp_raw"].ne("")]
    if pairs_df.empty:
        return []

    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str, str]] = []
    for raw, override in zip(
        pairs_df["rnp_raw"].tolist(),
        pairs_df["gen_override"].tolist(),
    ):
        rnp, general = parse_category_pair(raw, general_override=override)
        if not rnp:
            continue
        key = (rnp.casefold(), general.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append((rnp, general, format_category_pair(rnp, general)))

    return out


def _key_level4(u2: str, u3: str, u4: str) -> str:
    """Ключ справочника ур.2–4 в нижнем регистре (согласовано с проверкой дубликатов в Excel)."""
    return "||".join([_norm_cell(u2).lower(), _norm_cell(u3).lower(), _norm_cell(u4).lower()])


def _key_level3(u2: str, u3: str) -> str:
    return "||".join([_norm_cell(u2).lower(), _norm_cell(u3).lower()])


def _build_level_maps(category_df: pd.DataFrame):
    """
    Словари ключ -> (категория РНП, категория Общего РНП) для ур.4 / ур.3 / ур.2.
    """
    map4: dict[str, tuple[str, str]] = {}
    map3: dict[str, tuple[str, str]] = {}
    map2: dict[str, tuple[str, str]] = {}
    has_general_col = CATEGORY_COLUMN_GENERAL in category_df.columns

    for _, row in category_df.iterrows():
        u2 = _norm_cell(row.get("Товар ур.2"))
        u3 = _norm_cell(row.get("Товар ур.3"))
        u4 = _norm_cell(row.get("Товар ур.4")) if "Товар ур.4" in category_df.columns else ""
        override = (
            _norm_cell(row.get(CATEGORY_COLUMN_GENERAL)) if has_general_col else ""
        )
        rnp, general = parse_category_pair(
            row.get(CATEGORY_COLUMN_RNP, ""), general_override=override
        )
        if not rnp:
            continue
        pair = (rnp, general)

        if not _is_empty_level(u4):
            map4[_key_level4(u2, u3, u4)] = pair
        elif not _is_empty_level(u3):
            map3[_key_level3(u2, u3)] = pair
        else:
            map2[u2.lower()] = pair

    return map4, map3, map2


def get_level_maps(category_df: pd.DataFrame) -> tuple[dict, dict, dict]:
    """Кэшированные карты уровней товаров для одного датафрейма справочника."""
    cache_key = id(category_df)
    cached = _LEVEL_MAPS_CACHE.get(cache_key)
    if cached is not None:
        return cached
    maps = _build_level_maps(category_df)
    _LEVEL_MAPS_CACHE[cache_key] = maps
    return maps


def reference_product_keys(category_df: pd.DataFrame) -> set[str]:
    """Все ключи товара из справочника (ур.4, ур.3, ур.2), по которым возможно совпадение."""
    m4, m3, m2 = get_level_maps(category_df)
    return set(m4) | set(m3) | set(m2)


def product_matchable(u2, u3, u4, keys: set[str]) -> bool:
    """True, если для тройки (ур.2–4) в справочнике есть подходящий ключ."""
    u2, u3, u4 = _norm_cell(u2), _norm_cell(u3), _norm_cell(u4)
    if u2 and u3 and u4:
        if _key_level4(u2, u3, u4) in keys:
            return True
    if u2 and u3:
        if _key_level3(u2, u3) in keys:
            return True
    if u2 and u2.lower() in keys:
        return True
    return False


def apply_group_mapping(df_sales: pd.DataFrame, df_group: pd.DataFrame) -> pd.DataFrame:
    df_sales = df_sales.copy()
    df_group.columns = df_group.columns.str.strip()
    df_sales.columns = df_sales.columns.str.strip()
    df_sales = df_sales.merge(df_group, on="Магазин", how="left")
    return df_sales


def apply_category_reference(
    df_sales: pd.DataFrame,
    category_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Маппинг: Товар ур.2–4 → «Категория» (РНП) и «Категория товара Общий РНП:».
    В справочнике — одна ячейка «Категория товара РНП:» вида «РНП/Общий РНП».
    """
    df_sales = df_sales.copy()
    category_df = category_df.copy()
    category_df.columns = category_df.columns.str.strip()

    if "Товар ур.4" not in category_df.columns:
        category_df["Товар ур.4"] = ""

    for col in ("Товар ур.2", "Товар ур.3", "Товар ур.4", CATEGORY_COLUMN_RNP):
        category_df[col] = category_df[col].apply(_norm_cell)

    if CATEGORY_COLUMN_GENERAL in category_df.columns:
        category_df[CATEGORY_COLUMN_GENERAL] = category_df[CATEGORY_COLUMN_GENERAL].apply(
            _norm_cell
        )

    map4, map3, map2 = get_level_maps(category_df)

    if "Товар ур.2" not in df_sales.columns or "Товар ур.3" not in df_sales.columns:
        raise ValueError(
            "В данных продаж должны быть столбцы «Товар ур.2» и «Товар ур.3» для сопоставления "
            "со справочником категорий."
        )
    if "Товар ур.4" not in df_sales.columns:
        df_sales["Товар ур.4"] = ""

    u2 = df_sales["Товар ур.2"].map(_norm_cell)
    u3 = df_sales["Товар ур.3"].map(_norm_cell)
    u4 = df_sales["Товар ур.4"].map(_norm_cell)

    key4 = u2.str.lower() + "||" + u3.str.lower() + "||" + u4.str.lower()
    key3 = u2.str.lower() + "||" + u3.str.lower()

    def _map_pairs(keys: pd.Series, mapping: dict) -> tuple[pd.Series, pd.Series]:
        if not mapping:
            empty = pd.Series(pd.NA, index=keys.index)
            return empty, empty.copy()
        pairs = keys.map(mapping)
        rnp = pairs.map(lambda p: p[0] if isinstance(p, tuple) else pd.NA)
        gen = pairs.map(lambda p: p[1] if isinstance(p, tuple) else pd.NA)
        return rnp, gen

    rnp4, gen4 = _map_pairs(key4, map4)
    cat_rnp = rnp4.copy()
    cat_gen = gen4.copy()

    rnp3, gen3 = _map_pairs(key3, map3)
    cat_rnp = cat_rnp.fillna(rnp3)
    cat_gen = cat_gen.fillna(gen3)

    rnp2, gen2 = _map_pairs(u2.str.lower(), map2)
    cat_rnp = cat_rnp.fillna(rnp2)
    cat_gen = cat_gen.fillna(gen2)

    df_sales["Категория"] = cat_rnp.fillna("Прочие товары")
    df_sales[CATEGORY_COLUMN_GENERAL] = cat_gen.fillna("").astype(str)

    return df_sales
