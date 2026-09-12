from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, Enum, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.booking import BookingStatus

# Журнал завершённых/отменённых заявок — по прямой просьбе пользователя:
# заявка убирается из активного списка (освобождая слот, как и раньше), но
# не пропадает совсем, а переезжает сюда для просмотра при необходимости.
# Денормализовано намеренно (имя/email клиента, марка/модель авто, список
# услуг снимком в JSON) — это именно журнал для чтения человеком, а не
# нормализованная модель для сложных запросов; так запись остаётся читаемой
# даже если сам клиент/машина/услуга потом будут удалены или переименованы.


class BookingArchive(Base):
    __tablename__ = "booking_archive"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_booking_id: Mapped[int] = mapped_column(index=True)

    client_id: Mapped[int] = mapped_column(index=True)
    client_name: Mapped[str]
    client_email: Mapped[str]

    car_id: Mapped[int]
    car_make: Mapped[str]
    car_model: Mapped[str]

    post_id: Mapped[int]
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[BookingStatus] = mapped_column(Enum(BookingStatus, name="booking_status"))
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    services_snapshot: Mapped[list] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
