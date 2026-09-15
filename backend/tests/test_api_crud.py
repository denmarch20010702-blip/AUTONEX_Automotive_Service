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
async def test_client_email_is_case_insensitive(client: AsyncClient) -> None:
    # Найдено вручную 2026-09-13: "Test@Example.com" и "test@example.com"
    # считались разными клиентами — можно было случайно завести дубликат
    # аккаунта с той же почтой в другом регистре.
    email = unique_email()
    mixed_case = email.upper()

    resp1 = await client.post("/clients", json={"email": mixed_case, "name": "A"})
    assert resp1.status_code == 201
    client_id = resp1.json()["id"]
    assert resp1.json()["email"] == email  # сохранено нормализованным

    resp2 = await client.post("/clients", json={"email": email, "name": "B"})
    assert resp2.status_code == 409

    found = await client.get("/clients", params={"email": mixed_case})
    assert found.status_code == 200
    assert [c["id"] for c in found.json()] == [client_id]

    await client.delete(f"/clients/{client_id}")


@pytest.mark.asyncio
async def test_find_client_by_email(client: AsyncClient) -> None:
    email = unique_email()
    resp = await client.post("/clients", json={"email": email, "name": "Найди Меня"})
    client_id = resp.json()["id"]

    resp = await client.get("/clients", params={"email": email})
    assert resp.status_code == 200
    assert [c["id"] for c in resp.json()] == [client_id]

    resp = await client.get("/clients", params={"email": unique_email()})
    assert resp.status_code == 200
    assert resp.json() == []

    await client.delete(f"/clients/{client_id}")


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
async def test_cannot_delete_car_or_client_with_active_booking(client: AsyncClient) -> None:
    from datetime import date, datetime, timedelta, timezone

    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "С заявкой"}
    )
    client_id = client_resp.json()["id"]
    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Kia", "model": "Rio"}
    )
    car_id = car_resp.json()["id"]
    service_resp = await client.post(
        "/catalog", json={"name": f"Услуга {uuid4().hex}", "duration_minutes": 20, "price": "300.00"}
    )
    service_id = service_resp.json()["id"]

    day = date.today() + timedelta(days=60)
    slot = (
        await client.get(
            "/bookings/available-slots",
            # available-slots?date= теперь ждёт момент времени со смещением
            # часового пояса, не голую дату (см. day_start_iso в
            # test_api_bookings.py) — тестам сам пояс не важен, берём UTC.
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

    resp = await client.delete(f"/cars/{car_id}")
    assert resp.status_code == 409

    # UI_description.md п.32/41 (2026-09-15): удаление КЛИЕНТА (в отличие от
    # прямого удаления машины выше) теперь само отменяет активную заявку и
    # удаляет машину — не блокируется ими. См. подробный тест ниже
    # (test_delete_client_cascades_bookings_and_cars).
    resp = await client.delete(f"/clients/{client_id}")
    assert resp.status_code == 204

    await client.delete(f"/catalog/{service_id}")


@pytest.mark.asyncio
async def test_station_archive_is_paginated(client: AsyncClient) -> None:
    # UI_description.md п.40 (2026-09-15): журнал разросся настолько, что
    # приходилось много скроллить — backend теперь отдаёт его постранично.
    from datetime import date, datetime, timedelta, timezone

    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "Пагинация архива"}
    )
    client_id = client_resp.json()["id"]
    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Kia", "model": "Rio"}
    )
    car_id = car_resp.json()["id"]
    service_resp = await client.post(
        "/catalog", json={"name": f"Услуга {uuid4().hex}", "duration_minutes": 15, "price": "100.00"}
    )
    service_id = service_resp.json()["id"]

    # 3 отдельные заявки на разные дни -> 3 записи в архиве после отмены.
    for day_offset in (76, 77, 78):
        day = date.today() + timedelta(days=day_offset)
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
        await client.post(f"/bookings/{booking_id}/status", json={"status": "cancelled"})

    page1 = (
        await client.get(
            "/station/archive", params={"client_id": client_id, "page": 1, "page_size": 2}
        )
    ).json()
    assert page1["total"] == 3
    assert page1["page"] == 1
    assert page1["page_size"] == 2
    assert len(page1["items"]) == 2

    page2 = (
        await client.get(
            "/station/archive", params={"client_id": client_id, "page": 2, "page_size": 2}
        )
    ).json()
    assert len(page2["items"]) == 1
    # Разные страницы — разные записи, без дублей.
    assert {i["id"] for i in page1["items"]}.isdisjoint({i["id"] for i in page2["items"]})

    await client.delete(f"/clients/{client_id}")
    await client.delete(f"/catalog/{service_id}")


@pytest.mark.asyncio
async def test_delete_client_tolerates_booking_disappearing_mid_cascade(client: AsyncClient) -> None:
    # Найденная при код-ревью реальная гонка (2026-09-15): фоновый джоб
    # автоотмены просроченных заявок (app/services/overdue_bookings.py,
    # каждые 30 секунд) мог "увести" (отменить и удалить из живой таблицы)
    # одну из заявок клиента между выборкой списка внутри delete_client и
    # попыткой её отменить самим delete_client — раньше необработанный 404
    # прерывал удаление профиля на середине. Эмулируем гонку честно: пока
    # delete_client "пытается" отменить заявку, она РЕАЛЬНО исчезает из
    # живой таблицы в параллельной транзакции (как это сделал бы джоб), а
    # не просто кидаем исключение с оставшейся живой заявкой — иначе тест
    # проверял бы не гонку, а тупик от настоящего дублирования удаления.
    from datetime import date, datetime, timedelta, timezone
    from unittest.mock import patch

    from fastapi import HTTPException

    from app.db.session import async_session
    from app.models import Booking

    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "Гонка при удалении"}
    )
    client_id = client_resp.json()["id"]
    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Kia", "model": "Rio"}
    )
    car_id = car_resp.json()["id"]
    service_resp = await client.post(
        "/catalog", json={"name": f"Услуга {uuid4().hex}", "duration_minutes": 15, "price": "100.00"}
    )
    service_id = service_resp.json()["id"]

    day = date.today() + timedelta(days=79)
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

    async def already_gone(*args, **kwargs):
        async with async_session() as session:
            booking = await session.get(Booking, booking_id)
            if booking is not None:
                await session.delete(booking)
                await session.commit()
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    with patch("app.api.bookings.update_booking_status", side_effect=already_gone):
        resp = await client.delete(f"/clients/{client_id}")
    assert resp.status_code == 204

    assert (await client.get(f"/clients/{client_id}")).status_code == 404
    assert (await client.get(f"/cars/{car_id}")).status_code == 404

    await client.delete(f"/catalog/{service_id}")


@pytest.mark.asyncio
async def test_delete_client_cascades_bookings_and_cars(client: AsyncClient) -> None:
    # UI_description.md п.32/41 (2026-09-15, прямая просьба пользователя):
    # клиент должен уметь удалить свой профиль, даже если у него есть
    # активные записи и машины — они удаляются автоматически вместе с
    # профилем. Заявка не просто исчезает — она честно отменяется тем же
    # путём, что и ручная отмена (архивация, освобождение поста), поэтому
    # должна остаться видна в архиве станции со статусом "cancelled".
    from datetime import date, datetime, timedelta, timezone

    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "Удаляю профиль"}
    )
    client_id = client_resp.json()["id"]
    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Kia", "model": "Rio"}
    )
    car_id = car_resp.json()["id"]
    service_resp = await client.post(
        "/catalog", json={"name": f"Услуга {uuid4().hex}", "duration_minutes": 20, "price": "300.00"}
    )
    service_id = service_resp.json()["id"]

    day = date.today() + timedelta(days=75)
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

    resp = await client.delete(f"/clients/{client_id}")
    assert resp.status_code == 204

    # Клиент, машина и живая заявка — все исчезли.
    assert (await client.get(f"/clients/{client_id}")).status_code == 404
    assert (await client.get(f"/cars/{car_id}")).status_code == 404
    assert (await client.get(f"/bookings/{booking_id}")).status_code == 404

    # ...но заявка не пропала без следа — она в архиве, отменённая.
    archive = (await client.get("/station/archive", params={"client_id": client_id})).json()["items"]
    entry = next(a for a in archive if a["original_booking_id"] == booking_id)
    assert entry["status"] == "cancelled"

    await client.delete(f"/catalog/{service_id}")


@pytest.mark.asyncio
async def test_cannot_delete_client_with_tires_in_storage(client: AsyncClient) -> None:
    # UI_description.md п.32/41: в отличие от машин/заявок выше, шины на
    # хранении — блокирующее условие: клиент должен сначала их забрать.
    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "Шины на хранении"}
    )
    client_id = client_resp.json()["id"]
    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Kia", "model": "Sportage"}
    )
    car_id = car_resp.json()["id"]
    tire_set_resp = await client.post(
        "/tire-sets", json={"client_id": client_id, "car_id": car_id}
    )
    tire_set_id = tire_set_resp.json()["id"]

    resp = await client.delete(f"/clients/{client_id}")
    assert resp.status_code == 409
    assert "шин" in resp.json()["detail"]

    # После выдачи шин — удаление профиля проходит нормально.
    await client.post(f"/tire-sets/{tire_set_id}/issue")
    resp = await client.delete(f"/clients/{client_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_cannot_update_car_with_active_booking(client: AsyncClient) -> None:
    # UI_description.md п.27 (2026-09-14): реальный найденный баг — можно
    # было поменять марку/модель/пробег машины, пока она уже стоит в
    # активной заявке.
    from datetime import date, datetime, timedelta, timezone

    from app.db.session import async_session
    from app.models import Booking

    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "Активная запись"}
    )
    client_id = client_resp.json()["id"]
    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Kia", "model": "Sportage"}
    )
    car_id = car_resp.json()["id"]
    service_resp = await client.post(
        "/catalog", json={"name": f"Услуга {uuid4().hex}", "duration_minutes": 20, "price": "300.00"}
    )
    service_id = service_resp.json()["id"]

    day = date.today() + timedelta(days=70)
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
    try:
        resp = await client.patch(f"/cars/{car_id}", json={"mileage": 99999})
        assert resp.status_code == 409
    finally:
        async with async_session() as session:
            booking = await session.get(Booking, booking_id)
            await session.delete(booking)
            await session.commit()
        await client.delete(f"/cars/{car_id}")
        await client.delete(f"/clients/{client_id}")
        await client.delete(f"/catalog/{service_id}")


@pytest.mark.asyncio
async def test_cannot_update_car_with_blank_make_or_model(client: AsyncClient) -> None:
    # UI_description.md п.26 (2026-09-14): реальный найденный баг — можно
    # было сохранить машину с пустой маркой/моделью при редактировании
    # (create требовал непустые значения, update — нет).
    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "Пустая марка"}
    )
    client_id = client_resp.json()["id"]
    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Kia", "model": "Rio"}
    )
    car_id = car_resp.json()["id"]
    try:
        resp = await client.patch(f"/cars/{car_id}", json={"make": ""})
        assert resp.status_code == 422

        resp = await client.patch(f"/cars/{car_id}", json={"model": ""})
        assert resp.status_code == 422

        resp = await client.patch(f"/cars/{car_id}", json={"mileage": -5})
        assert resp.status_code == 422

        # Марка/модель не изменились после всех отклонённых попыток.
        resp = await client.get(f"/cars/{car_id}")
        assert resp.json()["make"] == "Kia"
        assert resp.json()["model"] == "Rio"
    finally:
        await client.delete(f"/cars/{car_id}")
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
async def test_cannot_update_service_with_blank_or_overlong_name(client: AsyncClient) -> None:
    # UI_description.md п.24/30 (2026-09-14): реальные найденные баги —
    # можно было сохранить услугу с пустым названием при редактировании, и
    # слишком длинное название расползалось за пределы плитки каталога.
    name = f"Услуга {uuid4().hex}"
    resp = await client.post("/catalog", json={"name": name, "duration_minutes": 30, "price": "500.00"})
    service_id = resp.json()["id"]
    try:
        resp = await client.patch(f"/catalog/{service_id}", json={"name": ""})
        assert resp.status_code == 422

        resp = await client.patch(f"/catalog/{service_id}", json={"name": "Х" * 61})
        assert resp.status_code == 422

        resp = await client.get(f"/catalog/{service_id}")
        assert resp.json()["name"] == name
    finally:
        await client.delete(f"/catalog/{service_id}")


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
