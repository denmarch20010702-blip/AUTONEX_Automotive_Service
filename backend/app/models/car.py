from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Car(Base):
    __tablename__ = "cars"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    make: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    mileage: Mapped[int] = mapped_column(default=0)
    last_service_date: Mapped[date | None] = mapped_column(Date, default=None)
    # B5: пробег на момент последнего ТО — вместе с текущим `mileage`
    # (который клиент правит вручную) даёт "пробег с последнего ТО" для
    # проактивного предложения записи. Обновляется одновременно с
    # `last_service_date` (см. app/api/bookings.py, UI_description.md п.31).
    mileage_at_last_service: Mapped[int | None] = mapped_column(default=None)

    client: Mapped["Client"] = relationship(back_populates="cars")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="car")
