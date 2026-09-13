"""Тесты на app/services/events.py и на то, что бизнес-логика реально
публикует события.

Важная оговорка (найдено при разработке): httpx ASGITransport, которым
пользуются остальные тесты, ждёт ПОЛНОГО завершения ASGI-приложения, прежде
чем вернуть хоть что-то вызывающему коду — а SSE-поток по определению
бесконечный, он никогда "не завершается". Поэтому реальный HTTP-эндпоинт
`GET /events` через этот тестовый клиент проверить нельзя в принципе — это
ограничение тестового инструмента, а не нашего кода. Что тестируем здесь:
саму шину (publish/subscribe) напрямую и то, что бизнес-логика её вызывает
с правильными данными. Живой стриминг по-настоящему проверяется вручную
через `curl` — см. VERIFICATION.md."""

import asyncio
import contextlib
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.services import events as events_module
from tests.test_api_bookings import cleanup, make_client_car, make_service


@pytest.mark.asyncio
async def test_subscriber_receives_published_event() -> None:
    async def consume_one():
        async for event in events_module.subscribe():
            return event

    task = asyncio.create_task(consume_one())
    await asyncio.sleep(0.01)  # дать подписке зарегистрироваться в шине
    events_module.publish("test_event", {"foo": "bar"})

    received = await asyncio.wait_for(task, timeout=2)
    assert received == {"type": "test_event", "data": {"foo": "bar"}}


@pytest.mark.asyncio
async def test_all_subscribers_receive_the_same_event() -> None:
    async def consume_one():
        async for event in events_module.subscribe():
            return event

    task_a = asyncio.create_task(consume_one())
    task_b = asyncio.create_task(consume_one())
    await asyncio.sleep(0.01)
    events_module.publish("broadcast", {"n": 1})

    received_a, received_b = await asyncio.wait_for(
        asyncio.gather(task_a, task_b), timeout=2
    )
    assert received_a == received_b == {"type": "broadcast", "data": {"n": 1}}


@pytest.mark.asyncio
async def test_subscriber_removed_after_generator_closed() -> None:
    before = events_module.subscriber_count()

    generator = events_module.subscribe()
    task = asyncio.create_task(generator.__anext__())
    await asyncio.sleep(0.01)
    assert events_module.subscriber_count() == before + 1

    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.01)
    assert events_module.subscriber_count() == before


@pytest.mark.asyncio
async def test_create_booking_publishes_booking_created(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client, duration_minutes=30)
    day = date.today() + timedelta(days=63)
    booking_id = None
    try:
        slot = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [service_id], "date": datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat()},
            )
        ).json()[0]

        with patch("app.api.bookings.publish") as mock_publish:
            resp = await client.post(
                "/bookings",
                json={
                    "client_id": client_id,
                    "car_id": car_id,
                    "start_at": slot["start_at"],
                    "service_ids": [service_id],
                },
            )
        assert resp.status_code == 201
        booking_id = resp.json()["id"]

        mock_publish.assert_called_once()
        event_type, data = mock_publish.call_args.args
        assert event_type == "booking_created"
        assert data["id"] == booking_id
        assert data["status"] == "accepted"
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_status_change_publishes_booking_status_changed(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client, duration_minutes=30)
    day = date.today() + timedelta(days=64)
    slot = (
        await client.get(
            "/bookings/available-slots",
            params={"service_ids": [service_id], "date": datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat()},
        )
    ).json()[0]
    create_resp = await client.post(
        "/bookings",
        json={
            "client_id": client_id,
            "car_id": car_id,
            "start_at": slot["start_at"],
            "service_ids": [service_id],
        },
    )
    booking_id = create_resp.json()["id"]
    try:
        with patch("app.api.bookings.publish") as mock_publish:
            resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200

        mock_publish.assert_called_once()
        event_type, data = mock_publish.call_args.args
        assert event_type == "booking_status_changed"
        assert data["id"] == booking_id
        assert data["status"] == "on_post"
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)
