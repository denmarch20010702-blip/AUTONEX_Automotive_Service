from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TireSetCreate(BaseModel):
    client_id: int
    car_id: int


class TireSetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    car_id: int
    stored_at: datetime
    issued_at: datetime | None
