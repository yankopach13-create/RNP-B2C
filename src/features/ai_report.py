"""Блок «ИИ отчёт B2C» — метрики из РНП B2C в заданном порядке (как Общий РНП)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from features.client_segments import compute_segment_revenue
from features.clients import COL_CUMULATIVE, COL_METRIC
from features.general_rnp import (
    COL_REPORT_WEEK_PREFIX,
    _apply_sheets_number_format,
    _financial_values,
    _load_client_metrics,
    _resolve_report_week,
    _split_sales_frames,
)
from features.metrics import (
    _can_build_category_sales,
    _category_totals,
    _fmt_fin_int,
    _fmt_int,
)

# Подпись в ИИ отчёте → ключ категории РНП (столбец «Категория» в продажах).
_AI_CATEGORY_MAP: list[tuple[str, str]] = [
    ("Одноразовые электронные сигареты ( 2 мл )", "ОЭС 2 мл"),
    ("Одноразовые электронные сигареты ( 10 мл )", "ОЭС 10 мл"),
    ("Жидкость 25 мл.", "Жидкость 25 мл"),
    ("Под-системы", "Под-системы"),
    ("Расходники", "Расходники"),
    ("Закрытые под-системы", "Закрытая под-система"),
    ("Картриджи с жидкостью", "Картриджи с жидкостью"),
    ("Никотиновые паучи", "Никотиновые паучи"),
    ("БКС", "БКС"),
    ("Прочие товары", "Прочие товары"),
]

_AI_AVG_CHECK_METRICS = frozenset(
    {
        "Средний чек всех клиентов",
        "средний чек клиентов  с бонусной картой",
        "средний чек клиентов без бонусной карты",
    }
)

_METRIC_CUMULATIVE_ONLY = "Клиенты с бонусной картой"


def render_ai_report_b2c(
    sales_df: pd.DataFrame | None,
    checks_clients_df: pd.DataFrame | None,
    *,
    client_segments_df: pd.DataFrame | None = None,
    report_week: int | None = None,
    excise_liquid_report_qty: float = 0.0,
) -> None:
    """Таблица метрик ИИ отчёта: Метрика / Накопительно / Отчётная неделя."""
    report_week = _resolve_report_week(sales_df, checks_clients_df, report_week)
    week_col = (
        f"{COL_REPORT_WEEK_PREFIX} ({report_week})"
        if report_week is not None
        else COL_REPORT_WEEK_PREFIX
    )

    table = build_ai_report_table(
        sales_df,
        checks_clients_df,
        client_segments_df=client_segments_df,
        report_week=report_week,
        week_column_label=week_col,
        excise_liquid_report_qty=excise_liquid_report_qty,
    )
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            COL_METRIC: st.column_config.TextColumn(COL_METRIC, width=320),
            COL_CUMULATIVE: st.column_config.TextColumn(COL_CUMULATIVE, width=120),
            week_col: st.column_config.TextColumn(week_col, width=140),
        },
    )


def build_ai_report_table(
    sales_df: pd.DataFrame | None,
    checks_clients_df: pd.DataFrame | None,
    *,
    client_segments_df: pd.DataFrame | None = None,
    report_week: int | None = None,
    week_column_label: str | None = None,
    excise_liquid_report_qty: float = 0.0,
) -> pd.DataFrame:
    """Собирает строки ИИ отчёта, копируя значения из расчётов РНП B2C."""
    report_week = _resolve_report_week(sales_df, checks_clients_df, report_week)
    week_col = week_column_label or (
        f"{COL_REPORT_WEEK_PREFIX} ({report_week})"
        if report_week is not None
        else COL_REPORT_WEEK_PREFIX
    )

    client_metrics = _load_client_metrics(
        checks_clients_df, client_segments_df, report_week
    )
    df_cum, df_week = _split_sales_frames(sales_df, report_week)
    totals_cum = _category_totals(df_cum) if _can_build_category_sales(df_cum) else None
    totals_week = (
        _category_totals(df_week) if _can_build_category_sales(df_week) else None
    )

    target_rev_week = non_target_rev_week = ""
    if client_segments_df is not None and report_week is not None:
        target_rev, non_target_rev = compute_segment_revenue(
            client_segments_df, report_week
        )
        target_rev_week = _fmt_fin_int(target_rev)
        non_target_rev_week = _fmt_fin_int(non_target_rev)

    rev_c, md_c, pct_c = _financial_values(df_cum)
    rev_w, md_w, pct_w = _financial_values(
        df_week, excise_liquid_report_qty=excise_liquid_report_qty
    )

    rows: list[list[str]] = []

    def empty_row(label: str) -> None:
        rows.append([label, "", ""])

    def client_row(label: str, cum_key: str | None, week_key: str | None) -> None:
        cum = client_metrics.get(cum_key, "") if cum_key else ""
        wk = client_metrics.get(week_key, "") if week_key else ""
        rows.append([label, cum, wk])

    empty_row("Новые клиенты")
    empty_row("Вернувшиеся клиенты")
    empty_row("Потерянные клиенты")
    empty_row("Активная клиенсткая база")
    client_row("Целевая клиентская база", "target_akb_cumulative", "target_akb_week")
    client_row(
        "Нецелевая клиентская база",
        "non_target_akb_cumulative",
        "non_target_akb_week",
    )
    client_row("Клиенты с бонусной картой", "clients_bk_cumulative", "clients_bk_week")
    empty_row("CSI")
    empty_row("CLI возврат")
    empty_row("CLI рекомендация")
    rows.append(["Продажи с НДС", rev_c, rev_w])
    rows.append(["Маржа", md_c, md_w])
    rows.append(["% Маржи", pct_c, pct_w])
    rows.append(["Продажи с НДС Целевых клиентов", "", target_rev_week])
    rows.append(["Продажи с НДС Нецелевых клиентов", "", non_target_rev_week])
    client_row("Кол-во чеков общее", None, "total_checks")
    client_row("Кол-во чеков с бонусной картой", None, "checks_with_bk")
    client_row("Кол-во чеков без бонусной карты", None, "checks_without_bk")
    client_row("Средний чек всех клиентов", None, "sch")
    client_row("средний чек клиентов  с бонусной картой", None, "sch_bk")
    client_row("средний чек клиентов без бонусной карты", None, "sch_no_bk")
    client_row("Начислено бонусов", None, "credited")
    client_row("Списано бонусов", None, "spent")

    for label, rnp_cat in _AI_CATEGORY_MAP:
        rows.append(
            [
                label,
                _category_qty(totals_cum, rnp_cat),
                _category_qty(totals_week, rnp_cat),
            ]
        )

    table = pd.DataFrame(rows, columns=[COL_METRIC, COL_CUMULATIVE, week_col])
    table = _cumulative_only_clients_bk(table)
    return _apply_sheets_number_format(
        table,
        (COL_CUMULATIVE, week_col),
        avg_check_metrics=_AI_AVG_CHECK_METRICS,
    )


def _category_qty(totals: pd.Series | None, category: str) -> str:
    if totals is None:
        return ""
    if category not in totals.index:
        return _fmt_int(0)
    return _fmt_int(float(totals[category]))


def _cumulative_only_clients_bk(df: pd.DataFrame) -> pd.DataFrame:
    """В «Накопительно» оставляем значение только у «Клиенты с бонусной картой»."""
    out = df.copy()
    if COL_CUMULATIVE not in out.columns or COL_METRIC not in out.columns:
        return out
    keep = out[COL_METRIC].astype(str).str.strip() == _METRIC_CUMULATIVE_ONLY
    out.loc[~keep, COL_CUMULATIVE] = ""
    return out
