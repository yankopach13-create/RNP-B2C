import re
import unicodedata
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from config.constants import (
    CATEGORY_ORDER,
    GROUP_COLORS,
    GROUP_ORDER,
    GROUP_INTERNET_SHOP,
    GROUP_SIGNET_BOOSTERS_NAMES,
    INTERNET_SHOP_CATEGORY_DISPLAY_NAMES,
)
from features.client_segments import compute_segment_revenue
from features.excise_liquid import apply_total_margin_deduction
from features.clients import render_client_block
from features.focus import render_focus_block
from features.reference_orders import (
    ordered_group_labels,
    ordered_shop_labels,
    resolve_categories_rnp,
    resolve_groups_order,
    resolve_shops_order,
)
from features.turnover import prepare_turnover_table


def _ordered_group_columns(
    group_labels,
    groups_order_rnp: list[str] | None = None,
) -> list:
    """Порядок групп: groups_order.xlsx (РНП), иначе GROUP_ORDER из constants."""
    return ordered_group_labels(group_labels, groups_order_rnp)


def render_global_metrics(
    df: pd.DataFrame,
    categories_df: pd.DataFrame = None,
    turnover_90_df: pd.DataFrame = None,
    turnover_week_df: pd.DataFrame = None,
    client_segments_df: pd.DataFrame = None,
    category_order_rnp: list[str] | None = None,
    groups_order_rnp: list[str] | None = None,
    focus_df: pd.DataFrame | None = None,
    shops_order: list[str] | None = None,
    checks_clients_df: pd.DataFrame | None = None,
    report_week: int | None = None,
    excise_liquid_report_qty: float = 0.0,
    turnover_table: pd.DataFrame | None = None,
):
    if df is None or df.empty:
        st.warning("Нет данных для отображения общих метрик.")
        return

    has_category = _can_build_category_sales(df)
    has_financial = _can_build_financial_metrics(df)

    if has_financial or has_category:
        col_fin, col_cat = st.columns([1, 1])

        with col_fin:
            st.subheader("Финансовые метрики")
            if has_financial:
                render_financial_metrics_table(
                    df,
                    client_segments_df,
                    report_week=report_week,
                    groups_order_rnp=groups_order_rnp,
                    excise_liquid_report_qty=excise_liquid_report_qty,
                )
            else:
                st.info("Нет данных для финансовых метрик.")

        with col_cat:
            st.subheader("Продажи категорий")
            if _can_build_category_sales(df):
                render_category_sales_table(
                    df,
                    category_order_rnp,
                    groups_order_rnp,
                )
            else:
                st.info("Нет данных по продажам категорий.")

    if turnover_table is None:
        turnover_table = _build_turnover_summary(
            turnover_90_df,
            turnover_week_df,
            categories_df,
            category_order_rnp,
        )

    df_kwargs = {
        "use_container_width": True,
        "height": "auto",
        "row_height": FINANCIAL_TABLE_ROW_HEIGHT_PX,
    }

    st.divider()
    col_turn, col_focus, col_client = st.columns([1, 1, 1.2])

    with col_turn:
        st.markdown("**Оборачиваемость**")
        if turnover_table is not None:
            st.dataframe(turnover_table, **df_kwargs)
        else:
            st.info("Нет данных для расчёта оборачиваемости.")

    with col_focus:
        render_focus_block(df, focus_df)

    with col_client:
        render_client_block(
            checks_clients_df,
            report_week,
            client_segments=client_segments_df,
            embedded=True,
            row_height=FINANCIAL_TABLE_ROW_HEIGHT_PX,
        )

def render_group_sections(df: pd.DataFrame):
    agg_group = df.groupby("Группа").agg({"Продажи с НДС": "sum", "Маржа": "sum"})
    categories = (
        df.groupby(["Группа", "Категория"])["Количество"]
        .sum()
        .unstack()
        .fillna(0)
        .reindex(columns=CATEGORY_ORDER, fill_value=0)
        .astype(int)
    )

    for idx, group in enumerate(GROUP_ORDER):
        if group not in agg_group.index:
            continue

        exp_color = GROUP_COLORS[idx % len(GROUP_COLORS)]
        st.markdown(
            f"""
            <div style="background-color:{exp_color}; border-radius:8px; padding:5px 13px 5px 12px; margin-bottom:-5px; margin-top:20px;">
                <b>{group}</b> (Сумма продаж с НДС: {_fmt_money(agg_group.loc[group, 'Продажи с НДС'])}, Маржа: {_fmt_money(agg_group.loc[group, 'Маржа'])})
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander("Открыть анализ группы", expanded=False):
            col_l, col_r = st.columns([1, 1.3])

            with col_l:
                df_metrics_group = (
                    pd.DataFrame(
                        {
                            "Показатель": ["Продажи с НДС", "Маржа"],
                            "Значение": [
                                _fmt_money(agg_group.loc[group, "Продажи с НДС"]),
                                _fmt_money(agg_group.loc[group, "Маржа"]),
                            ],
                        }
                    ).set_index("Показатель")
                )
                st.dataframe(df_metrics_group, use_container_width=True)

            with col_r:
                cat_row = categories.loc[group][CATEGORY_ORDER]
                df_cats = pd.DataFrame({"Продажи, шт.": cat_row})
                st.dataframe(df_cats, use_container_width=True)

# ------------------------------------------------------------------
# helpers

VAT_NET_DIVISOR = 1.2  # выручка без НДС при ставке НДС 20%

# Высота таблиц финансовых метрик: видно 3 строки данных + прокрутка
FINANCIAL_TABLE_VISIBLE_ROWS = 3
FINANCIAL_TABLE_ROW_HEIGHT_PX = 35
FINANCIAL_TABLE_HEADER_HEIGHT_PX = 38
# Одинаковая ширина столбцов в «Общие» и «Подразделения»
FINANCIAL_TABLE_COL_GROUP_PX = 200
FINANCIAL_TABLE_COL_METRIC_PX = 220
FINANCIAL_TABLE_COL_VALUE_PX = 130

# Пустые строки между подразделениями в таблицах
FINANCIAL_SUBDIVISION_SPACER_ROWS = 1
CATEGORY_SUBDIVISION_SPACER_ROWS = 3


def _financial_dataframe_height(visible_rows: int = FINANCIAL_TABLE_VISIBLE_ROWS) -> int:
    return FINANCIAL_TABLE_HEADER_HEIGHT_PX + visible_rows * FINANCIAL_TABLE_ROW_HEIGHT_PX


def _full_table_height(row_count: int) -> int:
    """Высота таблицы без внутренней прокрутки (все строки видны)."""
    rows = max(int(row_count), 1)
    return FINANCIAL_TABLE_HEADER_HEIGHT_PX + rows * FINANCIAL_TABLE_ROW_HEIGHT_PX


def _turnover_display_row_count(
    turnover_table: pd.DataFrame | None,
    category_order_rnp: list[str] | None,
) -> int:
    if turnover_table is not None and len(turnover_table) > 0:
        return len(turnover_table)
    ordered = resolve_categories_rnp(category_order_rnp)
    return len(ordered) if ordered else 1


def _financial_metrics_column_config() -> dict:
    """Единые ширины колонок Группа / Показатель / Значение для всех таблиц блока."""
    return {
        "Группа": st.column_config.TextColumn(
            "Группа",
            width=FINANCIAL_TABLE_COL_GROUP_PX,
        ),
        "Показатель": st.column_config.TextColumn(
            "Показатель",
            width=FINANCIAL_TABLE_COL_METRIC_PX,
        ),
        "Значение": st.column_config.TextColumn(
            "Значение",
            width=FINANCIAL_TABLE_COL_VALUE_PX,
        ),
    }


@dataclass
class _FinancialDisplayRow:
    group: str
    metric: str
    value: str
    value_red: bool = False
    metric_bold: bool = False
    spacer: bool = False


def _can_build_financial_metrics(df: pd.DataFrame) -> bool:
    return df is not None and not df.empty and all(
        c in df.columns for c in ("Продажи с НДС", "Маржа")
    )


def _md_pct(margin: float, revenue_vat: float) -> float | None:
    """МД% = маржа / (выручка с НДС / 1,2)."""
    if revenue_vat == 0:
        return None
    return margin / (revenue_vat / VAT_NET_DIVISOR) * 100


def _fmt_fin_int(value: float) -> str:
    try:
        return f"{int(round(float(value))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def _fmt_fin_pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.1f}%".replace(".", ",")


def _triple_metric_rows(group: str, revenue: float, margin: float) -> list[_FinancialDisplayRow]:
    """Три строки: выручка, МД, МД% (название группы только в первой строке)."""
    pct = _md_pct(margin, revenue)
    return [
        _FinancialDisplayRow(group, "Выручка", _fmt_fin_int(revenue)),
        _FinancialDisplayRow("", "МД", _fmt_fin_int(margin)),
        _FinancialDisplayRow("", "МД%", _fmt_fin_pct(pct)),
    ]


def _build_financial_b2c_rows(
    df: pd.DataFrame,
    client_segments_df: pd.DataFrame | None,
    report_week: int | None,
    *,
    excise_liquid_report_qty: float = 0.0,
) -> list[_FinancialDisplayRow]:
    revenue = float(df["Продажи с НДС"].sum())
    margin = apply_total_margin_deduction(
        float(df["Маржа"].sum()), excise_liquid_report_qty
    )
    rows = _triple_metric_rows("B2C", revenue, margin)

    if client_segments_df is not None and report_week is not None:
        target_rev, non_target_rev = compute_segment_revenue(
            client_segments_df, report_week
        )
        target_share = target_rev / revenue * 100 if revenue and target_rev else 0
        non_target_share = (
            non_target_rev / revenue * 100 if revenue and non_target_rev else 0
        )
        rows.extend(
            [
                _FinancialDisplayRow(
                    "", "Выручка целевой АКБ", _fmt_fin_int(target_rev)
                ),
                _FinancialDisplayRow(
                    "", "Удельный вес", _fmt_fin_pct(target_share), metric_bold=True
                ),
                _FinancialDisplayRow(
                    "", "Выручка нецелевой АКБ", _fmt_fin_int(non_target_rev)
                ),
                _FinancialDisplayRow(
                    "",
                    "Удельный вес",
                    _fmt_fin_pct(non_target_share),
                    metric_bold=True,
                ),
            ]
        )
    else:
        rows.extend(
            [
                _FinancialDisplayRow("", "Выручка целевой АКБ", ""),
                _FinancialDisplayRow("", "Удельный вес", "", metric_bold=True),
                _FinancialDisplayRow("", "Выручка нецелевой АКБ", ""),
                _FinancialDisplayRow("", "Удельный вес", "", metric_bold=True),
            ]
        )
    return rows


def _normalize_group_label(name: str) -> str:
    """Единый вид названия группы (пробелы, NBSP, регистр)."""
    s = unicodedata.normalize("NFKC", str(name or ""))
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s.casefold()


def _signet_boosters_norm_keys() -> frozenset[str]:
    return frozenset(
        _normalize_group_label(name) for name in GROUP_SIGNET_BOOSTERS_NAMES
    )


def _is_signet_boosters_group(group: str) -> bool:
    return _normalize_group_label(group) in _signet_boosters_norm_keys()


def _internet_shop_category_norm_keys() -> frozenset[str]:
    return frozenset(
        _normalize_group_label(name) for name in INTERNET_SHOP_CATEGORY_DISPLAY_NAMES
    )


def _is_internet_shop_group(group: str) -> bool:
    return _normalize_group_label(group) == _normalize_group_label(GROUP_INTERNET_SHOP)


def _categories_for_group_subdivision(
    group: str,
    ordered_cats: list[str],
) -> list[str]:
    """Для интернет-магазина в подразделениях — только Под-системы и Расходники."""
    if not _is_internet_shop_group(group):
        return ordered_cats
    allowed = _internet_shop_category_norm_keys()
    return [cat for cat in ordered_cats if _normalize_group_label(cat) in allowed]


def _signet_boosters_all_zero_financial(agg: pd.DataFrame, group: str) -> bool:
    if group not in agg.index:
        return True
    revenue = float(agg.loc[group, "Продажи с НДС"])
    margin = float(agg.loc[group, "Маржа"])
    return revenue == 0 and margin == 0


def _append_subdivision_spacers(
    rows: list[_FinancialDisplayRow],
    count: int,
) -> None:
    for _ in range(count):
        rows.append(_FinancialDisplayRow("", "", "", spacer=True))


def _filter_groups_for_financial_subdivisions(
    group_cols: list[str],
    financial_agg: pd.DataFrame,
) -> list[str]:
    """
    Signet Boosters: скрыть только если выручка и маржа нулевые.
    При ненулевых продажах — показать в финансовых подразделениях.
    """
    result: list[str] = []
    for group in group_cols:
        if _is_signet_boosters_group(group) and _signet_boosters_all_zero_financial(
            financial_agg, group
        ):
            continue
        result.append(group)
    return result


def _filter_groups_for_category_subdivisions(group_cols: list[str]) -> list[str]:
    """
    Signet Boosters никогда не выводятся в «Подразделения» продаж категорий
    (в «Общие» они уже входят через суммирование по всем магазинам).
    """
    return [g for g in group_cols if not _is_signet_boosters_group(g)]


def _build_financial_group_rows(
    df: pd.DataFrame,
    groups_order_rnp: list[str] | None = None,
) -> list[_FinancialDisplayRow]:
    if "Группа" not in df.columns:
        return []

    agg = df.groupby("Группа")[["Продажи с НДС", "Маржа"]].sum()
    group_cols = _filter_groups_for_financial_subdivisions(
        resolve_groups_order(groups_order_rnp),
        agg,
    )
    rows: list[_FinancialDisplayRow] = []
    for idx, group in enumerate(group_cols):
        if idx > 0:
            _append_subdivision_spacers(rows, FINANCIAL_SUBDIVISION_SPACER_ROWS)
        if group in agg.index:
            revenue = float(agg.loc[group, "Продажи с НДС"])
            margin = float(agg.loc[group, "Маржа"])
        else:
            revenue, margin = 0.0, 0.0
        rows.extend(_triple_metric_rows(str(group), revenue, margin))
    return rows


def _financial_rows_to_dataframe(
    rows: list[_FinancialDisplayRow],
) -> tuple[pd.DataFrame, list[str]]:
    """Колонки: Группа, Показатель, Значение. row_styles: normal | red | spacer."""
    table = pd.DataFrame(
        {
            "Группа": [r.group for r in rows],
            "Показатель": [r.metric for r in rows],
            "Значение": [r.value for r in rows],
        }
    )
    row_styles = [_financial_row_style_kind(r) for r in rows]
    return table, row_styles


def _financial_row_style_kind(row: _FinancialDisplayRow) -> str:
    if row.spacer:
        return "spacer"
    if row.metric_bold:
        return "weight"
    if row.value_red:
        return "red"
    return "normal"


def _style_financial_metrics_table(table: pd.DataFrame, row_styles: list[str]):
    """Жирная группа в первой строке блока, удельный вес — жирный, значения вправо."""

    def row_style(row: pd.Series) -> list[str]:
        kind = row_styles[row.name] if row.name < len(row_styles) else "normal"
        if kind == "spacer":
            return ["", "", ""]
        group_css = (
            "font-weight: 600"
            if str(row["Группа"]).strip() and str(row["Показатель"]).strip()
            else ""
        )
        metric_css = ""
        if kind == "weight":
            metric_css = "font-weight: 700"
        elif str(row["Показатель"]).strip() and not str(row["Группа"]).strip():
            metric_css = "font-weight: 600"
        value_css = "text-align: right"
        if kind == "red":
            value_css += "; color: #c00000"
        return [group_css, metric_css, value_css]

    return table.style.apply(row_style, axis=1)


def render_financial_metrics_table(
    df: pd.DataFrame,
    client_segments_df: pd.DataFrame = None,
    report_week: int | None = None,
    groups_order_rnp: list[str] | None = None,
    *,
    excise_liquid_report_qty: float = 0.0,
) -> None:
    """Две таблицы: общие показатели и подразделения (st.dataframe, можно копировать)."""
    if not _can_build_financial_metrics(df):
        st.info("Нет данных для финансовых метрик.")
        return

    b2c_rows = _build_financial_b2c_rows(
        df,
        client_segments_df,
        report_week,
        excise_liquid_report_qty=excise_liquid_report_qty,
    )
    general_table, general_styles = _financial_rows_to_dataframe(b2c_rows)
    st.caption("Общие")
    _render_financial_dataframe(general_table, general_styles)

    group_rows = _build_financial_group_rows(df, groups_order_rnp)
    if not group_rows:
        return

    groups_table, groups_styles = _financial_rows_to_dataframe(group_rows)
    st.caption("Подразделения")
    _render_financial_dataframe(groups_table, groups_styles)


def _render_financial_dataframe(table: pd.DataFrame, row_styles: list[str]) -> None:
    """Таблица с прокруткой; в полноэкранном режиме — все строки."""
    st.dataframe(
        _style_financial_metrics_table(table, row_styles),
        use_container_width=True,
        hide_index=True,
        column_config=_financial_metrics_column_config(),
        height="auto",
        row_height=FINANCIAL_TABLE_ROW_HEIGHT_PX,
    )


def _can_build_category_sales(df: pd.DataFrame) -> bool:
    return (
        df is not None
        and not df.empty
        and "Категория" in df.columns
        and "Количество" in df.columns
    )


def _category_totals(df: pd.DataFrame) -> pd.Series:
    return df.groupby("Категория")["Количество"].sum()


def _build_category_sales_general_rows(
    df: pd.DataFrame,
    category_order_rnp: list[str] | None,
) -> list[_FinancialDisplayRow]:
    """Общие продажи: все категории из справочника порядка, в порядке столбца РНП."""
    totals = _category_totals(df)
    ordered = resolve_categories_rnp(category_order_rnp)
    rows: list[_FinancialDisplayRow] = []
    for idx, cat in enumerate(ordered):
        qty = float(totals[cat]) if cat in totals.index else 0.0
        rows.append(
            _FinancialDisplayRow(
                "Общие" if idx == 0 else "",
                str(cat),
                _fmt_int(qty),
            )
        )
    return rows


def _build_category_sales_group_rows(
    df: pd.DataFrame,
    category_order_rnp: list[str] | None,
    groups_order_rnp: list[str] | None = None,
) -> list[_FinancialDisplayRow]:
    """Продажи по категориям в разрезе подразделений."""
    if "Группа" not in df.columns:
        return []

    pivot = (
        df.groupby(["Категория", "Группа"])["Количество"]
        .sum()
        .unstack(fill_value=0)
    )
    booster_cols = [c for c in pivot.columns if _is_signet_boosters_group(c)]
    if booster_cols:
        pivot = pivot.drop(columns=booster_cols, errors="ignore")

    ordered_cats = resolve_categories_rnp(category_order_rnp)
    pivot = pivot.reindex(index=ordered_cats, fill_value=0)
    group_cols = _filter_groups_for_category_subdivisions(
        resolve_groups_order(groups_order_rnp),
    )
    group_cols = [g for g in group_cols if not _is_signet_boosters_group(g)]

    rows: list[_FinancialDisplayRow] = []
    visible_idx = 0
    for group in group_cols:
        if _is_signet_boosters_group(group):
            continue
        if visible_idx > 0:
            _append_subdivision_spacers(rows, CATEGORY_SUBDIVISION_SPACER_ROWS)
        visible_idx += 1
        cats_for_group = _categories_for_group_subdivision(group, ordered_cats)
        for cidx, cat in enumerate(cats_for_group):
            qty = float(pivot.loc[cat, group]) if group in pivot.columns else 0.0
            rows.append(
                _FinancialDisplayRow(
                    str(group) if cidx == 0 else "",
                    str(cat),
                    _fmt_int(qty),
                )
            )
    return rows


def render_category_sales_table(
    df: pd.DataFrame,
    category_order_rnp: list[str] | None = None,
    groups_order_rnp: list[str] | None = None,
) -> None:
    """Две таблицы: общие и подразделения (Группа / Показатель / Значение)."""
    if not _can_build_category_sales(df):
        st.info("Нет данных по продажам категорий.")
        return

    ordered = resolve_categories_rnp(category_order_rnp)
    if not ordered:
        st.warning(
            "Справочник порядка категорий пуст. Добавьте строки в столбец «РНП» "
            "в лист category_order (Google Sheets) или category_order.xlsx."
        )
        return

    general_rows = _build_category_sales_general_rows(df, category_order_rnp)
    general_table, general_styles = _financial_rows_to_dataframe(general_rows)
    st.caption("Общие")
    _render_financial_dataframe(general_table, general_styles)

    group_rows = _build_category_sales_group_rows(
        df, category_order_rnp, groups_order_rnp
    )
    if not group_rows:
        return

    groups_table, groups_styles = _financial_rows_to_dataframe(group_rows)
    st.caption("Подразделения")
    _render_financial_dataframe(groups_table, groups_styles)


def _build_turnover_summary(
    turnover_90_df: pd.DataFrame,
    turnover_week_df: pd.DataFrame,
    categories_df: pd.DataFrame | None,
    category_order_rnp: list[str] | None = None,
) -> pd.DataFrame | None:
    if categories_df is None:
        return None

    table_90 = _build_turnover_display(turnover_90_df, categories_df, 90)
    table_7 = _build_turnover_display(turnover_week_df, categories_df, 7)

    if table_90 is None and table_7 is None:
        return None

    data = {}

    if table_90 is not None:
        for _, row in table_90.iterrows():
            data.setdefault(row["Категория"], {})["90 дней"] = row["Оборачиваемость"]

    if table_7 is not None:
        for _, row in table_7.iterrows():
            data.setdefault(row["Категория"], {})["7 дней"] = row["Оборачиваемость"]

    result = (
        pd.DataFrame.from_dict(data, orient="index")[["90 дней", "7 дней"]]
        if data
        else pd.DataFrame(columns=["90 дней", "7 дней"])
    )

    ordered = resolve_categories_rnp(category_order_rnp)
    if ordered:
        result = result.reindex(index=ordered)
    elif not result.empty:
        result = result.sort_index()

    return result.fillna("")

def _build_shop_economy_table(
    df: pd.DataFrame,
    shops_order: list[str] | None = None,
) -> pd.DataFrame:
    if df.empty or "Магазин" not in df.columns:
        return pd.DataFrame(columns=["Продажи с НДС"])

    shop_sales = df.groupby("Магазин")["Продажи с НДС"].sum()
    shop_sales.index = shop_sales.index.astype(str).str.strip()
    shop_sales = shop_sales[shop_sales.index != ""]

    if shop_sales.empty and not resolve_shops_order(shops_order):
        return pd.DataFrame(columns=["Продажи с НДС"])

    display_order = resolve_shops_order(shops_order)
    shops_in_data = set(shop_sales.index)
    ordered_shops = ordered_shop_labels(shops_in_data | set(display_order), shops_order)

    rows = []
    for shop in ordered_shops:
        value = shop_sales.get(shop)
        rows.append({
            "Магазин": shop,
            "Продажи с НДС": _fmt_number(value),
        })

    return pd.DataFrame(rows).set_index("Магазин")    

def _build_turnover_display(
    turnover_df: pd.DataFrame,
    categories_df: pd.DataFrame,
    period_days: int,
) -> pd.DataFrame | None:
    """Формирует таблицу оборачиваемости для отображения."""

    if turnover_df is None or turnover_df.empty:
        return None

    if categories_df is None:
        return None

    try:
        table = prepare_turnover_table(
            df_inventory=turnover_df,
            categories_df=categories_df,
            period_days=period_days,
        )
    except ValueError as exc:
        st.warning(str(exc))
        return None

    if table.empty:
        return None

    display_df = table.reset_index().rename(
        columns={
            "Категория": "Категория",
            "Оборачиваемость, дни": "Оборачиваемость",
        }
    )
    display_df["Оборачиваемость"] = display_df["Оборачиваемость"].apply(_fmt_turnover)
    return display_df


def _fmt_turnover(value) -> str:
    if value is None or value == "":
        return ""

    if isinstance(value, str):
        try:
            value = float(value.replace(",", ".").replace(" ", ""))
        except ValueError:
            return ""

    if pd.isna(value):
        return ""

    try:
        return f"{int(round(float(value)))}"
    except (TypeError, ValueError):
        return ""
    
def _fmt_int(value):
    try:
        return f"{int(round(float(value))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def _fmt_money(value):
    try:
        return f"{float(value):,.2f}".replace(",", " ").replace(".", ",")
    except (TypeError, ValueError):
        return "0,00"


def _fmt_number(value):
    if value is None:
        return ""

    try:
        if float(value).is_integer():
            return f"{int(value):,}".replace(",", " ")
        return f"{float(value):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return ""
