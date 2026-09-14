from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# UI_description.md п.28 (2026-09-14): найден реальный баг — комплект шин,
# в отличие от заявок, никогда не архивировался, оставался в живой
# `tire_sets` НАВСЕГДА (даже после выдачи), и внешний ключ на car_id/
# client_id блокировал удаление машины/клиента даже когда реальной
# "активной" сдачи давно не было — сообщение об ошибке при этом лгало,
# утверждая, что хранение активно. Тот же денормализованный журнал, что и
# BookingArchive: выданный комплект переезжает сюда и удаляется из живой
# таблицы, поэтому там остаются только реально активные сдачи.


class TireSetArchive(Base):
    __tablename__ = "tire_set_archive"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_tire_set_id: Mapped[int] = mapped_column(index=True)

    client_id: Mapped[int] = mapped_column(index=True)
    client_name: Mapped[str]
    client_email: Mapped[str]

    car_id: Mapped[int]
    car_make: Mapped[str]
    car_model: Mapped[str]

    stored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
