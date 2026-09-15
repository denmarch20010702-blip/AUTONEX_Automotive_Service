"""Общие тестовые утилиты, переиспользуемые в нескольких файлах тестов."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.db.session import async_session
from app.models import Booking, Post


async def make_startable_now(booking_id: int) -> None:
    """Реальный найденный баг (2026-09-14): машину нельзя принять на пост
    раньше назначенного `start_at` — теперь это проверяется на backend'е
    (см. app/api/bookings.py). Тесты создают заявки на слот в далёком
    будущем через `days_offset` — специально, чтобы избежать коллизий по
    датам/постам между разными тестами (см. `make_booking` в каждом файле),
    а не для проверки реального расписания. Эта функция сдвигает
    `start_at`/`end_at` (сохраняя длительность) в ближайшее прошлое —
    "как будто время уже пришло" — прямо перед переходом в `on_post`, и
    подбирает пост, реально свободный на это новое время (тот же приём,
    что и в test_reminders.py::set_start_at)."""
    async with async_session() as session:
        booking = await session.get(Booking, booking_id)
        duration = booking.end_at - booking.start_at
        start_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        end_at = start_at + duration

        posts = (await session.execute(select(Post.id))).scalars().all()
        occupied = (
            await session.execute(
                select(Booking.post_id).where(
                    Booking.id != booking_id,
                    Booking.status != "CANCELLED",
                    Booking.start_at < end_at,
                    Booking.end_at > start_at,
                )
            )
        ).scalars().all()
        free_post_id = next((p for p in posts if p not in occupied), None)
        if free_post_id is None:
            # Все посты реально заняты живыми заявками именно сейчас
            # (например, пока станцию тестируют вручную параллельно) —
            # внешнее обстоятельство, не связанное с проверяемой логикой.
            pytest.skip("все посты заняты живыми заявками прямо сейчас")

        await session.execute(
            update(Booking)
            .where(Booking.id == booking_id)
            .values(start_at=start_at, end_at=end_at, post_id=free_post_id)
        )
        await session.commit()
