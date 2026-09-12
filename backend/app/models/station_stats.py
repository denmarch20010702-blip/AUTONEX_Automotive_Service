from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# Единственная строка (id=1) — счётчик заработанных станцией денег. Растёт
# при полном завершении заявки (issued), после чего сама заявка удаляется
# из БД по прямой просьбе пользователя — этот счётчик остаётся единственным
# постоянным следом суммарной выручки после удаления.
STATION_STATS_ROW_ID = 1


class StationStats(Base):
    __tablename__ = "station_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    total_revenue: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
