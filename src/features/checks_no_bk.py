"""Блок «% чеков без БК»: продавцы, магазины, группы."""

from __future__ import annotations

import html
import io
import re

import pandas as pd
import streamlit as st

from config.constants import (
    PCT_NO_BK_COLUMN_GROUPS,
    PCT_NO_BK_COLUMN_SELLERS,
    PCT_NO_BK_COLUMN_SHOPS,
)
from data.loaders import _read_excel
from data.references import (
    REF_PCT_NO_BK,
    get_reference_label,
    get_sheets_connection_message,
    load_reference,
    sheets_configured,
)
from features.clients import _has_client_code
from features.reference_update import append_seller_to_pct_no_bk
from ui.upload_help import render_section_header_with_help

COL_PCT_NO_BK = "% без БК"
COL_SELLER = "Продавец"
COL_SHOP = "Магазин"
COL_GROUP = "Группа"

COL_UPLOAD_SHOP = "Магазин"
COL_UPLOAD_CASHIER = "Кассир"
COL_UPLOAD_CHECKS = "количество чеков"
COL_UPLOAD_CLIENT = "Код клиента"

_UPLOAD_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    COL_UPLOAD_SHOP: (COL_UPLOAD_SHOP, "магазин"),
    COL_UPLOAD_CASHIER: (
        COL_UPLOAD_CASHIER,
        "кассир",
        "Кассир (продавец)",
        "кассир (продавец)",
        "Продавец",
        "продавец",
    ),
    COL_UPLOAD_CHECKS: (
        COL_UPLOAD_CHECKS,
        "Количество чеков",
        "количество чеков",
        "количесвто чеков",
    ),
    COL_UPLOAD_CLIENT: (COL_UPLOAD_CLIENT, "код клиента"),
}

_TABLE_ROW_HEIGHT_PX = 35
_NAME_COL_WIDTH_PX = 210
_VALUE_COL_WIDTH_PX = 90

_XLSX_TYPES = ["xlsx", "xls"]
_SESSION_BYTES_KEY = "checks_no_bk_uploaded_bytes"

_NEW_SELLER_ROW_COL_WIDTHS = [2.4, 1]


def _key_part(value: str) -> str:
    return re.sub(r"[^\w]+", "_", str(value)[:48], flags=re.UNICODE).strip("_") or "x"


def _resolve_reference_sellers_column(df: pd.DataFrame) -> str | None:
    columns = [str(c).strip() for c in df.columns]
    if PCT_NO_BK_COLUMN_SELLERS in columns:
        return PCT_NO_BK_COLUMN_SELLERS
    for col in columns:
        if "продавц" in col.casefold():
            return col
    return columns[0] if columns else None


def _non_empty_series_count(series: pd.Series) -> int:
    normalized = series.map(_clean_cashier_label)
    return int(normalized.ne("").sum())


def _clean_cashier_label(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    label = str(value).strip()
    if label.lower() in ("nan", "none", "<na>"):
        return ""
    if re.fullmatch(r"-?\d+\.0", label):
        label = label[:-2]
    return label


def _pick_best_column(
    df: pd.DataFrame,
    lower_map: dict[str, str],
    aliases: tuple[str, ...],
    *,
    keyword_hints: tuple[str, ...] = (),
) -> str | None:
    candidates: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        key = alias.casefold()
        if key in lower_map:
            col = lower_map[key]
            if col not in seen:
                candidates.append(col)
                seen.add(col)
    for key, col in lower_map.items():
        if col in seen:
            continue
        if any(hint in key for hint in keyword_hints):
            candidates.append(col)
            seen.add(col)
    if not candidates:
        return None
    return max(candidates, key=lambda col: _non_empty_series_count(df[col]))


def collect_new_sellers(
    upload_df: pd.DataFrame,
    reference_df: pd.DataFrame | None,
) -> list[str]:
    """Кассиры из файла, которых нет в столбце «Порядок продавцов» справочника %_bk."""
    prepared = _prepare_upload_for_sellers(upload_df)
    if prepared is None:
        return []

    ref_keys: set[str] = set()
    if reference_df is not None and not reference_df.empty:
        ref_df = reference_df.copy()
        ref_df.columns = ref_df.columns.astype(str).str.strip()
        sellers_col = _resolve_reference_sellers_column(ref_df)
        if sellers_col:
            for name in _column_names_from_reference(ref_df, sellers_col):
                ref_keys.add(_normalize_seller_key(name))

    file_sellers: dict[str, str] = {}
    for key, group in prepared.groupby("_seller_key", sort=False):
        if not key or key in ref_keys:
            continue
        total_checks = float(group[COL_UPLOAD_CHECKS].sum())
        if total_checks <= 0:
            continue
        label = _best_cashier_label(group[COL_UPLOAD_CASHIER])
        if not label:
            continue
        prev = file_sellers.get(key)
        if prev is None or len(label) > len(prev):
            file_sellers[key] = label

    return sorted(file_sellers.values(), key=lambda x: x.casefold())


def _best_cashier_label(series: pd.Series) -> str:
    counts: dict[str, int] = {}
    for value in series:
        label = _clean_cashier_label(value)
        if not label:
            continue
        counts[label] = counts.get(label, 0) + 1
    if not counts:
        return ""
    return max(counts.items(), key=lambda item: (item[1], len(item[0])))[0]


def _render_new_sellers_panel(new_sellers: list[str], *, file_loaded: bool) -> None:
    if not file_loaded:
        return

    if not new_sellers:
        return

    if not sheets_configured():
        level, msg = get_sheets_connection_message()
        if level == "error":
            st.error(msg)
        else:
            st.warning(msg)

    st.markdown(
        '<div style="color:#8b949e;font-size:0.72rem;font-weight:600;margin:0 0 8px 0;">'
        "Новые продавцы</div>",
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        for index, seller in enumerate(new_sellers):
            col_name, col_btn = st.columns(_NEW_SELLER_ROW_COL_WIDTHS)
            key_suffix = f"{index}_{_key_part(seller)}"
            with col_name:
                st.markdown(
                    '<div style="color:#b1bac4;font-size:0.9rem;line-height:2.4rem;">'
                    f"{html.escape(seller)}</div>",
                    unsafe_allow_html=True,
                )
            with col_btn:
                if st.button(
                    "Добавить",
                    key=f"checks_no_bk_add_seller_{key_suffix}",
                    use_container_width=True,
                ):
                    ok, message = append_seller_to_pct_no_bk(seller)
                    if ok:
                        st.success(message)
                    else:
                        st.error(message)
                    st.rerun()


def _reference_column_series(df: pd.DataFrame, column: str) -> pd.Series:
    """Столбец справочника; при дублях заголовков берётся первый."""
    selected = df.loc[:, column]
    if isinstance(selected, pd.DataFrame):
        return selected.iloc[:, 0]
    return selected


def _column_names_from_reference(df: pd.DataFrame, column: str) -> list[str]:
    names: list[str] = []
    for val in _reference_column_series(df, column):
        if pd.isna(val):
            continue
        name = str(val).strip()
        if name and name.lower() not in ("nan", "none"):
            names.append(name)
    return names


def _normalize_label(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip().casefold()


def _normalize_seller_key(value: object) -> str:
    text = _normalize_label(value)
    if not text:
        return ""
    text = re.sub(r"[.\u00b7]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _canonical_seller_label(series: pd.Series) -> str:
    return _best_cashier_label(series)


def _normalize_shop_key(value: object) -> str:
    return _normalize_label(value)


def _fmt_share_pct(no_bk_checks: float, total_checks: float) -> str:
    if total_checks <= 0:
        return ""
    return f"{100 * no_bk_checks / total_checks:.1f}%".replace(".", ",")


def _resolve_upload_columns(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df.columns = df.columns.astype(str).str.strip()
    lower_map = {str(c).strip().casefold(): c for c in df.columns}
    resolved: dict[str, str] = {}

    shop_col = _pick_best_column(
        df,
        lower_map,
        _UPLOAD_COLUMN_ALIASES[COL_UPLOAD_SHOP],
        keyword_hints=("магазин",),
    )
    if shop_col is None:
        raise ValueError(f"В файле отсутствует столбец «{COL_UPLOAD_SHOP}».")
    resolved[COL_UPLOAD_SHOP] = shop_col

    cashier_col = _pick_best_column(
        df,
        lower_map,
        _UPLOAD_COLUMN_ALIASES[COL_UPLOAD_CASHIER],
        keyword_hints=("кассир", "продавец", "сотрудник"),
    )
    if cashier_col is None:
        raise ValueError(f"В файле отсутствует столбец «{COL_UPLOAD_CASHIER}».")
    resolved[COL_UPLOAD_CASHIER] = cashier_col

    for canonical in (COL_UPLOAD_CHECKS, COL_UPLOAD_CLIENT):
        found = None
        for alias in _UPLOAD_COLUMN_ALIASES[canonical]:
            key = alias.casefold()
            if key in lower_map:
                found = lower_map[key]
                break
        if found is None:
            raise ValueError(f"В файле отсутствует столбец «{canonical}».")
        resolved[canonical] = found

    rename = {src: dst for dst, src in resolved.items() if src != dst}
    for src, dst in rename.items():
        if dst in df.columns and src != dst:
            df = df.drop(columns=[dst])
    if rename:
        df = df.rename(columns=rename)
    return df


def _prepare_upload_for_sellers(raw: pd.DataFrame | None) -> pd.DataFrame | None:
    """Строки с кассиром — без отсечения по пустому магазину (для списка продавцов)."""
    if raw is None or raw.empty:
        return None
    df = _resolve_upload_columns(raw)
    df[COL_UPLOAD_CHECKS] = pd.to_numeric(df[COL_UPLOAD_CHECKS], errors="coerce").fillna(0)
    df[COL_UPLOAD_SHOP] = df[COL_UPLOAD_SHOP].astype(str).str.strip()
    df[COL_UPLOAD_CASHIER] = df[COL_UPLOAD_CASHIER].map(_clean_cashier_label)
    df = df.loc[
        df[COL_UPLOAD_CASHIER].ne("")
        & ~df[COL_UPLOAD_CASHIER].str.casefold().str.contains("итог", na=False)
    ]
    if df.empty:
        return None
    df = df.copy()
    df["_seller_key"] = df[COL_UPLOAD_CASHIER].map(_normalize_seller_key)
    df = df.loc[df["_seller_key"].ne("")]
    return df if not df.empty else None


def _prepare_upload_df(raw: pd.DataFrame | None) -> pd.DataFrame | None:
    df = _prepare_upload_for_sellers(raw)
    if df is None:
        return None
    df = df.loc[
        df[COL_UPLOAD_SHOP].ne("")
        & ~df[COL_UPLOAD_SHOP].str.casefold().str.contains("итог", na=False)
    ]
    if df.empty:
        return None
    return df


def _checks_without_bk_sum(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    mask = ~_has_client_code(df[COL_UPLOAD_CLIENT])
    return float(df.loc[mask, COL_UPLOAD_CHECKS].sum())


def _pct_for_rows(rows: pd.DataFrame) -> str:
    total = float(rows[COL_UPLOAD_CHECKS].sum())
    if total <= 0:
        return ""
    no_bk = _checks_without_bk_sum(rows)
    return _fmt_share_pct(no_bk, total)


def _build_shop_group_map(groups_df: pd.DataFrame | None) -> dict[str, str]:
    if groups_df is None or not isinstance(groups_df, pd.DataFrame) or groups_df.empty:
        return {}
    df = groups_df.copy()
    df.columns = df.columns.astype(str).str.strip()
    if COL_SHOP not in df.columns or "Группа" not in df.columns:
        return {}
    mapping: dict[str, str] = {}
    for _, row in df.iterrows():
        shop = str(row[COL_SHOP]).strip()
        group = str(row["Группа"]).strip()
        if shop and group and shop.lower() not in ("nan", "none"):
            mapping[_normalize_shop_key(shop)] = group
    return mapping


def _build_pct_table(
    reference_df: pd.DataFrame | None,
    order_column: str,
    name_column: str,
    pct_by_name: dict[str, str],
) -> pd.DataFrame:
    if reference_df is None or reference_df.empty:
        return pd.DataFrame(columns=[name_column, COL_PCT_NO_BK])

    df = reference_df.copy()
    df.columns = df.columns.astype(str).str.strip()
    if order_column not in df.columns:
        return pd.DataFrame(columns=[name_column, COL_PCT_NO_BK])

    names = _column_names_from_reference(df, order_column)
    if not names:
        return pd.DataFrame(columns=[name_column, COL_PCT_NO_BK])

    values = [pct_by_name.get(_normalize_seller_key(name), "") for name in names]
    return pd.DataFrame({name_column: names, COL_PCT_NO_BK: values})


def _compute_seller_pcts(upload_df: pd.DataFrame) -> dict[str, str]:
    prepared = _prepare_upload_for_sellers(upload_df)
    if prepared is None:
        return {}

    out: dict[str, str] = {}
    for seller_key, group in prepared.groupby("_seller_key", sort=False):
        if not seller_key:
            continue
        out[str(seller_key)] = _pct_for_rows(group)
    return out


def _compute_shop_pcts(upload_df: pd.DataFrame) -> dict[str, str]:
    prepared = _prepare_upload_df(upload_df)
    if prepared is None:
        return {}

    prepared = prepared.copy()
    prepared["_key"] = prepared[COL_UPLOAD_SHOP].map(_normalize_shop_key)
    prepared = prepared.loc[prepared["_key"].ne("")]

    out: dict[str, str] = {}
    for shop_key, group in prepared.groupby("_key", sort=False):
        out[str(shop_key)] = _pct_for_rows(group)
    return out


def _compute_group_pcts(
    upload_df: pd.DataFrame,
    groups_df: pd.DataFrame | None,
) -> dict[str, str]:
    prepared = _prepare_upload_df(upload_df)
    if prepared is None:
        return {}

    shop_group_map = _build_shop_group_map(groups_df)
    if not shop_group_map:
        return {}

    prepared = prepared.copy()
    prepared["_group"] = (
        prepared[COL_UPLOAD_SHOP]
        .map(_normalize_shop_key)
        .map(shop_group_map)
        .map(_normalize_label)
    )
    prepared = prepared.loc[prepared["_group"].ne("")]

    out: dict[str, str] = {}
    for group_key, group in prepared.groupby("_group", sort=False):
        out[str(group_key)] = _pct_for_rows(group)
    return out


def build_sellers_no_bk_table(
    reference_df: pd.DataFrame | None = None,
    upload_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    pct_by_name = _compute_seller_pcts(upload_df) if upload_df is not None else {}
    sellers_col = PCT_NO_BK_COLUMN_SELLERS
    if reference_df is not None and not reference_df.empty:
        ref_df = reference_df.copy()
        ref_df.columns = ref_df.columns.astype(str).str.strip()
        sellers_col = _resolve_reference_sellers_column(ref_df) or sellers_col
    return _build_pct_table(
        reference_df,
        sellers_col,
        COL_SELLER,
        pct_by_name,
    )


def build_shops_no_bk_table(
    reference_df: pd.DataFrame | None = None,
    upload_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    pct_by_name = _compute_shop_pcts(upload_df) if upload_df is not None else {}
    return _build_pct_table(
        reference_df,
        PCT_NO_BK_COLUMN_SHOPS,
        COL_SHOP,
        pct_by_name,
    )


def build_groups_no_bk_table(
    reference_df: pd.DataFrame | None = None,
    upload_df: pd.DataFrame | None = None,
    groups_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    pct_by_name = (
        _compute_group_pcts(upload_df, groups_df) if upload_df is not None else {}
    )
    return _build_pct_table(
        reference_df,
        PCT_NO_BK_COLUMN_GROUPS,
        COL_GROUP,
        pct_by_name,
    )


def _load_pct_no_bk_reference() -> pd.DataFrame | None:
    try:
        return load_reference(REF_PCT_NO_BK)
    except FileNotFoundError:
        st.warning(
            f"Справочник «% без БК» не найден ({get_reference_label(REF_PCT_NO_BK)}). "
            "Таблицы будут пустыми."
        )
        return None
    except Exception as exc:  # noqa: BLE001
        st.error(f"Не удалось загрузить справочник «% без БК»: {exc}")
        return None


def _read_checks_no_bk_bytes(content: bytes, *, label: str) -> pd.DataFrame | None:
    if not content:
        return None
    try:
        return _read_excel(io.BytesIO(content), label=label)
    except ValueError as exc:
        st.error(str(exc))
        return None


def _inject_checks_no_bk_upload_styles() -> None:
    st.markdown(
        """
        <style>
        .checks-no-bk-block [data-testid="stCaption"],
        .checks-no-bk-block div[data-testid="stFileUploader"] [data-testid="stFileUploaderFileName"],
        .checks-no-bk-block div[data-testid="stFileUploader"] [data-testid="stFileUploaderFileSize"],
        .checks-no-bk-block div[data-testid="stFileUploader"] section[data-testid="stFileUploaderDropzone"] ~ div,
        .checks-no-bk-block div[data-testid="stFileUploader"] [data-testid="stMarkdownContainer"] p {
            display: none !important;
        }
        .checks-no-bk-upload .help-popover {
            width: auto;
            text-align: right;
        }
        .checks-no-bk-upload .help-popover__panel {
            display: none;
        }
        .checks-no-bk-upload .help-popover__toggle:checked ~ .help-popover__panel {
            display: block;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_order_table(
    table: pd.DataFrame,
    *,
    name_column: str,
) -> None:
    if table.empty:
        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )
        return

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        row_height=_TABLE_ROW_HEIGHT_PX,
        column_config={
            name_column: st.column_config.TextColumn(
                name_column,
                width=_NAME_COL_WIDTH_PX,
            ),
            COL_PCT_NO_BK: st.column_config.TextColumn(
                COL_PCT_NO_BK,
                width=_VALUE_COL_WIDTH_PX,
            ),
        },
    )


def render_checks_no_bk_block(
    *,
    groups_df: pd.DataFrame | None = None,
) -> None:
    """Загрузчик Excel и три таблицы (продавцы, магазины, группы)."""
    try:
        _render_checks_no_bk_block_impl(groups_df=groups_df)
    except Exception as exc:  # noqa: BLE001
        st.error("Ошибка в блоке «% чеков без БК».")
        st.exception(exc)


def _render_checks_no_bk_block_impl(
    *,
    groups_df: pd.DataFrame | None = None,
) -> None:
    st.markdown("---")
    st.markdown('<div class="checks-no-bk-block">', unsafe_allow_html=True)
    _inject_checks_no_bk_upload_styles()

    col_upload, _col_spacer = st.columns([1, 3], gap="small")
    with col_upload:
        st.markdown('<div class="checks-no-bk-upload">', unsafe_allow_html=True)
        render_section_header_with_help(
            title="Динамика чеков без бк %",
            image_name="pct_no_bk.png",
            caption=(
                "Зайдите в Qlik под профилем User2.<br>"
                'В анализе чеков перейдите в закладку '
                '"АВТОМАТИЗАЦИЯ РНП B2С ( % чеков без бк)".<br><br>'
                "В фильтрах отберите актуальную неделю и скачайте отчёт "
                "без форматирования (не нажимайте галочку при скачивании).<br><br>"
                'Вставьте скачанный документ в контейнер «% чеков без бк».'
            ),
            align="right",
            popover_key="checks-no-bk-dynamics",
        )

        uploaded = st.file_uploader(
            "Загрузите Excel",
            type=_XLSX_TYPES,
            key="checks_no_bk_uploader",
            label_visibility="collapsed",
            help=(
                "Столбцы: Магазин, Кассир, количество чеков, Код клиента. "
                "Чек без БК — строка с пустым кодом клиента."
            ),
        )
        st.markdown("</div>", unsafe_allow_html=True)

    if uploaded is not None:
        st.session_state[_SESSION_BYTES_KEY] = uploaded.getvalue()

    upload_bytes: bytes | None = None
    if uploaded is not None:
        upload_bytes = uploaded.getvalue()
    elif _SESSION_BYTES_KEY in st.session_state:
        raw_bytes = st.session_state.get(_SESSION_BYTES_KEY)
        if isinstance(raw_bytes, (bytes, bytearray)) and raw_bytes:
            upload_bytes = bytes(raw_bytes)

    upload_df: pd.DataFrame | None = None
    if upload_bytes:
        upload_df = _read_checks_no_bk_bytes(upload_bytes, label="Файл % без БК")
        if upload_df is not None and upload_df.empty:
            st.warning("Загруженный файл не содержит данных.")
            upload_df = None

    reference_df = _load_pct_no_bk_reference()
    if reference_df is not None:
        reference_df = reference_df.copy()
        reference_df.columns = reference_df.columns.astype(str).str.strip()
        missing = []
        sellers_col = _resolve_reference_sellers_column(reference_df)
        required_cols = [PCT_NO_BK_COLUMN_SHOPS, PCT_NO_BK_COLUMN_GROUPS]
        if sellers_col is None:
            required_cols.insert(0, PCT_NO_BK_COLUMN_SELLERS)
        else:
            required_cols.insert(0, sellers_col)
        for col in required_cols:
            if col not in reference_df.columns:
                missing.append(col)
        if missing:
            st.warning(
                "В справочнике «%_bk» отсутствуют столбцы: "
                + ", ".join(f"«{c}»" for c in missing)
                + "."
            )

    if upload_df is not None:
        try:
            _prepare_upload_for_sellers(upload_df)
        except ValueError as exc:
            st.error(str(exc))
            upload_df = None

    if upload_df is not None and _build_shop_group_map(groups_df) == {}:
        st.info(
            "Справочник магазинов недоступен — таблица групп не будет рассчитана."
        )

    new_sellers = (
        collect_new_sellers(upload_df, reference_df) if upload_df is not None else []
    )
    _render_new_sellers_panel(new_sellers, file_loaded=upload_df is not None)

    col_sellers, col_shops, col_groups = st.columns([1, 1, 1])

    with col_sellers:
        st.markdown("**Продавцы**")
        _render_order_table(
            build_sellers_no_bk_table(reference_df, upload_df),
            name_column=COL_SELLER,
        )

    with col_shops:
        st.markdown("**Магазины**")
        _render_order_table(
            build_shops_no_bk_table(reference_df, upload_df),
            name_column=COL_SHOP,
        )

    with col_groups:
        st.markdown("**Группы**")
        _render_order_table(
            build_groups_no_bk_table(reference_df, upload_df, groups_df),
            name_column=COL_GROUP,
        )

    st.markdown("</div>", unsafe_allow_html=True)
