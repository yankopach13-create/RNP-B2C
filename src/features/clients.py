"""Расчёт и отображение клиентского блока (файл «Чеки и клиенты»)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from features.client_segments import compute_segment_client_metrics

CHECKS_CLIENTS_COLUMNS = [
    "Год-Неделя",
    "Неделя",
    "Количество чеков",
    "Продажи",
    "Начислено бонусов",
    "Списано бонусов",
    "Код клиента",
]

COL_WEEK = "Неделя"
COL_CHECKS = "Количество чеков"
COL_SALES = "Продажи"
COL_CREDITED = "Начислено бонусов"
COL_SPENT = "Списано бонусов"
COL_CLIENT = "Код клиента"

COL_METRIC = "Метрика"
COL_CUMULATIVE = "Накопительно"
CLIENT_METRIC_COL_WIDTH_PX = 195
CLIENT_VALUE_COL_WIDTH_PX = 92
CLIENT_TABLE_ROW_HEIGHT_PX = 35


def render_client_block(
    checks_clients: pd.DataFrame | None,
    report_week: int | None = None,
    *,
    client_segments: pd.DataFrame | None = None,
    embedded: bool = False,
    table_height: int | None = None,
    row_height: int = CLIENT_TABLE_ROW_HEIGHT_PX,
) -> None:
    """Таблица метрик: накопительно и отчётная неделя."""
    if not embedded:
        st.markdown("---")
        st.subheader("КЛИЕНТСКИЙ БЛОК")
    else:
        st.markdown("**КЛИЕНТСКИЙ БЛОК**")

    if checks_clients is None or checks_clients.empty:
        st.info("Загрузите файл «Чеки и клиенты» для расчёта")
        return

    try:
        df = _prepare_checks_clients(checks_clients)
    except ValueError as exc:
        st.error(str(exc))
        return

    if report_week is None:
        report_week = int(df[COL_WEEK].max())

    week_label = f"Неделя {report_week}"
    week_df = df[df[COL_WEEK] == report_week]
    metrics = _compute_client_metrics(df, week_df)

    clients_bk_week = _clients_bk_week_count(week_df)
    metrics.update(
        compute_segment_client_metrics(
            client_segments, report_week, clients_bk_week
        )
    )

    rows = _build_metric_rows(metrics)
    table = pd.DataFrame(rows, columns=[COL_METRIC, COL_CUMULATIVE, week_label])
    df_kwargs: dict = {
        "use_container_width": True,
        "hide_index": True,
        "column_config": _client_block_column_config(week_label),
        "row_height": row_height,
    }
    if table_height is not None:
        df_kwargs["height"] = table_height
    else:
        from features.table_layout import compact_dataframe_height

        df_kwargs["height"] = compact_dataframe_height()
    st.dataframe(table, **df_kwargs)


def _client_block_column_config(
    week_label: str,
) -> dict[str, st.column_config.TextColumn]:
    """Узкая колонка метрик — без горизонтальной прокрутки в общем ряду."""
    return {
        COL_METRIC: st.column_config.TextColumn(
            COL_METRIC,
            width=CLIENT_METRIC_COL_WIDTH_PX,
        ),
        COL_CUMULATIVE: st.column_config.TextColumn(
            COL_CUMULATIVE,
            width=CLIENT_VALUE_COL_WIDTH_PX,
        ),
        week_label: st.column_config.TextColumn(
            week_label,
            width=CLIENT_VALUE_COL_WIDTH_PX,
        ),
    }


def _prepare_checks_clients(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df.columns = df.columns.str.strip()
    missing = [c for c in CHECKS_CLIENTS_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            "В файле «Чеки и клиенты» отсутствуют столбцы: "
            + ", ".join(missing)
        )

    df = df[CHECKS_CLIENTS_COLUMNS].copy()
    df[COL_WEEK] = pd.to_numeric(df[COL_WEEK], errors="coerce")
    for col in (COL_CHECKS, COL_SALES, COL_CREDITED, COL_SPENT):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df = df.dropna(subset=[COL_WEEK])
    df[COL_WEEK] = df[COL_WEEK].astype(int)
    return df


def _clients_bk_week_count(week: pd.DataFrame) -> int:
    if week.empty:
        return 0
    has_code = _has_client_code(week[COL_CLIENT])
    week_with = week.loc[has_code]
    return int(week_with[COL_CLIENT].nunique()) if not week_with.empty else 0


def _has_client_code(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    empty = s.eq("") | s.str.lower().isin(("nan", "none", "<na>"))
    return series.notna() & ~empty


def _compute_client_metrics(full: pd.DataFrame, week: pd.DataFrame) -> dict:
    with_code_all = full.loc[_has_client_code(full[COL_CLIENT]), COL_CLIENT]

    out: dict = {
        "clients_bk_cumulative": _fmt_int(with_code_all.nunique()) if len(with_code_all) else "",
    }

    if week.empty:
        out.update(_empty_week_metrics())
        return out

    has_code = _has_client_code(week[COL_CLIENT])
    week_with = week.loc[has_code]
    week_without = week.loc[~has_code]

    clients_bk_week = _clients_bk_week_count(week)
    checks_without_bk = (
        float(week_without[COL_CHECKS].iloc[0])
        if len(week_without) == 1
        else float(week_without[COL_CHECKS].sum())
        if not week_without.empty
        else 0.0
    )
    total_checks = float(week[COL_CHECKS].sum())
    checks_with_bk = float(week_with[COL_CHECKS].sum())
    total_sales = float(week[COL_SALES].sum())
    sales_with_bk = float(week_with[COL_SALES].sum())
    credited = float(week[COL_CREDITED].sum())
    spent = float(week[COL_SPENT].sum())

    sch = total_sales / total_checks if total_checks else None
    sch_bk = sales_with_bk / checks_with_bk if checks_with_bk else None
    if len(week_without) >= 1 and checks_without_bk:
        sales_no_bk = float(week_without[COL_SALES].iloc[0])
        sch_no_bk = sales_no_bk / checks_without_bk
    else:
        sch_no_bk = None

    share_no_bk = (
        f"{100 * checks_without_bk / total_checks:.1f}%"
        if total_checks
        else "0,0%"
    )
    denom_bb = spent + total_sales
    pct_bb = f"{100 * spent / denom_bb:.1f}%" if denom_bb > 0 else "0,0%"

    out.update(
        {
            "clients_bk_week": _fmt_int(clients_bk_week),
            "clients_no_bk_week": _fmt_int(checks_without_bk),
            "total_checks": _fmt_int(total_checks),
            "checks_with_bk": _fmt_int(checks_with_bk),
            "checks_without_bk": _fmt_int(checks_without_bk),
            "share_checks_no_bk": share_no_bk,
            "sch": _fmt_float(sch),
            "sch_bk": _fmt_float(sch_bk),
            "sch_no_bk": _fmt_float(sch_no_bk),
            "credited": _fmt_int(credited),
            "spent": _fmt_int(spent),
            "pct_bb": pct_bb,
        }
    )
    return out


def _empty_week_metrics() -> dict:
    return {
        "clients_bk_week": "",
        "clients_no_bk_week": "",
        "total_checks": "",
        "checks_with_bk": "",
        "checks_without_bk": "",
        "share_checks_no_bk": "",
        "sch": "",
        "sch_bk": "",
        "sch_no_bk": "",
        "credited": "",
        "spent": "",
        "pct_bb": "",
    }


def _build_metric_rows(m: dict) -> list[list]:
    def row(name: str, cum_key: str | None, week_key: str | None) -> list:
        cum = m.get(cum_key, "") if cum_key else ""
        wk = m.get(week_key, "") if week_key else ""
        return [name, cum, wk]

    return [
        row("Кол-во новых клиентов", None, None),
        row("Кол-во вернувшихся клиентов", None, None),
        row("Кол-во потерянных клиентов", None, None),
        row("Активная клиентская база", None, None),
        row("Клиенты с БК", "clients_bk_cumulative", "clients_bk_week"),
        row("Клиенты без БК", None, "clients_no_bk_week"),
        row("Целевая АКБ", "target_akb_cumulative", "target_akb_week"),
        row("Динамика накопления Целевых", None, "target_dynamics_week"),
        row("Удельный вес", None, "target_weight_week"),
        row("Нецелевая АКБ", "non_target_akb_cumulative", "non_target_akb_week"),
        row("Удельный вес", None, "non_target_weight_week"),
        row("CSI", None, None),
        row("Динамика накопления CSI", None, None),
        row("CLI возврат", None, None),
        row("CLI рекомендация", None, None),
        row("Кол-во чеков", None, "total_checks"),
        row("С БК", None, "checks_with_bk"),
        row("Без БК", None, "checks_without_bk"),
        row("Доля чеков без БК", None, "share_checks_no_bk"),
        row("СЧ", None, "sch"),
        row("СЧ с БК", None, "sch_bk"),
        row("СЧ без БК", None, "sch_no_bk"),
        row("Начислено ББ", None, "credited"),
        row("Списано ББ", None, "spent"),
        row("% списания ББ от потенциальной выручки", None, "pct_bb"),
    ]


def _fmt_int(value: float | int) -> str:
    try:
        return f"{int(round(float(value))):,}".replace(",", " ")
    except (ValueError, TypeError):
        return ""


def _fmt_float(value: float | None) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.2f}".replace(".", ",")
    except (ValueError, TypeError):
        return "0,00"

