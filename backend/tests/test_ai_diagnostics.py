"""C4 (2026-09-15) — "AI Diagnostic Assistant" из buisness.md. Pluggable:
rule-based генератор по умолчанию (нет LLM_API_KEY в тестовом окружении),
реальный LLM — опционально (см. ARCHITECTURE.md, решение пользователя
2026-09-15: rule-based по умолчанию). Запускается сразу после приёма машины
на пост (accepted -> on_post) — см. app/api/bookings.py."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete as sa_delete
from sqlalchemy import select, update

from app.db.session import async_session
from app.models import AdditionalWork, Booking, Car, Client, OutboxEmail
from app.services.ai_diagnostics import (
    MILEAGE_THRESHOLD_KM,
    DiagnosticSuggestion,
    generate_diagnostic_suggestion,
)
from helpers import make_startable_now


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


async def make_client_car(client: AsyncClient, *, mileage: int = 0) -> tuple[int, int]:
    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "C4 Tester"}
    )
    client_id = client_resp.json()["id"]
    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Kia", "model": "Rio", "mileage": mileage}
    )
    return client_id, car_resp.json()["id"]


async def set_service_history(car_id: int, *, mileage_at_last_service: int) -> None:
    async with async_session() as session:
        await session.execute(
            update(Car)
            .where(Car.id == car_id)
            .values(
                last_service_date=date.today() - timedelta(days=30),
                mileage_at_last_service=mileage_at_last_service,
            )
        )
        await session.commit()


async def make_service(client: AsyncClient, name: str, *, duration_minutes: int = 30) -> int:
    resp = await client.post(
        "/catalog",
        json={"name": f"{name} {uuid4().hex[:8]}", "duration_minutes": duration_minutes, "price": "700.00"},
    )
    return resp.json()["id"]


async def get_car(car_id: int) -> Car:
    async with async_session() as session:
        return await session.get(Car, car_id)


async def evaluate(client_id: int, car_id: int) -> DiagnosticSuggestion | None:
    """Создаёт эфемерную заявку без услуг (для этих тестов важен только
    профиль машины/каталог, не сама заявка), прогоняет её через
    generate_diagnostic_suggestion и сразу удаляет — не оставляя следа."""
    car = await get_car(car_id)
    async with async_session() as session:
        # `services=[]` передаём в конструктор, а не назначаем после commit —
        # иначе первое чтение `.services` (внутри generate_diagnostic_
        # suggestion) считает коллекцию непрогруженной и попытается сделать
        # lazy-load синхронно вне greenlet-контекста (MissingGreenlet).
        booking = Booking(
            client_id=client_id,
            car_id=car_id,
            post_id=1,
            start_at=datetime.now(timezone.utc),
            end_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            services=[],
        )
        session.add(booking)
        await session.commit()
        suggestion = await generate_diagnostic_suggestion(session, booking, car)
        await session.delete(booking)
        await session.commit()
    return suggestion


async def cleanup(client: AsyncClient, *, car_id: int, client_id: int, service_ids: list[int]) -> None:
    await client.delete(f"/cars/{car_id}")
    await client.delete(f"/clients/{client_id}")
    for service_id in service_ids:
        await client.delete(f"/catalog/{service_id}")


@pytest.mark.asyncio
async def test_no_suggestion_without_service_history(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client, mileage=50_000)
    service_id = await make_service(client, "Замена масла")
    try:
        assert await evaluate(client_id, car_id) is None
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id, service_ids=[service_id])


@pytest.mark.asyncio
async def test_no_suggestion_below_mileage_threshold(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client, mileage=5_000)
    service_id = await make_service(client, "Замена масла")
    await set_service_history(car_id, mileage_at_last_service=0)
    try:
        assert await evaluate(client_id, car_id) is None
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id, service_ids=[service_id])


@pytest.mark.asyncio
async def test_no_suggestion_without_matching_catalog_keyword(client: AsyncClient) -> None:
    # Пробег превышен, но в каталоге нет ничего похожего на "масло/тормоза/
    # фильтр/..." — предлагать нечего, это не общая рекомендация "на глаз".
    client_id, car_id = await make_client_car(client, mileage=50_000)
    service_id = await make_service(client, "Мойка кузова")
    await set_service_history(car_id, mileage_at_last_service=0)
    try:
        assert await evaluate(client_id, car_id) is None
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id, service_ids=[service_id])


@pytest.mark.asyncio
async def test_suggests_matching_catalog_service_above_threshold(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client, mileage=MILEAGE_THRESHOLD_KM + 1_000)
    service_id = await make_service(client, "Замена масла")
    await set_service_history(car_id, mileage_at_last_service=0)
    try:
        car = await get_car(car_id)
        suggestion = await evaluate(client_id, car_id)
        assert suggestion is not None
        assert suggestion.service_id == service_id
        assert 0 < suggestion.confidence <= 1
        assert car.make in suggestion.reason and car.model in suggestion.reason
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id, service_ids=[service_id])


@pytest.mark.asyncio
async def test_llm_path_used_when_key_configured(client: AsyncClient) -> None:
    # Pluggable-контракт (C1): при наличии LLM_API_KEY используется реальный
    # вызов вместо rule-based — проверяем это через мок httpx, не настоящую
    # сеть (ключа в тестовом окружении нет и не должно быть).
    client_id, car_id = await make_client_car(client, mileage=MILEAGE_THRESHOLD_KM + 1_000)
    service_id = await make_service(client, "Замена масла")
    await set_service_history(car_id, mileage_at_last_service=0)
    try:
        car = await get_car(car_id)
        async with async_session() as session:
            booking = Booking(
                client_id=client_id, car_id=car_id, post_id=1,
                start_at=datetime.now(timezone.utc), end_at=datetime.now(timezone.utc) + timedelta(minutes=30),
                services=[],
            )
            session.add(booking)
            await session.commit()

            fake_response = AsyncMock()
            fake_response.raise_for_status = lambda: None
            fake_response.json = lambda: {
                "content": [{"text": f'{{"service_id": {service_id}, "confidence": 0.8, "reason": "тест"}}'}]
            }
            with (
                patch("app.services.ai_diagnostics.settings.llm_api_key", "fake-key-for-test"),
                patch("httpx.AsyncClient.post", return_value=fake_response),
            ):
                suggestion = await generate_diagnostic_suggestion(session, booking, car)

            await session.delete(booking)
            await session.commit()
        assert suggestion == DiagnosticSuggestion(service_id=service_id, confidence=0.8, reason="тест")
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id, service_ids=[service_id])


@pytest.mark.asyncio
async def test_ai_diagnostic_proposes_additional_work_on_arrival(client: AsyncClient) -> None:
    # Интеграционный тест сквозь настоящий API: приём машины на пост должен
    # сам создать предложение доп. работы от ИИ (proposed_by=ai), не трогая
    # обязательный шаг согласования клиентом (B2) — предложение остаётся
    # pending, а не выполняется само.
    client_id, car_id = await make_client_car(client, mileage=MILEAGE_THRESHOLD_KM + 5_000)
    main_service_id = await make_service(client, "Развал-схождение")
    extra_service_id = await make_service(client, "Замена тормозных колодок")
    await set_service_history(car_id, mileage_at_last_service=0)

    day = date.today() + timedelta(days=90)
    slot = (
        await client.get(
            "/bookings/available-slots",
            params={
                "service_ids": [main_service_id],
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
            "service_ids": [main_service_id],
        },
    )
    booking_id = booking_resp.json()["id"]
    try:
        await make_startable_now(booking_id)
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200

        works = (await client.get(f"/bookings/{booking_id}/additional-works")).json()
        assert len(works) == 1
        assert works[0]["proposed_by"] == "ai"
        assert works[0]["status"] == "pending"
        assert works[0]["service_id"] == extra_service_id

        async with async_session() as session:
            client_row = await session.get(Client, client_id)
            emails = (
                await session.execute(select(OutboxEmail).where(OutboxEmail.to == client_row.email))
            ).scalars().all()
        assert any("ИИ-диагностика" in e.subject for e in emails)
    finally:
        async with async_session() as session:
            await session.execute(sa_delete(AdditionalWork).where(AdditionalWork.booking_id == booking_id))
            booking = await session.get(Booking, booking_id)
            if booking is not None:
                await session.delete(booking)
            await session.commit()
        await cleanup(
            client, car_id=car_id, client_id=client_id, service_ids=[main_service_id, extra_service_id]
        )
