from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db.session import async_session
from app.models import AdditionalWork, AdditionalWorkStatus, Booking, BookingStatus
from app.schemas.booking import BookingRead
from app.services.events import publish

# Заметка пользователя (2026-09-13): после приёма машины на пост
# обслуживание должно самостоятельно идти по таймеру — длительность равна
# сумме длительностей выбранных услуг, по истечении статус меняется сам.
# Это пилотная, урезанная реализация части C2 (без очереди/симуляции
# сбоев — то будет доработано в самом C2, когда придёт черёд).
scheduler = AsyncIOScheduler()


def schedule_auto_advance(booking_id: int, duration: timedelta) -> None:
    run_at = datetime.now(timezone.utc) + duration
    scheduler.add_job(
        _auto_advance,
        "date",
        run_date=run_at,
        args=[booking_id],
        id=f"auto-advance-{booking_id}",
        replace_existing=True,
    )


async def _auto_advance(booking_id: int) -> None:
    async with async_session() as session:
        booking = (
            await session.execute(
                select(Booking).where(Booking.id == booking_id).with_for_update()
            )
        ).scalar_one_or_none()
        # Заявку могли уже отменить или вручную продвинуть дальше, пока
        # таймер тикал — тогда просто ничего не делаем, а не ломаем чужой
        # переход. Тот же принцип защиты, что и у ручных переходов (A5).
        if booking is None or booking.status != BookingStatus.ON_POST:
            return

        has_pending = (
            await session.execute(
                select(AdditionalWork.id)
                .where(
                    AdditionalWork.booking_id == booking_id,
                    AdditionalWork.status == AdditionalWorkStatus.PENDING,
                )
                .limit(1)
            )
        ).first()

        # Если есть неотвеченное предложение доп. работы — таймер доводит
        # заявку до "ожидает согласования", а не сразу "готова" (B2:
        # дальше статус не меняется, пока клиент не ответит).
        booking.status = (
            BookingStatus.AWAITING_APPROVAL if has_pending is not None else BookingStatus.READY
        )
        await session.commit()
        await session.refresh(booking)
        publish(
            "booking_status_changed",
            BookingRead.model_validate(booking).model_dump(mode="json"),
        )
