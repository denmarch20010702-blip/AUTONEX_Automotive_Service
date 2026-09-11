from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class TireSet(Base):
    """Комплект шин на хранении. Привязан к конкретной паре клиент+авто —
    именно эта пара не даёт выдать комплект другому клиенту или выдать его дважды
    (issued_at IS NULL означает "на хранении"; бизнес-правило — в сервисном слое B1)."""

    __tablename__ = "tire_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id"), index=True)
    stored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    client: Mapped["Client"] = relationship()
    car: Mapped["Car"] = relationship()
