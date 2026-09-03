"""Блок «Вложенность расходников»: продавцы, магазины, группы."""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from config.constants import (
    PCT_NO_BK_COLUMN_GROUPS,
    PCT_NO_BK_COLUMN_SELLERS,
    PCT_NO_BK_COLUMN_SHOPS,
)
from data.references import REF_PCT_NO_BK, get_reference_label, load_reference

COL_NESTING = "Вложенность"
COL_SELLER = "Продавец"
COL_SHOP = "Магазин"
COL_GROUP = "Группа"

COL_UPLOAD_CASHIER = "Кассир"
COL_UPLOAD_SHOP = "Магазин"
COL_UPLOAD_CHECKS = "количество чеков"
COL_UPLOAD_QTY = "количество товара"

_UPLOAD_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    COL_UPLOAD_CASHIER: (
        COL_UPLOAD_CASHIER,
        "кассир",
        "Кассир (продавец)",
        "кассир (продавец)",
        "Продавец",
        "продавец",
    ),
    COL_UPLOAD_SHOP: (COL_UPLOAD_SHOP, "магазин"),
    COL_UPLOAD_CHECKS: (
        COL_UPLOAD_CHECKS,
        "Количество чеков",
        "количество чеков",
        "кол-во чеков",
        "Кол-во чеков",
        "количесвто чеков",
    ),
    COL_UPLOAD_QTY: (
        COL_UPLOAD_QTY,
        "Количество товара",
        "количество товара",
        "кол-во товара",
        "Кол-во товара",
    ),
}

_TABLE_ROW_HEIGHT_PX = 35
_NAME_COL_WIDTH_PX = 140
_VALUE_COL_WIDTH_PX = 90
_NESTING_DECIMALS = 3


def _resolve_reference_sellers_column(df: pd.DataFrame) -> str | None:
    columns = [str(c).strip() for c in df.columns]
    if PCT_NO_BK_COLUMN_SELLERS in columns:
        return PCT_NO_BK_COLUMN_SELLERS
    for col in columns:
        if "продавц" in col.casefold():
            return col
    return columns[0] if columns else None


def _clean_cashier_label(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    label = str(value).strip()
    if label.lower() in ("nan", "none", "<na>"):
        return ""
    if re.fullmatch(r"-?\d+\.0", label):
        label = label[:-2]
    return label


def _non_empty_series_count(series: pd.Series) -> int:
    normalized = series.map(_clean_cashier_label)
    return int(normalized.ne("").sum())


def _pick_best_column(
    df: pd.DataFrame,
    lower_map: dict[str, str],
    aliases: tuple[str, ...],
    *,
    keyword_hints: tuple[str, ...] = (),
) -> str | None:
    candidates: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        key = alias.casefold()
        if key in lower_map:
            col = lower_map[key]
            if col not in seen:
                candidates.append(col)
                seen.add(col)
    for key, col in lower_map.items():
        if col in seen:
            continue
        if any(hint in key for hint in keyword_hints):
            candidates.append(col)
            seen.add(col)
    if not candidates:
        return None
    return max(candidates, key=lambda col: _non_empty_series_count(df[col]))


def _normalize_label(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip().casefold()


def _normalize_seller_key(value: object) -> str:
    text = _normalize_label(value)
    if not text:
        return ""
    text = re.sub(r"[.\u00b7]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_shop_key(value: object) -> str:
    return _normalize_label(value)


def _fmt_nesting(qty: float, checks: float) -> str:
    """Сумма товара / сумма чеков, формат как у кальянной вложенности."""
    if checks <= 0:
        return ""
    return f"{qty / checks:.{_NESTING_DECIMALS}f}".replace(".", ",")


def _column_names_from_reference(df: pd.DataFrame, column: str) -> list[str]:
    selected = df.loc[:, column]
    if isinstance(selected, pd.DataFrame):
        selected = selected.iloc[:, 0]
    names: list[str] = []
    for val in selected:
        if pd.isna(val):
            continue
        name = str(val).strip()
        if name and name.lower() not in ("nan", "none"):
            names.append(name)
    return names


def _is_totals_label(value: str) -> bool:
    return "итог" in value.casefold()


def _resolve_upload_columns(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df.columns = df.columns.astype(str).str.strip()
    lower_map = {str(c).strip().casefold(): c for c in df.columns}
    resolved: dict[str, str] = {}

    cashier_col = _pick_best_column(
        df,
        lower_map,
        _UPLOAD_COLUMN_ALIASES[COL_UPLOAD_CASHIER],
        keyword_hints=("кассир", "продавец", "сотрудник"),
    )
    if cashier_col is None:
        raise ValueError(f"В файле отсутствует столбец «{COL_UPLOAD_CASHIER}».")
    resolved[COL_UPLOAD_CASHIER] = cashier_col

    shop_col = _pick_best_column(
        df,
        lower_map,
        _UPLOAD_COLUMN_ALIASES[COL_UPLOAD_SHOP],
        keyword_hints=("магазин",),
    )
    if shop_col is None:
        raise ValueError(f"В файле отсутствует столбец «{COL_UPLOAD_SHOP}».")
    resolved[COL_UPLOAD_SHOP] = shop_col

    for canonical, hints in (
        (COL_UPLOAD_CHECKS, ("чеков", "чек")),
        (COL_UPLOAD_QTY, ("товар",)),
    ):
        found = _pick_best_column(
            df,
            lower_map,
            _UPLOAD_COLUMN_ALIASES[canonical],
            keyword_hints=hints,
        )
        if found is None:
            raise ValueError(f"В файле отсутствует столбец «{canonical}».")
        resolved[canonical] = found

    rename = {src: dst for dst, src in resolved.items() if src != dst}
    for src, dst in rename.items():
        if dst in df.columns and src != dst:
            df = df.drop(columns=[dst])
    if rename:
        df = df.rename(columns=rename)
    return df


def _prepare_upload_for_sellers(raw: pd.DataFrame | None) -> pd.DataFrame | None:
    """Строки с кассиром; пустой магазин не отсекается."""
    if raw is None or raw.empty:
        return None
    df = _resolve_upload_columns(raw)
    df[COL_UPLOAD_CHECKS] = pd.to_numeric(df[COL_UPLOAD_CHECKS], errors="coerce").fillna(0)
    df[COL_UPLOAD_QTY] = pd.to_numeric(df[COL_UPLOAD_QTY], errors="coerce").fillna(0)
    df[COL_UPLOAD_SHOP] = df[COL_UPLOAD_SHOP].astype(str).str.strip()
    df[COL_UPLOAD_CASHIER] = df[COL_UPLOAD_CASHIER].map(_clean_cashier_label)
    df = df.loc[
        df[COL_UPLOAD_CASHIER].ne("")
        & ~df[COL_UPLOAD_CASHIER].map(_is_totals_label)
    ]
    if df.empty:
        return None
    df = df.copy()
    df["_seller_key"] = df[COL_UPLOAD_CASHIER].map(_normalize_seller_key)
    df = df.loc[df["_seller_key"].ne("")]
    return df if not df.empty else None


def _prepare_upload_df(raw: pd.DataFrame | None) -> pd.DataFrame | None:
    df = _prepare_upload_for_sellers(raw)
    if df is None:
        return None
    df = df.loc[
        df[COL_UPLOAD_SHOP].ne("")
        & ~df[COL_UPLOAD_SHOP].map(_is_totals_label)
        & ~df[COL_UPLOAD_SHOP].str.casefold().isin(("nan", "none", "<na>"))
    ]
    if df.empty:
        return None
    return df


def _nesting_for_rows(rows: pd.DataFrame) -> str:
    checks = float(rows[COL_UPLOAD_CHECKS].sum())
    qty = float(rows[COL_UPLOAD_QTY].sum())
    return _fmt_nesting(qty, checks)


def _build_shop_group_map(groups_df: pd.DataFrame | None) -> dict[str, str]:
    if groups_df is None or not isinstance(groups_df, pd.DataFrame) or groups_df.empty:
        return {}
    df = groups_df.copy()
    df.columns = df.columns.astype(str).str.strip()
    if COL_SHOP not in df.columns or "Группа" not in df.columns:
        return {}
    mapping: dict[str, str] = {}
    for _, row in df.iterrows():
        shop = str(row[COL_SHOP]).strip()
        group = str(row["Группа"]).strip()
        if shop and group and shop.lower() not in ("nan", "none"):
            mapping[_normalize_shop_key(shop)] = group
    return mapping


def _build_order_table(
    reference_df: pd.DataFrame | None,
    order_column: str,
    name_column: str,
    values_by_key: dict[str, str],
    *,
    key_fn,
) -> pd.DataFrame:
    if reference_df is None or reference_df.empty:
        return pd.DataFrame(columns=[name_column, COL_NESTING])

    df = reference_df.copy()
    df.columns = df.columns.astype(str).str.strip()
    if order_column not in df.columns:
        return pd.DataFrame(columns=[name_column, COL_NESTING])

    names = _column_names_from_reference(df, order_column)
    if not names:
        return pd.DataFrame(columns=[name_column, COL_NESTING])

    values = [values_by_key.get(key_fn(name), "") for name in names]
    return pd.DataFrame({name_column: names, COL_NESTING: values})


def _compute_seller_values(upload_df: pd.DataFrame) -> dict[str, str]:
    prepared = _prepare_upload_for_sellers(upload_df)
    if prepared is None:
        return {}
    out: dict[str, str] = {}
    for seller_key, group in prepared.groupby("_seller_key", sort=False):
        if not seller_key:
            continue
        out[str(seller_key)] = _nesting_for_rows(group)
    return out


def _compute_shop_values(upload_df: pd.DataFrame) -> dict[str, str]:
    prepared = _prepare_upload_df(upload_df)
    if prepared is None:
        return {}
    prepared = prepared.copy()
    prepared["_key"] = prepared[COL_UPLOAD_SHOP].map(_normalize_shop_key)
    prepared = prepared.loc[prepared["_key"].ne("")]
    out: dict[str, str] = {}
    for shop_key, group in prepared.groupby("_key", sort=False):
        out[str(shop_key)] = _nesting_for_rows(group)
    return out


def _compute_group_values(
    upload_df: pd.DataFrame,
    groups_df: pd.DataFrame | None,
) -> dict[str, str]:
    prepared = _prepare_upload_df(upload_df)
    if prepared is None:
        return {}
    shop_group_map = _build_shop_group_map(groups_df)
    if not shop_group_map:
        return {}
    prepared = prepared.copy()
    prepared["_group"] = (
        prepared[COL_UPLOAD_SHOP]
        .map(_normalize_shop_key)
        .map(shop_group_map)
        .map(_normalize_label)
    )
    prepared = prepared.loc[prepared["_group"].ne("")]
    out: dict[str, str] = {}
    for group_key, group in prepared.groupby("_group", sort=False):
        out[str(group_key)] = _nesting_for_rows(group)
    return out


def build_sellers_nesting_table(
    reference_df: pd.DataFrame | None = None,
    upload_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    values = _compute_seller_values(upload_df) if upload_df is not None else {}
    sellers_col = PCT_NO_BK_COLUMN_SELLERS
    if reference_df is not None and not reference_df.empty:
        ref_df = reference_df.copy()
        ref_df.columns = ref_df.columns.astype(str).str.strip()
        sellers_col = _resolve_reference_sellers_column(ref_df) or sellers_col
    return _build_order_table(
        reference_df,
        sellers_col,
        COL_SELLER,
        values,
        key_fn=_normalize_seller_key,
    )


def build_shops_nesting_table(
    reference_df: pd.DataFrame | None = None,
    upload_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    values = _compute_shop_values(upload_df) if upload_df is not None else {}
    return _build_order_table(
        reference_df,
        PCT_NO_BK_COLUMN_SHOPS,
        COL_SHOP,
        values,
        key_fn=_normalize_shop_key,
    )


def build_groups_nesting_table(
    reference_df: pd.DataFrame | None = None,
    upload_df: pd.DataFrame | None = None,
    groups_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    values = (
        _compute_group_values(upload_df, groups_df) if upload_df is not None else {}
    )
    return _build_order_table(
        reference_df,
        PCT_NO_BK_COLUMN_GROUPS,
        COL_GROUP,
        values,
        key_fn=_normalize_label,
    )


def load_pct_no_bk_reference() -> pd.DataFrame | None:
    """Справочник порядка из %_bk; без Streamlit-сообщений (для Excel)."""
    try:
        return load_reference(REF_PCT_NO_BK)
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001
        return None


def build_consumables_nesting_excel_table(
    reference_df: pd.DataFrame | None = None,
    upload_df: pd.DataFrame | None = None,
    groups_df: pd.DataFrame | None = None,
) -> pd.DataFrame | None:
    """Три таблицы в ряд: продавцы, магазины, группы."""
    sellers = build_sellers_nesting_table(reference_df, upload_df)
    shops = build_shops_nesting_table(reference_df, upload_df)
    groups = build_groups_nesting_table(reference_df, upload_df, groups_df)
    if sellers.empty and shops.empty and groups.empty:
        return None

    n = max(len(sellers), len(shops), len(groups), 1)

    def _pad(table: pd.DataFrame) -> pd.DataFrame:
        if table.empty:
            cols = list(table.columns) or ["", COL_NESTING]
            return pd.DataFrame({c: [""] * n for c in cols})
        if len(table) >= n:
            return table.reset_index(drop=True)
        extra = pd.DataFrame(
            {c: [""] * (n - len(table)) for c in table.columns},
        )
        return pd.concat([table.reset_index(drop=True), extra], ignore_index=True)

    sellers = _pad(sellers)
    shops = _pad(shops)
    groups = _pad(groups)
    gap = pd.DataFrame({" ": [""] * n})
    gap2 = pd.DataFrame({"  ": [""] * n})
    return pd.concat([sellers, gap, shops, gap2, groups], axis=1)


def _render_order_table(table: pd.DataFrame, *, name_column: str) -> None:
    if table.empty:
        st.dataframe(table, use_container_width=True, hide_index=True)
        return
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        row_height=_TABLE_ROW_HEIGHT_PX,
        column_config={
            name_column: st.column_config.TextColumn(
                name_column,
                width=_NAME_COL_WIDTH_PX,
            ),
            COL_NESTING: st.column_config.TextColumn(
                COL_NESTING,
                width=_VALUE_COL_WIDTH_PX,
            ),
        },
    )


def render_consumables_nesting_block(
    *,
    upload_df: pd.DataFrame | None = None,
    groups_df: pd.DataFrame | None = None,
    embedded: bool = False,
) -> None:
    """Три мини-таблицы вложенности расходников."""
    try:
        _render_consumables_nesting_block_impl(
            upload_df=upload_df,
            groups_df=groups_df,
            embedded=embedded,
        )
    except Exception as exc:  # noqa: BLE001
        st.error("Ошибка в блоке «Вложенность расходников».")
        st.exception(exc)


def _render_consumables_nesting_block_impl(
    *,
    upload_df: pd.DataFrame | None = None,
    groups_df: pd.DataFrame | None = None,
    embedded: bool = False,
) -> None:
    if not embedded:
        st.markdown("---")
        st.subheader("Вложенность расходников")
    else:
        st.markdown("**Вложенность расходников**")

    if upload_df is not None and upload_df.empty:
        st.warning("Загруженный файл «Вложенность расходников» не содержит данных.")
        upload_df = None

    reference_df = load_pct_no_bk_reference()
    if reference_df is None:
        st.warning(
            f"Справочник «% без БК» не найден ({get_reference_label(REF_PCT_NO_BK)}). "
            "Таблицы будут пустыми."
        )
    else:
        reference_df = reference_df.copy()
        reference_df.columns = reference_df.columns.astype(str).str.strip()
        sellers_col = _resolve_reference_sellers_column(reference_df)
        required_cols = [PCT_NO_BK_COLUMN_SHOPS, PCT_NO_BK_COLUMN_GROUPS]
        required_cols.insert(0, sellers_col or PCT_NO_BK_COLUMN_SELLERS)
        missing = [c for c in required_cols if c not in reference_df.columns]
        if missing:
            st.warning(
                "В справочнике «%_bk» отсутствуют столбцы: "
                + ", ".join(f"«{c}»" for c in missing)
                + "."
            )

    if upload_df is not None:
        try:
            _prepare_upload_for_sellers(upload_df)
        except ValueError as exc:
            st.error(str(exc))
            upload_df = None

    if upload_df is not None and _build_shop_group_map(groups_df) == {}:
        st.info(
            "Справочник магазинов недоступен — таблица групп не будет рассчитана."
        )

    col_sellers, col_shops, col_groups = st.columns([1, 1, 1])
    with col_sellers:
        st.markdown("**Продавцы**")
        _render_order_table(
            build_sellers_nesting_table(reference_df, upload_df),
            name_column=COL_SELLER,
        )
    with col_shops:
        st.markdown("**Магазины**")
        _render_order_table(
            build_shops_nesting_table(reference_df, upload_df),
            name_column=COL_SHOP,
        )
    with col_groups:
        st.markdown("**Группы**")
        _render_order_table(
            build_groups_nesting_table(reference_df, upload_df, groups_df),
            name_column=COL_GROUP,
        )
