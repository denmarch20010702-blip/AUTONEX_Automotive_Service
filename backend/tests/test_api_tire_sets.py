"""UI_description.md п.47 (2026-09-16): хранение шин больше не голая кнопка
без визита — и сдача, и выдача возможны только пока машина реально на посту
по одной из двух защищённых услуг ("Сезонная замена шин" / "Получить/сдать
шины", см. app/api/tire_sets.py и миграцию 151f2fa88e1c)."""

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient

from helpers import make_startable_now

TIRE_VISIT_SERVICE_NAME = "Получить/сдать шины"
SEASONAL_TIRE_SWAP_SERVICE_NAME = "Сезонная замена шин"


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


async def get_protected_service_id(client: AsyncClient, name: str) -> int:
    services = (await client.get("/catalog")).json()
    return next(s["id"] for s in services if s["name"] == name)


async def make_on_post_booking(
    client: AsyncClient, *, client_id: int, car_id: int, service_name: str, days_offset: int
) -> int:
    """Создаёт заявку на защищённую услугу и переводит её на пост — только
    в таком состоянии `POST /tire-sets` и `.../issue` теперь разрешают
    действие (см. модуль docstring)."""
    service_id = await get_protected_service_id(client, service_name)
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
    booking_id = booking_resp.json()["id"]
    await make_startable_now(booking_id)
    resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
    assert resp.status_code == 200
    return booking_id


async def delete_booking(booking_id: int) -> None:
    from sqlalchemy import delete as sa_delete

    from app.db.session import async_session
    from app.models import AdditionalWork, Booking

    async with async_session() as session:
        await session.execute(sa_delete(AdditionalWork).where(AdditionalWork.booking_id == booking_id))
        booking = await session.get(Booking, booking_id)
        if booking is not None:
            await session.delete(booking)
        await session.commit()


async def cleanup(
    client: AsyncClient, *, tire_set_ids=None, booking_ids=None, car_id=None, client_id=None
) -> None:
    for tire_set_id in tire_set_ids or []:
        # DELETE-эндпоинта для комплектов шин нет и не нужен — история
        # хранения/выдачи должна оставаться; для тестовой уборки просто
        # выдаём (если ещё не выдан), чтобы не мешать индексу
        # "один активный комплект на машину" следующим тестам. Выдача теперь
        # тоже требует визита — доводим тем же вспомогательным визитом.
        booking_id = await make_on_post_booking(
            client, client_id=client_id, car_id=car_id,
            service_name=TIRE_VISIT_SERVICE_NAME, days_offset=550 + tire_set_id % 1000,
        )
        await client.post(f"/tire-sets/{tire_set_id}/issue")
        await delete_booking(booking_id)
    for booking_id in booking_ids or []:
        await delete_booking(booking_id)
    if car_id is not None:
        await client.delete(f"/cars/{car_id}")
    if client_id is not None:
        await client.delete(f"/clients/{client_id}")


@pytest.mark.asyncio
async def test_cannot_store_without_a_visit(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    try:
        resp = await client.post("/tire-sets", json={"client_id": client_id, "car_id": car_id})
        assert resp.status_code == 409
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id)


@pytest.mark.asyncio
async def test_cannot_issue_without_a_visit(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    booking_id = await make_on_post_booking(
        client, client_id=client_id, car_id=car_id, service_name=TIRE_VISIT_SERVICE_NAME, days_offset=500
    )
    tire_set_id = None
    try:
        resp = await client.post("/tire-sets", json={"client_id": client_id, "car_id": car_id})
        assert resp.status_code == 201
        tire_set_id = resp.json()["id"]
        await delete_booking(booking_id)  # визит закончился — машина уже не на посту

        resp = await client.post(f"/tire-sets/{tire_set_id}/issue")
        assert resp.status_code == 409
    finally:
        await cleanup(client, tire_set_ids=[tire_set_id] if tire_set_id else [], car_id=car_id, client_id=client_id)


@pytest.mark.asyncio
async def test_store_and_issue_tire_set_via_tire_visit_service(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    store_booking_id = await make_on_post_booking(
        client, client_id=client_id, car_id=car_id, service_name=TIRE_VISIT_SERVICE_NAME, days_offset=501
    )
    tire_set_id = None
    issue_booking_id = None
    try:
        resp = await client.post("/tire-sets", json={"client_id": client_id, "car_id": car_id})
        assert resp.status_code == 201
        body = resp.json()
        tire_set_id = body["id"]
        assert body["client_id"] == client_id
        assert body["car_id"] == car_id
        assert body["issued_at"] is None
        await delete_booking(store_booking_id)

        resp = await client.get("/tire-sets", params={"car_id": car_id})
        assert resp.status_code == 200
        assert any(t["id"] == tire_set_id for t in resp.json())

        issue_booking_id = await make_on_post_booking(
            client, client_id=client_id, car_id=car_id, service_name=TIRE_VISIT_SERVICE_NAME, days_offset=502
        )
        resp = await client.post(f"/tire-sets/{tire_set_id}/issue")
        assert resp.status_code == 200
        assert resp.json()["issued_at"] is not None
    finally:
        if issue_booking_id:
            await delete_booking(issue_booking_id)
        await cleanup(client, car_id=car_id, client_id=client_id)


@pytest.mark.asyncio
async def test_store_via_seasonal_swap_service(client: AsyncClient) -> None:
    # UI_description.md п.47: "Сезонная замена шин" тоже годится для сдачи
    # (это её основной сценарий) — но не для выдачи (см. тест ниже).
    client_id, car_id = await make_client_car(client)
    booking_id = await make_on_post_booking(
        client, client_id=client_id, car_id=car_id, service_name=SEASONAL_TIRE_SWAP_SERVICE_NAME, days_offset=503
    )
    tire_set_id = None
    try:
        resp = await client.post("/tire-sets", json={"client_id": client_id, "car_id": car_id})
        assert resp.status_code == 201
        tire_set_id = resp.json()["id"]
    finally:
        await delete_booking(booking_id)
        await cleanup(client, tire_set_ids=[tire_set_id] if tire_set_id else [], car_id=car_id, client_id=client_id)


@pytest.mark.asyncio
async def test_seasonal_swap_service_cannot_issue(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    store_booking_id = await make_on_post_booking(
        client, client_id=client_id, car_id=car_id, service_name=TIRE_VISIT_SERVICE_NAME, days_offset=504
    )
    tire_set_id = None
    swap_booking_id = None
    try:
        resp = await client.post("/tire-sets", json={"client_id": client_id, "car_id": car_id})
        tire_set_id = resp.json()["id"]
        await delete_booking(store_booking_id)

        swap_booking_id = await make_on_post_booking(
            client, client_id=client_id, car_id=car_id,
            service_name=SEASONAL_TIRE_SWAP_SERVICE_NAME, days_offset=505,
        )
        resp = await client.post(f"/tire-sets/{tire_set_id}/issue")
        assert resp.status_code == 409
    finally:
        if swap_booking_id:
            await delete_booking(swap_booking_id)
        await cleanup(client, tire_set_ids=[tire_set_id] if tire_set_id else [], car_id=car_id, client_id=client_id)


@pytest.mark.asyncio
async def test_cannot_store_second_active_set_for_same_car(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    booking_id = await make_on_post_booking(
        client, client_id=client_id, car_id=car_id, service_name=TIRE_VISIT_SERVICE_NAME, days_offset=506
    )
    tire_set_id = None
    try:
        resp = await client.post("/tire-sets", json={"client_id": client_id, "car_id": car_id})
        assert resp.status_code == 201
        tire_set_id = resp.json()["id"]

        # Вторая попытка сдать шины на ту же машину, пока первая не выдана —
        # тот же визит, всё ещё на посту.
        resp = await client.post("/tire-sets", json={"client_id": client_id, "car_id": car_id})
        assert resp.status_code == 409

        # После выдачи — можно сдать новый комплект (новым визитом).
        await client.post(f"/tire-sets/{tire_set_id}/issue")
        resp = await client.post("/tire-sets", json={"client_id": client_id, "car_id": car_id})
        assert resp.status_code == 201
        second_id = resp.json()["id"]
        await client.post(f"/tire-sets/{second_id}/issue")
    finally:
        await delete_booking(booking_id)
        await cleanup(client, car_id=car_id, client_id=client_id)


@pytest.mark.asyncio
async def test_cannot_issue_twice(client: AsyncClient) -> None:
    # UI_description.md п.28 (2026-09-14): выданный комплект теперь
    # архивируется и удаляется из живой таблицы (та же логика, что и у
    # заявок) — повторная попытка выдачи не находит строку вообще, поэтому
    # честно 404, а не 409 "уже выдан".
    client_id, car_id = await make_client_car(client)
    booking_id = await make_on_post_booking(
        client, client_id=client_id, car_id=car_id, service_name=TIRE_VISIT_SERVICE_NAME, days_offset=507
    )
    try:
        resp = await client.post("/tire-sets", json={"client_id": client_id, "car_id": car_id})
        tire_set_id = resp.json()["id"]

        resp = await client.post(f"/tire-sets/{tire_set_id}/issue")
        assert resp.status_code == 200

        resp = await client.post(f"/tire-sets/{tire_set_id}/issue")
        assert resp.status_code == 404
    finally:
        await delete_booking(booking_id)
        await cleanup(client, car_id=car_id, client_id=client_id)


@pytest.mark.asyncio
async def test_store_for_someone_elses_car_returns_403(client: AsyncClient) -> None:
    client_a_id, car_a_id = await make_client_car(client)
    client_b_id, car_b_id = await make_client_car(client)
    booking_id = await make_on_post_booking(
        client, client_id=client_a_id, car_id=car_a_id, service_name=TIRE_VISIT_SERVICE_NAME, days_offset=508
    )
    try:
        resp = await client.post("/tire-sets", json={"client_id": client_b_id, "car_id": car_a_id})
        assert resp.status_code == 403
    finally:
        await delete_booking(booking_id)
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
    booking_id = await make_on_post_booking(
        client, client_id=client_id, car_id=car_id, service_name=TIRE_VISIT_SERVICE_NAME, days_offset=509
    )
    resp = await client.post("/tire-sets", json={"client_id": client_id, "car_id": car_id})
    tire_set_id = resp.json()["id"]

    resp = await client.post(f"/tire-sets/{tire_set_id}/issue")
    assert resp.status_code == 200

    await delete_booking(booking_id)

    resp = await client.delete(f"/cars/{car_id}")
    assert resp.status_code == 204  # раньше здесь был 409

    resp = await client.delete(f"/clients/{client_id}")
    assert resp.status_code == 204

    archive = (await client.get("/tire-sets/archive", params={"client_id": client_id})).json()["items"]
    assert any(a["original_tire_set_id"] == tire_set_id for a in archive)
