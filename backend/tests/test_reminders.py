from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.db.session import async_session
from app.models import Booking, OutboxEmail, Post
from app.services.reminders import send_due_reminders


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


async def make_booking(client: AsyncClient) -> tuple[int, int, int, int]:
    # Найденный баг (2026-09-14, замечено пользователем — оставшиеся в живой
    # БД тестовые клиенты/машины/услуги): раньше client_id/car_id/service_id
    # создавались здесь, ДО того как вызывающий тест успевал войти в свой
    # `try`, — если следующий шаг (поиск слота на сегодня) кидал исключение
    # (что реально происходит: слотов на сегодня может уже не быть — их
    # разбирают и другие тесты, и ручное тестирование станции), уже
    # созданные записи никто не подчищал: `finally` вызывающего теста просто
    # не запускался, потому что исключение вылетало раньше, чем начинался
    # его `try`. Теперь хелпер сам чистит за собой при любой ошибке внутри
    # себя — вызывающему тесту нечего чистить, если сюда он вообще не попал.
    client_id = car_id = service_id = None
    try:
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
        slots = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [service_id], "date": window_start},
            )
        ).json()
        if not slots:
            pytest.skip("на сегодня уже нет свободных слотов — занято живыми данными, не связано с B3")
        booking_resp = await client.post(
            "/bookings",
            json={
                "client_id": client_id,
                "car_id": car_id,
                "start_at": slots[0]["start_at"],
                "service_ids": [service_id],
            },
        )
        return client_id, car_id, service_id, booking_resp.json()["id"]
    except BaseException:
        # BaseException, не Exception — `pytest.skip()` выше поднимает
        # `Skipped`, который наследуется от BaseException, а не Exception;
        # подчистить созданное нужно и в этом случае, не только при обычной
        # ошибке.
        if car_id is not None:
            await client.delete(f"/cars/{car_id}")
        if client_id is not None:
            await client.delete(f"/clients/{client_id}")
        if service_id is not None:
            await client.delete(f"/catalog/{service_id}")
        raise


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
        end_at = start_at + duration

        # Переставленное окно может попасть на живую заявку (реальную, не
        # тестовую) на том же посту, который был назначен исходному слоту "на
        # сегодня" — пересчитываем свободный пост под новое время, а не
        # держим старый жёстко, иначе тест ломается о чужую занятость.
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
            # Все посты реально заняты живыми заявками именно в этот момент
            # (например, пока станцию тестируют вручную параллельно) — это
            # внешнее обстоятельство, не имеющее отношения к логике
            # напоминаний B3, поэтому честно пропускаем тест, а не считаем
            # это его собственным падением.
            pytest.skip("все посты заняты живыми заявками прямо сейчас — не связано с B3")

        await session.execute(
            update(Booking)
            .where(Booking.id == booking_id)
            .values(start_at=start_at, end_at=end_at, post_id=free_post_id)
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
