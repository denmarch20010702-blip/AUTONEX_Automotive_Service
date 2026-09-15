"""C2/C3 (2026-09-15, доделано по прямой просьбе пользователя — "чтобы не
возвращаться к этим шагам"): точка отсчёта текущего раунда работы на посту
(on_post_started_at) — своя на основную услугу и на каждый новый раунд доп.
работы, даёт основу для процента прогресса на доске постов (C3)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete as sa_delete

from app.db.session import async_session
from app.models import AdditionalWork, Booking, BookingArchive


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


async def make_booking(
    client: AsyncClient, days_offset: int, *, duration_minutes: int = 20
) -> tuple[int, int, int, int]:
    client_resp = await client.post("/clients", json={"email": unique_email(), "name": "C2 Tester"})
    client_id = client_resp.json()["id"]
    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Renault", "model": "Duster"}
    )
    car_id = car_resp.json()["id"]
    service_resp = await client.post(
        "/catalog",
        json={"name": f"C2 Service {uuid4().hex[:8]}", "duration_minutes": duration_minutes, "price": "400.00"},
    )
    service_id = service_resp.json()["id"]
    day = date.today() + timedelta(days=days_offset)
    slot = (
        await client.get(
            "/bookings/available-slots",
            params={
                "service_ids": [service_id],
                "date": datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat(),
            },
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


@pytest.mark.asyncio
async def test_on_post_started_at_set_on_arrival_and_on_new_round(client: AsyncClient) -> None:
    from helpers import make_startable_now

    from app.services.robot_timer import _auto_advance

    client_id, car_id, service_id, booking_id = await make_booking(client, 403)
    extra_resp = await client.post(
        "/catalog", json={"name": f"C2 Extra {uuid4().hex[:8]}", "duration_minutes": 15, "price": "300.00"}
    )
    extra_id = extra_resp.json()["id"]
    try:
        await make_startable_now(booking_id)
        before_arrival = datetime.now(timezone.utc)
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200
        first_started = datetime.fromisoformat(resp.json()["on_post_started_at"].replace("Z", "+00:00"))
        assert first_started >= before_arrival

        work = (
            await client.post(f"/bookings/{booking_id}/additional-works", json={"service_id": extra_id})
        ).json()
        await client.post(f"/bookings/{booking_id}/status", json={"status": "awaiting_approval"})
        before_new_round = datetime.now(timezone.utc)
        resp = await client.post(f"/additional-works/{work['id']}/respond", json={"status": "approved"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

        booking_after = (await client.get(f"/bookings/{booking_id}")).json()
        assert booking_after["status"] == "on_post"
        second_started = datetime.fromisoformat(booking_after["on_post_started_at"].replace("Z", "+00:00"))
        assert second_started >= before_new_round
        assert second_started > first_started

        await _auto_advance(booking_id)
        assert (await client.get(f"/bookings/{booking_id}")).json()["status"] == "ready"
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)
        await client.delete(f"/catalog/{extra_id}")


@pytest.mark.asyncio
async def test_approved_work_waits_in_queue_while_a_sibling_is_still_pending(client: AsyncClient) -> None:
    # C2 (очередь задач, доделано по просьбе пользователя): одобренная доп.
    # работа не запускается сама, пока рядом висит другое неотвеченное
    # предложение по той же заявке — она "в очереди", а не "выполняется",
    # что и должно быть видно через execution_started=False.
    from helpers import make_startable_now

    client_id, car_id, service_id, booking_id = await make_booking(client, 404)
    extra_a_resp = await client.post(
        "/catalog", json={"name": f"C2 Queue A {uuid4().hex[:8]}", "duration_minutes": 10, "price": "150.00"}
    )
    extra_a = extra_a_resp.json()["id"]
    extra_b_resp = await client.post(
        "/catalog", json={"name": f"C2 Queue B {uuid4().hex[:8]}", "duration_minutes": 10, "price": "150.00"}
    )
    extra_b = extra_b_resp.json()["id"]
    try:
        await make_startable_now(booking_id)
        await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})

        work_a = (
            await client.post(f"/bookings/{booking_id}/additional-works", json={"service_id": extra_a})
        ).json()
        work_b = (
            await client.post(f"/bookings/{booking_id}/additional-works", json={"service_id": extra_b})
        ).json()
        await client.post(f"/bookings/{booking_id}/status", json={"status": "awaiting_approval"})

        # Отвечаем на A первым — но B всё ещё pending, поэтому раунд ещё не
        # стартует: A одобрена, но реально в очереди, не выполняется.
        resp = await client.post(f"/additional-works/{work_a['id']}/respond", json={"status": "approved"})
        assert resp.status_code == 200

        works = (await client.get(f"/bookings/{booking_id}/additional-works")).json()
        a_after_first_response = next(w for w in works if w["id"] == work_a["id"])
        assert a_after_first_response["status"] == "approved"
        assert a_after_first_response["execution_started"] is False  # в очереди, не выполняется

        # Отвечаем на B — теперь неотвеченных не осталось, раунд стартует,
        # и A (единственная одобренная) переходит из очереди в исполнение.
        resp = await client.post(f"/additional-works/{work_b['id']}/respond", json={"status": "declined"})
        assert resp.status_code == 200

        works = (await client.get(f"/bookings/{booking_id}/additional-works")).json()
        a_after_second_response = next(w for w in works if w["id"] == work_a["id"])
        assert a_after_second_response["execution_started"] is True  # теперь выполняется
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)
        await client.delete(f"/catalog/{extra_a}")
        await client.delete(f"/catalog/{extra_b}")
