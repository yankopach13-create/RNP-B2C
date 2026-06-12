"""Расчёт метрик по файлу сегментов покупателей."""

from __future__ import annotations

import pandas as pd

SEGMENTS_COLUMNS = [
    "Год-Неделя",
    "Сегменты покупателей",
    "Неделя",
    "Продажи",
    "Код клиента",
]

TARGET_SEGMENT = "Target clients"
COL_SEGMENT = "Сегменты покупателей"
COL_WEEK = "Неделя"
COL_SALES = "Продажи"
COL_CLIENT = "Код клиента"


def prepare_segments_df(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df.columns = df.columns.str.strip()
    missing = [c for c in SEGMENTS_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            "В файле сегментов отсутствуют столбцы: " + ", ".join(missing)
        )

    df = df[SEGMENTS_COLUMNS].copy()
    df[COL_WEEK] = pd.to_numeric(df[COL_WEEK], errors="coerce")
    df[COL_SALES] = pd.to_numeric(df[COL_SALES], errors="coerce").fillna(0)
    df = df.dropna(subset=[COL_WEEK])
    df[COL_WEEK] = df[COL_WEEK].astype(int)
    df[COL_SEGMENT] = df[COL_SEGMENT].astype(str)
    return df


def _is_target_segment(series: pd.Series) -> pd.Series:
    return series == TARGET_SEGMENT


def _has_client_code(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    empty = s.eq("") | s.str.lower().isin(("nan", "none", "<na>"))
    return series.notna() & ~empty


def compute_segment_revenue(
    segments_df: pd.DataFrame | None,
    report_week: int,
) -> tuple[float, float]:
    """Выручка целевых и нецелевых за отчётную неделю."""
    if segments_df is None or segments_df.empty:
        return 0.0, 0.0

    try:
        df = prepare_segments_df(segments_df)
    except ValueError:
        return 0.0, 0.0
    week = df[df[COL_WEEK] == report_week]
    if week.empty:
        return 0.0, 0.0

    target_mask = _is_target_segment(week[COL_SEGMENT])
    target_rev = float(week.loc[target_mask, COL_SALES].sum())
    non_target_rev = float(week.loc[~target_mask, COL_SALES].sum())
    return target_rev, non_target_rev


def compute_segment_client_metrics(
    segments_df: pd.DataFrame | None,
    report_week: int,
    clients_bk_week: int,
) -> dict[str, str]:
    """Метрики АКБ и удельного веса для клиентского блока."""
    empty = {
        "target_akb_cumulative": "",
        "target_akb_week": "",
        "target_dynamics_week": "",
        "target_weight_week": "",
        "non_target_akb_cumulative": "",
        "non_target_akb_week": "",
        "non_target_weight_week": "",
    }
    if segments_df is None or segments_df.empty:
        return empty

    try:
        df = prepare_segments_df(segments_df)
    except ValueError:
        return empty

    with_code = df.loc[_has_client_code(df[COL_CLIENT])]
    if with_code.empty:
        return empty

    target_all = with_code.loc[_is_target_segment(with_code[COL_SEGMENT])]
    non_target_all = with_code.loc[~_is_target_segment(with_code[COL_SEGMENT])]

    target_akb_cum = int(target_all[COL_CLIENT].nunique()) if not target_all.empty else 0
    non_target_akb_cum = (
        int(non_target_all[COL_CLIENT].nunique()) if not non_target_all.empty else 0
    )

    week = with_code[with_code[COL_WEEK] == report_week]
    if week.empty:
        return {
            **empty,
            "target_akb_cumulative": _fmt_int(target_akb_cum),
            "target_dynamics_week": _fmt_int(target_akb_cum),
            "non_target_akb_cumulative": _fmt_int(non_target_akb_cum),
        }

    target_week = week.loc[_is_target_segment(week[COL_SEGMENT])]
    non_target_week = week.loc[~_is_target_segment(week[COL_SEGMENT])]

    target_akb_week = (
        int(target_week[COL_CLIENT].nunique()) if not target_week.empty else 0
    )
    non_target_akb_week = (
        int(non_target_week[COL_CLIENT].nunique()) if not non_target_week.empty else 0
    )

    return {
        "target_akb_cumulative": _fmt_int(target_akb_cum),
        "target_akb_week": _fmt_int(target_akb_week),
        "target_dynamics_week": _fmt_int(target_akb_cum),
        "target_weight_week": _fmt_share_pct(target_akb_week, clients_bk_week),
        "non_target_akb_cumulative": _fmt_int(non_target_akb_cum),
        "non_target_akb_week": _fmt_int(non_target_akb_week),
        "non_target_weight_week": _fmt_share_pct(non_target_akb_week, clients_bk_week),
    }


def _fmt_int(value: int) -> str:
    try:
        return f"{int(value):,}".replace(",", " ")
    except (ValueError, TypeError):
        return ""


def _fmt_share_pct(part: int, whole: int) -> str:
    if not whole or part is None:
        return ""
    return f"{100 * part / whole:.1f}%".replace(".", ",")
