from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class StationStatsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_revenue: Decimal
