from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class BookingStatus(str, enum.Enum):
    ACCEPTED = "accepted"
    ON_POST = "on_post"
    AWAITING_APPROVAL = "awaiting_approval"
    READY = "ready"
    ISSUED = "issued"
    CANCELLED = "cancelled"


booking_services = Table(
    "booking_services",
    Base.metadata,
    Column("booking_id", ForeignKey("bookings.id"), primary_key=True),
    Column("service_id", ForeignKey("services.id"), primary_key=True),
)


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        # Ускоряет ровно тот запрос, вокруг которого построена вся логика A4:
        # "какие заявки уже есть на этом посту в этом интервале".
        Index("ix_bookings_post_start", "post_id", "start_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id"), index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status"),
        default=BookingStatus.ACCEPTED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    client: Mapped["Client"] = relationship(back_populates="bookings")
    car: Mapped["Car"] = relationship(back_populates="bookings")
    post: Mapped["Post"] = relationship(back_populates="bookings")
    services: Mapped[list["Service"]] = relationship(
        secondary=booking_services, back_populates="bookings"
    )
