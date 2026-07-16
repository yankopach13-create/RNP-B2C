"""Блок «ИИ отчёт B2C» — метрики из РНП B2C в заданном порядке (как Общий РНП)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from features.client_segments import compute_segment_revenue
from features.clients import COL_METRIC
from features.general_rnp import (
    COL_REPORT_WEEK_PREFIX,
    _apply_sheets_number_format,
    _financial_values,
    _load_client_metrics,
    _resolve_report_week,
    _split_sales_frames,
    can_build_general_category_sales,
    category_qty_from_totals,
    general_category_totals,
)
from features.metrics import _fmt_fin_int

# Фиксированный список категорий ИИ отчёта (под «Списано бонусов»).
# Значения — как в Общем РНП (столбец «Категория товара Общий РНП:»), без Oxva stick
# и без агрегата «Кальянная продукция» (только «Кальянные смеси»).
_AI_CATEGORY_METRIC_ROWS: list[tuple[str, str | tuple[str, ...]]] = [
    ("ОЭС 2 мл, шт.", "ОЭС 2 мл"),
    ("ОЭС 4 мл, шт.", "ОЭС 4 мл"),
    ("ОЭС 10 мл, шт", "ОЭС 10 мл"),
    ("Жидкость 25 мл, шт.", "Жидкость 25 мл"),
    ("Pod-системы, шт.", "Под-системы"),
    ("Расходники, шт.", "Расходники"),
    ("Закрытые pod-системы, шт.", "Закрытая под-система"),
    ("Картриджи с жидкостью, шт.", "Картриджи с жидкостью"),
    ("Никотиновые паучи, шт.", "Никотиновые паучи"),
    ("Кальянные смеси", "Кальянные смеси"),
    ("Прочие товары, шт.", "Прочие товары"),
]

_AI_AVG_CHECK_METRICS = frozenset(
    {
        "Средний чек всех клиентов",
        "средний чек клиентов  с бонусной картой",
        "средний чек клиентов без бонусной карты",
    }
)


def ai_category_metric_rows() -> list[tuple[str, str | tuple[str, ...]]]:
    """Строки количества в ИИ отчёте: (подпись, ключ суммирования Общего РНП)."""
    return list(_AI_CATEGORY_METRIC_ROWS)


def render_ai_report_b2c(
    sales_df: pd.DataFrame | None,
    checks_clients_df: pd.DataFrame | None,
    *,
    client_segments_df: pd.DataFrame | None = None,
    report_week: int | None = None,
    excise_liquid_report_qty: float = 0.0,
) -> None:
    """Таблица метрик ИИ отчёта: Метрика / Отчётная неделя."""
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
    _, df_week = _split_sales_frames(sales_df, report_week)
    totals_week = (
        general_category_totals(df_week)
        if can_build_general_category_sales(df_week)
        else None
    )

    target_rev_week = non_target_rev_week = ""
    if client_segments_df is not None and report_week is not None:
        target_rev, non_target_rev = compute_segment_revenue(
            client_segments_df, report_week
        )
        target_rev_week = _fmt_fin_int(target_rev)
        non_target_rev_week = _fmt_fin_int(non_target_rev)

    rev_w, md_w, pct_w = _financial_values(
        df_week, excise_liquid_report_qty=excise_liquid_report_qty
    )

    rows: list[list[str]] = []

    def empty_row(label: str) -> None:
        rows.append([label, ""])

    def client_row(label: str, week_key: str | None) -> None:
        wk = client_metrics.get(week_key, "") if week_key else ""
        rows.append([label, wk])

    empty_row("Новые клиенты")
    empty_row("Вернувшиеся клиенты")
    empty_row("Потерянные клиенты")
    empty_row("Активная клиенсткая база")
    client_row("Целевая клиентская база", "target_akb_week")
    client_row("Нецелевая клиентская база", "non_target_akb_week")
    client_row("Клиенты с бонусной картой", "clients_bk_week")
    empty_row("CSI")
    empty_row("CLI возврат")
    empty_row("CLI рекомендация")
    rows.append(["Продажи с НДС", rev_w])
    rows.append(["Маржа", md_w])
    rows.append(["% Маржи", pct_w])
    rows.append(["Продажи с НДС Целевых клиентов", target_rev_week])
    rows.append(["Продажи с НДС Нецелевых клиентов", non_target_rev_week])
    client_row("Кол-во чеков общее", "total_checks")
    client_row("Кол-во чеков с бонусной картой", "checks_with_bk")
    client_row("Кол-во чеков без бонусной карты", "checks_without_bk")
    client_row("Средний чек всех клиентов", "sch")
    client_row("средний чек клиентов  с бонусной картой", "sch_bk")
    client_row("средний чек клиентов без бонусной карты", "sch_no_bk")
    client_row("Начислено бонусов", "credited")
    client_row("Списано бонусов", "spent")

    for label, source in ai_category_metric_rows():
        rows.append([label, category_qty_from_totals(totals_week, source)])

    table = pd.DataFrame(rows, columns=[COL_METRIC, week_col])
    return _apply_sheets_number_format(
        table,
        (week_col,),
        avg_check_metrics=_AI_AVG_CHECK_METRICS,
    )
