from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingStatus, Post, Service

# Шаг перебора кандидатов слота. Станция роботизированная и работает 24/7
# (см. buisness/buisness.md) — рабочих часов нет, перебираем все сутки.
SLOT_STEP_MINUTES = 15


async def get_available_slots(
    session: AsyncSession, service_ids: list[int], day: date
) -> list[dict]:
    services_result = await session.execute(select(Service).where(Service.id.in_(service_ids)))
    services = services_result.scalars().all()
    if len(services) != len(set(service_ids)):
        return []

    duration = timedelta(minutes=sum(s.duration_minutes for s in services))
    if duration <= timedelta(0):
        return []

    posts = (await session.execute(select(Post))).scalars().all()

    day_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    # Берём с запасом по краям суток: заявка, начавшаяся вчера, может ещё
    # длиться в начале сегодняшнего дня, и наоборот.
    window_start = day_start - timedelta(hours=12)
    window_end = day_end + timedelta(hours=12)

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

    slots: list[dict] = []
    for post in posts:
        existing = bookings_by_post.get(post.id, [])
        candidate_start = day_start
        while candidate_start + duration <= day_end:
            candidate_end = candidate_start + duration
            overlaps = any(
                candidate_start < b.end_at and candidate_end > b.start_at for b in existing
            )
            if not overlaps:
                slots.append(
                    {"post_id": post.id, "start_at": candidate_start, "end_at": candidate_end}
                )
            candidate_start += timedelta(minutes=SLOT_STEP_MINUTES)

    slots.sort(key=lambda s: (s["start_at"], s["post_id"]))
    return slots
