from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdditionalWork, AdditionalWorkStatus, OutboxEmail


async def send_stub_email(session: AsyncSession, *, to: str, subject: str, body: str) -> None:
    """Заглушка внешнего email-сервиса — ничего никуда не отправляет, просто
    пишет строку в БД (см. общее требование про эмуляцию внешних сервисов).
    Не коммитит сама — вызывающий код решает, в одной ли транзакции с
    остальными изменениями это должно быть."""
    session.add(OutboxEmail(to=to, subject=subject, body=body))


async def notify_pending_additional_works(
    session: AsyncSession, booking_id: int, client_email: str
) -> None:
    """C5 (2026-09-16, буквальное требование задания: "Мастер предложил
    дополнительную работу — клиенту приходит письмо... Работа не начинается,
    пока клиент не ответил") — единое письмо для ОБОИХ источников
    предложения (мастер вручную ИЛИ ИИ-диагностика, C4): клиенту всё равно,
    кто предложил, письмо для него выглядит одинаково в обоих случаях, не
    упоминает ИИ и никогда не разбивается на несколько писем подряд — даже
    если ИИ нашла сразу несколько подходящих услуг за один заезд (найдено
    пользователем на практике: раньше уходило по письму на каждую услугу).

    Перечисляет ТЕКУЩИЙ полный список неотвеченных предложений по заявке —
    не только то, что добавилось последним — так письмо всегда честно
    отражает весь список, на который клиенту нужно ответить прямо сейчас."""
    pending = (
        await session.execute(
            select(AdditionalWork).where(
                AdditionalWork.booking_id == booking_id,
                AdditionalWork.status == AdditionalWorkStatus.PENDING,
            )
        )
    ).scalars().all()
    if not pending:
        return
    lines = "\n".join(f"- {w.description} — {w.price} ₽" for w in pending)
    await send_stub_email(
        session,
        to=client_email,
        subject=f"Заявка №{booking_id}: доп. работы требуют вашего решения",
        body=f"{lines}\n\nПодтвердите или отклоните в личном кабинете.",
    )
