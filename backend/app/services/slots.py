from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingStatus, Post, Service

# Шаг перебора кандидатов слота. Станция роботизированная и работает 24/7
# (см. buisness/buisness.md) — рабочих часов нет, перебираем все сутки.
# Это же шаг, с которым обязан совпадать start_at в POST /bookings — клиент
# выбирает время кликом по предложенному слоту, а не вводит его руками.
SLOT_STEP_MINUTES = 15


def is_on_slot_grid(moment: datetime) -> bool:
    utc_moment = moment.astimezone(timezone.utc)
    return (
        utc_moment.second == 0
        and utc_moment.microsecond == 0
        and utc_moment.minute % SLOT_STEP_MINUTES == 0
    )


async def get_service_duration(session: AsyncSession, service_ids: list[int]) -> timedelta | None:
    """None означает "услуги не найдены/список пуст" — вызывающий код решает, как это трактовать."""
    services_result = await session.execute(select(Service).where(Service.id.in_(service_ids)))
    services = services_result.scalars().all()
    if len(services) != len(set(service_ids)):
        return None
    duration = timedelta(minutes=sum(s.duration_minutes for s in services))
    return duration if duration > timedelta(0) else None


async def get_bookings_overlapping(
    session: AsyncSession, window_start: datetime, window_end: datetime
) -> dict[int, list[Booking]]:
    existing_result = await session.execute(
        select(Booking).where(
            Booking.status != BookingStatus.CANCELLED,
            Booking.start_at < window_end,
            Booking.end_at > window_start,
        )
    )
    bookings_by_post: dict[int, list[Booking]] = {}
    for booking in existing_result.scalars().all():
        bookings_by_post.setdefault(booking.post_id, []).append(booking)
    return bookings_by_post


def post_is_free(existing: list[Booking], start_at: datetime, end_at: datetime) -> bool:
    return not any(start_at < b.end_at and end_at > b.start_at for b in existing)


async def car_is_free(
    session: AsyncSession, car_id: int, start_at: datetime, end_at: datetime
) -> bool:
    """Машина физически не может обслуживаться на двух постах одновременно —
    в отличие от постов, тут проверяем не по посту, а по car_id напрямую."""
    result = await session.execute(
        select(Booking.id).where(
            Booking.car_id == car_id,
            Booking.status != BookingStatus.CANCELLED,
            Booking.start_at < end_at,
            Booking.end_at > start_at,
        )
    )
    return result.first() is None


async def get_available_slots(
    session: AsyncSession, service_ids: list[int], day: date
) -> list[dict]:
    """Клиенту не важно, на каком посту его обслужат — здесь отдаются только
    моменты времени, свободные хотя бы на одном посту. Конкретный пост
    подбирается автоматически при создании заявки (см. app/api/bookings.py).

    Услуга может быть длиннее суток — тогда и конец интервала, и окно поиска
    конфликтующих заявок должны выходить за пределы запрошенного дня; сутки
    здесь ограничивают только МОМЕНТ СТАРТА, а не всю занятость."""
    duration = await get_service_duration(session, service_ids)
    if duration is None:
        return []

    posts = (await session.execute(select(Post))).scalars().all()

    day_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    now = datetime.now(timezone.utc)

    # Окно поиска конфликтов должно покрывать самый долгий кандидат целиком —
    # последний старт возможен почти в day_end, значит конец может уйти на
    # duration вперёд. Начало окна — просто day_start: заявка, ещё идущая на
    # начало дня, всё равно попадёт под фильтр end_at > window_start.
    bookings_by_post = await get_bookings_overlapping(session, day_start, day_end + duration)

    slots: list[dict] = []
    candidate_start = day_start
    while candidate_start < day_end:
        if candidate_start >= now:  # прошедшее время не предлагаем, даже сегодняшнее
            candidate_end = candidate_start + duration
            if any(
                post_is_free(bookings_by_post.get(post.id, []), candidate_start, candidate_end)
                for post in posts
            ):
                slots.append({"start_at": candidate_start, "end_at": candidate_end})
        candidate_start += timedelta(minutes=SLOT_STEP_MINUTES)

    return slots
