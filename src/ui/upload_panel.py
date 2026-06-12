from dataclasses import dataclass

import streamlit as st

_XLSX_TYPES = ["xlsx", "xls"]


@dataclass
class UploadedFiles:
    sales: object = None
    checks_clients: object = None
    client_segments: object = None
    turnover_week: object = None
    turnover_90: object = None
    run_analysis: bool = False


def _render_section_header(title: str, tooltip: str) -> None:
    """Заголовок секции с иконкой подсказки, как на макете."""
    header_col, info_col = st.columns([0.92, 0.08])
    with header_col:
        st.markdown(
            f"<div class='upload-section-title'>{title}</div>",
            unsafe_allow_html=True,
        )
    with info_col:
        st.markdown(
            f"""
            <div class="upload-info-wrap">
              <span class="upload-info-icon" title="{tooltip}">i</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_upload_panel() -> UploadedFiles:
    """Панель загрузки данных."""
    container = st.container()
    with container:
        _inject_upload_styles()
        col1, col2, col3 = st.columns(3)

        with col1:
            _render_section_header(
                "Продажи",
                "Файл продаж в формате XLSX или XLS",
            )
            data_file = st.file_uploader(
                "Продажи",
                type=_XLSX_TYPES,
                key="data",
                help="Лимит 200 МБ на файл • XLSX, XLS",
            )

        with col2:
            _render_section_header(
                "Оборачиваемость",
                "Файлы оборачиваемости за 7 и 90 дней в формате XLSX или XLS",
            )
            turnover_week_file = st.file_uploader(
                "7 дней",
                type=_XLSX_TYPES,
                key="turnover_week",
                help="Лимит 200 МБ на файл • XLSX, XLS",
            )
            turnover_90_file = st.file_uploader(
                "90 дней",
                type=_XLSX_TYPES,
                key="turnover_90",
                help="Лимит 200 МБ на файл • XLSX, XLS",
            )

        with col3:
            _render_section_header(
                "Чеки и клиенты",
                "Файлы чеков, клиентов и сегментов покупателей в формате XLSX или XLS",
            )
            checks_clients_file = st.file_uploader(
                "Чеки и клиенты",
                type=_XLSX_TYPES,
                key="checks_clients",
                help="Лимит 200 МБ на файл • XLSX, XLS",
            )
            client_segments_file = st.file_uploader(
                "Сегменты покупателей",
                type=_XLSX_TYPES,
                key="client_segments",
                help="Лимит 200 МБ на файл • XLSX, XLS",
            )

        run_analysis = st.button(
            "Загрузить данные",
            type="primary",
            key="upload_data_btn",
        )

    if run_analysis:
        st.session_state["data_reload_requested"] = True
        st.session_state["uploaded_files"] = {
            "sales": data_file,
            "checks_clients": checks_clients_file,
            "client_segments": client_segments_file,
            "turnover_week": turnover_week_file,
            "turnover_90": turnover_90_file,
        }
        st.session_state["run_analysis"] = True
        container.empty()
        return UploadedFiles(
            sales=data_file,
            checks_clients=checks_clients_file,
            client_segments=client_segments_file,
            turnover_week=turnover_week_file,
            turnover_90=turnover_90_file,
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
            run_analysis=True,
        )

    return UploadedFiles()


def _inject_upload_styles() -> None:
    st.markdown(
        """
        <style>
        .upload-section-title {
            font-size: 1.35rem;
            font-weight: 700;
            color: #FAFAFA;
            margin-bottom: 4px;
            line-height: 1.2;
        }
        .upload-info-wrap {
            display: flex;
            justify-content: flex-end;
            padding-top: 2px;
        }
        .upload-info-icon {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 28px;
            height: 28px;
            border-radius: 6px;
            border: 1px solid #3a3d46;
            background: #1a1c24;
            color: #4A90E2;
            font-weight: 700;
            font-size: 0.85rem;
            font-style: italic;
            cursor: help;
        }
        div[data-testid="stFileUploader"] {
            margin-bottom: 0.75rem;
        }
        div[data-testid="stFileUploader"] label p {
            color: #A3A8B4 !important;
            font-size: 0.9rem !important;
            font-weight: 500 !important;
            margin-bottom: 6px !important;
        }
        section[data-testid="stFileUploaderDropzone"] {
            background-color: #262730 !important;
            border: 1px solid #3a3d46 !important;
            border-radius: 10px !important;
            min-height: 72px !important;
            padding: 12px 16px !important;
        }
        section[data-testid="stFileUploaderDropzone"]:hover {
            border-color: #4A90E2 !important;
        }
        section[data-testid="stFileUploaderDropzone"] span,
        section[data-testid="stFileUploaderDropzone"] p {
            color: #FAFAFA !important;
        }
        section[data-testid="stFileUploaderDropzone"] small {
            color: #A3A8B4 !important;
        }
        section[data-testid="stFileUploaderDropzone"] button {
            background: transparent !important;
            border: 1px solid #3a3d46 !important;
            color: #FAFAFA !important;
            border-radius: 8px !important;
            font-weight: 500 !important;
        }
        section[data-testid="stFileUploaderDropzone"] button:hover,
        section[data-testid="stFileUploaderDropzone"] button:active,
        section[data-testid="stFileUploaderDropzone"] button:focus,
        section[data-testid="stFileUploaderDropzone"] button:focus-visible {
            border-color: #4A90E2 !important;
            background: rgba(74, 144, 226, 0.08) !important;
            box-shadow: none !important;
            color: #FAFAFA !important;
        }
        .st-key-upload_data_btn button[kind="primary"] {
            background-color: #e84545 !important;
            border-color: #e84545 !important;
        }
        .st-key-upload_data_btn button[kind="primary"]:hover,
        .st-key-upload_data_btn button[kind="primary"]:active,
        .st-key-upload_data_btn button[kind="primary"]:focus,
        .st-key-upload_data_btn button[kind="primary"]:focus-visible {
            background-color: #d63f3f !important;
            border-color: #d63f3f !important;
            box-shadow: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
