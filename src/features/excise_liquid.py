"""Корректировка маржи по вводу «Акцизной жидкости в шт.» (× 4,25)."""

from __future__ import annotations

from dataclasses import dataclass

EXCISE_LIQUID_MARGIN_FACTOR = 4.25
CATEGORY_LIQUID_25ML = "Жидкость 25 мл"


@dataclass(frozen=True)
class WeekCalculationConfig:
    """Недели LFL/отчётная и количество акцизной жидкости по неделям."""

    lfl_week: int
    report_week: int
    excise_liquid_lfl: float = 0.0
    excise_liquid_report: float = 0.0


def excise_margin_deduction(qty: float) -> float:
    """Сумма вычета из маржи: количество шт. × 4,25."""
    try:
        return max(0.0, float(qty)) * EXCISE_LIQUID_MARGIN_FACTOR
    except (TypeError, ValueError):
        return 0.0


def apply_total_margin_deduction(margin: float, excise_report_qty: float) -> float:
    """Вычет из общей маржи (только итог B2C / МД в РНП и ИИ отчёте)."""
    return float(margin) - excise_margin_deduction(excise_report_qty)
