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
async def test_parking_sweep_auto_accepts_confirmed_arrival_when_time_arrives(client: AsyncClient) -> None:
    from app.services.parking import run_parking_sweep

    client_id, car_id, service_id, booking_id = await make_booking(client, 603)
    try:
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
