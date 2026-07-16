"""Таблица «Общий РНП B2C» — метрики из блока РНП B2C в формате Метрика / Накопительно / Отчётная неделя."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config.constants import CATEGORY_COLUMN_GENERAL
from features.client_segments import compute_segment_client_metrics
from features.clients import (
    COL_CUMULATIVE,
    COL_METRIC,
    COL_SALES,
    COL_SPENT,
    COL_WEEK,
    _clients_bk_week_count,
    _compute_client_metrics,
    _prepare_checks_clients,
)
from features.data_prep import (
    filter_sales_by_report_week,
    filter_sales_cumulative_to_week,
    sales_week_numbers,
)
from features.excise_liquid import apply_total_margin_deduction
from features.metrics import (
    _can_build_category_sales,
    _can_build_financial_metrics,
    _fmt_fin_int,
    _fmt_fin_pct,
    _fmt_int,
    _md_pct,
)
from features.reference_orders import resolve_categories_general

COL_REPORT_WEEK_PREFIX = "Отчётная неделя"

# В «Накопительно» оставляем значение только у этой строки (остальные — пусто).
_METRIC_CUMULATIVE_ONLY = "Клиенты с БК"

# Строки среднего чека: для копирования в Google Таблицы оставляем 2 знака после запятой.
_METRICS_AVG_CHECK_DECIMALS = frozenset({"СЧ", "С БК", "Без БК"})


def _sheets_friendly_cell(
    value: object, *, two_decimal_places: bool = False
) -> str:
    """
    Формат для копирования в Google Таблицы: без группировки тысяч.
    По умолчанию — целое без дробной части; с two_decimal_places — два знака после запятой (запятая).
    Проценты: всегда два знака в числовой части, знак % сохраняется.
    """
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return ""
    if "%" in s:
        num_part = s.split("%", 1)[0].strip()
        num_part = num_part.replace(" ", "").replace("\xa0", "").replace(",", ".")
        try:
            v = float(num_part)
            return f"{v:.2f}%".replace(".", ",")
        except ValueError:
            return s
    collapsed = s.replace(" ", "").replace("\xa0", "")
    try:
        v = float(collapsed.replace(",", "."))
    except ValueError:
        return s
    if two_decimal_places:
        return f"{v:.2f}".replace(".", ",")
    return str(int(round(v)))


def _apply_sheets_number_format(
    df: pd.DataFrame,
    value_columns: tuple[str, ...],
    *,
    avg_check_metrics: frozenset[str] | None = None,
) -> pd.DataFrame:
    """Приводит числовые ячейки: целые без «,00»; дробь только для СЧ/среднего чека и процентов."""
    decimal_labels = avg_check_metrics or _METRICS_AVG_CHECK_DECIMALS
    out = df.copy()
    if COL_METRIC not in out.columns:
        return out
    for col in value_columns:
        if col not in out.columns:
            continue
        for idx in out.index:
            raw = out.at[idx, col]
            metric = str(out.at[idx, COL_METRIC]).strip()
            use_decimals = metric in decimal_labels
            out.at[idx, col] = _sheets_friendly_cell(
                raw, two_decimal_places=use_decimals
            )
    return out


def _cumulative_only_clients_bk(df: pd.DataFrame) -> pd.DataFrame:
    """Столбец «Накопительно»: только «Клиенты с БК», у остальных метрик — пусто."""
    out = df.copy()
    if COL_CUMULATIVE not in out.columns or COL_METRIC not in out.columns:
        return out
    keep = out[COL_METRIC].astype(str).str.strip() == _METRIC_CUMULATIVE_ONLY
    out.loc[~keep, COL_CUMULATIVE] = ""
    return out


# Подпись в Общем РНП → имя категории Общего РНП.
_GENERAL_CATEGORY_MAP: list[tuple[str, str]] = [
    ("ОЭС 2 мл , шт.", "ОЭС 2 мл"),
    ("ОЭС 4 мл, шт.", "ОЭС 4 мл"),
    ("ОЭС 10 мл, шт.", "ОЭС 10 мл"),
    ("Жидкость 25 мл, шт.", "Жидкость 25 мл"),
    ("Под-системы, шт.", "Под-системы"),
    ("Расходники, шт.", "Расходники"),
    ("Закрытые под-системы, шт.", "Закрытая под-система"),
    ("Картриджи с жидкостью, шт.", "Картриджи с жидкостью"),
    ("Никотиновые паучи, шт.", "Никотиновые паучи"),
    ("Кальянная продукция,шт.", "Кальянная продукция"),
    ("Прочие товары, шт.", "Прочие товары"),
]

_GENERAL_HOOKAH_PRODUCT = "Кальянная продукция"
# Сумма для строки «Кальянная продукция» (все варианты имён в продажах).
_GENERAL_HOOKAH_COMPONENTS = (
    "Уголь",
    "Кальян",
    "Кальяны",
    "Кальянные смеси",
    "Аксессуары",
)
# Не выводить в Общем РНП, даже если есть в category_order (устаревшие строки).
_GENERAL_SKIP_CATEGORY_ROWS = frozenset({"БКС", "в т.ч. Кальянные смеси"})


def _is_skipped_general_category(category: str) -> bool:
    text = str(category or "").strip()
    if not text or text in _GENERAL_SKIP_CATEGORY_ROWS:
        return True
    lower = text.casefold()
    return "в т.ч." in lower and "кальян" in lower


def _general_category_source(category: str) -> str | tuple[str, ...]:
    if category == _GENERAL_HOOKAH_PRODUCT:
        return _GENERAL_HOOKAH_COMPONENTS
    return category


def _general_category_metric_rows(
    category_order_general: list[str] | None,
) -> list[tuple[str, str | tuple[str, ...]]]:
    """
    Строки количества в Общем РНП: (подпись, ключ суммирования).
    Строго по столбцу category_order «Общий РНП».
    """
    label_by_source: dict[str, str] = {}
    for label, source in _GENERAL_CATEGORY_MAP:
        label_by_source[source] = label

    order = (
        resolve_categories_general(category_order_general)
        if category_order_general
        else []
    )

    rows: list[tuple[str, str | tuple[str, ...]]] = []
    for gen in order:
        if _is_skipped_general_category(gen):
            continue
        label = label_by_source.get(gen, f"{gen}, шт.")
        rows.append((label, _general_category_source(gen)))
    return rows


def render_general_rnp_b2c(
    sales_df: pd.DataFrame | None,
    checks_clients_df: pd.DataFrame | None,
    *,
    client_segments_df: pd.DataFrame | None = None,
    report_week: int | None = None,
    category_order_general: list[str] | None = None,
    excise_liquid_report_qty: float = 0.0,
) -> None:
    """Одна таблица: метрики РНП B2C + пустые строки по ТЗ."""
    report_week = _resolve_report_week(sales_df, checks_clients_df, report_week)
    week_col = (
        f"{COL_REPORT_WEEK_PREFIX} ({report_week})"
        if report_week is not None
        else COL_REPORT_WEEK_PREFIX
    )

    table = build_general_rnp_table(
        sales_df,
        checks_clients_df,
        client_segments_df=client_segments_df,
        report_week=report_week,
        week_column_label=week_col,
        category_order_general=category_order_general,
        excise_liquid_report_qty=excise_liquid_report_qty,
    )
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            COL_METRIC: st.column_config.TextColumn(COL_METRIC, width=280),
            COL_CUMULATIVE: st.column_config.TextColumn(COL_CUMULATIVE, width=120),
            week_col: st.column_config.TextColumn(week_col, width=140),
        },
    )


def build_general_rnp_table(
    sales_df: pd.DataFrame | None,
    checks_clients_df: pd.DataFrame | None,
    *,
    client_segments_df: pd.DataFrame | None = None,
    report_week: int | None = None,
    week_column_label: str | None = None,
    category_order_general: list[str] | None = None,
    excise_liquid_report_qty: float = 0.0,
) -> pd.DataFrame:
    report_week = _resolve_report_week(sales_df, checks_clients_df, report_week)
    week_col = week_column_label or (
        f"{COL_REPORT_WEEK_PREFIX} ({report_week})"
        if report_week is not None
        else COL_REPORT_WEEK_PREFIX
    )

    client_metrics = _load_client_metrics(
        checks_clients_df, client_segments_df, report_week
    )
    pct_rev_cum, pct_rev_week = _bonus_share_of_revenue(
        checks_clients_df, report_week
    )
    df_cum, df_week = _split_sales_frames(sales_df, report_week)
    totals_general_cum = (
        _general_category_totals(df_cum)
        if _can_build_general_category_sales(df_cum)
        else None
    )
    totals_general_week = (
        _general_category_totals(df_week)
        if _can_build_general_category_sales(df_week)
        else None
    )

    rows: list[list[str]] = []

    def empty_row(label: str) -> None:
        rows.append([label, "", ""])

    def client_row(label: str, cum_key: str | None, week_key: str | None) -> None:
        cum = client_metrics.get(cum_key, "") if cum_key else ""
        wk = client_metrics.get(week_key, "") if week_key else ""
        rows.append([label, cum, wk])

    empty_row("CSI")
    empty_row("CLI")
    client_row("Клиенты с БК", "clients_bk_cumulative", "clients_bk_week")
    client_row("Клиенты без БК", None, "clients_no_bk_week")
    client_row("Кол-во чеков", None, "total_checks")
    client_row("СЧ", None, "sch")
    client_row("С БК", None, "sch_bk")
    client_row("Без БК", None, "sch_no_bk")
    client_row("Начислено бонусов", None, "credited")
    client_row("Списано бонусов", None, "spent")
    rows.append(["% от выручки", pct_rev_cum, pct_rev_week])
    empty_row("Кол-во обработанных жалоб")
    empty_row("Открыто магазинов невовремя")
    empty_row("Кол-во нарушений")

    for label, source in _general_category_metric_rows(category_order_general):
        rows.append(
            [
                label,
                _category_qty(totals_general_cum, source),
                _category_qty(totals_general_week, source),
            ]
        )

    empty_row("Кол-во брака")
    empty_row("% брака")

    rev_c, md_c, pct_c = _financial_values(df_cum)
    rev_w, md_w, pct_w = _financial_values(
        df_week, excise_liquid_report_qty=excise_liquid_report_qty
    )
    rows.append(["Выручка", rev_c, rev_w])
    rows.append(["МД", md_c, md_w])
    rows.append(["МД%", pct_c, pct_w])

    table = pd.DataFrame(rows, columns=[COL_METRIC, COL_CUMULATIVE, week_col])
    table = _cumulative_only_clients_bk(table)
    return _apply_sheets_number_format(table, (COL_CUMULATIVE, week_col))


def _resolve_report_week(
    sales_df: pd.DataFrame | None,
    checks_clients_df: pd.DataFrame | None,
    report_week: int | None,
) -> int | None:
    if report_week is not None:
        return int(report_week)
    if sales_df is not None:
        weeks = sales_week_numbers(sales_df)
        if weeks:
            return weeks[-1]
    if checks_clients_df is not None and not checks_clients_df.empty:
        try:
            df = _prepare_checks_clients(checks_clients_df)
            return int(df[COL_WEEK].max())
        except ValueError:
            pass
    return None


def _split_sales_frames(
    sales_df: pd.DataFrame | None,
    report_week: int | None,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    if sales_df is None or sales_df.empty:
        return None, None
    if report_week is None:
        return sales_df.copy(), sales_df.copy()
    return (
        filter_sales_cumulative_to_week(sales_df, report_week),
        filter_sales_by_report_week(sales_df, report_week),
    )


def _load_client_metrics(
    checks_clients_df: pd.DataFrame | None,
    client_segments_df: pd.DataFrame | None,
    report_week: int | None,
) -> dict:
    if checks_clients_df is None or checks_clients_df.empty:
        return {}
    try:
        df = _prepare_checks_clients(checks_clients_df)
    except ValueError:
        return {}

    if report_week is None:
        report_week = int(df[COL_WEEK].max())

    week_df = df[df[COL_WEEK] == report_week]
    metrics = _compute_client_metrics(df, week_df)
    metrics.update(
        compute_segment_client_metrics(
            client_segments_df, report_week, _clients_bk_week_count(week_df)
        )
    )
    return metrics


def general_category_metric_rows(
    category_order_general: list[str] | None,
) -> list[tuple[str, str | tuple[str, ...]]]:
    """Строки количества по категориям Общего РНП (подпись, ключ суммирования)."""
    return _general_category_metric_rows(category_order_general)


def general_category_totals(df: pd.DataFrame) -> pd.Series:
    """Количество по категориям из «Категория товара Общий РНП:»."""
    return _general_category_totals(df)


def can_build_general_category_sales(df: pd.DataFrame | None) -> bool:
    return _can_build_general_category_sales(df)


def category_qty_from_totals(
    totals: pd.Series | None,
    category: str | tuple[str, ...],
) -> str:
    return _category_qty(totals, category)


def _can_build_general_category_sales(df: pd.DataFrame | None) -> bool:
    if df is None:
        return False
    return (
        _can_build_category_sales(df)
        and CATEGORY_COLUMN_GENERAL in df.columns
    )


def _general_category_totals(df: pd.DataFrame) -> pd.Series:
    """Количество по категориям из «Категория товара Общий РНП:» (справочник categories)."""
    gen = df[CATEGORY_COLUMN_GENERAL].astype(str).str.strip()
    mask = gen != ""
    if not mask.any():
        return pd.Series(dtype=float)
    work = df.loc[mask].copy()
    work["_general_cat"] = gen[mask]
    return work.groupby("_general_cat")["Количество"].sum()


def _category_qty(totals: pd.Series | None, category: str | tuple[str, ...]) -> str:
    if totals is None:
        return ""
    names = (category,) if isinstance(category, str) else category
    qty = sum(float(totals[n]) for n in names if n in totals.index)
    return _fmt_int(qty)


def _bonus_share_of_revenue(
    checks_clients_df: pd.DataFrame | None,
    report_week: int | None,
) -> tuple[str, str]:
    """% от выручки = списано бонусов / выручка (файл «Чеки и клиенты», колонка «Продажи»)."""
    if checks_clients_df is None or checks_clients_df.empty:
        return "", ""
    try:
        df = _prepare_checks_clients(checks_clients_df)
    except ValueError:
        return "", ""

    if report_week is None:
        report_week = int(df[COL_WEEK].max())

    week_df = df[df[COL_WEEK] == report_week]
    cum_df = filter_sales_cumulative_to_week(df, report_week)
    return (_fmt_bonus_revenue_pct(cum_df), _fmt_bonus_revenue_pct(week_df))


def _fmt_bonus_revenue_pct(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    spent = float(df[COL_SPENT].sum())
    revenue = float(df[COL_SALES].sum())
    if revenue <= 0:
        return "0,0%"
    return f"{100 * spent / revenue:.1f}%".replace(".", ",")


def _financial_values(
    df: pd.DataFrame | None,
    *,
    excise_liquid_report_qty: float = 0.0,
) -> tuple[str, str, str]:
    if df is None or not _can_build_financial_metrics(df):
        return "", "", ""
    revenue = float(df["Продажи с НДС"].sum())
    margin = apply_total_margin_deduction(
        float(df["Маржа"].sum()), excise_liquid_report_qty
    )
    return (
        _fmt_fin_int(revenue),
        _fmt_fin_int(margin),
        _fmt_fin_pct(_md_pct(margin, revenue)),
    )
