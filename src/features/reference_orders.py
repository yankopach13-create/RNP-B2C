"""Порядок групп и категорий из справочников *_order (с fallback на constants)."""

import pandas as pd

from config.constants import CATEGORY_ORDER, GROUP_ORDER, SHOP_ORDER


def resolve_groups_order(groups_order_rnp: list[str] | None) -> list[str]:
    """Список групп РНП: groups_order или GROUP_ORDER из constants."""
    if groups_order_rnp:
        return list(groups_order_rnp)
    return list(GROUP_ORDER)


def resolve_categories_rnp(category_order_rnp: list[str] | None) -> list[str]:
    if category_order_rnp:
        return list(category_order_rnp)
    return list(CATEGORY_ORDER)


def resolve_categories_general(category_order_general: list[str] | None) -> list[str]:
    """Список категорий Общего РНП из category_order (без fallback на РНП)."""
    if category_order_general:
        return list(category_order_general)
    return []


def resolve_shops_order(shops_order: list[str] | None) -> list[str]:
    """Список магазинов: groups_order «Порядок магазинов» или SHOP_ORDER из constants."""
    if shops_order:
        return list(shops_order)
    return list(SHOP_ORDER)


def ordered_shop_labels(
    shop_labels,
    shops_order: list[str] | None = None,
) -> list[str]:
    """Магазины в порядке справочника; прочие — в конце по алфавиту."""
    order = resolve_shops_order(shops_order)
    uniq: list[str] = []
    for s in shop_labels:
        if s is None or (isinstance(s, float) and pd.isna(s)):
            continue
        name = str(s).strip()
        if not name or name in uniq:
            continue
        uniq.append(name)
    head = [s for s in order if s in uniq]
    tail = sorted(s for s in uniq if s not in order)
    return head + tail


def ordered_group_labels(
    group_labels,
    groups_order_rnp: list[str] | None = None,
) -> list[str]:
    """Группы из данных в порядке groups_order; прочие — в конце по алфавиту."""
    order = resolve_groups_order(groups_order_rnp)
    uniq: list[str] = []
    for g in group_labels:
        if g is None or (isinstance(g, float) and pd.isna(g)):
            continue
        gs = str(g).strip()
        if not gs or gs in uniq:
            continue
        uniq.append(gs)
    head = [g for g in order if g in uniq]
    tail = sorted(g for g in uniq if g not in order)
    return head + tail
