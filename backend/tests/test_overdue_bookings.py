"""UI_description.md (2026-09-15): заявки, которые пропустили своё время
приёма на пост и рискуют задержать/столкнуться с уже существующей следующей
заявкой на том же посту, должны отменяться автоматически (см.
app/services/overdue_bookings.py). Тестируем саму функцию напрямую — тем же
приёмом, что и test_reminders.py::send_due_reminders — а не через реальный
APScheduler: джобу не место в тестовом прогоне (найдено на практике — джоб,
крутящийся в живом dev-процессе backend'а с `--reload`, реально отменял
заявки прямо посреди прогона тестов, пока делил с pytest одну и ту же БД)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import async_session
from app.models import Booking, BookingStatus, Post
from app.services.overdue_bookings import MIN_OVERDUE_GRACE, cancel_bookings_that_would_delay_the_queue


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


async def make_client_car(client: AsyncClient) -> tuple[int, int]:
    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "Overdue Tester"}
    )
    client_id = client_resp.json()["id"]
    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Renault", "model": "Logan"}
    )
    return client_id, car_resp.json()["id"]


async def make_service(client: AsyncClient, duration_minutes: int) -> int:
    resp = await client.post(
        "/catalog",
        json={"name": f"Overdue Service {uuid4().hex[:8]}", "duration_minutes": duration_minutes, "price": "500.00"},
    )
    return resp.json()["id"]


async def find_free_post(session, window_start: datetime, window_end: datetime) -> int | None:
    posts = (await session.execute(select(Post.id))).scalars().all()
    occupied = (
        await session.execute(
            select(Booking.post_id).where(
                Booking.status != BookingStatus.CANCELLED,
                Booking.start_at < window_end,
                Booking.end_at > window_start,
            )
        )
    ).scalars().all()
    return next((p for p in posts if p not in occupied), None)


async def insert_booking(
    session, *, client_id: int, car_id: int, service_id: int, post_id: int, start_at: datetime, end_at: datetime
) -> int:
    from app.models import Service

    service = await session.get(Service, service_id)
    booking = Booking(
        client_id=client_id,
        car_id=car_id,
        post_id=post_id,
        start_at=start_at,
        end_at=end_at,
        status=BookingStatus.ACCEPTED,
        services=[service],
    )
    session.add(booking)
    await session.commit()
    await session.refresh(booking)
    return booking.id


async def cleanup(client: AsyncClient, *, booking_ids: list[int], car_id: int, client_id: int, service_id: int) -> None:
    from app.models import BookingArchive
    from sqlalchemy import delete as sa_delete

    async with async_session() as session:
        for booking_id in booking_ids:
            booking = await session.get(Booking, booking_id)
            if booking is not None:
                await session.delete(booking)
        # Найденный на практике баг (2026-09-15): cancel_bookings_that_would_
        # delay_the_queue() отменяет заявку через update_booking_status(),
        # который теперь архивирует CANCELLED в BookingArchive (не только
        # удаляет из активной таблицы) — без явной очистки здесь эти строки
        # копились в общей dev-БД при каждом прогоне тестов (пользователь
        # заметил разросшийся архив станции с записями "Overdue Tester").
        if booking_ids:
            await session.execute(
                sa_delete(BookingArchive).where(
                    BookingArchive.original_booking_id.in_(booking_ids)
                )
            )
        await session.commit()
    await client.delete(f"/cars/{car_id}")
    await client.delete(f"/clients/{client_id}")
    await client.delete(f"/catalog/{service_id}")


@pytest.mark.asyncio
async def test_overdue_booking_blocking_next_one_gets_cancelled(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client, duration_minutes=5)
    booking_id = other_id = None
    other_client_id = other_car_id = None
    try:
        now = datetime.now(timezone.utc)
        # Заявка, которая давно должна была начаться (сильно дольше
        # MIN_OVERDUE_GRACE) и уже закончиться, но никто её не принял.
        overdue_start = now - MIN_OVERDUE_GRACE - timedelta(minutes=10)
        overdue_end = overdue_start + timedelta(minutes=5)
        # Реальная "следующая" заявка на тот же пост, которая скоро должна
        # начаться — продление просроченной (от "сейчас") её заденет.
        next_start = now + timedelta(minutes=2)
        next_end = next_start + timedelta(minutes=5)

        async with async_session() as session:
            post_id = await find_free_post(session, overdue_start, next_end)
            if post_id is None:
                pytest.skip("все посты заняты живыми заявками прямо сейчас")
            booking_id = await insert_booking(
                session,
                client_id=client_id,
                car_id=car_id,
                service_id=service_id,
                post_id=post_id,
                start_at=overdue_start,
                end_at=overdue_end,
            )

        other_client_id, other_car_id = await make_client_car(client)
        async with async_session() as session:
            other_id = await insert_booking(
                session,
                client_id=other_client_id,
                car_id=other_car_id,
                service_id=service_id,
                post_id=post_id,
                start_at=next_start,
                end_at=next_end,
            )

        async with async_session() as session:
            cancelled = await cancel_bookings_that_would_delay_the_queue(session)
        assert cancelled >= 1

        async with async_session() as session:
            booking = await session.get(Booking, booking_id)
            assert booking is None or booking.status == BookingStatus.CANCELLED

        # "Следующая" заявка не тронута.
        resp = await client.get(f"/bookings/{other_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"
    finally:
        ids = [b for b in (booking_id, other_id) if b]
        await cleanup(client, booking_ids=ids, car_id=car_id, client_id=client_id, service_id=service_id)
        if other_car_id:
            await client.delete(f"/cars/{other_car_id}")
        if other_client_id:
            await client.delete(f"/clients/{other_client_id}")


@pytest.mark.asyncio
async def test_overdue_booking_with_nothing_after_it_is_left_alone(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client, duration_minutes=5)
    booking_id = None
    try:
        now = datetime.now(timezone.utc)
        overdue_start = now - MIN_OVERDUE_GRACE - timedelta(minutes=10)
        overdue_end = overdue_start + timedelta(minutes=5)

        async with async_session() as session:
            # Свободный пост на широком горизонте — чтобы точно ничего не
            # стояло следом и заявку не за что было отменять.
            post_id = await find_free_post(session, overdue_start, now + timedelta(hours=1))
            if post_id is None:
                pytest.skip("все посты заняты живыми заявками прямо сейчас")
            booking_id = await insert_booking(
                session,
                client_id=client_id,
                car_id=car_id,
                service_id=service_id,
                post_id=post_id,
                start_at=overdue_start,
                end_at=overdue_end,
            )

        async with async_session() as session:
            await cancel_bookings_that_would_delay_the_queue(session)

        resp = await client.get(f"/bookings/{booking_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"
    finally:
        await cleanup(client, booking_ids=[booking_id] if booking_id else [], car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_freshly_overdue_booking_within_grace_period_is_left_alone(client: AsyncClient) -> None:
    # Даже если она бы столкнулась со следующей заявкой — в пределах
    # MIN_OVERDUE_GRACE её ещё не трогаем (см. модуль).
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client, duration_minutes=5)
    booking_id = other_id = None
    other_client_id = other_car_id = None
    try:
        now = datetime.now(timezone.utc)
        overdue_start = now - timedelta(seconds=5)
        overdue_end = overdue_start + timedelta(minutes=5)
        # Дальше, чем конец просроченной заявки — иначе их собственные
        # (ещё не продлённые) интервалы пересекутся уже при вставке, и тест
        # ничего не докажет про сам порог MIN_OVERDUE_GRACE.
        next_start = overdue_end + timedelta(minutes=5)
        next_end = next_start + timedelta(minutes=5)

        async with async_session() as session:
            post_id = await find_free_post(session, overdue_start, next_end)
            if post_id is None:
                pytest.skip("все посты заняты живыми заявками прямо сейчас")
            booking_id = await insert_booking(
                session,
                client_id=client_id,
                car_id=car_id,
                service_id=service_id,
                post_id=post_id,
                start_at=overdue_start,
                end_at=overdue_end,
            )

        other_client_id, other_car_id = await make_client_car(client)
        async with async_session() as session:
            other_id = await insert_booking(
                session,
                client_id=other_client_id,
                car_id=other_car_id,
                service_id=service_id,
                post_id=post_id,
                start_at=next_start,
                end_at=next_end,
            )

        async with async_session() as session:
            cancelled = await cancel_bookings_that_would_delay_the_queue(session)
        assert cancelled == 0

        resp = await client.get(f"/bookings/{booking_id}")
        assert resp.json()["status"] == "accepted"
    finally:
        ids = [b for b in (booking_id, other_id) if b]
        await cleanup(client, booking_ids=ids, car_id=car_id, client_id=client_id, service_id=service_id)
        if other_car_id:
            await client.delete(f"/cars/{other_car_id}")
        if other_client_id:
            await client.delete(f"/clients/{other_client_id}")
