from dataclasses import dataclass

import streamlit as st


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
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown(
                "<div style='font-size:16px; font-weight:bold; margin-bottom:8px;'>📊 Продажи</div>",
                unsafe_allow_html=True,
            )
            data_file = st.file_uploader(
                "Продажи",
                type="xlsx",
                key="data",
            )

        with col2:
            st.markdown(
                "<div style='font-size:16px; font-weight:bold; margin-bottom:8px;'>🔄 Оборачиваемость</div>",
                unsafe_allow_html=True,
            )
            turnover_week_file = st.file_uploader(
                "7 дней",
                type="xlsx",
                key="turnover_week",
            )
            turnover_90_file = st.file_uploader(
                "90 дней",
                type="xlsx",
                key="turnover_90",
            )

        with col3:
            st.markdown(
                "<div style='font-size:16px; font-weight:bold; margin-bottom:8px;'>💳 Чеки и клиенты</div>",
                unsafe_allow_html=True,
            )
            checks_clients_file = st.file_uploader(
                "Чеки и клиенты",
                type="xlsx",
                key="checks_clients",
            )
            client_segments_file = st.file_uploader(
                "Сегменты покупателей",
                type="xlsx",
                key="client_segments",
            )

        _inject_upload_button_style()
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


def _inject_upload_button_style() -> None:
    st.markdown(
        """
        <style>
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
