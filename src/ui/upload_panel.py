from dataclasses import dataclass

import streamlit as st

from ui.upload_help import inject_help_popover_styles, render_section_header_with_help
_XLSX_TYPES = ["xlsx", "xls"]


@dataclass
class UploadedFiles:
    sales: object = None
    liquid_cost: object = None
    excise_liquid_lfl: object = None
    excise_liquid_report: object = None
    checks_clients: object = None
    client_segments: object = None
    turnover_week: object = None
    turnover_90: object = None
    focus_hookah: object = None
    consumables_nesting: object = None
    checks_no_bk: object = None
    run_analysis: bool = False


def render_upload_panel() -> UploadedFiles:
    """Панель загрузки данных."""
    inject_help_popover_styles()
    container = st.container()
    with container:
        col_sales, col_liquid, col_turnover, col_clients, col_focus, col_no_bk = st.columns(
            6
        )

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
            liquid_cost_file = st.file_uploader(
                "Себестоимость жидкости",
                type=_XLSX_TYPES,
                key="liquid_cost_uploader",
                help="Бух. себестоимость «Жидкость 25 мл» без акциза (Склад, Товар4, Год-Неделя).",
            )

        with col_liquid:
            render_section_header_with_help(
                title="Акциз жидкости",
                image_name="sales.png",
                caption=(
                    "Загрузите два файла акциза для блока «Розница»: "
                    "отдельно для LFL-недели и для отчётной недели.<br><br>"
                    "Столбец 2 — SKU (Товар ур.4), столбец 9 — шт, столбец 10 — сумма акциза."
                ),
                align="left",
            )
            excise_lfl_file = st.file_uploader(
                "Акциз жидкости (LFL)",
                type=_XLSX_TYPES,
                key="excise_liquid_lfl_uploader",
            )
            excise_report_file = st.file_uploader(
                "Акциз жидкости (отчётная)",
                type=_XLSX_TYPES,
                key="excise_liquid_report_uploader",
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
                title="Вложенность",
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
                align="right",
            )
            focus_hookah_file = st.file_uploader(
                "Кальянная продукция",
                type=_XLSX_TYPES,
                key="focus_hookah_uploader",
            )
            consumables_nesting_file = st.file_uploader(
                "Вложенность расходников",
                type=_XLSX_TYPES,
                key="consumables_nesting_uploader",
            )

        with col_no_bk:
            render_section_header_with_help(
                title="% чеков без бк",
                image_name="pct_no_bk.png",
                caption=(
                    "Зайдите в Qlik под профилем User2.<br>"
                    'В анализе чеков перейдите в закладку '
                    '"АВТОМАТИЗАЦИЯ РНП B2С ( % чеков без бк)".<br><br>'
                    "В фильтрах отберите актуальную неделю и скачайте отчёт "
                    "без форматирования (не нажимайте галочку при скачивании).<br><br>"
                    'Вставьте скачанный документ в контейнер «% чеков без бк».'
                ),
                caption_title="% чеков без бк",
                align="right",
            )
            checks_no_bk_file = st.file_uploader(
                "% чеков без бк",
                type=_XLSX_TYPES,
                key="checks_no_bk_uploader",
                help=(
                    "Столбцы: Магазин, Кассир, количество чеков, Код клиента. "
                    "Чек без БК — строка с пустым кодом клиента."
                ),
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
            "liquid_cost": liquid_cost_file,
            "excise_liquid_lfl": excise_lfl_file,
            "excise_liquid_report": excise_report_file,
            "checks_clients": checks_clients_file,
            "client_segments": client_segments_file,
            "turnover_week": turnover_week_file,
            "turnover_90": turnover_90_file,
            "focus_hookah": focus_hookah_file,
            "consumables_nesting": consumables_nesting_file,
            "checks_no_bk": checks_no_bk_file,
        }
        st.session_state["run_analysis"] = True
        container.empty()
        return UploadedFiles(
            sales=data_file,
            liquid_cost=liquid_cost_file,
            excise_liquid_lfl=excise_lfl_file,
            excise_liquid_report=excise_report_file,
            checks_clients=checks_clients_file,
            client_segments=client_segments_file,
            turnover_week=turnover_week_file,
            turnover_90=turnover_90_file,
            focus_hookah=focus_hookah_file,
            consumables_nesting=consumables_nesting_file,
            checks_no_bk=checks_no_bk_file,
            run_analysis=True,
        )

    if st.session_state.get("run_analysis"):
        u = st.session_state.get("uploaded_files", {})
        return UploadedFiles(
            sales=u.get("sales"),
            liquid_cost=u.get("liquid_cost"),
            excise_liquid_lfl=u.get("excise_liquid_lfl"),
            excise_liquid_report=u.get("excise_liquid_report"),
            checks_clients=u.get("checks_clients"),
            client_segments=u.get("client_segments"),
            turnover_week=u.get("turnover_week"),
            turnover_90=u.get("turnover_90"),
            focus_hookah=u.get("focus_hookah"),
            consumables_nesting=u.get("consumables_nesting"),
            checks_no_bk=u.get("checks_no_bk"),
            run_analysis=True,
        )

    return UploadedFiles()


def _inject_upload_page_styles() -> None:
    st.markdown(
        """
        <style>
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
