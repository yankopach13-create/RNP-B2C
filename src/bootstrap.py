"""Регистрация пакетов до импорта подмодулей (Streamlit Cloud, Python 3.14)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent


def ensure_src_on_path() -> None:
    src = str(_SRC_ROOT)
    if src not in sys.path:
        sys.path.insert(0, src)


def ensure_packages() -> None:
    """Импортирует верхнеуровневые пакеты, чтобы importlib видел родителей."""
    ensure_src_on_path()
    for name in ("config", "data", "features", "ui"):
        importlib.import_module(name)
