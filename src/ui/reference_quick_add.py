"""Форма быстрого добавления магазинов и товаров в справочники (Sheets / xlsx)."""

from __future__ import annotations

import html
import re

import streamlit as st

from data.references import get_sheets_connection_message, sheets_configured
from features.categories import (
    category_pair_label,
    format_category_pair,
    parse_category_pair,
    unique_category_pairs,
)
from features.data_prep import UnmatchedProductGroup
from features.reference_orders import (
    resolve_categories_general,
    resolve_categories_rnp,
    resolve_groups_order,
)
from features.reference_update import (
    QuickCategoryOrderEntry,
    QuickProductEntry,
    apply_reference_updates_batch,
)

CREATE_NEW_CATEGORY_LABEL = "Создать новую категорию"

# Магазины: подпись | группа. Товары: подпись | категория (+ блок ниже при «Создать новую»).
_SHOP_ROW_COL_WIDTHS = [1.4, 2.4]
_REF_ROW_COL_WIDTHS = [1.35, 2.1]

_POSITION_END = "— В конец списка —"
_POSITION_START = "— В начало списка —"
_POSITION_START_VALUE = "__START__"

_ST = {
    "alert": (
        "background-color:#1A2332;color:#9ec5fe;padding:12px 16px;border-radius:6px;"
        "border-left:4px solid #3b82f6;margin-bottom:14px;font-size:0.95rem;"
    ),
    "title": "color:#f0f6fc;font-size:1.35rem;font-weight:700;margin:0 0 12px 0;",
    "section_highlight": (
        "background:linear-gradient(90deg, rgba(35,134,54,0.22) 0%, rgba(35,134,54,0.06) 100%);"
        "color:#f0f6fc;font-weight:700;font-size:0.9rem;text-transform:uppercase;"
        "letter-spacing:0.07em;padding:10px 14px;margin:14px 0 10px 0;border-radius:6px;"
        "border:1px solid rgba(63,185,80,0.4);border-left:4px solid #3fb950;",
    ),
    "col_header": (
        "color:#8b949e;font-size:0.72rem;font-weight:600;margin:0 0 6px 0;"
        "padding:4px 2px 2px 0;line-height:1.2;"
    ),
    "new_item": (
        "background-color:rgba(48,54,61,0.5);color:#b1bac4;font-style:italic;font-size:0.88rem;"
        "line-height:1.45;word-break:break-word;padding:6px 10px;border-radius:4px;"
        "border:1px solid rgba(72,79,88,0.55);"
    ),
    "new_item_product": (
        "background-color:rgba(48,54,61,0.5);color:#56d364;font-style:italic;font-size:0.88rem;"
        "line-height:1.45;word-break:break-word;padding:6px 10px;border-radius:4px;"
        "border:1px solid rgba(63,185,80,0.45);",
    ),
    "new_cat_block": (
        "background-color:rgba(35,134,54,0.08);border:1px solid rgba(63,185,80,0.35);"
        "border-radius:6px;padding:10px 12px;margin:0 0 14px 0;"
    ),
}


def _key_part(s: str) -> str:
    return re.sub(r"[^\w]+", "_", str(s)[:48], flags=re.UNICODE).strip("_") or "x"


def _format_category_select_label(label: str) -> str:
    """Подпись в списке; для «Создать новую» — маркер (цвет задаётся CSS)."""
    if label == CREATE_NEW_CATEGORY_LABEL:
        return f"➕ {label}"
    return label


def _inject_create_category_select_style() -> None:
    """Синий пункт «Создать новую категорию» в выпадающем списке (Baseweb select)."""
    st.markdown(
        """
        <style>
        div[data-baseweb="popover"] li[role="option"]:last-child {
            color: #58a6ff !important;
            font-weight: 600 !important;
        }
        div[data-testid="stSelectbox"] [data-baseweb="select"] > div {
            color: inherit;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_shop_column_headers() -> None:
    h1, h2 = st.columns(_SHOP_ROW_COL_WIDTHS)
    with h1:
        st.markdown(f'<div style="{_ST["col_header"]}">&nbsp;</div>', unsafe_allow_html=True)
    with h2:
        st.markdown(f'<div style="{_ST["col_header"]}">Группа</div>', unsafe_allow_html=True)


def _render_product_column_headers() -> None:
    h1, h2 = st.columns(_REF_ROW_COL_WIDTHS)
    with h1:
        st.markdown(f'<div style="{_ST["col_header"]}">&nbsp;</div>', unsafe_allow_html=True)
    with h2:
        st.markdown(f'<div style="{_ST["col_header"]}">Категория</div>', unsafe_allow_html=True)


def _category_pair_options(categories_df) -> list[tuple[str, str]]:
    """(stored_value, label) для selectbox."""
    pairs = unique_category_pairs(categories_df)
    return [
        (stored, category_pair_label(rnp, general))
        for rnp, general, stored in pairs
    ]


def _position_options(order_list: list[str]) -> list[str]:
    opts = [_POSITION_END, _POSITION_START]
    opts.extend(f"После: {name}" for name in order_list)
    return opts


def _parse_position_choice(choice: str) -> str | None:
    """None — в конец; __START__ — в начало; иначе имя категории «после которой»."""
    c = str(choice or "").strip()
    if not c or c == _POSITION_END:
        return None
    if c == _POSITION_START:
        return _POSITION_START_VALUE
    if c.startswith("После: "):
        return c[7:].strip()
    return None


def _resolve_category_from_form(
    sel_label: str,
    label_to_stored: dict[str, str],
    new_rnp: str,
    new_general: str,
) -> tuple[str | None, str | None, bool]:
    """
    (category_pair, error, is_new_category).
    «Создать новую категорию» — поля РНП и Общий РНП; иначе выбор из списка.
    """
    label = str(sel_label or "").strip()
    if label == CREATE_NEW_CATEGORY_LABEL:
        rnp = str(new_rnp or "").strip()
        general = str(new_general or "").strip()
        if not rnp:
            return None, "Укажите название категории РНП.", True
        if not general:
            return None, "Укажите название категории Общего РНП.", True
        return format_category_pair(rnp, general), None, True

    if label:
        stored = label_to_stored.get(label, label)
        rnp, general = parse_category_pair(stored)
        if rnp:
            return format_category_pair(rnp, general), None, False
        return None, "Некорректная категория в списке.", False

    return None, None, False


def _render_new_category_fields(
    kp: str,
    rnp_position_options: list[str],
    general_position_options: list[str],
) -> None:
    """Поля новой категории и позиции в списке — под строкой товара."""
    st.markdown(f'<div style="{_ST["new_cat_block"]}">', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.text_input(
            "Категория РНП",
            value="",
            key=f"ref_pc_new_rnp_{kp}",
            placeholder="Название для отчёта РНП",
        )
    with c2:
        st.text_input(
            "Категория Общий РНП",
            value="",
            key=f"ref_pc_new_gen_{kp}",
            placeholder="Название для Общего РНП",
        )
    c3, c4 = st.columns(2)
    with c3:
        st.selectbox(
            "Позиция в списке РНП",
            rnp_position_options,
            key=f"ref_pc_pos_rnp_{kp}",
        )
    with c4:
        st.selectbox(
            "Позиция в списке Общий РНП",
            general_position_options,
            key=f"ref_pc_pos_gen_{kp}",
        )
    st.markdown("</div>", unsafe_allow_html=True)


def render_quick_reference_update(
    new_shops: list[str],
    unmatched_products: list[UnmatchedProductGroup],
    groups_df,
    categories_df,
    groups_order_rnp: list[str] | None = None,
    category_order_rnp: list[str] | None = None,
    category_order_general: list[str] | None = None,
) -> None:
    if not new_shops and not unmatched_products:
        return

    st.markdown(
        f'<div style="{_ST["alert"]}">Обнаружены новые товары или магазины — распределите их '
        "в справочнике ниже.</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="{_ST["title"]}">Быстрое добавление в справочники</p>',
        unsafe_allow_html=True,
    )
    if not sheets_configured():
        level, msg = get_sheets_connection_message()
        if level == "error":
            st.error(msg)
        else:
            st.warning(msg)

    group_options = resolve_groups_order(groups_order_rnp)
    if not groups_order_rnp and groups_df is not None and "Группа" in groups_df.columns:
        from_groups = sorted(
            groups_df["Группа"].dropna().astype(str).str.strip().unique().tolist()
        )
        group_options = list(dict.fromkeys(group_options + from_groups))

    pair_options = _category_pair_options(categories_df)
    select_labels = [""] + [label for _, label in pair_options] + [CREATE_NEW_CATEGORY_LABEL]
    label_to_stored = {label: stored for stored, label in pair_options}

    rnp_order = resolve_categories_rnp(category_order_rnp)
    general_order = resolve_categories_general(category_order_general)
    rnp_position_options = _position_options(rnp_order)
    general_position_options = _position_options(general_order)

    with st.container(border=True):
        if new_shops:
            st.markdown(
                f'<div style="{_ST["section_highlight"]}">Новые магазины</div>',
                unsafe_allow_html=True,
            )
            _render_shop_column_headers()
            for i, shop in enumerate(new_shops):
                c1, c2 = st.columns(_SHOP_ROW_COL_WIDTHS)
                ks = _key_part(shop) + f"_{i}"
                with c1:
                    st.markdown(
                        f'<div style="{_ST["new_item"]}">{html.escape(shop)}</div>',
                        unsafe_allow_html=True,
                    )
                with c2:
                    st.selectbox(
                        "Группа РНП",
                        [""] + group_options,
                        key=f"ref_shop_sel_{ks}",
                        label_visibility="collapsed",
                    )

        if unmatched_products:
            _inject_create_category_select_style()
            st.markdown(
                f'<div style="{_ST["section_highlight"]}">Новые товары</div>',
                unsafe_allow_html=True,
            )
            _render_product_column_headers()
            for j, (u2, u3, _u4s) in enumerate(unmatched_products):
                label = f"{u2} \\ {u3}"
                kp = f"{j}_{_key_part(u2)}_{_key_part(u3)}"
                c1, c2 = st.columns(_REF_ROW_COL_WIDTHS)
                with c1:
                    st.markdown(
                        f'<div style="{_ST["new_item_product"]}">{html.escape(label)}</div>',
                        unsafe_allow_html=True,
                    )
                with c2:
                    sel = st.selectbox(
                        "Категория",
                        select_labels,
                        key=f"ref_pc_sel_{kp}",
                        label_visibility="collapsed",
                        format_func=_format_category_select_label,
                    )
                if sel == CREATE_NEW_CATEGORY_LABEL:
                    _render_new_category_fields(
                        kp, rnp_position_options, general_position_options
                    )

        submitted = st.button(
            "Обновить справочники и пересчитать отчёт",
            type="primary",
            use_container_width=True,
            key="quick_reference_submit",
        )

    if not submitted:
        return

    shop_entries: list[tuple[str, str]] = []
    validation_messages: list[str] = []

    if new_shops:
        for i, shop in enumerate(new_shops):
            ks = _key_part(shop) + f"_{i}"
            sel = str(st.session_state.get(f"ref_shop_sel_{ks}", "") or "").strip()
            if not sel:
                validation_messages.append(f"«{shop}»: выберите группу РНП.")
                continue
            shop_entries.append((shop, sel))

    product_entries: list[QuickProductEntry] = []

    if unmatched_products:
        for j, (u2, u3, u4_variants) in enumerate(unmatched_products):
            kp = f"{j}_{_key_part(u2)}_{_key_part(u3)}"
            sel_label = str(st.session_state.get(f"ref_pc_sel_{kp}", "") or "").strip()

            new_rnp = str(st.session_state.get(f"ref_pc_new_rnp_{kp}", "") or "")
            new_general = str(st.session_state.get(f"ref_pc_new_gen_{kp}", "") or "")
            pair, err, is_new = _resolve_category_from_form(
                sel_label, label_to_stored, new_rnp, new_general
            )

            if err:
                validation_messages.append(f"«{u2} \\ {u3}»: {err}")
                continue
            if not pair:
                validation_messages.append(
                    f"«{u2} \\ {u3}»: выберите категорию из списка или пункт "
                    f"«{CREATE_NEW_CATEGORY_LABEL}» и заполните поля ниже."
                )
                continue

            new_category: QuickCategoryOrderEntry | None = None
            if is_new:
                rnp, general = parse_category_pair(pair)
                new_category = QuickCategoryOrderEntry(
                    rnp=rnp,
                    general=general,
                    rnp_after=_parse_position_choice(
                        st.session_state.get(f"ref_pc_pos_rnp_{kp}", _POSITION_END)
                    ),
                    general_after=_parse_position_choice(
                        st.session_state.get(f"ref_pc_pos_gen_{kp}", _POSITION_END)
                    ),
                )

            product_entries.append(
                QuickProductEntry(
                    u2=u2,
                    u3=u3,
                    u4_variants=list(u4_variants),
                    category_pair=pair,
                    new_category=new_category,
                )
            )

    ok_any = False
    messages: list[str] = list(validation_messages)

    if shop_entries or product_entries:
        ok_any, batch_messages = apply_reference_updates_batch(
            shop_entries, product_entries
        )
        messages.extend(batch_messages)

    for m in messages:
        low = m.lower()
        if "обновл" in low or "добавлен" in low or "актуальна" in low:
            st.success(m)
        elif "не удалось" in m.lower() or m.startswith("Не "):
            st.error(m)
        elif "уже есть" in m.lower():
            st.warning(m)
        else:
            st.info(m)

    if ok_any:
        st.session_state["data_reload_requested"] = True
        st.rerun()
