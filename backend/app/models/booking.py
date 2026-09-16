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
    # Заметка пользователя (UI_description.md, п.11): таймер до завершения
    # работ должен быть виден и станции, и клиенту — момент, когда сработает
    # автотаймер (см. app/services/robot_timer.py), сохраняем на самой
    # заявке, а не только внутри задачи планировщика, иначе фронтенду неоткуда
    # взять точку отсчёта для обратного отсчёта.
    service_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # C2/C3 (2026-09-15): момент, когда ТЕКУЩИЙ раунд работы на посту реально
    # начался — либо приём на пост (основная услуга), либо повторный выход
    # на пост ради одобренной доп. работы (см. robot_timer.py::resolve_next_
    # step). Вместе с `service_ends_at` даёт точку отсчёта для процента
    # прогресса на доске постов — без него нельзя отличить "только начали"
    # от "почти закончили" тем же способом для доп. работы, что и для
    # основной услуги (разная длительность раунда).
    on_post_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # B3: напоминание клиенту за день до записи должно прийти РОВНО одно —
    # флаг гарантирует это при периодическом опросе (app/services/reminders.py),
    # а не полагается на точную привязку к моменту "минус 24 часа".
    reminder_sent: Mapped[bool] = mapped_column(default=False, server_default="false")
    # UI_description.md п.47 (2026-09-16): клиент ответил "нет" на вопрос
    # "сдать шины на хранение?" во время визита на "Сезонная замена шин" —
    # не задавать вопрос повторно за ЭТОТ же визит (см. app/api/tire_sets.py).
    tire_offer_declined: Mapped[bool] = mapped_column(default=False, server_default="false")

    client: Mapped["Client"] = relationship(back_populates="bookings")
    car: Mapped["Car"] = relationship(back_populates="bookings")
    post: Mapped["Post"] = relationship(back_populates="bookings")
    services: Mapped[list["Service"]] = relationship(
        secondary=booking_services, back_populates="bookings"
    )
