from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.booking import BookingStatus


class BookingArchiveRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_booking_id: int
    client_id: int
    client_name: str
    client_email: str
    car_id: int
    car_make: str
    car_model: str
    post_id: int
    start_at: datetime
    end_at: datetime
    status: BookingStatus
    total_price: Decimal
    service_price: Decimal
    parking_surcharge: Decimal
    parking_wait_minutes: int
    services_snapshot: list[dict]
    additional_works_snapshot: list[dict]
    created_at: datetime
    archived_at: datetime
