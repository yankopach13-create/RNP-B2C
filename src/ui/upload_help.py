from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INSTRUCTIONS_DIR = PROJECT_ROOT / "assets" / "instructions"
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
# Старые имена в коде → фактические файлы в assets/instructions
_IMAGE_STEM_ALIASES: dict[str, str] = {
    "checks_clients": "clients",
    "client_segments": "segments",
    "sales": "sales",
    "turnover": "turnover",
    "hookah": "hookah",
    "focus_hookah": "hookah",
    "fill_free": "fill_free",
    "focus_fill_free": "fill_free",
    "pct_no_bk": "pct_no_bk",
    "checks_no_bk": "pct_no_bk",
}


def _render_help_html(html: str) -> None:
    """Один атомарный HTML-блок без обёртки Streamlit в <p>."""
    st.html(html)


def inject_help_popover_styles() -> None:
    """Стили всплывающих подсказок — на каждом rerun Streamlit."""
    st.markdown(
        """
        <style>
        .help-popover {
            position: relative;
            display: inline-block;
            width: auto;
            z-index: 10;
        }
        .help-popover--inline {
            flex-shrink: 0;
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
            list-style: none;
        }
        .help-popover__trigger::-webkit-details-marker {
            display: none;
        }
        .help-popover__trigger::marker {
            content: "";
        }
        .help-popover__trigger:hover {
            background: rgba(255, 255, 255, 0.1);
            border-color: rgba(255, 255, 255, 0.55);
        }
        .help-popover:not([open]) > .help-popover__panel {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
            overflow: hidden !important;
            padding: 0 !important;
            margin: 0 !important;
            border: 0 !important;
        }
        .help-popover[open] > .help-popover__panel {
            display: block !important;
            visibility: visible !important;
            height: auto !important;
            overflow: auto !important;
            padding: 0.9rem !important;
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
        .help-popover__panel {
            position: absolute;
            top: calc(100% + 0.5rem);
            width: min(68vw, 760px);
            min-width: min(92vw, 360px);
            max-width: 92vw;
            max-height: 72vh;
            border-radius: 0.75rem;
            border: 1px solid rgba(250, 250, 250, 0.18);
            background: rgba(15, 15, 15, 0.98);
            box-shadow: 0 16px 36px rgba(0, 0, 0, 0.45);
            text-align: left;
            z-index: 999;
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
        </style>
        """,
        unsafe_allow_html=True,
    )


def _normalize_image_stem(stem: str) -> str:
    return _IMAGE_STEM_ALIASES.get(stem.casefold(), stem)


def _find_image_by_stem(stem: str) -> Path | None:
    stem = _normalize_image_stem(stem)
    stem_key = stem.casefold()
    if not INSTRUCTIONS_DIR.is_dir():
        return None
    for path in INSTRUCTIONS_DIR.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in _IMAGE_EXTENSIONS:
            continue
        if path.stem.casefold() == stem_key:
            return path
    return None


def _resolve_instruction_image_path(image_name: str) -> Path:
    image_path = INSTRUCTIONS_DIR / image_name
    if image_path.exists():
        return image_path

    stem = _normalize_image_stem(Path(image_name).stem)
    for suffix in _IMAGE_EXTENSIONS:
        candidate = INSTRUCTIONS_DIR / f"{stem}{suffix}"
        if candidate.exists():
            return candidate

    found = _find_image_by_stem(stem)
    if found is not None:
        return found

    return image_path


def _build_instruction_image_html(image_name: str) -> str:
    image_path = _resolve_instruction_image_path(image_name)
    if not image_path.exists():
        return (
            "<div class='help-popover__warning'>"
            f"Скриншот не найден: {image_name}"
            "</div>"
        )

    suffix = image_path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "application/octet-stream")
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    data_url = f"data:{mime};base64,{encoded}"

    return (
        "<div class='help-popover__image-wrapper'>"
        f"<img src='{data_url}' alt='{image_name}' class='help-popover__image' />"
        f"<a href='{data_url}' download='{image_path.name}' class='help-popover__download'>"
        "Скачать изображение"
        "</a>"
        "</div>"
    )


def _split_caption_paragraphs(caption: str) -> list[str]:
    if not caption:
        return []
    return [part.strip() for part in caption.split("<br><br>") if part.strip()]


def _build_column_instruction_html(
    title: str,
    caption: str,
    image_name: str | None,
) -> str:
    blocks: list[str] = []
    if title:
        blocks.append(f"<div class='help-popover__col-title'>{title}</div>")
    for paragraph in _split_caption_paragraphs(caption):
        blocks.append(f"<div class='help-popover__paragraph'>{paragraph}</div>")
    if image_name:
        blocks.append(_build_instruction_image_html(image_name))
    return f"<div class='help-popover__split-col'>{''.join(blocks)}</div>"


def _build_help_popover_html(
    popover_key: str,
    caption: str,
    image_name: str | None = None,
    second_image_name: str | None = None,
    second_caption: str = "",
    caption_title: str = "",
    second_caption_title: str = "",
    trigger_label: str = "ℹ️",
    align: str = "right",
    two_column_layout: bool = False,
    compact_images: bool = False,
    inline: bool = False,
) -> str:
    parts: list[str] = []
    if two_column_layout and second_image_name and image_name:
        parts.append(
            (
                "<div class='help-popover__split help-popover__split-columns'>"
                f"{_build_column_instruction_html(caption_title, caption, image_name)}"
                f"{_build_column_instruction_html(second_caption_title, second_caption, second_image_name)}"
                "</div>"
            )
        )
    else:
        if caption:
            parts.append(f"<div class='help-popover__caption'>{caption}</div>")
        if image_name:
            parts.append(_build_instruction_image_html(image_name))

        if second_image_name:
            if second_caption:
                parts.append(f"<div class='help-popover__caption'>{second_caption}</div>")
            parts.append(_build_instruction_image_html(second_image_name))

    compact_class = " help-popover--compact" if compact_images else ""
    inline_class = " help-popover--inline" if inline else ""

    return (
        f"<details class='help-popover help-popover--{align}{compact_class}{inline_class}' "
        f"id='help-popover-{popover_key}'>"
        f"<summary class='help-popover__trigger'>{trigger_label}</summary>"
        f"<div class='help-popover__panel'>{''.join(parts)}</div>"
        "</details>"
    )


def render_custom_help_popover(
    popover_key: str,
    caption: str,
    image_name: str | None = None,
    second_image_name: str | None = None,
    second_caption: str = "",
    caption_title: str = "",
    second_caption_title: str = "",
    trigger_label: str = "ℹ️",
    align: str = "right",
    two_column_layout: bool = False,
    compact_images: bool = False,
    inline: bool = False,
) -> None:
    _render_help_html(
        _build_help_popover_html(
            popover_key=popover_key,
            caption=caption,
            image_name=image_name,
            second_image_name=second_image_name,
            second_caption=second_caption,
            caption_title=caption_title,
            second_caption_title=second_caption_title,
            trigger_label=trigger_label,
            align=align,
            two_column_layout=two_column_layout,
            compact_images=compact_images,
            inline=inline,
        ),
    )


def render_section_header_with_help(
    title: str,
    image_name: str,
    caption: str,
    second_image_name: str | None = None,
    second_caption: str = "",
    caption_title: str = "",
    second_caption_title: str = "",
    align: str = "right",
    two_column_layout: bool = False,
    compact_images: bool = False,
    popover_key: str | None = None,
) -> None:
    title_col, help_col = st.columns([0.92, 0.08], gap="small")
    with title_col:
        st.subheader(title)
    with help_col:
        align_map = {"left": "left", "center": "center", "right": "right"}
        align_style = align_map.get(align, "right")
        popover_html = _build_help_popover_html(
            popover_key=popover_key or title.lower().replace(" ", "-"),
            caption=caption,
            image_name=image_name,
            second_image_name=second_image_name,
            second_caption=second_caption,
            caption_title=caption_title,
            second_caption_title=second_caption_title,
            align=align,
            two_column_layout=two_column_layout,
            compact_images=compact_images,
            inline=True,
        )
        _render_help_html(
            f"<div style='text-align:{align_style};padding-top:6px;'>{popover_html}</div>",
        )
