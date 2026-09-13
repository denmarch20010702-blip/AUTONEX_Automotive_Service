from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.db.session import async_session
from app.models import Booking, OutboxEmail
from app.services.reminders import send_due_reminders


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


async def make_booking(client: AsyncClient) -> tuple[int, int, int, int]:
    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "Reminder Tester"}
    )
    client_id = client_resp.json()["id"]
    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Kia", "model": "Rio"}
    )
    car_id = car_resp.json()["id"]
    service_resp = await client.post(
        "/catalog", json={"name": f"Reminder Service {uuid4().hex[:8]}", "duration_minutes": 30, "price": "500.00"}
    )
    service_id = service_resp.json()["id"]
    day = date.today()
    window_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat()
    slot = (
        await client.get(
            "/bookings/available-slots",
            params={"service_ids": [service_id], "date": window_start},
        )
    ).json()[0]
    booking_resp = await client.post(
        "/bookings",
        json={
            "client_id": client_id,
            "car_id": car_id,
            "start_at": slot["start_at"],
            "service_ids": [service_id],
        },
    )
    return client_id, car_id, service_id, booking_resp.json()["id"]


async def set_start_at(booking_id: int, start_at: datetime) -> None:
    # Реальный мастер записи не позволяет выбрать точное время за пределами
    # 15-минутной сетки/произвольного смещения от "сейчас" — для теста окна
    # напоминания (ровно 24ч) нужен точный контроль, поэтому меняем `start_at`
    # напрямую в БД уже после легитимного создания заявки через API.
    # `end_at` двигаем вместе со `start_at` (сохраняя исходную длительность) —
    # иначе EXCLUDE-ограничение на диапазон поста (A4) не даёт start_at > end_at.
    async with async_session() as session:
        booking = await session.get(Booking, booking_id)
        duration = booking.end_at - booking.start_at
        await session.execute(
            update(Booking)
            .where(Booking.id == booking_id)
            .values(start_at=start_at, end_at=start_at + duration)
        )
        await session.commit()


async def cleanup(client: AsyncClient, *, booking_id: int, car_id: int, client_id: int, service_id: int) -> None:
    async with async_session() as session:
        booking = await session.get(Booking, booking_id)
        if booking is not None:
            await session.delete(booking)
            await session.commit()
    await client.delete(f"/cars/{car_id}")
    await client.delete(f"/clients/{client_id}")
    await client.delete(f"/catalog/{service_id}")


async def outbox_count(to: str) -> int:
    async with async_session() as session:
        result = await session.execute(select(OutboxEmail).where(OutboxEmail.to == to))
        return len(result.scalars().all())


async def delete_outbox(to: str) -> None:
    async with async_session() as session:
        from sqlalchemy import delete as sa_delete

        await session.execute(sa_delete(OutboxEmail).where(OutboxEmail.to == to))
        await session.commit()


@pytest.mark.asyncio
async def test_reminder_sent_for_booking_within_24_hours(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client)
    email = (await client.get(f"/clients/{client_id}")).json()["email"]
    try:
        await set_start_at(booking_id, datetime.now(timezone.utc) + timedelta(hours=20))

        async with async_session() as session:
            sent = await send_due_reminders(session)
        assert sent == 1
        assert await outbox_count(email) == 1

        booking = (await client.get(f"/bookings/{booking_id}")).json()
        # reminder_sent не входит в публичную схему — проверяем через ORM.
        async with async_session() as session:
            row = await session.get(Booking, booking_id)
            assert row.reminder_sent is True
        assert booking["id"] == booking_id
    finally:
        await delete_outbox(email)
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_reminder_not_sent_twice(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client)
    email = (await client.get(f"/clients/{client_id}")).json()["email"]
    try:
        await set_start_at(booking_id, datetime.now(timezone.utc) + timedelta(hours=10))

        async with async_session() as session:
            first = await send_due_reminders(session)
        async with async_session() as session:
            second = await send_due_reminders(session)

        assert first == 1
        assert second == 0  # уже отправлено — флаг reminder_sent не даёт продублировать
        assert await outbox_count(email) == 1
    finally:
        await delete_outbox(email)
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_reminder_not_sent_for_booking_far_in_future(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client)
    email = (await client.get(f"/clients/{client_id}")).json()["email"]
    try:
        await set_start_at(booking_id, datetime.now(timezone.utc) + timedelta(hours=48))

        async with async_session() as session:
            sent = await send_due_reminders(session)
        assert sent == 0
        assert await outbox_count(email) == 0
    finally:
        await delete_outbox(email)
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)
