"""Точка входа B2C РНП (локально и Streamlit Cloud)."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from bootstrap import ensure_packages

ensure_packages()

import pandas as pd
import streamlit as st

from data.loaders import AppData
from data.references import is_sheets_quota_error
from features.data_prep import (
    default_lfl_and_report_weeks,
    sales_week_numbers,
)
from features.clients import render_client_block
from features.lfl import build_lfl_factor_table, render_lfl_block
from features.fill_free_products import render_fill_free_products_block
from features.hookah_products import render_hookah_products_block
from features.metrics import (
    render_financial_metrics_table,
    render_global_metrics,
    _build_shop_economy_table,
    _can_build_financial_metrics,
    _fmt_fin_int,
    _full_table_height,
    FINANCIAL_TABLE_ROW_HEIGHT_PX,
)
from features.excise_liquid import WeekCalculationConfig, excise_margin_deduction
from features.excel_export import rnp_b2c_excel_filename
from features.ai_report import render_ai_report_b2c
from features.general_rnp import render_general_rnp_b2c
from features.checks_no_bk import render_checks_no_bk_block
from ui.data_session import (
    DOWNLOAD_RNP_EXCEL_KEY,
    get_cached_excel_bytes,
    get_cached_turnover_table,
    get_df_report_cached,
    get_stored_app_data,
    get_stored_prepared,
    ensure_app_logic_version,
    load_and_store_app_data,
    should_reload_data,
)
from ui.reference_quick_add import render_quick_reference_update
from ui.upload_panel import UploadedFiles, render_upload_panel

st.set_page_config(page_title="B2C РНП", page_icon="📊", layout="wide")

SHOP_ECONOMY_SALES_COL_WIDTH_PX = 70
SHOP_ECONOMY_SHOP_COL_WIDTH_PX = 165


def main():
    ensure_app_logic_version()
    st.title("B2C")
    st.markdown(
        '<a href="https://docs.google.com/spreadsheets/d/14ecZy9BRnYiHOjASyPmcBttuUjtv6rY-a4cazeBhldM/edit?hl=ru&gid=1406589453#gid=1406589453" '
        'target="_blank" rel="noopener noreferrer">База данных</a>',
        unsafe_allow_html=True,
    )

    files: UploadedFiles = render_upload_panel()
    if not files.run_analysis:
        return

    if should_reload_data():
        try:
            with st.spinner("Загрузка и подготовка данных…"):
                data, prepared = load_and_store_app_data(files)
        except (ValueError, OSError) as exc:
            st.error(str(exc))
            st.stop()
        except Exception as exc:
            if is_sheets_quota_error(exc):
                st.error(
                    "Превышена квота Google Sheets API при загрузке справочников "
                    "(магазины, категории, порядок групп). Загруженные .xlsx из Qlik "
                    "здесь ни при чём — подождите 1–2 минуты и нажмите «Запустить анализ» снова."
                )
            else:
                st.error(
                    "Ошибка при чтении загруженных файлов. "
                    "Проверьте, что все файлы — корректные .xlsx из Qlik (без форматирования)."
                )
            st.caption(str(exc))
            st.stop()
    else:
        data = get_stored_app_data()
        prepared = get_stored_prepared()
        if data is None:
            return

    has_any_data = any(
        [
            data.sales is not None,
            data.checks_clients is not None,
            data.lfl is not None,
            data.turnover_90 is not None,
            data.turnover_week is not None,
        ]
    )

    if not has_any_data:
        st.warning("Загрузите хотя бы один файл для анализа.")
        return

    week_config: WeekCalculationConfig | None = None
    if data.sales is not None:
        week_config = _render_week_selectors(data.sales)

    if prepared is not None:
        render_quick_reference_update(
            prepared.new_shops,
            prepared.unmatched_products,
            data.groups,
            data.categories,
            data.groups_order_rnp,
            data.category_order_rnp,
            data.category_order_general,
        )

    _render_rnp_b2c_header(data, prepared, week_config)


def _render_excel_download_button(
    data: AppData,
    prepared,
    week_config: WeekCalculationConfig | None,
) -> None:
    """Скачивание Excel: сборка в кэш при необходимости, одно нажатие на загрузку."""
    report_week = week_config.report_week if week_config else None

    @st.fragment
    def _download_fragment() -> None:
        excel_bytes = get_cached_excel_bytes(data, prepared, week_config)
        st.download_button(
            label="Скачать РНП отчёт в Excel",
            data=excel_bytes or b"",
            file_name=rnp_b2c_excel_filename(report_week),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="secondary",
            use_container_width=True,
            key=DOWNLOAD_RNP_EXCEL_KEY,
            disabled=not excel_bytes,
        )

    _download_fragment()


def _render_rnp_b2c_header(
    data: AppData,
    prepared,
    week_config: WeekCalculationConfig | None,
) -> None:
    """Кнопки-переключатели блоков отчёта и скачивание Excel (как в B2B)."""
    _inject_rnp_block_styles()

    if "show_rnp_b2c_block" not in st.session_state:
        st.session_state.show_rnp_b2c_block = False
    if "show_general_rnp_b2c_block" not in st.session_state:
        st.session_state.show_general_rnp_b2c_block = False
    if "show_ai_rnp_b2c_block" not in st.session_state:
        st.session_state.show_ai_rnp_b2c_block = False
    if "show_checks_no_bk_block" not in st.session_state:
        st.session_state.show_checks_no_bk_block = False

    toggle_label = (
        "▼ РНП B2C (нажмите, чтобы свернуть)"
        if st.session_state.show_rnp_b2c_block
        else "▶ РНП B2C (нажмите, чтобы развернуть)"
    )
    col_toggle, col_download = st.columns([1.35, 1], gap="small")
    with col_toggle:
        if st.button(
            toggle_label,
            key="toggle_rnp_b2c_block_btn",
            type="tertiary",
            use_container_width=True,
        ):
            st.session_state.show_rnp_b2c_block = not st.session_state.show_rnp_b2c_block
            st.rerun()
    with col_download:
        _render_excel_download_button(data, prepared, week_config)

    if st.session_state.show_rnp_b2c_block:
        _render_rnp_b2c_results(data, prepared, week_config)

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    general_toggle_label = (
        "▼ Общий РНП B2C (нажмите, чтобы свернуть)"
        if st.session_state.show_general_rnp_b2c_block
        else "▶ Общий РНП B2C (нажмите, чтобы развернуть)"
    )
    col_general_toggle, col_general_spacer = st.columns([1.35, 1], gap="small")
    with col_general_toggle:
        if st.button(
            general_toggle_label,
            key="toggle_general_rnp_b2c_block_btn",
            type="secondary",
            use_container_width=True,
        ):
            st.session_state.show_general_rnp_b2c_block = (
                not st.session_state.show_general_rnp_b2c_block
            )
            st.rerun()
    with col_general_spacer:
        st.empty()

    if st.session_state.show_general_rnp_b2c_block:
        report_week = week_config.report_week if week_config else None
        excise_report = week_config.excise_liquid_report if week_config else 0.0
        sales_df = prepared.df if prepared is not None else data.sales
        render_general_rnp_b2c(
            sales_df,
            data.checks_clients,
            client_segments_df=data.client_segments,
            report_week=report_week,
            category_order_general=data.category_order_general,
            excise_liquid_report_qty=excise_report,
        )

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    ai_toggle_label = (
        "▼ ИИ отчёт B2C (нажмите, чтобы свернуть)"
        if st.session_state.show_ai_rnp_b2c_block
        else "▶ ИИ отчёт B2C (нажмите, чтобы развернуть)"
    )
    col_ai_toggle, col_ai_spacer = st.columns([1.35, 1], gap="small")
    with col_ai_toggle:
        if st.button(
            ai_toggle_label,
            key="toggle_ai_rnp_b2c_block_btn",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.show_ai_rnp_b2c_block = not st.session_state.show_ai_rnp_b2c_block
            st.rerun()
    with col_ai_spacer:
        st.empty()

    if st.session_state.show_ai_rnp_b2c_block:
        report_week = week_config.report_week if week_config else None
        excise_report = week_config.excise_liquid_report if week_config else 0.0
        sales_df = prepared.df if prepared is not None else data.sales
        render_ai_report_b2c(
            sales_df,
            data.checks_clients,
            client_segments_df=data.client_segments,
            report_week=report_week,
            excise_liquid_report_qty=excise_report,
        )

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    checks_no_bk_toggle_label = (
        "▼ % чеков без БК (нажмите, чтобы свернуть)"
        if st.session_state.show_checks_no_bk_block
        else "▶ % чеков без БК (нажмите, чтобы развернуть)"
    )
    col_checks_no_bk_toggle, col_checks_no_bk_spacer = st.columns([1.35, 1], gap="small")
    with col_checks_no_bk_toggle:
        if st.button(
            checks_no_bk_toggle_label,
            key="toggle_checks_no_bk_block_btn",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.show_checks_no_bk_block = (
                not st.session_state.show_checks_no_bk_block
            )
            st.rerun()
    with col_checks_no_bk_spacer:
        st.empty()

    if st.session_state.show_checks_no_bk_block:
        render_checks_no_bk_block(groups_df=data.groups)


def _inject_rnp_block_styles() -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stButton"] button[kind="tertiary"] {
            background-color: #0b2e6b !important;
            color: #ffffff !important;
            border: 1px solid #0b2e6b !important;
            font-weight: 800 !important;
            font-size: 1.05rem !important;
            border-radius: 10px !important;
            min-height: 44px !important;
            padding: 0.5rem 1rem !important;
            justify-content: flex-start !important;
            text-align: left !important;
        }
        div[data-testid="stButton"] button[kind="tertiary"]:hover,
        div[data-testid="stButton"] button[kind="tertiary"]:active,
        div[data-testid="stButton"] button[kind="tertiary"]:focus,
        div[data-testid="stButton"] button[kind="tertiary"]:focus-visible {
            background-color: #082554 !important;
            border-color: #082554 !important;
            color: #ffffff !important;
            box-shadow: none !important;
            outline: none !important;
        }
        div[data-testid="stButton"] button[kind="secondary"] {
            background-color: #1f5d35 !important;
            color: #ffffff !important;
            border: 1px solid #1f5d35 !important;
            font-weight: 800 !important;
            font-size: 1.05rem !important;
            border-radius: 10px !important;
            min-height: 44px !important;
            padding: 0.5rem 1rem !important;
            justify-content: flex-start !important;
            text-align: left !important;
        }
        div[data-testid="stButton"] button[kind="secondary"]:hover {
            background-color: #17472a !important;
            border-color: #17472a !important;
        }
        .st-key-toggle_ai_rnp_b2c_block_btn button {
            background-color: #b56a1a !important;
            color: #ffffff !important;
            border: 1px solid #b56a1a !important;
            font-weight: 800 !important;
            font-size: 1.05rem !important;
            border-radius: 10px !important;
            min-height: 44px !important;
            padding: 0.5rem 1rem !important;
            justify-content: flex-start !important;
            text-align: left !important;
        }
        .st-key-toggle_ai_rnp_b2c_block_btn button:hover,
        .st-key-toggle_ai_rnp_b2c_block_btn button:active,
        .st-key-toggle_ai_rnp_b2c_block_btn button:focus,
        .st-key-toggle_ai_rnp_b2c_block_btn button:focus-visible {
            background-color: #955716 !important;
            border-color: #955716 !important;
            color: #ffffff !important;
            box-shadow: none !important;
            outline: none !important;
        }
        .st-key-toggle_checks_no_bk_block_btn button {
            background-color: #5c3d8f !important;
            color: #ffffff !important;
            border: 1px solid #5c3d8f !important;
            font-weight: 800 !important;
            font-size: 1.05rem !important;
            border-radius: 10px !important;
            min-height: 44px !important;
            padding: 0.5rem 1rem !important;
            justify-content: flex-start !important;
            text-align: left !important;
        }
        .st-key-toggle_checks_no_bk_block_btn button:hover,
        .st-key-toggle_checks_no_bk_block_btn button:active,
        .st-key-toggle_checks_no_bk_block_btn button:focus,
        .st-key-toggle_checks_no_bk_block_btn button:focus-visible {
            background-color: #4a3173 !important;
            border-color: #4a3173 !important;
            color: #ffffff !important;
            box-shadow: none !important;
            outline: none !important;
        }
        div[data-testid="stDownloadButton"] button {
            background: transparent !important;
            color: inherit !important;
            border: 1px solid rgba(250, 250, 250, 0.9) !important;
            font-weight: 700 !important;
            font-size: 1.05rem !important;
            border-radius: 10px !important;
            min-height: 44px !important;
            padding: 0.5rem 1rem !important;
        }
        div[data-testid="stDownloadButton"] button:hover {
            background: rgba(255, 255, 255, 0.06) !important;
            border-color: #ffffff !important;
        }
        div[data-testid="stDownloadButton"] button:disabled {
            opacity: 0.5;
            border-color: rgba(250, 250, 250, 0.35) !important;
        }
        @media (prefers-color-scheme: light) {
            div[data-testid="stDownloadButton"] button {
                border-color: rgba(49, 51, 63, 0.55) !important;
                color: rgb(49, 51, 63) !important;
            }
            div[data-testid="stDownloadButton"] button:hover {
                border-color: rgb(49, 51, 63) !important;
                background: rgba(49, 51, 63, 0.04) !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_rnp_b2c_results(
    data: AppData,
    prepared,
    week_config: WeekCalculationConfig | None,
) -> None:
    """Все расчёты и таблицы отчёта B2C."""
    if week_config is not None:
        st.divider()

    df = prepared.df if prepared is not None else None

    df_report = _filter_report_sales(df, week_config) if df is not None else None
    if df is not None and df_report is None:
        return

    report_week = week_config.report_week if week_config else None
    lfl_week = week_config.lfl_week if week_config else None
    excise_report = week_config.excise_liquid_report if week_config else 0.0
    excise_lfl = week_config.excise_liquid_lfl if week_config else 0.0

    if df_report is not None:
        render_global_metrics(
            df_report,
            data.categories,
            data.turnover_90,
            data.turnover_week,
            data.client_segments,
            category_order_rnp=data.category_order_rnp,
            groups_order_rnp=data.groups_order_rnp,
            focus_df=data.focus,
            turnover_categories=getattr(data, "turnover_categories", None),
            shops_order=data.shops_order,
            checks_clients_df=data.checks_clients,
            report_week=report_week,
            excise_liquid_report_qty=excise_report,
            turnover_table=get_cached_turnover_table(data),
        )
        _render_shop_economy_and_lfl(
            data,
            df_report,
            lfl_week,
            report_week,
            excise_lfl_qty=excise_lfl,
            excise_report_qty=excise_report,
        )
    elif data.sales is not None:
        sales_report = _filter_report_sales(data.sales, week_config)
        if sales_report is None:
            return
        if _can_build_financial_metrics(sales_report):
            st.subheader("Финансовые метрики")
            render_financial_metrics_table(
                sales_report,
                data.client_segments,
                report_week=report_week,
                excise_liquid_report_qty=excise_report,
            )

        if data.checks_clients is not None:
            render_client_block(
                data.checks_clients,
                report_week,
                client_segments=data.client_segments,
            )

        _render_shop_economy_and_lfl(
            data,
            sales_report,
            lfl_week,
            report_week,
            excise_lfl_qty=excise_lfl,
            excise_report_qty=excise_report,
        )


def _inject_week_selector_input_styles() -> None:
    """Одинаковый размер ячеек недель и акцизной жидкости."""
    _input_w = "6.75rem"
    st.markdown(
        f"""
        <style>
        div[class*="st-key-week_lfl"],
        div[class*="st-key-week_report"] {{
            width: {_input_w} !important;
            max-width: {_input_w} !important;
            min-width: {_input_w} !important;
            flex: 0 0 {_input_w} !important;
        }}
        div[class*="st-key-excise_liquid_lfl"] div[data-testid="stNumberInput"],
        div[class*="st-key-excise_liquid_report"] div[data-testid="stNumberInput"] {{
            width: {_input_w} !important;
            max-width: {_input_w} !important;
            min-width: {_input_w} !important;
            flex: 0 0 {_input_w} !important;
        }}
        div[class*="st-key-week_lfl"] div[data-baseweb="select"] > div,
        div[class*="st-key-week_report"] div[data-baseweb="select"] > div,
        div[class*="st-key-excise_liquid_lfl"] input,
        div[class*="st-key-excise_liquid_report"] input {{
            min-height: 46px !important;
            font-size: 1.15rem !important;
            width: 100% !important;
        }}
        div[class*="st-key-week_lfl"] div[data-baseweb="select"] span,
        div[class*="st-key-week_report"] div[data-baseweb="select"] span,
        div[class*="st-key-excise_liquid_lfl"] input,
        div[class*="st-key-excise_liquid_report"] input {{
            font-size: 1.15rem !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_week_selectors(sales_df: pd.DataFrame) -> WeekCalculationConfig | None:
    """
    Недели из файла продаж: слева LFL (меньшая по умолчанию), справа отчётная (большая).
    None — в продажах нет колонки «Неделя» или нет недель.
    """
    weeks = sales_week_numbers(sales_df)
    if not weeks:
        return None

    _inject_week_selector_input_styles()
    lfl_default, report_default = default_lfl_and_report_weeks(weeks)
    _SECTION_TITLE_HTML = (
        '<h2 style="color: #1f77b4; margin: 0; padding-top: 0.35rem;">{text}</h2>'
    )
    # Те же доли колонок, что у «РНП B2C» / «Скачать РНП» — акциз по левому краю кнопки Excel.
    col_weeks, col_excise = st.columns([1.35, 1], gap="small")
    select_kwargs = {"label_visibility": "collapsed"}
    number_kwargs = {
        "min_value": 0.0,
        "step": 1.0,
        "format": "%.0f",
        "label_visibility": "collapsed",
    }
    _week_pair_cols = [0.42, 0.42, 2.16]
    _excise_pair_cols = [0.42, 0.14, 0.42, 2.02]

    with col_weeks:
        st.markdown(
            _SECTION_TITLE_HTML.format(text="Настройка недель для расчёта"),
            unsafe_allow_html=True,
        )
        col_lfl, col_report, _sp_w = st.columns(_week_pair_cols, gap="small")
        with col_lfl:
            st.caption("LFL")
            lfl_week = st.selectbox(
                "LFL",
                weeks,
                index=weeks.index(lfl_default),
                key="week_lfl",
                **select_kwargs,
            )
        with col_report:
            st.caption("Отчётная")
            report_week = st.selectbox(
                "Отчётная",
                weeks,
                index=weeks.index(report_default),
                key="week_report",
                **select_kwargs,
            )

    with col_excise:
        st.markdown(
            _SECTION_TITLE_HTML.format(text="Акцизной жидкости в шт."),
            unsafe_allow_html=True,
        )
        col_exc_lfl, _exc_gap, col_exc_report, _sp_e = st.columns(
            _excise_pair_cols, gap="small"
        )
        with _exc_gap:
            st.empty()
        with col_exc_lfl:
            st.caption("LFL")
            excise_lfl = st.number_input(
                "Акциз LFL", key="excise_liquid_lfl", **number_kwargs
            )
            st.caption(
                f"Вычтено из МД: {_fmt_fin_int(excise_margin_deduction(excise_lfl))}"
            )
        with col_exc_report:
            st.caption("Отчётная")
            excise_report = st.number_input(
                "Акциз отчётная", key="excise_liquid_report", **number_kwargs
            )
            st.caption(
                f"Вычтено из МД: {_fmt_fin_int(excise_margin_deduction(excise_report))}"
            )
    return WeekCalculationConfig(
        lfl_week=int(lfl_week),
        report_week=int(report_week),
        excise_liquid_lfl=float(excise_lfl),
        excise_liquid_report=float(excise_report),
    )


def _filter_report_sales(
    df: pd.DataFrame,
    week_config: WeekCalculationConfig | None,
) -> pd.DataFrame | None:
    """Фильтр отчётных продаж по выбранной неделе. None — нет строк по неделе."""
    if week_config is None:
        return df
    filtered = get_df_report_cached(df, week_config)
    if filtered is None or filtered.empty:
        st.error(f"В данных нет строк с неделей {week_config.report_week}.")
        return None
    return filtered


def _build_shop_economy_table_simple(
    df_sales: pd.DataFrame,
    shops_order: list[str] | None = None,
):
    """Упрощенная версия экономики магазинов."""
    return _build_shop_economy_table(df_sales, shops_order)


def _render_shop_economy_and_lfl(
    data: AppData,
    sales_df: pd.DataFrame | None,
    lfl_week: int | None,
    report_week: int | None,
    *,
    excise_lfl_qty: float = 0.0,
    excise_report_qty: float = 0.0,
) -> None:
    """Экономика магазинов, факторный анализ, кальянная продукция и Fill free."""
    hookah_kwargs = {
        "sales_df": sales_df if sales_df is not None else data.sales,
        "focus_hookah": data.focus_hookah,
        "groups_df": data.groups,
        "report_week": None if sales_df is not None else report_week,
        "embedded": True,
    }
    fill_free_kwargs = {
        "focus_fill_free": data.focus_fill_free,
        "groups_df": data.groups,
        "report_week": report_week,
        "embedded": True,
    }
    has_shop = sales_df is not None and not sales_df.empty
    has_lfl = data.lfl is not None
    if not has_shop and not has_lfl:
        st.divider()
        col_hookah, col_fill_free = st.columns(2)
        with col_hookah:
            render_hookah_products_block(**hookah_kwargs)
        with col_fill_free:
            render_fill_free_products_block(**fill_free_kwargs)
        return

    st.divider()
    col_left, col_lfl = st.columns([1.28, 1.82])

    lfl_table = None
    if has_lfl:
        lfl_table = build_lfl_factor_table(
            data.lfl,
            data.categories,
            lfl_week,
            report_week,
            data.category_order_rnp,
            excise_liquid_lfl_qty=excise_lfl_qty,
            excise_liquid_report_qty=excise_report_qty,
        )
    paired_table_height = (
        _full_table_height(len(lfl_table))
        if lfl_table is not None and not lfl_table.empty
        else None
    )

    with col_left:
        st.markdown("**Экономика магазинов**")
        if has_shop:
            shop_table = _build_shop_economy_table_simple(
                sales_df, data.shops_order
            )
            if not shop_table.empty:
                shop_table_height = paired_table_height or _full_table_height(
                    len(shop_table)
                )
                st.dataframe(
                    shop_table.reset_index(),
                    use_container_width=True,
                    hide_index=True,
                    height=shop_table_height,
                    row_height=FINANCIAL_TABLE_ROW_HEIGHT_PX,
                    column_config={
                        "Магазин": st.column_config.TextColumn(
                            "Магазин",
                            width=SHOP_ECONOMY_SHOP_COL_WIDTH_PX,
                        ),
                        "Продажи с НДС": st.column_config.TextColumn(
                            "Продажи с НДС",
                            width=SHOP_ECONOMY_SALES_COL_WIDTH_PX,
                        ),
                    },
                )
            else:
                st.info("Нет данных по магазинам.")
        else:
            st.info("Нет данных по магазинам.")

    with col_lfl:
        if has_lfl:
            render_lfl_block(
                data.lfl,
                data.categories,
                lfl_week,
                report_week,
                data.category_order_rnp,
                excise_liquid_lfl_qty=excise_lfl_qty,
                excise_liquid_report_qty=excise_report_qty,
                embedded=True,
                prebuilt_table=lfl_table,
                table_height=paired_table_height,
            )
        else:
            st.markdown("**Факторный анализ**")
            st.info(
                "Нет данных для факторного анализа "
                "(загрузите продажи с колонкой «Неделя» или отдельный файл)."
            )

    st.divider()
    col_hookah, col_fill_free = st.columns(2)
    with col_hookah:
        render_hookah_products_block(**hookah_kwargs)
    with col_fill_free:
        render_fill_free_products_block(**fill_free_kwargs)


if __name__ == "__main__":
    main()
