from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


async def make_booking(client: AsyncClient, days_offset: int) -> tuple[int, int, int, int]:
    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "AW Tester"}
    )
    client_id = client_resp.json()["id"]
    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Honda", "model": "Civic"}
    )
    car_id = car_resp.json()["id"]
    service_resp = await client.post(
        "/catalog", json={"name": f"AW Service {uuid4().hex[:8]}", "duration_minutes": 30, "price": "500.00"}
    )
    service_id = service_resp.json()["id"]
    day = date.today() + timedelta(days=days_offset)
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


async def cleanup(client: AsyncClient, *, booking_id: int, car_id: int, client_id: int, service_id: int) -> None:
    from sqlalchemy import delete as sa_delete

    from app.db.session import async_session
    from app.models import AdditionalWork, Booking

    async with async_session() as session:
        await session.execute(sa_delete(AdditionalWork).where(AdditionalWork.booking_id == booking_id))
        booking = await session.get(Booking, booking_id)
        if booking is not None:
            await session.delete(booking)
        await session.commit()
    await client.delete(f"/cars/{car_id}")
    await client.delete(f"/clients/{client_id}")
    await client.delete(f"/catalog/{service_id}")


@pytest.mark.asyncio
async def test_propose_and_approve_additional_work(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 300)
    try:
        resp = await client.post(
            f"/bookings/{booking_id}/additional-works",
            json={"description": "Заменить тормозные колодки", "price": "1500.00"},
        )
        assert resp.status_code == 201
        work = resp.json()
        assert work["status"] == "pending"
        assert work["proposed_by"] == "mechanic"
        work_id = work["id"]

        resp = await client.get(f"/bookings/{booking_id}/additional-works")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp = await client.post(f"/additional-works/{work_id}/respond", json={"status": "approved"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_decline_additional_work(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 301)
    try:
        resp = await client.post(
            f"/bookings/{booking_id}/additional-works",
            json={"description": "Полировка кузова", "price": "3000.00"},
        )
        work_id = resp.json()["id"]

        resp = await client.post(f"/additional-works/{work_id}/respond", json={"status": "declined"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "declined"
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_cannot_respond_twice(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 302)
    try:
        resp = await client.post(
            f"/bookings/{booking_id}/additional-works",
            json={"description": "Замена фильтра", "price": "800.00"},
        )
        work_id = resp.json()["id"]

        resp = await client.post(f"/additional-works/{work_id}/respond", json={"status": "approved"})
        assert resp.status_code == 200

        resp = await client.post(f"/additional-works/{work_id}/respond", json={"status": "declined"})
        assert resp.status_code == 409
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_propose_for_nonexistent_booking_returns_404(client: AsyncClient) -> None:
    resp = await client.post(
        "/bookings/999999999/additional-works",
        json={"description": "Что-то", "price": "100.00"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_respond_to_nonexistent_work_returns_404(client: AsyncClient) -> None:
    resp = await client.post("/additional-works/999999999/respond", json={"status": "approved"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancelling_booking_with_additional_work_does_not_crash(client: AsyncClient) -> None:
    # Регресс-тест на реальный найденный баг (2026-09-13): additional_works
    # имеет FK на bookings без каскада — отмена/выдача заявки с хотя бы
    # одной доп. работой падала 500 (IntegrityError) вместо обычной
    # архивации. Проверяем оба терминальных статуса и то, что снимок доп.
    # работ сохраняется в журнале, а не молча теряется.
    client_id, car_id, service_id, booking_id = await make_booking(client, 303)
    try:
        resp = await client.post(
            f"/bookings/{booking_id}/additional-works",
            json={"description": "Диагностика подвески", "price": "700.00"},
        )
        assert resp.status_code == 201
        work_id = resp.json()["id"]
        await client.post(f"/additional-works/{work_id}/respond", json={"status": "approved"})

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "cancelled"})
        assert resp.status_code == 200  # раньше здесь был 500

        archive = await client.get("/station/archive", params={"client_id": client_id})
        entries = archive.json()
        assert len(entries) == 1
        snapshot = entries[0]["additional_works_snapshot"]
        assert len(snapshot) == 1
        assert snapshot[0]["description"] == "Диагностика подвески"
        assert snapshot[0]["status"] == "approved"
    finally:
        from app.db.session import async_session
        from app.models import BookingArchive

        async with async_session() as session:
            entry = (
                await session.execute(
                    select(BookingArchive).where(BookingArchive.original_booking_id == booking_id)
                )
            ).scalar_one_or_none()
            if entry is not None:
                await session.delete(entry)
                await session.commit()
        await client.delete(f"/cars/{car_id}")
        await client.delete(f"/clients/{client_id}")
        await client.delete(f"/catalog/{service_id}")
