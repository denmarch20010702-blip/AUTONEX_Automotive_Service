from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ProposedBy(str, enum.Enum):
    MECHANIC = "mechanic"
    AI = "ai"


class AdditionalWorkStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"


class AdditionalWork(Base):
    """Предложение доп. работы по заявке. Работа не начинается, пока клиент
    не подтвердил (см. B2) — здесь только данные, сам поток согласования будет в B2/C5."""

    __tablename__ = "additional_works"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"), index=True)
    description: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # UI_description.md п.19: доп. работа выбирается из каталога услуг
    # (`Service`) кликом, не вводится вручную — description/price выше
    # остаются снимком названия/цены на момент предложения (та же логика,
    # что и services_snapshot в архиве — каталог мог измениться позже), а
    # duration_minutes нужна, чтобы после согласования запустить настоящий
    # таймер выполнения этой доп. работы (см. app/api/additional_works.py).
    duration_minutes: Mapped[int] = mapped_column(default=0, server_default="0")
    # Отмечает, что длительность этой работы уже учтена в каком-то таймере
    # (см. respond_additional_work) — без этого флага повторное предложение
    # новой доп. работы после уже отработанной старой задвоило бы её
    # длительность при пересчёте суммы для таймера.
    execution_started: Mapped[bool] = mapped_column(default=False, server_default="false")
    # UI_description.md п.37 (2026-09-14): если на посту сразу нет места
    # (продление занятости пересеклось бы со следующей заявкой), клиенту
    # предлагается отдельный будущий визит именно на эту услугу — для этого
    # нужна настоящая ссылка на каталог (снимков description/price/duration
    # выше недостаточно, чтобы создать новую `Booking`). `ondelete=SET NULL`,
    # а не CASCADE/RESTRICT — если услугу позже удалят из каталога, история
    # предложения не должна пропадать, отдельный визит просто станет
    # невозможен (см. schedule_additional_work_separately).
    service_id: Mapped[int | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"), nullable=True
    )
    # Заполняется, когда клиент выбрал время отдельного визита (см. выше) —
    # ссылка на новую самостоятельную заявку именно на эту доп. работу.
    scheduled_booking_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True
    )
    proposed_by: Mapped[ProposedBy] = mapped_column(Enum(ProposedBy, name="proposed_by"))
    status: Mapped[AdditionalWorkStatus] = mapped_column(
        Enum(AdditionalWorkStatus, name="additional_work_status"),
        default=AdditionalWorkStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Явный foreign_keys нужен, потому что теперь в этой таблице два FK на
    # bookings.id (booking_id и scheduled_booking_id) — без этого SQLAlchemy
    # не может сам угадать, какой из них тут имеется в виду.
    booking: Mapped["Booking"] = relationship(foreign_keys=[booking_id])
