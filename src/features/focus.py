import re
import pandas as pd
import streamlit as st
from config.constants import GROUP_ORDER
from data.references import REF_FOCUS, get_reference_label

EXCLUDED_GROUPS = {"Интернет-магазин"}
_INVALID_LABELS = {"", "nan", "none", "<na>"}


def _is_valid_label(value) -> bool:
    if value is None or pd.isna(value):
        return False
    text = str(value).strip()
    return bool(text) and text.casefold() not in _INVALID_LABELS


def _ordered_focus_categories(categories) -> list[str]:
    return list(dict.fromkeys(cat for cat in categories if _is_valid_label(cat)))


def render_focus_block(
    df_sales: pd.DataFrame,
    focus_df: pd.DataFrame,
    table_height: int | None = None,
):
    st.markdown("**Фокусные позиции**")

    display_df = build_focus_display_df(df_sales, focus_df)
    if display_df is None:
        if focus_df is None:
            st.info(
                f"Справочник фокусных позиций не найден ({get_reference_label(REF_FOCUS)})."
            )
        else:
            st.info("Нет данных для отображения фокусных позиций.")
        return

    df_kwargs: dict = {"use_container_width": True, "hide_index": True}
    if table_height is not None:
        from features.metrics import FINANCIAL_TABLE_ROW_HEIGHT_PX

        df_kwargs["height"] = table_height
        df_kwargs["row_height"] = FINANCIAL_TABLE_ROW_HEIGHT_PX
    st.dataframe(display_df, **df_kwargs)


def build_focus_display_df(
    df_sales: pd.DataFrame,
    focus_df: pd.DataFrame | None,
) -> pd.DataFrame | None:
    """Таблица фокусных позиций для UI и Excel."""
    if focus_df is None:
        return None

    required_cols = {"Фокусные позиции ур. 3", "Категория фокуса"}
    if not required_cols.issubset(focus_df.columns):
        return None

    focus_df = focus_df.copy()
    focus_df.columns = focus_df.columns.str.strip()
    focus_df["Фокусные позиции ур. 3"] = (
        focus_df["Фокусные позиции ур. 3"].astype(str).str.strip()
    )
    focus_df["Категория фокуса"] = (
        focus_df["Категория фокуса"].astype(str).str.strip()
    )

    category_order_focus = _ordered_focus_categories(
        focus_df["Категория фокуса"].dropna().astype(str).str.strip().tolist()
    )
    if not category_order_focus:
        return None

    names_focus_set = {
        str(x).strip()
        for x in focus_df["Фокусные позиции ур. 3"]
        if _is_valid_label(x)
    }
    cat_map_focus = {
        str(pos).strip(): cat
        for pos, cat in zip(
            focus_df["Фокусные позиции ур. 3"], focus_df["Категория фокуса"]
        )
        if _is_valid_label(pos) and _is_valid_label(cat)
    }

    # Поиск фокусных позиций по уровню 3 и (при наличии столбца) по уровню 4
    sales_l3 = df_sales["Товар ур.3"].astype(str).str.strip()
    mask_l3 = sales_l3.isin(names_focus_set)
    if "Товар ур.4" in df_sales.columns:
        sales_l4 = df_sales["Товар ур.4"].astype(str).str.strip()
        mask_l4 = sales_l4.isin(names_focus_set)
        focus_mask = mask_l3 | mask_l4
    else:
        focus_mask = mask_l3

    df_focus_sales = df_sales[focus_mask].copy() if names_focus_set else pd.DataFrame()

    if not df_focus_sales.empty:
        # Категория фокуса: приоритет совпадению по ур.3, иначе по ур.4
        df_focus_sales["_cat_l3"] = (
            df_focus_sales["Товар ур.3"].astype(str).str.strip().map(cat_map_focus)
        )
        if "Товар ур.4" in df_focus_sales.columns:
            df_focus_sales["_cat_l4"] = (
                df_focus_sales["Товар ур.4"].astype(str).str.strip().map(cat_map_focus)
            )
            df_focus_sales["Категория фокуса"] = (
                df_focus_sales["_cat_l3"].fillna(df_focus_sales["_cat_l4"])
            )
            df_focus_sales = df_focus_sales.drop(columns=["_cat_l3", "_cat_l4"])
        else:
            df_focus_sales["Категория фокуса"] = df_focus_sales["_cat_l3"]
            df_focus_sales = df_focus_sales.drop(columns=["_cat_l3"])

        # Приведём названия групп (без изменения регистра)
        df_focus_sales["Группа"] = (
            df_focus_sales["Группа"]
            .astype(str)
            .str.strip()
            .str.replace(r"\s+", " ", regex=True)
        )

        def _normalize_group(value: str) -> str:
            if pd.isna(value):
                return ""
            return re.sub(r"\s+", " ", str(value).strip()).casefold()

        EXCLUDED_GROUPS_NORM = {_normalize_group(g) for g in EXCLUDED_GROUPS}
        group_order_norm_map = {_normalize_group(g): g for g in GROUP_ORDER}

        df_focus_sales["_group_norm"] = df_focus_sales["Группа"].apply(_normalize_group)
        df_focus_sales = df_focus_sales[
            ~df_focus_sales["_group_norm"].isin(EXCLUDED_GROUPS_NORM)
        ]

        if not df_focus_sales.empty:
            df_focus_sales["Группа_отчет"] = df_focus_sales["_group_norm"].map(
                group_order_norm_map
            )
            mask_missing = df_focus_sales["Группа_отчет"].isna()
            df_focus_sales.loc[mask_missing, "Группа_отчет"] = (
                df_focus_sales.loc[mask_missing, "Группа"]
                .fillna("")
                .astype(str)
                .str.strip()
            )

            df_focus_sales = df_focus_sales[
                df_focus_sales["Группа_отчет"].astype(str).str.len() > 0
            ]

    if df_focus_sales.empty:
        pivot = pd.DataFrame(columns=category_order_focus)
    else:
        pivot = (
            df_focus_sales.groupby(["Группа_отчет", "Категория фокуса"])["Количество"]
            .sum()
            .unstack(fill_value=0)
        )

    ordered_categories = list(category_order_focus)
    for cat in pivot.columns:
        if cat not in ordered_categories:
            ordered_categories.append(cat)
    pivot = pivot.reindex(columns=ordered_categories, fill_value=0)

    overall = (
        pivot.sum(axis=0).reindex(ordered_categories, fill_value=0)
        if not pivot.empty
        else pd.Series(0, index=ordered_categories)
    )

    ordered_groups = [g for g in GROUP_ORDER if g in pivot.index]
    extra_groups = [g for g in pivot.index if g not in ordered_groups]
    ordered_groups.extend(extra_groups)

    rows = []

    def append_group_rows(label: str, series: pd.Series):
        first = True
        for category in ordered_categories:
            value = series.get(category, 0)
            rows.append(
                {
                    "Показатель": label if first else "",
                    "Фокусная позиция": category,
                    "Продажи, шт.": _fmt_int(value),
                }
            )
            first = False
        rows.append({"Показатель": "", "Фокусная позиция": "", "Продажи, шт.": ""})

    append_group_rows("Общие показатели", overall)

    for group in ordered_groups:
        group_series = pivot.loc[group] if group in pivot.index else None
        if group_series is not None:
            append_group_rows(group, group_series)

    if rows and all(value == "" for value in rows[-1].values()):
        rows.pop()

    return pd.DataFrame(
        rows, columns=["Показатель", "Фокусная позиция", "Продажи, шт."]
    )


def _fmt_int(value) -> str:
    try:
        return f"{int(round(float(value))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


