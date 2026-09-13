"""A10 — скрипт-доказательство конкурентной безопасности бронирования.

Демонстрирует именно то, ради чего в шаге A4 построена вся защита
(EXCLUDE-ограничения в БД + блокировка строк `FOR UPDATE`): когда два
клиента одновременно пытаются занять последний свободный пост на одно и то
же время, ровно один получает слот, а другой — честный явный отказ (409),
а не тихая порча данных, зависание или двойное бронирование.

В отличие от автотестов (`backend/tests/test_api_bookings.py`), которые
проверяют то же самое через httpx.ASGITransport (внутрипроцессно, без сети),
этот скрипт бьёт по-настоящему поднятому backend по HTTP — то есть
демонстрирует поведение реальной работающей системы, а не только кода.

Запуск (backend должен быть поднят, `docker compose up -d`):
    docker compose exec backend python scripts/prove_concurrency.py
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import httpx

BASE_URL = "http://localhost:8000"


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


async def make_client_car(client: httpx.AsyncClient, label: str) -> tuple[int, int]:
    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": f"A10 {label}"}
    )
    client_resp.raise_for_status()
    client_id = client_resp.json()["id"]

    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Lada", "model": "Vesta"}
    )
    car_resp.raise_for_status()
    car_id = car_resp.json()["id"]

    return client_id, car_id


async def book(client: httpx.AsyncClient, client_id: int, car_id: int, start_at: str, service_id: int) -> httpx.Response:
    return await client.post(
        "/bookings",
        json={
            "client_id": client_id,
            "car_id": car_id,
            "start_at": start_at,
            "service_ids": [service_id],
        },
    )


async def cleanup(client: httpx.AsyncClient, *, booking_ids: list[int], car_ids: list[int], client_ids: list[int], service_id: int) -> None:
    # Только штатные REST-эндпоинты — без прямого доступа к БД. Заявки
    # отменяем (не удаляем — DELETE /bookings/{id} нет и не планируется,
    # отмена — штатный жизненный цикл заявки, см. A5/B4), затем убираем
    # машины/клиентов/услугу.
    for booking_id in booking_ids:
        await client.post(f"/bookings/{booking_id}/status", json={"status": "cancelled"})
    for car_id in car_ids:
        await client.delete(f"/cars/{car_id}")
    for client_id in client_ids:
        await client.delete(f"/clients/{client_id}")
    await client.delete(f"/catalog/{service_id}")


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10) as client:
        print("=== A10: доказательство конкурентной безопасности ===\n")

        # 1. Одноразовая услуга для эксперимента.
        service_resp = await client.post(
            "/catalog",
            json={"name": f"A10 Proof {uuid4().hex[:8]}", "duration_minutes": 30, "price": "500.00"},
        )
        service_resp.raise_for_status()
        service_id = service_resp.json()["id"]
        print(f"Услуга создана: id={service_id}")

        # 2. Находим реальный свободный слот на всех 3 постах через сам API
        #    (а не гадаем время руками) — далеко в будущем, чтобы точно не
        #    столкнуться с чужими данными в БД.
        day = date.today() + timedelta(days=180)
        window_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat()
        slots_resp = await client.get(
            "/bookings/available-slots",
            params={"service_ids": [service_id], "date": window_start},
        )
        slots_resp.raise_for_status()
        target_slot = slots_resp.json()[0]["start_at"]
        print(f"Целевое время для эксперимента: {target_slot} (постов на станции: 3)\n")

        # 3. Занимаем 2 из 3 постов заранее (последовательно, без гонки) —
        #    остаётся ровно один свободный пост на это время.
        filler_client_ids: list[int] = []
        filler_car_ids: list[int] = []
        filler_booking_ids: list[int] = []
        for i in range(2):
            cid, car_id = await make_client_car(client, f"Filler-{i+1}")
            filler_client_ids.append(cid)
            filler_car_ids.append(car_id)
            resp = await book(client, cid, car_id, target_slot, service_id)
            resp.raise_for_status()
            booking = resp.json()
            filler_booking_ids.append(booking["id"])
            print(f"Занят пост {booking['post_id']} клиентом Filler-{i+1} (booking id={booking['id']})")

        print("\nОстался ровно один свободный пост. Теперь два РАЗНЫХ клиента")
        print("одновременно (по-настоящему параллельно) бронируют это же время...\n")

        # 4. Два новых клиента одновременно бьют за последний свободный пост.
        client_a_id, car_a_id = await make_client_car(client, "Racer-A")
        client_b_id, car_b_id = await make_client_car(client, "Racer-B")

        started_at = datetime.now(timezone.utc)
        result_a, result_b = await asyncio.gather(
            book(client, client_a_id, car_a_id, target_slot, service_id),
            book(client, client_b_id, car_b_id, target_slot, service_id),
        )
        elapsed_ms = (datetime.now(timezone.utc) - started_at).total_seconds() * 1000

        print(f"Оба запроса отправлены одновременно, завершились за {elapsed_ms:.0f} мс:")
        print(f"  Racer-A -> HTTP {result_a.status_code}: {result_a.json()}")
        print(f"  Racer-B -> HTTP {result_b.status_code}: {result_b.json()}")

        statuses = sorted([result_a.status_code, result_b.status_code])
        racer_booking_ids = [r.json()["id"] for r in (result_a, result_b) if r.status_code == 201]

        print()
        if statuses == [201, 409]:
            winner = "Racer-A" if result_a.status_code == 201 else "Racer-B"
            loser = "Racer-B" if winner == "Racer-A" else "Racer-A"
            print(f"РЕЗУЛЬТАТ: {winner} получил слот (201), {loser} получил явный отказ (409).")
            print("Ни двойного бронирования, ни зависания, ни тихой порчи данных — как и требуется.")
        else:
            print(f"НЕОЖИДАННЫЙ РЕЗУЛЬТАТ: коды ответов {statuses} — ожидались ровно [201, 409].")

        # 5. Убираем за собой всё, что создали.
        await cleanup(
            client,
            booking_ids=filler_booking_ids + racer_booking_ids,
            car_ids=filler_car_ids + [car_a_id, car_b_id],
            client_ids=filler_client_ids + [client_a_id, client_b_id],
            service_id=service_id,
        )
        print("\nВременные данные эксперимента удалены.")

        if statuses != [201, 409]:
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
