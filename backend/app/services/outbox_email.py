from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEmail


async def send_stub_email(session: AsyncSession, *, to: str, subject: str, body: str) -> None:
    """Заглушка внешнего email-сервиса — ничего никуда не отправляет, просто
    пишет строку в БД (см. общее требование про эмуляцию внешних сервисов).
    Не коммитит сама — вызывающий код решает, в одной ли транзакции с
    остальными изменениями это должно быть."""
    session.add(OutboxEmail(to=to, subject=subject, body=body))
