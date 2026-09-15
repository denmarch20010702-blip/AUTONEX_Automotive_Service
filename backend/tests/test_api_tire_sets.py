from uuid import uuid4

import pytest
from httpx import AsyncClient


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


async def make_client_car(client: AsyncClient) -> tuple[int, int]:
    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "Tire Tester"}
    )
    client_id = client_resp.json()["id"]
    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Toyota", "model": "Camry"}
    )
    return client_id, car_resp.json()["id"]


async def cleanup(client: AsyncClient, *, tire_set_ids=None, car_id=None, client_id=None) -> None:
    for tire_set_id in tire_set_ids or []:
        # DELETE-эндпоинта для комплектов шин нет и не нужен — история
        # хранения/выдачи должна оставаться; для тестовой уборки просто
        # выдаём (если ещё не выдан), чтобы не мешать индексу
        # "один активный комплект на машину" следующим тестам.
        await client.post(f"/tire-sets/{tire_set_id}/issue")
    if car_id is not None:
        await client.delete(f"/cars/{car_id}")
    if client_id is not None:
        await client.delete(f"/clients/{client_id}")


@pytest.mark.asyncio
async def test_store_and_issue_tire_set(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    tire_set_id = None
    try:
        resp = await client.post("/tire-sets", json={"client_id": client_id, "car_id": car_id})
        assert resp.status_code == 201
        body = resp.json()
        tire_set_id = body["id"]
        assert body["client_id"] == client_id
        assert body["car_id"] == car_id
        assert body["issued_at"] is None

        resp = await client.get("/tire-sets", params={"car_id": car_id})
        assert resp.status_code == 200
        assert any(t["id"] == tire_set_id for t in resp.json())

        resp = await client.post(f"/tire-sets/{tire_set_id}/issue")
        assert resp.status_code == 200
        assert resp.json()["issued_at"] is not None
    finally:
        await cleanup(client, tire_set_ids=[tire_set_id] if tire_set_id else [], car_id=car_id, client_id=client_id)


@pytest.mark.asyncio
async def test_cannot_store_second_active_set_for_same_car(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    tire_set_id = None
    try:
        resp = await client.post("/tire-sets", json={"client_id": client_id, "car_id": car_id})
        assert resp.status_code == 201
        tire_set_id = resp.json()["id"]

        # Вторая попытка сдать шины на ту же машину, пока первая не выдана.
        resp = await client.post("/tire-sets", json={"client_id": client_id, "car_id": car_id})
        assert resp.status_code == 409

        # После выдачи — можно сдать новый комплект.
        await client.post(f"/tire-sets/{tire_set_id}/issue")
        resp = await client.post("/tire-sets", json={"client_id": client_id, "car_id": car_id})
        assert resp.status_code == 201
        second_id = resp.json()["id"]
        await client.post(f"/tire-sets/{second_id}/issue")
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id)


@pytest.mark.asyncio
async def test_cannot_issue_twice(client: AsyncClient) -> None:
    # UI_description.md п.28 (2026-09-14): выданный комплект теперь
    # архивируется и удаляется из живой таблицы (та же логика, что и у
    # заявок) — повторная попытка выдачи не находит строку вообще, поэтому
    # честно 404, а не 409 "уже выдан".
    client_id, car_id = await make_client_car(client)
    tire_set_id = None
    try:
        resp = await client.post("/tire-sets", json={"client_id": client_id, "car_id": car_id})
        tire_set_id = resp.json()["id"]

        resp = await client.post(f"/tire-sets/{tire_set_id}/issue")
        assert resp.status_code == 200

        resp = await client.post(f"/tire-sets/{tire_set_id}/issue")
        assert resp.status_code == 404
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id)


@pytest.mark.asyncio
async def test_store_for_someone_elses_car_returns_403(client: AsyncClient) -> None:
    client_a_id, car_a_id = await make_client_car(client)
    client_b_id, car_b_id = await make_client_car(client)
    try:
        resp = await client.post("/tire-sets", json={"client_id": client_b_id, "car_id": car_a_id})
        assert resp.status_code == 403
    finally:
        await cleanup(client, car_id=car_a_id, client_id=client_a_id)
        await cleanup(client, car_id=car_b_id, client_id=client_b_id)


@pytest.mark.asyncio
async def test_issue_nonexistent_tire_set_returns_404(client: AsyncClient) -> None:
    resp = await client.post("/tire-sets/999999999/issue")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_car_deletable_after_tire_set_issued(client: AsyncClient) -> None:
    # UI_description.md п.28 (2026-09-14): реальный найденный баг — выданный
    # (уже не активный) комплект шин навсегда блокировал удаление машины и
    # клиента внешним ключом, а сообщение об ошибке лгало про "активное"
    # хранение. Теперь выданный комплект архивируется и удаляется из живой
    # таблицы — машину и клиента можно удалить сразу после выдачи.
    client_id, car_id = await make_client_car(client)
    resp = await client.post("/tire-sets", json={"client_id": client_id, "car_id": car_id})
    tire_set_id = resp.json()["id"]

    resp = await client.post(f"/tire-sets/{tire_set_id}/issue")
    assert resp.status_code == 200

    resp = await client.delete(f"/cars/{car_id}")
    assert resp.status_code == 204  # раньше здесь был 409

    resp = await client.delete(f"/clients/{client_id}")
    assert resp.status_code == 204

    archive = (await client.get("/tire-sets/archive", params={"client_id": client_id})).json()["items"]
    assert any(a["original_tire_set_id"] == tire_set_id for a in archive)
