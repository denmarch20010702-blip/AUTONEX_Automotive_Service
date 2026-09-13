from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class OutboxEmail(Base):
    """Заглушка внешнего email-сервиса (см. общее требование про эмуляцию
    внешних сервисов) — вместо реальной отправки просто пишем строку в БД.
    Используется и для уведомления о доп. работе (B2), и для напоминаний
    (B3/B5/B6)."""

    __tablename__ = "outbox_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    to: Mapped[str] = mapped_column(String(255), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
