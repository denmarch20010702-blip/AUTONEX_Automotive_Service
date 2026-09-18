"""C4 (2026-09-15) — "AI Diagnostic Assistant" из buisness.md. Pluggable:
rule-based генератор по умолчанию (нет LLM_API_KEY в тестовом окружении),
реальный LLM — опционально (см. ARCHITECTURE.md, решение пользователя
2026-09-15: rule-based по умолчанию). Запускается сразу после приёма машины
на пост (accepted -> on_post) — см. app/api/bookings.py.

Доработано по прямой просьбе пользователя (2026-09-15, найдено на реальных
данных): рекомендации всегда сходились к одной и той же случайной дешёвой
услуге среди широкого списка ключевых слов. Решение пользователя — единый
класс "ТО" по одному ключевому слову, и предлагать ВСЕ подходящие услуги
сразу, а не одну."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from helpers import make_startable_now
from httpx import AsyncClient
from sqlalchemy import delete as sa_delete
from sqlalchemy import select, update

from app.db.session import async_session
from app.models import AdditionalWork, Booking, Car, Client, OutboxEmail
from app.services.ai_diagnostics import (
    MILEAGE_THRESHOLD_KM,
    DiagnosticSuggestion,
    generate_diagnostic_suggestions,
)


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


async def evaluate(client_id: int, car_id: int) -> list[DiagnosticSuggestion]:
    """Создаёт эфемерную заявку без услуг (для этих тестов важен только
    профиль машины/каталог, не сама заявка), прогоняет её через
    generate_diagnostic_suggestions и сразу удаляет — не оставляя следа."""
    car = await get_car(car_id)
    async with async_session() as session:
        # `services=[]` передаём в конструктор, а не назначаем после commit —
        # иначе первое чтение `.services` (внутри generate_diagnostic_
        # suggestions) считает коллекцию непрогруженной и попытается сделать
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
        suggestions = await generate_diagnostic_suggestions(session, booking, car)
        await session.delete(booking)
        await session.commit()
    return suggestions


async def cleanup(client: AsyncClient, *, car_id: int, client_id: int, service_ids: list[int]) -> None:
    await client.delete(f"/cars/{car_id}")
    await client.delete(f"/clients/{client_id}")
    for service_id in service_ids:
        await client.delete(f"/catalog/{service_id}")


@pytest.mark.asyncio
async def test_no_suggestions_without_service_history(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client, mileage=50_000)
    service_id = await make_service(client, "Плановое ТО")
    try:
        assert await evaluate(client_id, car_id) == []
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id, service_ids=[service_id])


@pytest.mark.asyncio
async def test_no_suggestions_below_mileage_threshold(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client, mileage=5_000)
    service_id = await make_service(client, "Плановое ТО")
    await set_service_history(car_id, mileage_at_last_service=0)
    try:
        assert await evaluate(client_id, car_id) == []
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id, service_ids=[service_id])


@pytest.mark.asyncio
async def test_no_suggestions_without_matching_catalog_keyword(client: AsyncClient) -> None:
    # Пробег превышен, но в каталоге нет ничего из класса "ТО" — предлагать
    # нечего, это не общая рекомендация "на глаз".
    client_id, car_id = await make_client_car(client, mileage=50_000)
    service_id = await make_service(client, "Мойка кузова")
    await set_service_history(car_id, mileage_at_last_service=0)
    try:
        assert await evaluate(client_id, car_id) == []
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id, service_ids=[service_id])


@pytest.mark.asyncio
async def test_keyword_matches_word_boundary_not_substring_inside_avto(client: AsyncClient) -> None:
    # Найденный при реализации риск: голый substring "то" совпал бы внутри
    # "авто-..." — проверяем, что матчинг именно по границе слова.
    client_id, car_id = await make_client_car(client, mileage=MILEAGE_THRESHOLD_KM + 1_000)
    service_id = await make_service(client, "Автополировка кузова")
    await set_service_history(car_id, mileage_at_last_service=0)
    try:
        assert await evaluate(client_id, car_id) == []
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id, service_ids=[service_id])


@pytest.mark.asyncio
async def test_suggests_single_matching_catalog_service_above_threshold(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client, mileage=MILEAGE_THRESHOLD_KM + 1_000)
    service_id = await make_service(client, "Плановое ТО")
    await set_service_history(car_id, mileage_at_last_service=0)
    try:
        car = await get_car(car_id)
        suggestions = await evaluate(client_id, car_id)
        assert len(suggestions) == 1
        assert suggestions[0].service_id == service_id
        assert 0 < suggestions[0].confidence <= 1
        # Найдено пользователем (2026-09-16): причина не должна повторять
        # марку/модель машины на каждой строке (раздувает панель доп. работ
        # на станции при нескольких предложениях сразу) — это уже видно из
        # контекста самой заявки на странице.
        assert car.make not in suggestions[0].reason and car.model not in suggestions[0].reason
        assert "Плановое ТО" in suggestions[0].reason
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id, service_ids=[service_id])


@pytest.mark.asyncio
async def test_suggests_all_matching_catalog_services_not_just_one(client: AsyncClient) -> None:
    # Решение пользователя (2026-09-15): раньше выбиралась одна самая
    # дешёвая услуга — теперь предлагаются ВСЕ подходящие по классу "ТО".
    client_id, car_id = await make_client_car(client, mileage=MILEAGE_THRESHOLD_KM + 1_000)
    service_a = await make_service(client, "ТО-1: замена масла")
    service_b = await make_service(client, "ТО-2: замена фильтров")
    unrelated = await make_service(client, "Мойка кузова")
    await set_service_history(car_id, mileage_at_last_service=0)
    try:
        suggestions = await evaluate(client_id, car_id)
        suggested_ids = {s.service_id for s in suggestions}
        assert suggested_ids == {service_a, service_b}
        assert unrelated not in suggested_ids
    finally:
        await cleanup(
            client, car_id=car_id, client_id=client_id, service_ids=[service_a, service_b, unrelated]
        )


@pytest.mark.asyncio
async def test_llm_path_used_when_key_configured(client: AsyncClient) -> None:
    # Pluggable-контракт (C1): при наличии LLM_API_KEY используется реальный
    # вызов вместо rule-based — проверяем это через мок httpx, не настоящую
    # сеть (ключа в тестовом окружении нет и не должно быть).
    client_id, car_id = await make_client_car(client, mileage=MILEAGE_THRESHOLD_KM + 1_000)
    service_id = await make_service(client, "Плановое ТО")
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
                "content": [
                    {"text": f'[{{"service_id": {service_id}, "confidence": 0.8, "reason": "тест"}}]'}
                ]
            }
            with (
                patch("app.services.ai_diagnostics.settings.llm_api_key", "fake-key-for-test"),
                patch("httpx.AsyncClient.post", return_value=fake_response),
            ):
                suggestions = await generate_diagnostic_suggestions(session, booking, car)

            await session.delete(booking)
            await session.commit()
        assert suggestions == [DiagnosticSuggestion(service_id=service_id, confidence=0.8, reason="тест")]
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
    extra_service_id = await make_service(client, "ТО: замена тормозных колодок")
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
        # C5 (2026-09-16): причина/уверенность сохранены — но только для
        # оверсайта станции, не упоминаются в письме клиенту (см. ниже).
        assert works[0]["ai_confidence"] is not None
        assert works[0]["ai_reason"]

        async with async_session() as session:
            client_row = await session.get(Client, client_id)
            emails = (
                await session.execute(select(OutboxEmail).where(OutboxEmail.to == client_row.email))
            ).scalars().all()
        # C5: письмо неотличимо от предложения мастера — не упоминает ИИ.
        assert any("доп. работы требуют вашего решения" in e.subject for e in emails)
        assert not any("ИИ" in e.subject or "вероятность" in e.body for e in emails)
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


@pytest.mark.asyncio
async def test_ai_diagnostic_proposes_multiple_works_on_arrival(client: AsyncClient) -> None:
    # То же самое, но с двумя подходящими услугами в каталоге — обе должны
    # прийти клиенту за один заезд, не только первая попавшаяся.
    client_id, car_id = await make_client_car(client, mileage=MILEAGE_THRESHOLD_KM + 5_000)
    main_service_id = await make_service(client, "Развал-схождение")
    extra_a = await make_service(client, "ТО: замена масла")
    extra_b = await make_service(client, "ТО: замена фильтров")
    await set_service_history(car_id, mileage_at_last_service=0)

    day = date.today() + timedelta(days=91)
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
        proposed_service_ids = {w["service_id"] for w in works if w["proposed_by"] == "ai"}
        assert proposed_service_ids == {extra_a, extra_b}

        # C5 (2026-09-16, найдено пользователем на практике): раньше на КАЖДУЮ
        # предложенную услугу уходило своё письмо — при двух совпадениях сразу
        # это было 2 письма подряд. Теперь ровно одно письмо со списком всех
        # текущих неотвеченных предложений.
        async with async_session() as session:
            client_row = await session.get(Client, client_id)
            emails = (
                await session.execute(select(OutboxEmail).where(OutboxEmail.to == client_row.email))
            ).scalars().all()
        pending_notice_emails = [e for e in emails if e.subject.endswith("требуют вашего решения")]
        assert len(pending_notice_emails) == 1
        assert "замена масла" in pending_notice_emails[0].body.lower()
        assert "замена фильтров" in pending_notice_emails[0].body.lower()
    finally:
        async with async_session() as session:
            await session.execute(sa_delete(AdditionalWork).where(AdditionalWork.booking_id == booking_id))
            booking = await session.get(Booking, booking_id)
            if booking is not None:
                await session.delete(booking)
            await session.commit()
        await cleanup(
            client, car_id=car_id, client_id=client_id, service_ids=[main_service_id, extra_a, extra_b]
        )
