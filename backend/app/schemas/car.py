from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class CarCreate(BaseModel):
    client_id: int
    make: str
    model: str
    mileage: int = 0
    last_service_date: date | None = None


class CarUpdate(BaseModel):
    make: str | None = None
    model: str | None = None
    mileage: int | None = None
    last_service_date: date | None = None


class CarRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    make: str
    model: str
    mileage: int
    last_service_date: date | None
