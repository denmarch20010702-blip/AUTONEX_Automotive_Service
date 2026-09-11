from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.booking import BookingStatus


class SlotOption(BaseModel):
    post_id: int
    start_at: datetime
    end_at: datetime


class BookingCreate(BaseModel):
    client_id: int
    car_id: int
    post_id: int
    start_at: datetime
    end_at: datetime
    service_ids: list[int]


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    car_id: int
    post_id: int
    start_at: datetime
    end_at: datetime
    status: BookingStatus
