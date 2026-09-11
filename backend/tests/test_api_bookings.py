import asyncio
from datetime import date, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.db.session import async_session
from app.models import Booking


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


async def make_client_car(client: AsyncClient) -> tuple[int, int]:
    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "Booking Tester"}
    )
    client_id = client_resp.json()["id"]
    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Lada", "model": "Vesta"}
    )
    return client_id, car_resp.json()["id"]


async def make_service(client: AsyncClient, duration_minutes: int = 30) -> int:
    resp = await client.post(
        "/catalog",
        json={
            "name": f"Услуга {uuid4().hex}",
            "duration_minutes": duration_minutes,
            "price": "500.00",
        },
    )
    return resp.json()["id"]


async def delete_booking(booking_id: int) -> None:
    # Прямая ORM-очистка: DELETE-эндпоинта для заявок пока нет (это B4),
    # а оставленная заявка блокирует внешним ключом удаление поста/авто/
    # клиента и, в частности, ломает полный цикл downgrade/upgrade миграций
    # (проверено на практике — см. logs/EXECUTION_PLAN.md, шаг A4).
    async with async_session() as session:
        booking = await session.get(Booking, booking_id)
        if booking is not None:
            await session.delete(booking)
            await session.commit()


async def cleanup(client: AsyncClient, *, booking_id=None, car_id=None, client_id=None, service_id=None) -> None:
    if booking_id is not None:
        await delete_booking(booking_id)
    if car_id is not None:
        await client.delete(f"/cars/{car_id}")
    if client_id is not None:
        await client.delete(f"/clients/{client_id}")
    if service_id is not None:
        await client.delete(f"/catalog/{service_id}")


@pytest.mark.asyncio
async def test_available_slots_lists_all_three_posts(client: AsyncClient) -> None:
    service_id = await make_service(client)
    day = date.today() + timedelta(days=30)
    try:
        resp = await client.get(
            "/bookings/available-slots",
            params={"service_ids": [service_id], "date": day.isoformat()},
        )
        assert resp.status_code == 200
        slots = resp.json()
        assert len(slots) > 0
        post_ids = {s["post_id"] for s in slots}
        assert len(post_ids) == 3  # 3 сервисных поста, засеяны миграцией
    finally:
        await cleanup(client, service_id=service_id)


@pytest.mark.asyncio
async def test_booking_removes_slot_from_availability(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client, duration_minutes=30)
    day = date.today() + timedelta(days=31)
    booking_id = None
    try:
        slots_resp = await client.get(
            "/bookings/available-slots",
            params={"service_ids": [service_id], "date": day.isoformat()},
        )
        slot = slots_resp.json()[0]

        create_resp = await client.post(
            "/bookings",
            json={
                "client_id": client_id,
                "car_id": car_id,
                "post_id": slot["post_id"],
                "start_at": slot["start_at"],
                "end_at": slot["end_at"],
                "service_ids": [service_id],
            },
        )
        assert create_resp.status_code == 201
        assert create_resp.json()["status"] == "accepted"
        booking_id = create_resp.json()["id"]

        slots_resp_after = await client.get(
            "/bookings/available-slots",
            params={"service_ids": [service_id], "date": day.isoformat()},
        )
        taken = (slot["post_id"], slot["start_at"])
        assert not any((s["post_id"], s["start_at"]) == taken for s in slots_resp_after.json())

        get_resp = await client.get(f"/bookings/{booking_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["post_id"] == slot["post_id"]
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_get_nonexistent_booking_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/bookings/999999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_booking_with_nonexistent_references_returns_404(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client)
    day = date.today() + timedelta(days=32)
    try:
        resp = await client.post(
            "/bookings",
            json={
                "client_id": client_id,
                "car_id": car_id,
                "post_id": 999999999,
                "start_at": f"{day.isoformat()}T09:00:00Z",
                "end_at": f"{day.isoformat()}T09:30:00Z",
                "service_ids": [service_id],
            },
        )
        assert resp.status_code == 404

        resp = await client.post(
            "/bookings",
            json={
                "client_id": client_id,
                "car_id": car_id,
                "post_id": 1,
                "start_at": f"{day.isoformat()}T09:00:00Z",
                "end_at": f"{day.isoformat()}T09:30:00Z",
                "service_ids": [999999999],
            },
        )
        assert resp.status_code == 404
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_overlapping_booking_on_same_post_returns_409(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client, duration_minutes=30)
    day = date.today() + timedelta(days=33)
    booking_id = None
    try:
        slot = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [service_id], "date": day.isoformat()},
            )
        ).json()[0]

        payload = {
            "client_id": client_id,
            "car_id": car_id,
            "post_id": slot["post_id"],
            "start_at": slot["start_at"],
            "end_at": slot["end_at"],
            "service_ids": [service_id],
        }

        first = await client.post("/bookings", json=payload)
        assert first.status_code == 201
        booking_id = first.json()["id"]

        second = await client.post("/bookings", json=payload)
        assert second.status_code == 409
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_concurrent_bookings_on_same_slot_only_one_succeeds(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client, duration_minutes=30)
    day = date.today() + timedelta(days=34)
    booking_id = None
    try:
        slot = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [service_id], "date": day.isoformat()},
            )
        ).json()[0]

        payload = {
            "client_id": client_id,
            "car_id": car_id,
            "post_id": slot["post_id"],
            "start_at": slot["start_at"],
            "end_at": slot["end_at"],
            "service_ids": [service_id],
        }

        responses = await asyncio.gather(
            client.post("/bookings", json=payload),
            client.post("/bookings", json=payload),
        )
        codes = [r.status_code for r in responses]
        print(f"\nДва одновременных запроса на один слот -> статусы: {codes}")
        for i, r in enumerate(responses, start=1):
            print(f"  запрос {i}: {r.status_code} {r.json()}")
        statuses = sorted(codes)
        assert statuses == [201, 409]

        booking_id = next(r.json()["id"] for r in responses if r.status_code == 201)
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)
