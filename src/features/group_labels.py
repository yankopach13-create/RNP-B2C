"""Нормализация названий групп (общая для metrics, focus и др.)."""

from __future__ import annotations

import re
import unicodedata

from config.constants import GROUP_SIGNET_BOOSTERS_NAMES


def normalize_group_label(name: str) -> str:
    """Единый вид названия группы (пробелы, NBSP, регистр)."""
    s = unicodedata.normalize("NFKC", str(name or ""))
    s = s.replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip().casefold()


_SIGNET_BOOSTERS_NORM_KEYS = frozenset(
    normalize_group_label(name) for name in GROUP_SIGNET_BOOSTERS_NAMES
)


def is_signet_boosters_group(group: str) -> bool:
    return normalize_group_label(group) in _SIGNET_BOOSTERS_NORM_KEYS
