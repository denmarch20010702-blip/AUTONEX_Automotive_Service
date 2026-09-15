from datetime import date, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.db.session import async_session
from app.models import Car


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


async def make_client_car(client: AsyncClient, *, mileage: int = 0) -> tuple[int, int]:
    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "B5 Tester"}
    )
    client_id = client_resp.json()["id"]
    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Kia", "model": "Rio", "mileage": mileage}
    )
    car_id = car_resp.json()["id"]
    return client_id, car_id


async def set_service_history(car_id: int, *, last_service_date, mileage_at_last_service) -> None:
    from sqlalchemy import update

    async with async_session() as session:
        await session.execute(
            update(Car)
            .where(Car.id == car_id)
            .values(last_service_date=last_service_date, mileage_at_last_service=mileage_at_last_service)
        )
        await session.commit()


async def cleanup(client: AsyncClient, *, car_id: int, client_id: int) -> None:
    await client.delete(f"/cars/{car_id}")
    await client.delete(f"/clients/{client_id}")


@pytest.mark.asyncio
async def test_no_suggestion_for_car_never_serviced(client: AsyncClient) -> None:
    # B5: нет базы для сравнения (last_service_date=None) — молчим, не гадаем.
    client_id, car_id = await make_client_car(client)
    try:
        resp = await client.get(f"/clients/{client_id}/maintenance-suggestions")
        assert resp.status_code == 200
        assert resp.json()["suggestions"] == []
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id)


@pytest.mark.asyncio
async def test_suggestion_by_time_after_six_months(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    try:
        await set_service_history(
            car_id, last_service_date=date.today() - timedelta(days=200), mileage_at_last_service=0
        )
        resp = await client.get(f"/clients/{client_id}/maintenance-suggestions")
        suggestions = resp.json()["suggestions"]
        assert len(suggestions) == 1
        assert suggestions[0]["car_id"] == car_id
        assert suggestions[0]["reason"] == "time"
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id)


@pytest.mark.asyncio
async def test_suggestion_by_mileage(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client, mileage=15_000)
    try:
        # Недавнее ТО по времени (месяц назад), но пробег с тех пор большой.
        await set_service_history(
            car_id, last_service_date=date.today() - timedelta(days=30), mileage_at_last_service=3_000
        )
        resp = await client.get(f"/clients/{client_id}/maintenance-suggestions")
        suggestions = resp.json()["suggestions"]
        assert len(suggestions) == 1
        assert suggestions[0]["reason"] == "mileage"
        assert suggestions[0]["km_since_service"] == 12_000
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id)


@pytest.mark.asyncio
async def test_no_suggestion_when_recently_serviced_and_low_mileage(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client, mileage=1_000)
    try:
        await set_service_history(
            car_id, last_service_date=date.today() - timedelta(days=10), mileage_at_last_service=900
        )
        resp = await client.get(f"/clients/{client_id}/maintenance-suggestions")
        assert resp.json()["suggestions"] == []
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id)


@pytest.mark.asyncio
async def test_suggestions_for_nonexistent_client_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/clients/999999999/maintenance-suggestions")
    assert resp.status_code == 404
