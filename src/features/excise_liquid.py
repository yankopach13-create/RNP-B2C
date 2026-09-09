"""Конфигурация недель и константы категории жидкости."""

from __future__ import annotations

from dataclasses import dataclass

CATEGORY_LIQUID_25ML = "Жидкость 25 мл"


@dataclass(frozen=True)
class WeekCalculationConfig:
    """Недели LFL и отчётная для расчёта."""

    lfl_week: int
    report_week: int
