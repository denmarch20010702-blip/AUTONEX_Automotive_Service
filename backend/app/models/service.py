from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.booking import booking_services


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    duration_minutes: Mapped[int]
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # UI_description.md п.47 (2026-09-16): "Сезонная замена шин" и "Получить/
    # сдать шины" — проводники к обязательному функционалу B1 (хранение
    # шин), не обычные услуги. Цену/длительность можно редактировать как
    # обычно, но переименование/удаление запрещены (см. app/api/catalog.py) —
    # иначе хранение шин осталось бы без единой точки входа в интерфейсе.
    protected: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    bookings: Mapped[list["Booking"]] = relationship(
        secondary=booking_services, back_populates="services"
    )
