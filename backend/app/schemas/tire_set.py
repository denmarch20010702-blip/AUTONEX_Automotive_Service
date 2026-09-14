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


class TireSetArchiveRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_tire_set_id: int
    client_id: int
    client_name: str
    client_email: str
    car_id: int
    car_make: str
    car_model: str
    stored_at: datetime
    issued_at: datetime
    archived_at: datetime
