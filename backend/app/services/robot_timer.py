from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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


async def resolve_next_step(session: AsyncSession, booking: Booking) -> None:
    """Решает, что делать с заявкой в момент, когда она "освобождается" с
    поста — будь то конец основной услуги ИЛИ конец только что отработанной
    доп. работы (см. вызовы ниже и в app/api/additional_works.py).

    UI_description.md п.20/25 (2026-09-14): раньше таймер доп. работы
    запускался только если её одобрили ДО того, как основная услуга уже
    закончилась (заявка была ровно в 'awaiting_approval' в момент ответа
    клиента) — если клиент одобрял позже (заявка уже 'ready', основная
    работа готова) или почти одновременно с концом основной услуги, таймер
    доп. работы не запускался вообще, и она считалась выполненной просто по
    факту согласования, без реальной отработки. Эта функция — единая точка
    принятия решения "что дальше", вызываемая и из таймера, и из ответа
    клиента, поэтому пропустить отработку одобренной доп. работы теперь
    невозможно ни при каком порядке событий.

    Не коммитит сама — вызывающий код решает, когда это делать (может быть
    частью более крупной транзакции)."""
    has_pending = (
        await session.execute(
            select(AdditionalWork.id)
            .where(
                AdditionalWork.booking_id == booking.id,
                AdditionalWork.status == AdditionalWorkStatus.PENDING,
            )
            .limit(1)
        )
    ).first()
    if has_pending is not None:
        # Неотвеченное предложение — дальше не едем, ждём клиента (B2).
        booking.status = BookingStatus.AWAITING_APPROVAL
        return

    # Одобренные, но ещё не отработанные доп. работы — едем на пост ещё раз,
    # на их суммарную длительность, тем же механизмом, что и основная
    # услуга. `execution_started` не даёт задвоить длительность уже
    # отработанной работы при повторном вызове этой функции позже.
    newly_approved = (
        await session.execute(
            select(AdditionalWork).where(
                AdditionalWork.booking_id == booking.id,
                AdditionalWork.status == AdditionalWorkStatus.APPROVED,
                AdditionalWork.execution_started.is_(False),
                # Тот же баг, что и в app/api/bookings.py (найден пользователем
                # 2026-09-15): работа, перенесённая на отдельный будущий визит
                # (`scheduled_booking_id` заполнен), не должна продлевать
                # занятость ЭТОГО поста сейчас — она будет реально выполнена
                # на другой заявке, в другой день.
                AdditionalWork.scheduled_booking_id.is_(None),
            )
        )
    ).scalars().all()
    extra_minutes = sum(w.duration_minutes for w in newly_approved)
    if extra_minutes > 0:
        for w in newly_approved:
            w.execution_started = True
        booking.status = BookingStatus.ON_POST
        new_ends_at = datetime.now(timezone.utc) + timedelta(minutes=extra_minutes)
        booking.service_ends_at = new_ends_at
        # UI_description.md п.35 (2026-09-14): реальный найденный баг —
        # `end_at` заявки не продлевался вместе с `service_ends_at`, а
        # именно `end_at` (не `service_ends_at`) используется во всех
        # проверках занятости поста/машины (EXCLUDE-ограничения A4,
        # `car_is_free`/`get_available_slots`). Пока доп. работа реально
        # выполнялась на посту, по данным этих проверок пост/машина уже
        # считались свободными сразу после ИЗНАЧАЛЬНОГО `end_at` — можно
        # было создать вторую заявку на тот же пост или ту же машину на это
        # же время. Синхронизируем `end_at` с новым концом занятости, чтобы
        # EXCLUDE-ограничения на уровне БД реально защищали продлённый
        # интервал, а не только исходный.
        if new_ends_at > booking.end_at:
            booking.end_at = new_ends_at
        schedule_auto_advance(booking.id, timedelta(minutes=extra_minutes))
        return

    # Ничего не ждём и нечего отрабатывать — всё сделано.
    booking.status = BookingStatus.READY


async def _auto_advance(booking_id: int) -> None:
    async with async_session() as session:
        booking = (
            await session.execute(
                select(Booking)
                .options(selectinload(Booking.services))
                .where(Booking.id == booking_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        # Заявку могли уже отменить или вручную продвинуть дальше, пока
        # таймер тикал — тогда просто ничего не делаем, а не ломаем чужой
        # переход. Тот же принцип защиты, что и у ручных переходов (A5).
        if booking is None or booking.status != BookingStatus.ON_POST:
            return

        await resolve_next_step(session, booking)
        try:
            await session.commit()
        except IntegrityError:
            # Крайне редкий случай (п.35): продлённый интервал пересёкся с
            # чужой заявкой. Автотаймер работает в фоне без запроса, кому
            # вернуть 409 — просто откатываем, заявка останется в 'on_post'
            # без нового таймера; станция увидит это и разберётся вручную.
            await session.rollback()
            return
        await session.refresh(booking)
        publish(
            "booking_status_changed",
            BookingRead.model_validate(booking).model_dump(mode="json"),
        )
