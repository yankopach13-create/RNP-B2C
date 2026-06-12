from dataclasses import dataclass

import streamlit as st

_XLSX_TYPES = ["xlsx", "xls"]
_UPLOADER_LABEL = "XLS, XLSX"


@dataclass
class UploadedFiles:
    sales: object = None
    checks_clients: object = None
    client_segments: object = None
    turnover_week: object = None
    turnover_90: object = None
    run_analysis: bool = False


def render_upload_panel() -> UploadedFiles:
    """Панель загрузки данных."""
    container = st.container()
    with container:
        _inject_upload_panel_styles()
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown(
                "<h2 style='margin:0 0 0.35rem 0; padding:0; font-size:1.75rem;'>Продажи</h2>",
                unsafe_allow_html=True,
            )
            data_file = st.file_uploader(
                _UPLOADER_LABEL,
                type=_XLSX_TYPES,
                key="data",
            )

        with col2:
            st.subheader("Оборачиваемость")
            st.markdown(
                "<div class='upload-item-name'>7 дней</div>",
                unsafe_allow_html=True,
            )
            turnover_week_file = st.file_uploader(
                _UPLOADER_LABEL,
                type=_XLSX_TYPES,
                key="turnover_week",
            )
            st.markdown(
                "<div class='upload-item-name'>90 дней</div>",
                unsafe_allow_html=True,
            )
            turnover_90_file = st.file_uploader(
                _UPLOADER_LABEL,
                type=_XLSX_TYPES,
                key="turnover_90",
            )

        with col3:
            st.subheader("Чеки и клиенты")
            st.markdown(
                "<div class='upload-item-name'>Чеки и клиенты</div>",
                unsafe_allow_html=True,
            )
            checks_clients_file = st.file_uploader(
                _UPLOADER_LABEL,
                type=_XLSX_TYPES,
                key="checks_clients",
            )
            st.markdown(
                "<div class='upload-item-name'>Сегменты покупателей</div>",
                unsafe_allow_html=True,
            )
            client_segments_file = st.file_uploader(
                _UPLOADER_LABEL,
                type=_XLSX_TYPES,
                key="client_segments",
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


def _inject_upload_panel_styles() -> None:
    st.markdown(
        """
        <style>
        .upload-item-name {
            font-size: 0.9rem;
            font-weight: 600;
            color: #FAFAFA;
            margin: 0.15rem 0 0.1rem 0;
        }
        div[data-testid="stFileUploader"] {
            margin-bottom: 0.35rem;
        }
        div[data-testid="stFileUploader"] label {
            margin-bottom: 0.15rem !important;
        }
        div[data-testid="stFileUploader"] label p {
            font-size: 0.85rem !important;
            color: #A3A8B4 !important;
            margin: 0 !important;
        }
        div[data-testid="stFileUploader"] label [data-testid="stTooltipIcon"],
        div[data-testid="stFileUploader"] label button {
            display: none !important;
        }
        section[data-testid="stFileUploaderDropzone"] {
            min-height: 2.1rem !important;
            padding: 0.3rem 0.65rem !important;
        }
        section[data-testid="stFileUploaderDropzone"] > div {
            align-items: center !important;
            gap: 0.5rem !important;
            min-height: 0 !important;
        }
        section[data-testid="stFileUploaderDropzone"] > div > div:first-child {
            display: none !important;
        }
        section[data-testid="stFileUploaderDropzone"] button {
            display: inline-flex !important;
            margin-left: auto !important;
            min-height: 1.75rem !important;
            padding: 0.2rem 0.65rem !important;
            font-size: 0.8rem !important;
        }
        section[data-testid="stFileUploaderDropzone"]:has([data-testid="stFileUploaderFile"]) > div > div:first-child {
            display: flex !important;
            flex: 1 !important;
            min-width: 0 !important;
            font-size: 0.82rem !important;
            color: #FAFAFA !important;
        }
        section[data-testid="stFileUploaderDropzone"]:has([data-testid="stFileUploaderFile"]) svg,
        section[data-testid="stFileUploaderDropzone"]:has([data-testid="stFileUploaderFile"]) small {
            display: none !important;
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
