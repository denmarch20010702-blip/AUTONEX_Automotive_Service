from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ParkingSpot(Base):
    """C7 (buisness.md, "Smart Parking Management"): 6 фиксированных мест
    ожидания — та же физическая, не управляемая через CRUD конфигурация,
    что и `Post` (см. миграцию-сидинг). Занятость не хранится отдельным
    флагом здесь — как и у постов, она всегда выводится из живых заявок,
    ссылающихся на это место (`Booking.parking_spot_id`)."""

    __tablename__ = "parking_spots"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
