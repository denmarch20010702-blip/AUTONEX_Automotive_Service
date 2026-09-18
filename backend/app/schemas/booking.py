from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.booking import BookingStatus
from app.schemas.service import ServiceRead


class SlotOption(BaseModel):
    start_at: datetime
    end_at: datetime


class BookingCreate(BaseModel):
    client_id: int
    car_id: int
    start_at: datetime
    service_ids: list[int]


class BookingStatusUpdate(BaseModel):
    status: BookingStatus


class BookingReschedule(BaseModel):
    start_at: datetime


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    car_id: int
    post_id: int
    start_at: datetime
    end_at: datetime
    status: BookingStatus
    # UI_description.md п.11 (таймер виден станции и клиенту) и п.12 (в
    # таблице станции должна быть видна изначально забронированная услуга).
    service_ends_at: datetime | None = None
    # C3: начало текущего раунда работы на посту — для процента прогресса.
    on_post_started_at: datetime | None = None
    # UI_description.md п.47: клиент отклонил предложение сдать шины во
    # время визита на "Сезонная замена шин" — прячет вопрос в кабинете.
    tire_offer_declined: bool = False
    # C7 (buisness.md, "Smart Parking Management"): место ожидания — либо
    # ДО обслуживания (клиент подтвердил приезд, ждёт своего start_at), либо
    # ПОСЛЕ (заявка готова, ждёт, чтобы забрали) — см. app/services/parking.py.
    parking_spot_id: int | None = None
    parked_at: datetime | None = None
    services: list[ServiceRead] = []
