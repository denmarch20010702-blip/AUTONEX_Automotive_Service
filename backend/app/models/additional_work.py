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
    proposed_by: Mapped[ProposedBy] = mapped_column(Enum(ProposedBy, name="proposed_by"))
    status: Mapped[AdditionalWorkStatus] = mapped_column(
        Enum(AdditionalWorkStatus, name="additional_work_status"),
        default=AdditionalWorkStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    booking: Mapped["Booking"] = relationship()
