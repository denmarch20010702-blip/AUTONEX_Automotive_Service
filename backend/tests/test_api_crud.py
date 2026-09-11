from uuid import uuid4

import pytest
from httpx import AsyncClient


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


@pytest.mark.asyncio
async def test_client_crud(client: AsyncClient) -> None:
    email = unique_email()

    resp = await client.post("/clients", json={"email": email, "name": "Иван Иванов"})
    assert resp.status_code == 201
    client_id = resp.json()["id"]

    resp = await client.get("/clients")
    assert resp.status_code == 200
    assert any(c["id"] == client_id for c in resp.json())

    resp = await client.get(f"/clients/{client_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Иван Иванов"

    resp = await client.patch(f"/clients/{client_id}", json={"name": "Иван Петров"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Иван Петров"

    resp = await client.delete(f"/clients/{client_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/clients/{client_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_client_duplicate_email_conflict(client: AsyncClient) -> None:
    email = unique_email()
    resp1 = await client.post("/clients", json={"email": email, "name": "A"})
    assert resp1.status_code == 201

    resp2 = await client.post("/clients", json={"email": email, "name": "B"})
    assert resp2.status_code == 409

    await client.delete(f"/clients/{resp1.json()['id']}")


@pytest.mark.asyncio
async def test_get_nonexistent_client_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/clients/999999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_car_crud(client: AsyncClient) -> None:
    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "Владелец авто"}
    )
    client_id = client_resp.json()["id"]

    resp = await client.post(
        "/cars",
        json={"client_id": client_id, "make": "Toyota", "model": "Camry", "mileage": 10000},
    )
    assert resp.status_code == 201
    car_id = resp.json()["id"]

    resp = await client.get("/cars", params={"client_id": client_id})
    assert resp.status_code == 200
    assert any(c["id"] == car_id for c in resp.json())

    resp = await client.patch(f"/cars/{car_id}", json={"mileage": 15000})
    assert resp.status_code == 200
    assert resp.json()["mileage"] == 15000

    resp = await client.delete(f"/cars/{car_id}")
    assert resp.status_code == 204

    await client.delete(f"/clients/{client_id}")


@pytest.mark.asyncio
async def test_create_car_for_nonexistent_client_returns_404(client: AsyncClient) -> None:
    resp = await client.post(
        "/cars", json={"client_id": 999999999, "make": "Lada", "model": "Vesta"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_service_crud(client: AsyncClient) -> None:
    name = f"Услуга {uuid4().hex}"

    resp = await client.post(
        "/catalog", json={"name": name, "duration_minutes": 45, "price": "1200.50"}
    )
    assert resp.status_code == 201
    service_id = resp.json()["id"]

    resp = await client.get(f"/catalog/{service_id}")
    assert resp.status_code == 200
    assert resp.json()["duration_minutes"] == 45

    resp = await client.patch(f"/catalog/{service_id}", json={"price": "1300.00"})
    assert resp.status_code == 200
    assert resp.json()["price"] == "1300.00"

    resp = await client.delete(f"/catalog/{service_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/catalog/{service_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_service_duplicate_name_conflict(client: AsyncClient) -> None:
    name = f"Услуга {uuid4().hex}"
    resp1 = await client.post(
        "/catalog", json={"name": name, "duration_minutes": 30, "price": "500.00"}
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/catalog", json={"name": name, "duration_minutes": 60, "price": "900.00"}
    )
    assert resp2.status_code == 409

    await client.delete(f"/catalog/{resp1.json()['id']}")
