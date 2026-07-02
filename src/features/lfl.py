import pandas as pd
import streamlit as st

from features.categories import apply_category_reference
from features.excise_liquid import (
    CATEGORY_LIQUID_25ML,
    excise_margin_deduction,
)
from features.table_layout import (
    FINANCIAL_TABLE_ROW_HEIGHT_PX,
    compact_dataframe_height,
)
from features.reference_orders import resolve_categories_rnp

LFL_CATEGORY_COL_WIDTH_PX = 200
LFL_METRIC_COL_WIDTH_PX = 112


def _lfl_column_config(table: pd.DataFrame) -> dict:
    config = {
        "Категория": st.column_config.TextColumn(
            "Категория",
            width=LFL_CATEGORY_COL_WIDTH_PX,
        ),
    }
    for column in table.columns:
        if column == "Категория":
            continue
        config[column] = st.column_config.TextColumn(
            column,
            width=LFL_METRIC_COL_WIDTH_PX,
        )
    return config


def render_lfl_block(
    lfl_df: pd.DataFrame,
    categories_df: pd.DataFrame,
    lfl_week: int | None = None,
    report_week: int | None = None,
    category_order_rnp: list[str] | None = None,
    *,
    excise_liquid_lfl_qty: float = 0.0,
    excise_liquid_report_qty: float = 0.0,
    embedded: bool = False,
    prebuilt_table: pd.DataFrame | None = None,
    table_height: int | None = None,
):
    if not embedded:
        st.markdown("---")
        st.subheader("Факторный анализ")
    else:
        st.markdown("**Факторный анализ**")

    table = prebuilt_table
    if table is None:
        table = build_lfl_factor_table(
            lfl_df,
            categories_df,
            lfl_week,
            report_week,
            category_order_rnp,
            excise_liquid_lfl_qty=excise_liquid_lfl_qty,
            excise_liquid_report_qty=excise_liquid_report_qty,
        )
    if table is None:
        if lfl_df is None:
            st.info(
                "Нет данных для факторного анализа "
                "(загрузите продажи с колонкой «Неделя» или отдельный файл)."
            )
        elif categories_df is None:
            st.warning(
                "Для факторного анализа требуется справочник категорий "
                "(лист categories в Google Sheets или categories.xlsx)."
            )
        else:
            st.info("Нет данных для факторного анализа.")
        return

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        height=table_height if table_height is not None else compact_dataframe_height(),
        row_height=FINANCIAL_TABLE_ROW_HEIGHT_PX,
        column_config=_lfl_column_config(table),
    )


def build_lfl_factor_table(
    lfl_df: pd.DataFrame | None,
    categories_df: pd.DataFrame | None,
    lfl_week: int | None = None,
    report_week: int | None = None,
    category_order_rnp: list[str] | None = None,
    *,
    excise_liquid_lfl_qty: float = 0.0,
    excise_liquid_report_qty: float = 0.0,
) -> pd.DataFrame | None:
    """Таблица факторного анализа для UI и Excel."""
    if lfl_df is None or categories_df is None:
        return None

    required_cols = {
        "Товар ур.2",
        "Товар ур.3",
        "Неделя",
        "Продажи с НДС",
        "Маржа",
        "Количество",
    }
    if not required_cols.issubset(lfl_df.columns):
        return None

    df = lfl_df.copy()
    df.columns = df.columns.str.strip()

    for col in ["Товар ур.2", "Товар ур.3"]:
        df[col] = df[col].astype(str).str.strip()
    if "Товар ур.4" in df.columns:
        df["Товар ур.4"] = df["Товар ур.4"].astype(str).str.strip()
    else:
        df["Товар ур.4"] = ""

    numeric_cols = ["Неделя", "Продажи с НДС", "Маржа", "Количество"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["Неделя"])
    df["Неделя"] = df["Неделя"].astype(int)

    if lfl_week is not None and report_week is not None:
        compare_weeks = sorted({int(lfl_week), int(report_week)})
        df = df.loc[df["Неделя"].isin(compare_weeks)].copy()
        if df.empty:
            return None

    df["Продажи с НДС"] = df["Продажи с НДС"].fillna(0.0)
    df["Маржа"] = df["Маржа"].fillna(0.0)
    df["Количество"] = df["Количество"].fillna(0.0)

    df = apply_category_reference(df, categories_df)
    if "Категория" not in df.columns:
        return None

    agg = (
        df.groupby(["Категория", "Неделя"])
        .agg({"Количество": "sum", "Продажи с НДС": "sum", "Маржа": "sum"})
        .reset_index()
    )
    if agg.empty:
        return None

    weeks = sorted(int(w) for w in agg["Неделя"].unique())
    if len(weeks) < 2:
        return None

    ordered_categories = resolve_categories_rnp(category_order_rnp)
    if not ordered_categories:
        ordered_categories = sorted(agg["Категория"].astype(str).unique().tolist())

    metric_info = [
        ("Кол-во", lambda subset: subset["Количество"].sum(), _fmt_int),
        ("Продажи с НДС", lambda subset: subset["Продажи с НДС"].sum(), _fmt_money),
        ("Маржа", lambda subset: subset["Маржа"].sum(), _fmt_money),
    ]

    table_rows = []
    for category in ordered_categories:
        row = {"Категория": category}
        for metric_name, aggregator, formatter in metric_info:
            for week in weeks:
                subset = agg[
                    (agg["Категория"] == category) & (agg["Неделя"] == week)
                ]
                value = _margin_with_excise_liquid(
                    aggregator(subset),
                    category=category,
                    metric_name=metric_name,
                    week=week,
                    lfl_week=lfl_week,
                    report_week=report_week,
                    excise_liquid_lfl_qty=excise_liquid_lfl_qty,
                    excise_liquid_report_qty=excise_liquid_report_qty,
                )
                row[f"{week} {metric_name}"] = formatter(value)
        table_rows.append(row)

    columns = ["Категория"]
    for metric_name, _, _ in metric_info:
        columns.extend([f"{week} {metric_name}" for week in weeks])

    return pd.DataFrame(table_rows, columns=columns)


def _margin_with_excise_liquid(
    value: float,
    *,
    category: str,
    metric_name: str,
    week: int,
    lfl_week: int | None,
    report_week: int | None,
    excise_liquid_lfl_qty: float,
    excise_liquid_report_qty: float,
) -> float:
    """Маржа «Жидкость 25 мл»: вычет × 4,25 по неделе LFL и отчётной."""
    if category != CATEGORY_LIQUID_25ML or metric_name != "Маржа":
        return float(value)
    if lfl_week is not None and week == int(lfl_week):
        return float(value) - excise_margin_deduction(excise_liquid_lfl_qty)
    if report_week is not None and week == int(report_week):
        return float(value) - excise_margin_deduction(excise_liquid_report_qty)
    return float(value)


def _fmt_money(value):
    try:
        return f"{float(value):,.2f}".replace(",", " ").replace(".", ",")
    except (ValueError, TypeError):
        return "0,00"


def _fmt_int(value):
    try:
        return f"{int(round(float(value))):,}".replace(",", " ")
    except (ValueError, TypeError):
        return "0"


def _fmt_percent(value):
    try:
        return f"{float(value) * 100:.1f}%".replace(".", ",")
    except (ValueError, TypeError):
        return "0,0%"
