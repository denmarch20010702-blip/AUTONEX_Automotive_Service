import asyncio
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.db.session import async_session
from app.models import Booking


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


async def make_client_car(client: AsyncClient) -> tuple[int, int]:
    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "Booking Tester"}
    )
    client_id = client_resp.json()["id"]
    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Lada", "model": "Vesta"}
    )
    return client_id, car_resp.json()["id"]


async def make_service(client: AsyncClient, duration_minutes: int = 30) -> int:
    resp = await client.post(
        "/catalog",
        json={
            "name": f"Услуга {uuid4().hex}",
            "duration_minutes": duration_minutes,
            "price": "500.00",
        },
    )
    return resp.json()["id"]


async def delete_booking(booking_id: int) -> None:
    # Прямая ORM-очистка: DELETE-эндпоинта для заявок пока нет (это B4),
    # а оставленная заявка блокирует внешним ключом удаление поста/авто/
    # клиента и, в частности, ломает полный цикл downgrade/upgrade миграций
    # (проверено на практике — см. logs/EXECUTION_PLAN.md, шаг A4).
    async with async_session() as session:
        booking = await session.get(Booking, booking_id)
        if booking is not None:
            await session.delete(booking)
            await session.commit()


async def cleanup(
    client: AsyncClient,
    *,
    booking_ids=None,
    booking_id=None,
    car_ids=None,
    car_id=None,
    client_ids=None,
    client_id=None,
    service_id=None,
) -> None:
    for bid in (booking_ids or []) + ([booking_id] if booking_id is not None else []):
        await delete_booking(bid)
    for cid in (car_ids or []) + ([car_id] if car_id is not None else []):
        await client.delete(f"/cars/{cid}")
    for cid in (client_ids or []) + ([client_id] if client_id is not None else []):
        await client.delete(f"/clients/{cid}")
    if service_id is not None:
        await client.delete(f"/catalog/{service_id}")


@pytest.mark.asyncio
async def test_available_slots_returns_times_without_post_id(client: AsyncClient) -> None:
    # Клиенту не важно, на каком посту его обслужат — слот отдаётся просто
    # как момент времени, пост подбирается автоматически при бронировании.
    service_id = await make_service(client)
    day = date.today() + timedelta(days=30)
    try:
        resp = await client.get(
            "/bookings/available-slots",
            params={"service_ids": [service_id], "date": day.isoformat()},
        )
        assert resp.status_code == 200
        slots = resp.json()
        assert len(slots) > 0
        assert set(slots[0].keys()) == {"start_at", "end_at"}
    finally:
        await cleanup(client, service_id=service_id)


@pytest.mark.asyncio
async def test_booking_auto_assigns_a_post(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client, duration_minutes=30)
    day = date.today() + timedelta(days=31)
    booking_id = None
    try:
        slot = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [service_id], "date": day.isoformat()},
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
        assert create_resp.status_code == 201
        body = create_resp.json()
        assert body["status"] == "accepted"
        assert isinstance(body["post_id"], int)  # подобран автоматически
        booking_id = body["id"]

        get_resp = await client.get(f"/bookings/{booking_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["post_id"] == body["post_id"]

        list_resp = await client.get("/bookings")
        assert list_resp.status_code == 200
        assert any(b["id"] == booking_id for b in list_resp.json())

        filtered_resp = await client.get("/bookings", params={"client_id": client_id})
        assert filtered_resp.status_code == 200
        assert [b["id"] for b in filtered_resp.json()] == [booking_id]
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_get_nonexistent_booking_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/bookings/999999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_booking_with_nonexistent_references_returns_404(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client)
    day = date.today() + timedelta(days=32)
    try:
        resp = await client.post(
            "/bookings",
            json={
                "client_id": 999999999,
                "car_id": car_id,
                "start_at": f"{day.isoformat()}T09:00:00Z",
                "service_ids": [service_id],
            },
        )
        assert resp.status_code == 404

        resp = await client.post(
            "/bookings",
            json={
                "client_id": client_id,
                "car_id": car_id,
                "start_at": f"{day.isoformat()}T09:00:00Z",
                "service_ids": [999999999],
            },
        )
        assert resp.status_code == 404
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_same_car_cannot_be_booked_twice_at_overlapping_time(client: AsyncClient) -> None:
    # Баг, найденный пользователем вручную: одна машина получала 3 заявки на
    # 3 разных поста в одно и то же время — физически невозможно, машина не
    # может обслуживаться сразу на нескольких постах.
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client, duration_minutes=30)
    day = date.today() + timedelta(days=35)
    booking_id = None
    try:
        slot = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [service_id], "date": day.isoformat()},
            )
        ).json()[0]
        payload = {
            "client_id": client_id,
            "car_id": car_id,
            "start_at": slot["start_at"],
            "service_ids": [service_id],
        }

        first = await client.post("/bookings", json=payload)
        assert first.status_code == 201
        booking_id = first.json()["id"]

        for _ in range(2):  # раньше каждая из этих попыток уходила на новый пост и получала 201
            again = await client.post("/bookings", json=payload)
            assert again.status_code == 409
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_concurrent_bookings_same_car_only_one_succeeds(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client, duration_minutes=30)
    day = date.today() + timedelta(days=36)
    booking_id = None
    try:
        slot = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [service_id], "date": day.isoformat()},
            )
        ).json()[0]
        payload = {
            "client_id": client_id,
            "car_id": car_id,
            "start_at": slot["start_at"],
            "service_ids": [service_id],
        }

        responses = await asyncio.gather(
            client.post("/bookings", json=payload),
            client.post("/bookings", json=payload),
            client.post("/bookings", json=payload),
        )
        codes = [r.status_code for r in responses]
        print(f"\nТри одновременных запроса на одну машину -> статусы: {codes}")
        for i, r in enumerate(responses, start=1):
            print(f"  запрос {i}: {r.status_code} {r.json()}")
        assert sorted(codes) == [201, 409, 409]

        booking_id = next(r.json()["id"] for r in responses if r.status_code == 201)
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_slot_disappears_only_once_all_posts_booked_then_409(client: AsyncClient) -> None:
    service_id = await make_service(client, duration_minutes=30)
    day = date.today() + timedelta(days=33)
    client_ids: list[int] = []
    car_ids: list[int] = []
    booking_ids: list[int] = []
    try:
        slot = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [service_id], "date": day.isoformat()},
            )
        ).json()[0]

        assigned_posts = set()
        for _ in range(3):  # ровно 3 поста засеяны миграцией
            cl_id, car_id = await make_client_car(client)
            client_ids.append(cl_id)
            car_ids.append(car_id)
            resp = await client.post(
                "/bookings",
                json={
                    "client_id": cl_id,
                    "car_id": car_id,
                    "start_at": slot["start_at"],
                    "service_ids": [service_id],
                },
            )
            assert resp.status_code == 201
            booking_ids.append(resp.json()["id"])
            assigned_posts.add(resp.json()["post_id"])

        assert len(assigned_posts) == 3  # каждой заявке — свой пост, без повторов

        slots_after = await client.get(
            "/bookings/available-slots",
            params={"service_ids": [service_id], "date": day.isoformat()},
        )
        assert slot not in slots_after.json()

        cl_id, car_id = await make_client_car(client)
        client_ids.append(cl_id)
        car_ids.append(car_id)
        fourth = await client.post(
            "/bookings",
            json={
                "client_id": cl_id,
                "car_id": car_id,
                "start_at": slot["start_at"],
                "service_ids": [service_id],
            },
        )
        assert fourth.status_code == 409
    finally:
        await cleanup(
            client,
            booking_ids=booking_ids,
            car_ids=car_ids,
            client_ids=client_ids,
            service_id=service_id,
        )


@pytest.mark.asyncio
async def test_concurrent_bookings_on_same_slot_exactly_three_succeed(client: AsyncClient) -> None:
    # 4 одновременных запроса на один и тот же момент времени, но только
    # 3 поста — ожидаем ровно три 201 (на три разных поста) и один 409.
    service_id = await make_service(client, duration_minutes=30)
    day = date.today() + timedelta(days=34)
    client_ids: list[int] = []
    car_ids: list[int] = []
    booking_ids: list[int] = []
    try:
        slot = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [service_id], "date": day.isoformat()},
            )
        ).json()[0]

        payloads = []
        for _ in range(4):
            cl_id, car_id = await make_client_car(client)
            client_ids.append(cl_id)
            car_ids.append(car_id)
            payloads.append(
                {
                    "client_id": cl_id,
                    "car_id": car_id,
                    "start_at": slot["start_at"],
                    "service_ids": [service_id],
                }
            )

        responses = await asyncio.gather(*(client.post("/bookings", json=p) for p in payloads))
        codes = [r.status_code for r in responses]
        print(f"\nЧетыре одновременных запроса на 3 поста -> статусы: {codes}")
        for i, r in enumerate(responses, start=1):
            print(f"  запрос {i}: {r.status_code} {r.json()}")

        assert sorted(codes) == [201, 201, 201, 409]

        succeeded = [r.json() for r in responses if r.status_code == 201]
        booking_ids = [b["id"] for b in succeeded]
        assert len({b["post_id"] for b in succeeded}) == 3  # без повторного назначения поста
    finally:
        await cleanup(
            client,
            booking_ids=booking_ids,
            car_ids=car_ids,
            client_ids=client_ids,
            service_id=service_id,
        )


@pytest.mark.asyncio
async def test_slots_available_right_up_to_midnight(client: AsyncClient) -> None:
    # Баг, найденный при разборе логики: сутки считались изолированно, и
    # слоты, чей конец уходит за полночь, пропадали — хотя станция 24/7 и
    # ничего не мешает начать обслуживание в 23:30 и закончить после полуночи.
    service_id = await make_service(client, duration_minutes=45)
    day = date.today() + timedelta(days=40)
    try:
        resp = await client.get(
            "/bookings/available-slots",
            params={"service_ids": [service_id], "date": day.isoformat()},
        )
        starts = {s["start_at"] for s in resp.json()}
        assert f"{day.isoformat()}T23:15:00Z" in starts
        assert f"{day.isoformat()}T23:30:00Z" in starts  # раньше пропадал
        assert f"{day.isoformat()}T23:45:00Z" in starts  # раньше пропадал
    finally:
        await cleanup(client, service_id=service_id)


@pytest.mark.asyncio
async def test_service_longer_than_a_day_is_bookable(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client, duration_minutes=25 * 60)  # 25 часов
    day = date.today() + timedelta(days=41)
    booking_id = None
    try:
        slots = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [service_id], "date": day.isoformat()},
            )
        ).json()
        assert len(slots) > 0

        create_resp = await client.post(
            "/bookings",
            json={
                "client_id": client_id,
                "car_id": car_id,
                "start_at": slots[0]["start_at"],
                "service_ids": [service_id],
            },
        )
        assert create_resp.status_code == 201
        booking_id = create_resp.json()["id"]
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_cannot_book_in_the_past(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client, duration_minutes=30)
    try:
        past = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=365)
        past_on_grid = past.replace(minute=(past.minute // 15) * 15, second=0)
        resp = await client.post(
            "/bookings",
            json={
                "client_id": client_id,
                "car_id": car_id,
                "start_at": past_on_grid.isoformat(),
                "service_ids": [service_id],
            },
        )
        assert resp.status_code == 422
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_start_at_must_be_on_the_15_minute_grid(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client, duration_minutes=30)
    day = date.today() + timedelta(days=42)
    try:
        resp = await client.post(
            "/bookings",
            json={
                "client_id": client_id,
                "car_id": car_id,
                "start_at": f"{day.isoformat()}T09:07:00Z",  # не кратно 15 минутам
                "service_ids": [service_id],
            },
        )
        assert resp.status_code == 422
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_cannot_book_someone_elses_car(client: AsyncClient) -> None:
    # Баг, найденный при разборе логики: create_booking проверял, что car_id
    # существует, но не что он принадлежит именно этому клиенту.
    owner_id, car_id = await make_client_car(client)
    other_client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "Другой клиент"}
    )
    other_client_id = other_client_resp.json()["id"]
    service_id = await make_service(client, duration_minutes=30)
    day = date.today() + timedelta(days=43)
    try:
        slot = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [service_id], "date": day.isoformat()},
            )
        ).json()[0]

        resp = await client.post(
            "/bookings",
            json={
                "client_id": other_client_id,  # не владелец машины
                "car_id": car_id,
                "start_at": slot["start_at"],
                "service_ids": [service_id],
            },
        )
        assert resp.status_code == 403
    finally:
        await cleanup(
            client,
            car_id=car_id,
            client_ids=[owner_id, other_client_id],
            service_id=service_id,
        )


@pytest.mark.asyncio
async def test_service_with_non_positive_duration_or_price_rejected(client: AsyncClient) -> None:
    resp = await client.post(
        "/catalog", json={"name": f"Bad {uuid4().hex}", "duration_minutes": 0, "price": "10.00"}
    )
    assert resp.status_code == 422

    resp = await client.post(
        "/catalog", json={"name": f"Bad {uuid4().hex}", "duration_minutes": 30, "price": "0.00"}
    )
    assert resp.status_code == 422

    resp = await client.post(
        "/catalog", json={"name": f"Bad {uuid4().hex}", "duration_minutes": -10, "price": "10.00"}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_same_car_two_non_overlapping_times_both_succeed(client: AsyncClient) -> None:
    # Регрессия на аудите: блокировка строки авто (FOR UPDATE) сериализует
    # конкурентные попытки, но не должна ошибочно блокировать легитимные
    # заявки той же машины на РАЗНОЕ время.
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client, duration_minutes=30)
    day = date.today() + timedelta(days=44)
    booking_ids: list[int] = []
    try:
        slots = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [service_id], "date": day.isoformat()},
            )
        ).json()
        first_slot, second_slot = slots[0], slots[-1]
        assert first_slot["start_at"] != second_slot["start_at"]

        for slot in (first_slot, second_slot):
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
            booking_ids.append(resp.json()["id"])
    finally:
        await cleanup(
            client, booking_ids=booking_ids, car_id=car_id, client_id=client_id, service_id=service_id
        )


@pytest.mark.asyncio
async def test_booking_with_empty_service_ids_rejected(client: AsyncClient) -> None:
    client_id, car_id = await make_client_car(client)
    day = date.today() + timedelta(days=45)
    try:
        resp = await client.post(
            "/bookings",
            json={
                "client_id": client_id,
                "car_id": car_id,
                "start_at": f"{day.isoformat()}T09:00:00Z",
                "service_ids": [],
            },
        )
        assert resp.status_code == 422
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id)


async def make_booking(client: AsyncClient, days_offset: int) -> tuple[int, int, int, int]:
    client_id, car_id = await make_client_car(client)
    service_id = await make_service(client, duration_minutes=30)
    day = date.today() + timedelta(days=days_offset)
    slot = (
        await client.get(
            "/bookings/available-slots",
            params={"service_ids": [service_id], "date": day.isoformat()},
        )
    ).json()[0]
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
    return client_id, car_id, service_id, resp.json()["id"]


@pytest.mark.asyncio
async def test_status_happy_path_through_awaiting_approval(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 50)
    try:
        for target in ("on_post", "awaiting_approval", "ready", "issued"):
            resp = await client.post(f"/bookings/{booking_id}/status", json={"status": target})
            assert resp.status_code == 200, resp.json()
            assert resp.json()["status"] == target
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_status_happy_path_skipping_approval(client: AsyncClient) -> None:
    # awaiting_approval — развилка, а не обязательная стадия.
    client_id, car_id, service_id, booking_id = await make_booking(client, 51)
    try:
        for target in ("on_post", "ready", "issued"):
            resp = await client.post(f"/bookings/{booking_id}/status", json={"status": target})
            assert resp.status_code == 200
            assert resp.json()["status"] == target
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_status_invalid_transitions_rejected(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 52)
    try:
        # Пропуск стадии: accepted -> ready напрямую.
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "ready"})
        assert resp.status_code == 409

        # Переводим в on_post легитимно, затем пробуем откатить назад и повторить.
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "accepted"})
        assert resp.status_code == 409  # откат назад

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 409  # повтор того же перехода
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_status_nonexistent_booking_returns_404(client: AsyncClient) -> None:
    resp = await client.post("/bookings/999999999/status", json={"status": "on_post"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_status_concurrent_same_transition_only_one_succeeds(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 53)
    try:
        responses = await asyncio.gather(
            client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"}),
            client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"}),
        )
        codes = [r.status_code for r in responses]
        print(f"\nДва одновременных перехода accepted->on_post -> статусы: {codes}")
        for i, r in enumerate(responses, start=1):
            print(f"  запрос {i}: {r.status_code} {r.json()}")
        assert sorted(codes) == [200, 409]  # применился ровно один переход

        final = await client.get(f"/bookings/{booking_id}")
        assert final.json()["status"] == "on_post"  # не откатилось и не сломалось
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)
