from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    # UI_description.md п.44 (2026-09-15): баннер B6 закрывается крестиком и
    # не должен возвращаться до конца текущего сезона — хранит метку сезона
    # (то же "весна 2026"/"осень 2026", что и в теме письма), а не булев флаг,
    # иначе пришлось бы отдельно сбрасывать его при смене сезона.
    tire_season_reminder_dismissed_season: Mapped[str | None] = mapped_column(String(32), default=None)

    cars: Mapped[list["Car"]] = relationship(back_populates="client")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="client")
