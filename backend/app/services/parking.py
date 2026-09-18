from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import async_session
from app.models import (
    STATION_SETTINGS_ROW_ID,
    Booking,
    BookingStatus,
    ParkingSpot,
    StationSettings,
)
from app.schemas.booking import BookingStatusUpdate

# C7 (buisness.md, "Smart Parking Management", 2026-09-17): "в общей
# сложности до приёма и после приёма на обслуживание, бесплатное время
# ожидания на парковочной зоне = 2 часа" — обе фазы (до/после обслуживания)
# считаются вместе, порог общий, не по 2 часа на каждую отдельно.
PARKING_FREE_MINUTES = 120

# Тот же интервал, что и у overdue_bookings.py — секундная точность не
# нужна, но и не должен разрастаться шаг ожидания клиента заметно дольше
# самого автотаймера (демо-услуги в проекте короткие).
PARKING_SWEEP_INTERVAL_SECONDS = 20


async def assign_parking_spot(session: AsyncSession, booking: Booking) -> bool:
    """Подбирает свободное место и ставит машину на него — тот же приём,
    что и подбор свободного поста в create_booking (блокировка строк FOR
    UPDATE в фиксированном порядке, чтобы конкурентные попытки встали в
    очередь на этой блокировке, а не гонялись за одним и тем же местом).
    Возвращает False, если свободных мест прямо сейчас нет — вызывающий код
    решает, что делать (см. п.47.1 ниже — sweep сам повторит попытку позже).

    Найдено при код-ревью (2026-09-18): без этой проверки повторный вызов на
    заявке, которая уже стоит на месте (например, run_parking_sweep обрабатывает
    устаревший в памяти объект, который тем временем получил место через
    параллельный запрос), тихо переставлял бы её на другое место и сбрасывал
    `parked_at` — теряя уже накопленное время ожидания текущей паузы."""
    if booking.parking_spot_id is not None:
        return True
    spots = (
        await session.execute(select(ParkingSpot).order_by(ParkingSpot.id).with_for_update())
    ).scalars().all()
    occupied = (
        await session.execute(
            select(Booking.parking_spot_id).where(
                Booking.parking_spot_id.is_not(None), Booking.id != booking.id
            )
        )
    ).scalars().all()
    free_spot = next((s for s in spots if s.id not in occupied), None)
    if free_spot is None:
        return False
    booking.parking_spot_id = free_spot.id
    booking.parked_at = datetime.now(timezone.utc)
    return True


async def ensure_waiting_spot(session: AsyncSession, booking: Booking) -> None:
    """C7: единая точка входа для "машина сейчас не на посту, но заявка ещё
    не выдана — ей нужно место ожидания", вместо повторения условия
    `status in (READY, AWAITING_APPROVAL) and parking_spot_id is None` в
    каждом из трёх мест, где статус заявки меняется на один из этих двух
    (update_booking_status в app/api/bookings.py и оба выхода в
    resolve_next_step ниже, в robot_timer.py) — найдено при код-ревью
    (2026-09-18): дублирование одного и того же условия в разных файлах
    легко забыть обновить одновременно, если появится четвёртое такое
    место. Безобидный no-op, если место уже назначено или мест нет прямо
    сейчас (см. assign_parking_spot — sweep сам повторит попытку позже)."""
    if booking.status in (BookingStatus.READY, BookingStatus.AWAITING_APPROVAL):
        await assign_parking_spot(session, booking)


def leave_parking(booking: Booking) -> None:
    """Машина съезжает с парковки на пост — фиксирует, сколько реально
    прождала В ЭТОЙ паузе, накапливая в `Booking.parking_wait_minutes`,
    потому что `parked_at` тут же будет переиспользован для СЛЕДУЮЩЕЙ паузы
    (см. assign_parking_spot выше) и текущее значение иначе было бы
    потеряно. Вызывается и на первом заезде (accepted -> on_post), и при
    повторном выезде на пост для отработки согласованной доп. работы
    (awaiting_approval -> on_post, см. robot_timer.py::resolve_next_step).
    Безобидный no-op, если машина не пользовалась парковкой в этой паузе
    (заявку приняли по старинке, кнопкой станции, без подтверждения приезда
    клиентом из кабинета)."""
    if booking.parking_spot_id is not None and booking.parked_at is not None:
        elapsed = datetime.now(timezone.utc) - booking.parked_at
        booking.parking_wait_minutes += max(0, int(elapsed.total_seconds() // 60))
    booking.parking_spot_id = None
    booking.parked_at = None


def total_parking_wait_minutes(booking: Booking, *, now: datetime | None = None) -> int:
    """Returns all parking time, including the current unfinished pause.

    Keeping this calculation in one place prevents the archived audit fields
    and the surcharge from drifting by a minute at the moment of issue.
    """
    total = booking.parking_wait_minutes
    if booking.parking_spot_id is not None and booking.parked_at is not None:
        elapsed = (now or datetime.now(timezone.utc)) - booking.parked_at
        total += max(0, int(elapsed.total_seconds() // 60))
    return total


async def compute_parking_surcharge(session: AsyncSession, total_wait_minutes: int) -> Decimal:
    """Наценка за простой на парковке — суммарно по ВСЕМ паузам (до первого
    приёма, между раундами, после готовности) сверх 2 бесплатных часов, по
    тарифу из StationSettings (buisness.md: "по тарифу который можно менять
    в личном кабинете станции"). Вызывается в момент выдачи — ДО того как
    заявка архивируется и `parked_at` перестаёт существовать.

    Принимает уже посчитанное `total_wait_minutes` (см. total_parking_wait_
    minutes), а не сам `booking` — раньше эта функция пересчитывала его
    заново отдельным вызовом `datetime.now()`, что было и лишней работой, и
    потенциальным источником рассинхрона с архивным полем `parking_wait_
    minutes`, если оба вызова случились по разные стороны границы минуты
    (найдено при код-ревью, 2026-09-18)."""
    overdue_minutes = max(0, total_wait_minutes - PARKING_FREE_MINUTES)
    if overdue_minutes == 0:
        return Decimal("0")
    settings_row = await session.get(StationSettings, STATION_SETTINGS_ROW_ID)
    rate = settings_row.parking_overdue_rate_per_minute if settings_row else Decimal("5.00")
    return Decimal(overdue_minutes) * rate


async def confirm_parked_before_service(session: AsyncSession, booking_id: int) -> Booking:
    """Клиент из личного кабинета подтверждает, что машина реально
    физически стоит на парковке (buisness.md: "Ставит автомобиль на один из
    свободных парковочных слотов. В личном кабинете подтверждает что машина
    на месте") — до этого подтверждения автоматический выезд на пост (см.
    run_parking_sweep ниже) не наступит, даже если время уже подошло."""
    booking = (
        await session.execute(
            select(Booking)
            .options(selectinload(Booking.services))
            .where(Booking.id == booking_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if booking is None:
        raise ValueError("booking_not_found")
    if booking.status != BookingStatus.ACCEPTED:
        raise ValueError("wrong_status")
    if booking.parking_spot_id is not None:
        raise ValueError("already_parked")
    if not await assign_parking_spot(session, booking):
        raise ValueError("no_free_spot")
    await session.commit()
    await session.refresh(booking)
    return booking


async def run_parking_sweep(session: AsyncSession) -> None:
    """Два независимых дела за один проход, оба — автоматизация того, что
    иначе требовало бы ручного клика станции (тот же принцип, что и у
    overdue_bookings.py/robot_timer.py::resume_stalled_on_post_bookings):

    1. Заявки, где клиент уже подтвердил приезд (parking_spot_id стоит,
       статус ещё `accepted`) и назначенное время уже настало — сами едут
       на пост (buisness.md: "когда наступает время обслуживания — заявка
       автоматически принимает статус on_post").
    2. Заявки `ready`/`awaiting_approval` без места на парковке — потому что
       все 6 были заняты в момент, когда машина освободила пост (открытый
       вопрос из BUSINESS_FEATURES_REVIEW.md, решение: не блокировать
       ничего, просто повторять попытку, пока место не найдётся). Для
       `awaiting_approval` это не просто "красивее" — без места машина
       физически "нигде" на станции, хотя по логике должна быть на
       парковке, пока клиент решает по доп. работе (найдено пользователем
       на практике)."""
    from app.api.bookings import update_booking_status

    now = datetime.now(timezone.utc)
    due = (
        await session.execute(
            select(Booking.id).where(
                Booking.status == BookingStatus.ACCEPTED,
                Booking.parking_spot_id.is_not(None),
                Booking.start_at <= now,
            )
        )
    ).scalars().all()
    for booking_id in due:
        try:
            await update_booking_status(
                booking_id, BookingStatusUpdate(status=BookingStatus.ON_POST), session
            )
        except Exception:
            # Гонка (заявку уже приняли/отменили между выборкой и этим
            # циклом) или честный 409 (продлённое occupancy пересеклось с
            # чем-то) — не роняем весь sweep из-за одной заявки.
            #
            # Найдено при код-ревью (2026-09-18): `update_booking_status`
            # сам делает rollback только на IntegrityError/DBAPIError — на
            # любой другой исход (например HTTPException из-за проверки
            # статуса/перехода, сработавшей раньше, чем дело дошло до
            # try/commit внутри) он выбрасывает исключение, не откатывая
            # транзакцию. Без явного rollback здесь FOR UPDATE-блокировка,
            # взятая внутри до этого исключения, осталась бы висеть на всю
            # оставшуюся часть этого прохода sweep'а (до закрытия сессии в
            # _parking_sweep) и мешала бы конкурентным запросам к этой же
            # заявке.
            await session.rollback()
            continue

    unparked = (
        await session.execute(
            select(Booking)
            .where(
                Booking.status.in_([BookingStatus.READY, BookingStatus.AWAITING_APPROVAL]),
                Booking.parking_spot_id.is_(None),
            )
            .with_for_update()
        )
    ).scalars().all()
    for booking in unparked:
        if await assign_parking_spot(session, booking):
            await session.commit()


async def _parking_sweep() -> None:
    async with async_session() as session:
        await run_parking_sweep(session)


def schedule_parking_sweep(scheduler) -> None:
    scheduler.add_job(
        _parking_sweep,
        "interval",
        seconds=PARKING_SWEEP_INTERVAL_SECONDS,
        id="parking-sweep",
        replace_existing=True,
    )
