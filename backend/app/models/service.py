from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.booking import booking_services


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    duration_minutes: Mapped[int]
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    bookings: Mapped[list["Booking"]] = relationship(
        secondary=booking_services, back_populates="services"
    )
