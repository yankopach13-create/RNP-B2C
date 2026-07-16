from dataclasses import dataclass

import streamlit as st

from ui.upload_help import inject_help_popover_styles, render_section_header_with_help

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
                second_caption_title="Сегменты",
                second_caption=(
                    "Зайдите в Qlik под профилем User2.<br>"
                    'В анализе чеков перейдите в закладку '
                    '"АВТОМАТИЗАЦИЯ РНП B2С ( Сегменты)".<br><br>'
                    "В фильтрах отберите недели актуального цикла и скачайте отчёт "
                    "без форматирования (не нажимайте галочку при скачивании).<br><br>"
                    'Вставьте скачанный документ в контейнер «Сегменты покупателей».'
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
            render_section_header_with_help(
                title="Категории в фокусе",
                image_name="hookah.png",
                caption=(
                    "Зайдите в Qlik под профилем User2.<br>"
                    'В анализе чеков перейдите в закладку '
                    '"АВТОМАТИЗАЦИЯ РНП B2С ( Кальянная продукция)".<br><br>'
                    "В фильтрах отберите актуальную неделю и скачайте отчёт "
                    "с форматированием (нажмите галочку при скачивании).<br><br>"
                    'Вставьте скачанный документ в контейнер «Кальянная продукция».'
                ),
                caption_title="Кальянная продукция",
                second_image_name="fill_free.png",
                second_caption_title="Fill free",
                second_caption=(
                    "Зайдите в Qlik под профилем User2.<br>"
                    'В анализе чеков перейдите в закладку '
                    '"АВТОМАТИЗАЦИЯ РНП B2С ( Fill free)".<br><br>'
                    "В фильтрах отберите недели актуального цикла и скачайте отчёт "
                    "без форматирования (не нажимайте галочку при скачивании).<br><br>"
                    'Вставьте скачанный документ в контейнер «Fill free».'
                ),
                align="right",
                two_column_layout=True,
                compact_images=True,
            )
            focus_hookah_file = st.file_uploader(
                "Кальянная продукция",
                type=_XLSX_TYPES,
                key="focus_hookah_uploader",
            )
            focus_fill_free_file = st.file_uploader(
                "Fill free",
                type=_XLSX_TYPES,
                key="focus_fill_free_uploader",
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
    inject_help_popover_styles()
    st.markdown(
        """
        <style>
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
