from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class CarCreate(BaseModel):
    client_id: int
    make: str = Field(min_length=1)
    model: str = Field(min_length=1)
    mileage: int = Field(default=0, ge=0)
    last_service_date: date | None = None


class CarUpdate(BaseModel):
    # UI_description.md п.26 (2026-09-14): раньше можно было сохранить
    # машину с пустой маркой/моделью при редактировании (create требовал
    # непустые значения, update — нет) — `min_length`/`ge` применяются и
    # здесь, когда поле явно передано (None — "не менять это поле" — не
    # проверяется на длину).
    make: str | None = Field(default=None, min_length=1)
    model: str | None = Field(default=None, min_length=1)
    mileage: int | None = Field(default=None, ge=0)
    last_service_date: date | None = None


class CarRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    make: str
    model: str
    mileage: int
    last_service_date: date | None
