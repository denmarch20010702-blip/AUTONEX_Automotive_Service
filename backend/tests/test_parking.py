"""C7 (buisness.md, "Smart Parking Management", 2026-09-17): 6 мест
ожидания, автоматический выезд на пост по подтверждению приезда клиента и
наступлению времени, автоматическая парковка готовой машины, наценка за
простой сверх 2 бесплатных часов (обе фазы вместе)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from helpers import make_startable_now
from httpx import AsyncClient
from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from app.db.session import async_session
from app.models import AdditionalWork, Booking, BookingArchive, ParkingSpot


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


async def make_booking(client: AsyncClient, days_offset: int, *, duration_minutes: int = 10) -> tuple[int, int, int, int]:
    client_id = car_id = service_id = None
    try:
        client_resp = await client.post("/clients", json={"email": unique_email(), "name": "Parking Tester"})
        client_id = client_resp.json()["id"]
        car_resp = await client.post(
            "/cars", json={"client_id": client_id, "make": "Skoda", "model": "Octavia"}
        )
        car_id = car_resp.json()["id"]
        service_resp = await client.post(
            "/catalog",
            json={"name": f"Parking Service {uuid4().hex[:8]}", "duration_minutes": duration_minutes, "price": "300.00"},
        )
        service_id = service_resp.json()["id"]
        day = date.today() + timedelta(days=days_offset)
        slots = (
            await client.get(
                "/bookings/available-slots",
                params={
                    "service_ids": [service_id],
                    "date": datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat(),
                },
            )
        ).json()
        if not slots:
            pytest.skip(f"на день +{days_offset} не осталось свободных слотов")
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
        if car_id is not None:
            await client.delete(f"/cars/{car_id}")
        if client_id is not None:
            await client.delete(f"/clients/{client_id}")
        if service_id is not None:
            await client.delete(f"/catalog/{service_id}")
        raise


async def make_second_booking_for_same_car(
    client: AsyncClient, client_id: int, car_id: int, days_offset: int, *, duration_minutes: int = 10
) -> tuple[int, int]:
    """Вторая заявка для ТОЙ ЖЕ машины и клиента — другая услуга, другое
    время (UI_description.md п.49: у машины может быть несколько отдельных
    визитов на разное время)."""
    service_resp = await client.post(
        "/catalog",
        json={"name": f"Parking Service {uuid4().hex[:8]}", "duration_minutes": duration_minutes, "price": "300.00"},
    )
    service_id = service_resp.json()["id"]
    day = date.today() + timedelta(days=days_offset)
    slots = (
        await client.get(
            "/bookings/available-slots",
            params={
                "service_ids": [service_id],
                "date": datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat(),
            },
        )
    ).json()
    if not slots:
        pytest.skip(f"на день +{days_offset} не осталось свободных слотов")
    booking_resp = await client.post(
        "/bookings",
        json={
            "client_id": client_id,
            "car_id": car_id,
            "start_at": slots[0]["start_at"],
            "service_ids": [service_id],
        },
    )
    return service_id, booking_resp.json()["id"]


async def cleanup(client: AsyncClient, *, booking_id: int, car_id: int, client_id: int, service_id: int) -> None:
    async with async_session() as session:
        await session.execute(sa_delete(AdditionalWork).where(AdditionalWork.booking_id == booking_id))
        await session.execute(sa_delete(BookingArchive).where(BookingArchive.original_booking_id == booking_id))
        booking = await session.get(Booking, booking_id)
        if booking is not None:
            await session.delete(booking)
        await session.commit()
    await client.delete(f"/cars/{car_id}")
    await client.delete(f"/clients/{client_id}")
    await client.delete(f"/catalog/{service_id}")


async def free_spots_count() -> int:
    async with async_session() as session:
        total = (await session.execute(select(ParkingSpot.id))).scalars().all()
        occupied = (
            await session.execute(select(Booking.parking_spot_id).where(Booking.parking_spot_id.is_not(None)))
        ).scalars().all()
        return len(total) - len(set(occupied))


async def set_parked_at(booking_id: int, when: datetime) -> None:
    async with async_session() as session:
        booking = await session.get(Booking, booking_id)
        booking.parked_at = when
        await session.commit()


async def set_start_at(booking_id: int, when: datetime) -> None:
    async with async_session() as session:
        booking = await session.get(Booking, booking_id)
        duration = booking.end_at - booking.start_at
        booking.start_at = when
        booking.end_at = when + duration
        await session.commit()


async def get_booking_row(booking_id: int) -> Booking:
    async with async_session() as session:
        return await session.get(Booking, booking_id)


@pytest.mark.asyncio
async def test_confirm_parked_requires_accepted_status(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 600)
    try:
        await make_startable_now(booking_id)
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200

        resp = await client.post(f"/bookings/{booking_id}/park")
        assert resp.status_code == 409
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_confirm_parked_assigns_a_free_spot(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 601)
    try:
        await set_start_at(booking_id, datetime.now(timezone.utc) + timedelta(minutes=30))
        resp = await client.post(f"/bookings/{booking_id}/park")
        assert resp.status_code == 200
        body = resp.json()
        assert body["parking_spot_id"] is not None
        assert body["parked_at"] is not None
        assert body["status"] == "accepted"
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_confirm_parked_twice_returns_409(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 602)
    try:
        await set_start_at(booking_id, datetime.now(timezone.utc) + timedelta(minutes=30))
        resp = await client.post(f"/bookings/{booking_id}/park")
        assert resp.status_code == 200

        resp = await client.post(f"/bookings/{booking_id}/park")
        assert resp.status_code == 409
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_confirm_parked_nonexistent_booking_404(client: AsyncClient) -> None:
    resp = await client.post("/bookings/999999999/park")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_confirm_parked_more_than_hour_before_start_returns_409(client: AsyncClient) -> None:
    """UI_description.md п.50 (2026-09-18, найдено пользователем на
    практике): подтверждение приезда сильно заранее занимает место надолго
    без необходимости и мешает машинам с более ранними записями."""
    client_id, car_id, service_id, booking_id = await make_booking(client, 612)
    try:
        # `make_booking` записывает на слот далеко в будущем — заведомо
        # больше часа от "сейчас", без специального сдвига времени.
        resp = await client.post(f"/bookings/{booking_id}/park")
        assert resp.status_code == 409
        assert "за час" in resp.json()["detail"]
        assert (await get_booking_row(booking_id)).parking_spot_id is None
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_confirm_parked_within_hour_before_start_succeeds(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 613)
    try:
        await set_start_at(booking_id, datetime.now(timezone.utc) + timedelta(minutes=30))
        resp = await client.post(f"/bookings/{booking_id}/park")
        assert resp.status_code == 200
        assert resp.json()["parking_spot_id"] is not None
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_pre_service_arrivals_reserve_a_spot_for_cars_currently_on_post(client: AsyncClient) -> None:
    """UI_description.md п.51 (2026-09-18, найдено пользователем на
    практике): места не должны все уйти под заранее приехавшие машины —
    иначе машине, которая только что закончила обслуживание на посту, будет
    физически некуда съехать. Резервируем по одному месту на каждую заявку,
    реально работающую на посту (on_post) прямо сейчас."""
    on_post_booking = None
    pre_service_bookings: list[tuple[int, int, int, int]] = []
    try:
        # Одна заявка реально на посту — под неё должно резервироваться
        # место, хотя у неё самой пока места нет (см. leave_parking).
        client_id0, car_id0, service_id0, on_post_booking = await make_booking(client, 614, duration_minutes=1)
        await make_startable_now(on_post_booking)
        resp = await client.post(f"/bookings/{on_post_booking}/status", json={"status": "on_post"})
        assert resp.status_code == 200

        # Заполняем ВСЕ 6 мест заранее приехавшими машинами — по идее шестая
        # (последняя свободная) должна остаться зарезервированной для той,
        # что сейчас на посту, и её заявке места не хватит. Короткая
        # длительность (1 мин) + разведение по времени с запасом от окна
        # оккупации on_post_booking (см. выше) и друг от друга — иначе
        # разным дальним дням мог достаться один и тот же пост и они
        # столкнулись бы после сдвига в одно и то же "почти сейчас" окно
        # (EXCLUDE-ограничение "no_overlapping_bookings").
        for i in range(6):
            ids = await make_booking(client, 615 + i, duration_minutes=1)
            pre_service_bookings.append(ids)
            _, _, _, booking_id = ids
            await set_start_at(booking_id, datetime.now(timezone.utc) + timedelta(minutes=2 + i * 8))
            resp = await client.post(f"/bookings/{booking_id}/park")
            if i < 5:
                assert resp.status_code == 200, f"попытка {i} должна была получить место"
            else:
                # Шестая заранее приехавшая машина не должна забрать
                # последнее свободное место — оно зарезервировано.
                assert resp.status_code == 409
                assert "за час" not in resp.json()["detail"]

        # Как только заявка на посту заканчивает обслуживание (ready), она
        # сама получает то самое зарезервированное место.
        resp = await client.post(f"/bookings/{on_post_booking}/status", json={"status": "ready"})
        assert resp.status_code == 200
        assert resp.json()["parking_spot_id"] is not None
    finally:
        for client_id_i, car_id_i, service_id_i, booking_id_i in pre_service_bookings:
            await cleanup(client, booking_id=booking_id_i, car_id=car_id_i, client_id=client_id_i, service_id=service_id_i)
        if on_post_booking is not None:
            await cleanup(client, booking_id=on_post_booking, car_id=car_id0, client_id=client_id0, service_id=service_id0)


@pytest.mark.asyncio
async def test_same_car_cannot_occupy_two_parking_spots_at_once(client: AsyncClient) -> None:
    """Найденный пользователем на практике реальный баг (UI_description.md
    п.49, 2026-09-18): у одной машины может быть несколько своих заявок на
    разные услуги в разное время — но физически машина одна, и второе
    подтверждение приезда не должно выдавать ей отдельное место, пока первое
    ещё не освобождено (не выдано)."""
    client_id, car_id, service_id, booking1_id = await make_booking(client, 610)
    service2_id = booking2_id = None
    try:
        await set_start_at(booking1_id, datetime.now(timezone.utc) + timedelta(minutes=5))
        resp = await client.post(f"/bookings/{booking1_id}/park")
        assert resp.status_code == 200
        first_spot = resp.json()["parking_spot_id"]
        assert first_spot is not None

        service2_id, booking2_id = await make_second_booking_for_same_car(client, client_id, car_id, 611)
        await set_start_at(booking2_id, datetime.now(timezone.utc) + timedelta(minutes=15))
        resp = await client.post(f"/bookings/{booking2_id}/park")
        assert resp.status_code == 409
        assert "уже на станции" in resp.json()["detail"]

        # Место так и не назначено второй заявке — не "переставили" её тихо.
        second = await get_booking_row(booking2_id)
        assert second.parking_spot_id is None

        # После выдачи первой машины (место освобождено) вторая заявка та же
        # самая машина спокойно может подтвердить приезд.
        await make_startable_now(booking1_id)
        resp = await client.post(f"/bookings/{booking1_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200
        resp = await client.post(f"/bookings/{booking1_id}/status", json={"status": "ready"})
        assert resp.status_code == 200
        resp = await client.post(f"/bookings/{booking1_id}/status", json={"status": "issued"})
        assert resp.status_code == 200

        resp = await client.post(f"/bookings/{booking2_id}/park")
        assert resp.status_code == 200
        assert resp.json()["parking_spot_id"] == first_spot
    finally:
        if booking2_id is not None:
            async with async_session() as session:
                await session.execute(sa_delete(AdditionalWork).where(AdditionalWork.booking_id == booking2_id))
                await session.execute(sa_delete(BookingArchive).where(BookingArchive.original_booking_id == booking2_id))
                booking = await session.get(Booking, booking2_id)
                if booking is not None:
                    await session.delete(booking)
                await session.commit()
        if service2_id is not None:
            await client.delete(f"/catalog/{service2_id}")
        await cleanup(client, booking_id=booking1_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_same_car_cannot_be_on_two_posts_at_once(client: AsyncClient) -> None:
    """Разбор сценариев посты×парковка×слоты×машина (2026-09-18, продолжение
    UI_description.md п.49): продление occupancy заявки №1 (п.35) может
    "растянуть" её до момента, когда должна начаться заявка №2 ТОЙ ЖЕ
    машины — обе не пересекались по времени в момент создания (`car_is_free`
    проверяет это только тогда), но реально дошли до попытки приёма
    одновременно. Машина физически не может обслуживаться на двух постах."""
    client_id, car_id, service_id, booking1_id = await make_booking(client, 620)
    service2_id = booking2_id = None
    try:
        await make_startable_now(booking1_id)
        resp = await client.post(f"/bookings/{booking1_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200

        # Заявка №1 формально уже должна была закончиться (её `end_at` в
        # прошлом), но статус ещё `on_post` — та самая гонка "таймер не
        # успел довести до ready" (или доп. работа ещё не отработана), а не
        # надуманная ситуация. Двигаем `end_at` в прошлое прямым UPDATE —
        # не через API, потому что нас интересует именно рассинхрон
        # времени/статуса, а не сам механизм автотаймера.
        now = datetime.now(timezone.utc)
        async with async_session() as session:
            b1 = await session.get(Booking, booking1_id)
            b1.end_at = now - timedelta(seconds=1)
            await session.commit()

        # Заявка №2 той же машины — НЕ пересекается по времени с заявкой №1
        # (начинается ровно там, где та формально закончилась), но тоже уже
        # "подошла" (`start_at` в прошлом). `no_overlapping_car_bookings`
        # (EXCLUDE-ограничение A4) это разрешает — окна не перекрываются,
        # только наша новая проверка статуса должна остановить приём.
        service2_id, booking2_id = await make_second_booking_for_same_car(client, client_id, car_id, 621)
        async with async_session() as session:
            b2 = await session.get(Booking, booking2_id)
            duration = b2.end_at - b2.start_at
            b2.start_at = now - timedelta(seconds=1)
            b2.end_at = b2.start_at + duration
            await session.commit()

        resp = await client.post(f"/bookings/{booking2_id}/status", json={"status": "on_post"})
        assert resp.status_code == 409
        assert "обслуживается по другой записи" in resp.json()["detail"]
        assert (await get_booking_row(booking2_id)).status == "accepted"

        # Пока заявка №1 на посту, подтвердить парковку по заявке №2 той же
        # машины тоже нельзя — та же самая машина не может быть и на посту,
        # и (готовящейся встать) на парковке одновременно.
        resp = await client.post(f"/bookings/{booking2_id}/park")
        assert resp.status_code == 409
        assert "уже на станции" in resp.json()["detail"]

        # Как только заявка №1 освобождает пост (выдана), заявку №2 принять
        # уже можно как обычно.
        resp = await client.post(f"/bookings/{booking1_id}/status", json={"status": "ready"})
        assert resp.status_code == 200
        resp = await client.post(f"/bookings/{booking1_id}/status", json={"status": "issued"})
        assert resp.status_code == 200

        resp = await client.post(f"/bookings/{booking2_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200
    finally:
        if booking2_id is not None:
            async with async_session() as session:
                await session.execute(sa_delete(AdditionalWork).where(AdditionalWork.booking_id == booking2_id))
                await session.execute(sa_delete(BookingArchive).where(BookingArchive.original_booking_id == booking2_id))
                booking = await session.get(Booking, booking2_id)
                if booking is not None:
                    await session.delete(booking)
                await session.commit()
        if service2_id is not None:
            await client.delete(f"/catalog/{service2_id}")
        await cleanup(client, booking_id=booking1_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_parking_sweep_auto_accepts_confirmed_arrival_when_time_arrives(client: AsyncClient) -> None:
    from app.services.parking import run_parking_sweep

    client_id, car_id, service_id, booking_id = await make_booking(client, 603)
    try:
        # В пределах часа до начала (п.50) — подтвердить приезд уже можно,
        # но до самого start_at ещё есть время.
        await set_start_at(booking_id, datetime.now(timezone.utc) + timedelta(minutes=30))
        resp = await client.post(f"/bookings/{booking_id}/park")
        assert resp.status_code == 200
        spot_id = resp.json()["parking_spot_id"]

        # Ещё рано — до start_at далеко, sweep не должен ничего трогать.
        async with async_session() as session:
            await run_parking_sweep(session)
        booking_now = (await client.get(f"/bookings/{booking_id}")).json()
        assert booking_now["status"] == "accepted"
        assert booking_now["parking_spot_id"] == spot_id

        await make_startable_now(booking_id)
        async with async_session() as session:
            await run_parking_sweep(session)

        booking_now = (await client.get(f"/bookings/{booking_id}")).json()
        assert booking_now["status"] == "on_post"
        assert booking_now["parking_spot_id"] is None  # место освобождено
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_leaving_parking_records_wait_before_service(client: AsyncClient) -> None:
    from app.services.parking import run_parking_sweep

    client_id, car_id, service_id, booking_id = await make_booking(client, 604)
    try:
        await set_start_at(booking_id, datetime.now(timezone.utc) + timedelta(minutes=30))
        resp = await client.post(f"/bookings/{booking_id}/park")
        assert resp.status_code == 200

        await set_parked_at(booking_id, datetime.now(timezone.utc) - timedelta(minutes=42))
        await make_startable_now(booking_id)
        async with async_session() as session:
            await run_parking_sweep(session)

        booking = await get_booking_row(booking_id)
        assert booking.parking_wait_minutes >= 42
        assert booking.parking_spot_id is None
        assert booking.parked_at is None
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_ready_booking_auto_assigned_parking_spot(client: AsyncClient) -> None:
    from app.services.robot_timer import _auto_advance

    client_id, car_id, service_id, booking_id = await make_booking(client, 605)
    try:
        await make_startable_now(booking_id)
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200

        await _auto_advance(booking_id)
        booking_now = (await client.get(f"/bookings/{booking_id}")).json()
        assert booking_now["status"] == "ready"
        assert booking_now["parking_spot_id"] is not None
        assert booking_now["parked_at"] is not None
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_awaiting_approval_gets_parking_spot_and_declining_keeps_same_spot(client: AsyncClient) -> None:
    # Найдено пользователем на практике (2026-09-17): пока клиент решает по
    # доп. работе, машина физически должна где-то стоять на станции — пост
    # уже визуально свободен по расчётному интервалу, а места ожидания
    # раньше назначались только при готовности. Отказ от доп. работы не
    # должен переставлять машину — она остаётся на ТОМ ЖЕ месте.
    from app.services.robot_timer import _auto_advance

    client_id, car_id, service_id, booking_id = await make_booking(client, 610)
    extra_resp = await client.post(
        "/catalog", json={"name": f"Parking Extra {uuid4().hex[:8]}", "duration_minutes": 5, "price": "200.00"}
    )
    extra_id = extra_resp.json()["id"]
    try:
        await make_startable_now(booking_id)
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200

        work = (
            await client.post(f"/bookings/{booking_id}/additional-works", json={"service_id": extra_id})
        ).json()

        await _auto_advance(booking_id)
        booking_now = (await client.get(f"/bookings/{booking_id}")).json()
        assert booking_now["status"] == "awaiting_approval"
        spot_id = booking_now["parking_spot_id"]
        assert spot_id is not None
        assert booking_now["parked_at"] is not None

        resp = await client.post(f"/additional-works/{work['id']}/respond", json={"status": "declined"})
        assert resp.status_code == 200

        booking_now = (await client.get(f"/bookings/{booking_id}")).json()
        assert booking_now["status"] == "ready"
        assert booking_now["parking_spot_id"] == spot_id  # то же самое место, не переназначено
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)
        await client.delete(f"/catalog/{extra_id}")


@pytest.mark.asyncio
async def test_awaiting_approval_approved_with_room_frees_spot_and_returns_to_post(client: AsyncClient) -> None:
    # Клиент согласился отработать доп. работу, и место на посту есть —
    # машина съезжает с парковки обратно на пост (leave_parking), время
    # ожидания между раундами накапливается в parking_wait_minutes.
    from app.services.robot_timer import _auto_advance

    client_id, car_id, service_id, booking_id = await make_booking(client, 611)
    extra_resp = await client.post(
        "/catalog", json={"name": f"Parking Extra {uuid4().hex[:8]}", "duration_minutes": 5, "price": "200.00"}
    )
    extra_id = extra_resp.json()["id"]
    try:
        await make_startable_now(booking_id)
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200

        work = (
            await client.post(f"/bookings/{booking_id}/additional-works", json={"service_id": extra_id})
        ).json()

        await _auto_advance(booking_id)
        booking_now = (await client.get(f"/bookings/{booking_id}")).json()
        assert booking_now["status"] == "awaiting_approval"
        assert booking_now["parking_spot_id"] is not None

        resp = await client.post(f"/additional-works/{work['id']}/respond", json={"status": "approved"})
        assert resp.status_code == 200

        booking_now = (await client.get(f"/bookings/{booking_id}")).json()
        assert booking_now["status"] == "on_post"
        assert booking_now["parking_spot_id"] is None  # съехала обратно на пост, место освобождено

        booking_row = await get_booking_row(booking_id)
        assert booking_row.parking_wait_minutes >= 0
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)
        await client.delete(f"/catalog/{extra_id}")


@pytest.mark.asyncio
async def test_manual_ready_via_station_button_also_assigns_spot(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 606)
    try:
        await make_startable_now(booking_id)
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "ready"})
        assert resp.status_code == 200
        assert resp.json()["parking_spot_id"] is not None
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_issue_frees_parking_spot(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 607)
    try:
        await make_startable_now(booking_id)
        await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "ready"})
        spot_id = resp.json()["parking_spot_id"]
        assert spot_id is not None

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "issued"})
        assert resp.status_code == 200

        # Заявка архивирована и удалена из живой таблицы — место свободно.
        async with async_session() as session:
            occupied = (
                await session.execute(select(Booking.id).where(Booking.parking_spot_id == spot_id))
            ).first()
        assert occupied is None
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_no_surcharge_within_free_two_hours(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 608)
    try:
        await make_startable_now(booking_id)
        await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "ready"})
        assert resp.status_code == 200

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "issued"})
        assert resp.status_code == 200

        archive = (await client.get("/station/archive", params={"client_id": client_id})).json()["items"]
        entry = next(a for a in archive if a["original_booking_id"] == booking_id)
        # 300.00 — цена самой услуги, без всякой наценки (простоя почти нет).
        assert entry["total_price"] == "300.00"
        assert entry["service_price"] == "300.00"
        assert entry["parking_surcharge"] == "0.00"
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_surcharge_added_after_grace_period_combines_both_phases(client: AsyncClient) -> None:
    # 50 минут ожидания ДО обслуживания + 100 минут ПОСЛЕ = 150 суммарно —
    # 30 минут сверх 2 бесплатных часов, по ставке из station_settings.
    client_id, car_id, service_id, booking_id = await make_booking(client, 609)
    try:
        await set_start_at(booking_id, datetime.now(timezone.utc) + timedelta(minutes=30))
        resp = await client.post(f"/bookings/{booking_id}/park")
        assert resp.status_code == 200
        await set_parked_at(booking_id, datetime.now(timezone.utc) - timedelta(minutes=50))
        await make_startable_now(booking_id)

        from app.services.parking import run_parking_sweep

        async with async_session() as session:
            await run_parking_sweep(session)
        booking_now = (await client.get(f"/bookings/{booking_id}")).json()
        assert booking_now["status"] == "on_post"

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "ready"})
        assert resp.status_code == 200
        await set_parked_at(booking_id, datetime.now(timezone.utc) - timedelta(minutes=100))

        settings_resp = await client.get("/station/settings")
        rate = float(settings_resp.json()["parking_overdue_rate_per_minute"])

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "issued"})
        assert resp.status_code == 200

        archive = (await client.get("/station/archive", params={"client_id": client_id})).json()["items"]
        entry = next(a for a in archive if a["original_booking_id"] == booking_id)
        expected = 300.00 + 30 * rate
        assert abs(float(entry["total_price"]) - expected) < 0.01
        assert entry["service_price"] == "300.00"
        assert abs(float(entry["parking_surcharge"]) - (30 * rate)) < 0.01
        assert entry["parking_wait_minutes"] >= 150
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_all_spots_occupied_returns_409_then_sweep_fills_ready_booking_once_freed(
    client: AsyncClient,
) -> None:
    # Занимаем ВСЕ 6 мест реальными подтверждёнными заявками, проверяем
    # честный отказ седьмой, затем освобождаем одно место (выдав его заявку)
    # и проверяем, что заявка, ставшая "ready" без места, сама получает его
    # через sweep — открытый вопрос из BUSINESS_FEATURES_REVIEW.md.
    holders: list[tuple[int, int, int, int]] = []
    unparked_ready_holder: tuple[int, int, int, int] | None = None
    try:
        for i in range(6):
            holder = await make_booking(client, 650 + i)
            holders.append(holder)
            # Разводим по времени с шагом >= длительности (10 мин) — иначе
            # разные заявки на РАЗНЫЕ дальние дни могли достаться одному и
            # тому же посту и столкнуться после сдвига в одно и то же "почти
            # сейчас" окно (EXCLUDE-ограничение "no_overlapping_bookings").
            await set_start_at(holder[3], datetime.now(timezone.utc) + timedelta(minutes=5 + i * 10))
            resp = await client.post(f"/bookings/{holder[3]}/park")
            assert resp.status_code == 200, f"место {i} должно быть свободно"

        assert await free_spots_count() == 0

        # Седьмая заявка, готовая к парковке "после обслуживания" — мест нет.
        unparked_ready_holder = await make_booking(client, 660)
        _, _, _, ready_booking_id = unparked_ready_holder
        await make_startable_now(ready_booking_id)
        await client.post(f"/bookings/{ready_booking_id}/status", json={"status": "on_post"})
        resp = await client.post(f"/bookings/{ready_booking_id}/status", json={"status": "ready"})
        assert resp.status_code == 200
        assert resp.json()["parking_spot_id"] is None  # честно ждёт, не блокирует ничего

        # Освобождаем ОДНО место — снимаем с парковки первого держателя (по
        # старинке, приёмом на пост без ожидания sweep'а).
        first_holder_booking_id = holders[0][3]
        await make_startable_now(first_holder_booking_id)
        resp = await client.post(f"/bookings/{first_holder_booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200

        from app.services.parking import run_parking_sweep

        async with async_session() as session:
            await run_parking_sweep(session)

        booking_now = (await client.get(f"/bookings/{ready_booking_id}")).json()
        assert booking_now["parking_spot_id"] is not None
    finally:
        for holder in holders:
            await cleanup(client, booking_id=holder[3], car_id=holder[1], client_id=holder[0], service_id=holder[2])
        if unparked_ready_holder is not None:
            await cleanup(
                client,
                booking_id=unparked_ready_holder[3],
                car_id=unparked_ready_holder[1],
                client_id=unparked_ready_holder[0],
                service_id=unparked_ready_holder[2],
            )


@pytest.mark.asyncio
async def test_station_settings_get_and_patch(client: AsyncClient) -> None:
    resp = await client.get("/station/settings")
    assert resp.status_code == 200
    original_rate = resp.json()["parking_overdue_rate_per_minute"]

    try:
        resp = await client.patch("/station/settings", json={"parking_overdue_rate_per_minute": "12.50"})
        assert resp.status_code == 200
        assert resp.json()["parking_overdue_rate_per_minute"] == "12.50"

        resp = await client.get("/station/settings")
        assert resp.json()["parking_overdue_rate_per_minute"] == "12.50"

        # Отрицательная ставка превращала бы парковку в скидку и уменьшала
        # выручку, поэтому отклоняется ещё до записи в БД.
        resp = await client.patch("/station/settings", json={"parking_overdue_rate_per_minute": "-0.01"})
        assert resp.status_code == 422
    finally:
        # Возвращаем как было — это singleton-строка, общая для всех тестов.
        await client.patch("/station/settings", json={"parking_overdue_rate_per_minute": original_rate})


@pytest.mark.asyncio
async def test_list_parking_spots(client: AsyncClient) -> None:
    resp = await client.get("/parking-spots")
    assert resp.status_code == 200
    spots = resp.json()
    assert len(spots) == 6
    assert all(isinstance(s["id"], int) and s["name"] for s in spots)
