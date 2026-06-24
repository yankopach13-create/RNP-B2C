from dataclasses import dataclass

import streamlit as st

from ui.upload_help import render_section_header_with_help

_XLSX_TYPES = ["xlsx", "xls"]


@dataclass
class UploadedFiles:
    sales: object = None
    checks_clients: object = None
    client_segments: object = None
    turnover_week: object = None
    turnover_90: object = None
    focus_hookah: object = None
    focus_fill_free: object = None
    run_analysis: bool = False


def render_upload_panel() -> UploadedFiles:
    """Панель загрузки данных."""
    container = st.container()
    with container:
        col_sales, col_turnover, col_clients, col_focus = st.columns(4)

        with col_sales:
            render_section_header_with_help(
                title="Продажи",
                image_name="sales.png",
                caption=(
                    "Зайдите в Qlik под профилем User2.<br>"
                    'В анализе продаж перейдите в закладку '
                    '"АВТОМАТИЗАЦИЯ РНП B2C (ПРОДАЖИ И ЛФЛ)".<br><br>'
                    "Отберите актуальную и LFL недели и скачайте отчёт без форматирования "
                    "(не нажимайте галочку при скачивании).<br><br>"
                    'Вставьте скачанный документ в контейнер «Продажи».'
                ),
                align="left",
            )
            data_file = st.file_uploader(
                "Продажи",
                type=_XLSX_TYPES,
                key="sales_uploader",
            )

        with col_turnover:
            render_section_header_with_help(
                title="Оборачиваемость",
                image_name="turnover.png",
                caption=(
                    "Зайдите в Qlik под профилем User2.<br>"
                    'В анализе запасов перейдите в закладку '
                    '"АВТОМАТИЗАЦИЯ РНП B2С ( Оборачиваемость 7/90)".<br><br>'
                    "Отберите необходимые периоды для расчёта оборачиваемости и скачайте отчёты.<br><br>"
                    'Вставьте скачанные документы в контейнеры «Оборачиваемость 90 дней» '
                    'и «Оборачиваемость 7 дней».'
                ),
                align="center",
            )
            turnover_90_file = st.file_uploader(
                "Оборачиваемость (90 дней)",
                type=_XLSX_TYPES,
                key="turnover_90_uploader",
            )
            turnover_week_file = st.file_uploader(
                "Оборачиваемость (7 дней)",
                type=_XLSX_TYPES,
                key="turnover_week_uploader",
            )

        with col_clients:
            render_section_header_with_help(
                title="Чеки и клиенты",
                image_name="clients.png",
                caption_title="Чеки и клиенты",
                caption=(
                    "Зайдите в Qlik под профилем User2.<br>"
                    'В анализе чеков перейдите в закладку '
                    '"АВТОМАТИЗАЦИЯ РНП B2С ( Чеки и клиенты)".<br><br>'
                    "В фильтрах отберите недели актуального цикла и скачайте отчёт "
                    "без форматирования (не нажимайте галочку при скачивании).<br><br>"
                    'Вставьте скачанный документ в контейнер «Чеки и клиенты».'
                ),
                second_image_name="segments.png",
                second_caption_title="Чеки и клиенты",
                second_caption=(
                    "Зайдите в Qlik под профилем User2.<br>"
                    'В анализе чеков перейдите в закладку '
                    '"АВТОМАТИЗАЦИЯ РНП B2С ( Сегменты)".<br><br>'
                    "В фильтрах отберите недели актуального цикла и скачайте отчёт "
                    "без форматирования (не нажимайте галочку при скачивании).<br><br>"
                    'Вставьте скачанный документ в контейнер «Чеки и клиенты».'
                ),
                align="right",
                two_column_layout=True,
                compact_images=True,
            )
            checks_clients_file = st.file_uploader(
                "Чеки и клиенты",
                type=_XLSX_TYPES,
                key="checks_clients_uploader",
            )
            client_segments_file = st.file_uploader(
                "Сегменты покупателей",
                type=_XLSX_TYPES,
                key="client_segments_uploader",
            )

        with col_focus:
            st.subheader("Категории в фокусе")
            st.caption(
                "Фокусные позиции в отчёте берутся из справочника focus (Google Sheets). "
                "Загрузка файлов ниже пока не используется."
            )
            st.markdown(
                "<p class='upload-mini-title'>Кальянная продукция</p>",
                unsafe_allow_html=True,
            )
            focus_hookah_file = st.file_uploader(
                "Кальянная продукция",
                type=_XLSX_TYPES,
                key="focus_hookah_uploader",
                label_visibility="collapsed",
            )
            st.markdown(
                "<p class='upload-mini-title'>Fill free</p>",
                unsafe_allow_html=True,
            )
            focus_fill_free_file = st.file_uploader(
                "Fill free",
                type=_XLSX_TYPES,
                key="focus_fill_free_uploader",
                label_visibility="collapsed",
            )

        _inject_upload_page_styles()
        st.markdown("")
        run_analysis = st.button(
            "Загрузить данные",
            type="primary",
            key="load_data_btn",
        )

    if run_analysis:
        st.session_state["data_reload_requested"] = True
        st.session_state["uploaded_files"] = {
            "sales": data_file,
            "checks_clients": checks_clients_file,
            "client_segments": client_segments_file,
            "turnover_week": turnover_week_file,
            "turnover_90": turnover_90_file,
            "focus_hookah": focus_hookah_file,
            "focus_fill_free": focus_fill_free_file,
        }
        st.session_state["run_analysis"] = True
        container.empty()
        return UploadedFiles(
            sales=data_file,
            checks_clients=checks_clients_file,
            client_segments=client_segments_file,
            turnover_week=turnover_week_file,
            turnover_90=turnover_90_file,
            focus_hookah=focus_hookah_file,
            focus_fill_free=focus_fill_free_file,
            run_analysis=True,
        )

    if st.session_state.get("run_analysis"):
        u = st.session_state.get("uploaded_files", {})
        return UploadedFiles(
            sales=u.get("sales"),
            checks_clients=u.get("checks_clients"),
            client_segments=u.get("client_segments"),
            turnover_week=u.get("turnover_week"),
            turnover_90=u.get("turnover_90"),
            focus_hookah=u.get("focus_hookah"),
            focus_fill_free=u.get("focus_fill_free"),
            run_analysis=True,
        )

    return UploadedFiles()


def _inject_upload_page_styles() -> None:
    st.markdown(
        """
        <style>
        .help-popover {
            position: relative;
            display: inline-block;
            width: 100%;
            text-align: right;
            z-index: 10;
        }
        .help-popover--inline {
            width: auto;
            text-align: left;
            flex-shrink: 0;
        }
        .help-popover__toggle {
            position: absolute;
            opacity: 0;
            pointer-events: none;
        }
        .help-popover__trigger {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 2rem;
            height: 2rem;
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 0.5rem;
            color: rgba(250, 250, 250, 0.95);
            cursor: pointer;
            user-select: none;
            font-size: 1.05rem;
            line-height: 1;
            background: rgba(255, 255, 255, 0.04);
            transition: background-color 0.15s ease, border-color 0.15s ease;
            position: relative;
            z-index: 1000;
        }
        .help-popover__trigger:hover {
            background: rgba(255, 255, 255, 0.1);
            border-color: rgba(255, 255, 255, 0.55);
        }
        .help-popover__backdrop {
            display: none;
            position: fixed;
            inset: 0;
            z-index: 998;
            background: transparent;
        }
        .help-popover__panel {
            display: none;
            position: absolute;
            top: calc(100% + 0.5rem);
            width: min(68vw, 760px);
            min-width: min(92vw, 360px);
            max-width: 92vw;
            max-height: 72vh;
            overflow: auto;
            padding: 0.9rem;
            border-radius: 0.75rem;
            border: 1px solid rgba(250, 250, 250, 0.18);
            background: rgba(15, 15, 15, 0.98);
            box-shadow: 0 16px 36px rgba(0, 0, 0, 0.45);
            text-align: left;
            z-index: 999;
        }
        .help-popover--left .help-popover__panel {
            left: 0;
            right: auto;
        }
        .help-popover--center .help-popover__panel {
            left: 50%;
            right: auto;
            transform: translateX(-50%);
        }
        .help-popover--right .help-popover__panel {
            right: 0;
            left: auto;
        }
        .help-popover__toggle:checked ~ .help-popover__backdrop {
            display: block;
        }
        .help-popover__toggle:checked ~ .help-popover__panel {
            display: block;
        }
        .help-popover__caption {
            white-space: pre-line;
            font-size: 0.95rem;
            color: rgba(250, 250, 250, 0.86);
            margin-bottom: 0.75rem;
        }
        .help-popover__col-title {
            font-size: 1rem;
            font-weight: 700;
            color: rgba(250, 250, 250, 0.95);
            margin-bottom: 0.65rem;
        }
        .help-popover__split-columns {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.3rem;
            margin-bottom: 0.25rem;
        }
        .help-popover__split-columns .help-popover__paragraph {
            margin-bottom: 0.65rem;
        }
        .help-popover__image-wrapper {
            margin-bottom: 1rem;
        }
        .help-popover__image {
            width: 100%;
            height: auto;
            border-radius: 0.5rem;
            border: 1px solid rgba(250, 250, 250, 0.16);
        }
        .help-popover--compact .help-popover__image {
            max-height: 280px;
            object-fit: contain;
            background: rgba(0, 0, 0, 0.15);
        }
        .help-popover__split {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.3rem;
        }
        .help-popover__split-text {
            display: block;
        }
        .help-popover__row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.3rem;
            margin-bottom: 0.75rem;
        }
        .help-popover__paragraph {
            white-space: pre-line;
            font-size: 0.95rem;
            color: rgba(250, 250, 250, 0.86);
            min-height: 1.45rem;
        }
        .help-popover__split-col {
            min-width: 0;
        }
        .help-popover__split-images .help-popover__split-col {
            display: flex;
            align-items: flex-start;
        }
        .help-popover__split-images .help-popover__image-wrapper {
            width: 100%;
        }
        @media (max-width: 1100px) {
            .help-popover__split {
                grid-template-columns: 1fr;
            }
        }
        .help-popover__download {
            display: inline-block;
            margin-top: 0.55rem;
            color: #d95f5f;
            text-decoration: none;
            font-weight: 600;
        }
        .help-popover__download:hover {
            text-decoration: underline;
        }
        .help-popover__warning {
            color: #ff8f8f;
            font-size: 0.92rem;
            margin-bottom: 0.85rem;
        }
        .upload-mini-title {
            font-size: 0.92rem;
            font-weight: 600;
            color: rgba(250, 250, 250, 0.9);
            margin: 0.35rem 0 0.15rem;
        }
        .st-key-load_data_btn button {
            background-color: #b23a3a !important;
            border: 1px solid #b23a3a !important;
            color: #ffffff !important;
            font-weight: 700 !important;
        }
        .st-key-load_data_btn button:hover {
            background-color: #9a3131 !important;
            border-color: #9a3131 !important;
        }
        .st-key-load_data_btn button:active,
        .st-key-load_data_btn button:focus,
        .st-key-load_data_btn button:focus-visible {
            background-color: #9a3131 !important;
            border-color: #9a3131 !important;
            color: #ffffff !important;
            box-shadow: none !important;
            outline: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
