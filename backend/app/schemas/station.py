from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class StationStatsRead(BaseModel):
    total_revenue: Decimal
    # UI_description.md п.45 (2026-09-15): компактный счётчик в правом
    # верхнем углу станции — выручка в двух строках ("за всё время"/"за
    # сегодня") плюс 3 бизнес-метрики вместо прежних 4 статус-счётчиков.
    today_revenue: Decimal
    average_check: Decimal | None
    issued_count: int
    cancelled_count: int
    completion_rate_percent: float | None
    additional_work_conversion_percent: float | None
