"""Точка входа для Streamlit Community Cloud (main file: streamlit_app.py)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bootstrap import ensure_packages

ensure_packages()

from app import main

main()
