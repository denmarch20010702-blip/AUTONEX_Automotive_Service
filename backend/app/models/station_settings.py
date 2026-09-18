from __future__ import annotations

from decimal import Decimal

from sqlalchemy import CheckConstraint, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# Единственная строка (id=1), тот же принцип, что и StationStats — станция
# в этом проекте не имеет отдельного "личного кабинета" с полноценным
# входом (см. открытый вопрос про авторизацию в ARCHITECTURE.md), поэтому
# "настройки станции" — это просто редактируемая строка, а не сущность с
# владельцем.
STATION_SETTINGS_ROW_ID = 1


class StationSettings(Base):
    """C7 (buisness.md): тариф наценки за простой на парковке — "по тарифу
    который можно менять в личном кабинете станции" — редактируется через
    PATCH /station/settings, не хардкод в коде."""

    __tablename__ = "station_settings"
    __table_args__ = (
        CheckConstraint(
            "parking_overdue_rate_per_minute >= 0",
            name="ck_station_settings_parking_overdue_rate_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # ₽ за каждую минуту простоя сверх бесплатных 2 часов (см.
    # PARKING_FREE_MINUTES в app/services/parking.py). Конкретная стартовая
    # цифра не задана в задании — решение AI, задокументировано в
    # ARCHITECTURE.md.
    parking_overdue_rate_per_minute: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("5.00")
    )
