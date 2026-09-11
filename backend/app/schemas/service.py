from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ServiceCreate(BaseModel):
    name: str
    duration_minutes: int
    price: Decimal


class ServiceUpdate(BaseModel):
    name: str | None = None
    duration_minutes: int | None = None
    price: Decimal | None = None


class ServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    duration_minutes: int
    price: Decimal
