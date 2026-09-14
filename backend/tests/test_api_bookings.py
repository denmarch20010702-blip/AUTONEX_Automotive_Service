import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.db.session import async_session
from app.models import Booking


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


def day_start_iso(day: date) -> str:
    # `/bookings/available-slots?date=` теперь ждёт точный момент со
    # смещением часового пояса, а не голую календарную дату — иначе backend
    # не может понять, что для клиента значит "начало суток" (обнаружено на
    # практике 2026-09-13: UTC-интерпретация рвала выдачу слотов на границе
    # часовых поясов). Тестам сам часовой пояс не важен — берём UTC.
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat()


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


async def refund_revenue(amount) -> None:
    # Тесты, доводящие заявку до "issued", необратимо прибавляют деньги в
    # общий (не изолированный per-test) счётчик станции — иначе прогон
    # автотестов постепенно "накручивал" бы реальную выручку на dev-БД.
    # Возвращаем добавленное обратно в finally каждого такого теста.
    from app.models import STATION_STATS_ROW_ID, StationStats
    from sqlalchemy import update

    async with async_session() as session:
        await session.execute(
            update(StationStats)
            .where(StationStats.id == STATION_STATS_ROW_ID)
            .values(total_revenue=StationStats.total_revenue - amount)
        )
        await session.commit()


async def delete_archive_entry(original_booking_id: int) -> None:
    # issued/cancelled теперь архивируют заявку вместо (или вместе с)
    # удаления — тестовые записи в журнале тоже нужно убирать за собой,
    # иначе BookingArchive будет бесконечно расти при каждом прогоне тестов.
    from app.models import BookingArchive
    from sqlalchemy import delete as sa_delete

    async with async_session() as session:
        await session.execute(
            sa_delete(BookingArchive).where(
                BookingArchive.original_booking_id == original_booking_id
            )
        )
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
            params={"service_ids": [service_id], "date": day_start_iso(day)},
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
                params={"service_ids": [service_id], "date": day_start_iso(day)},
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
                params={"service_ids": [service_id], "date": day_start_iso(day)},
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
                params={"service_ids": [service_id], "date": day_start_iso(day)},
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
                params={"service_ids": [service_id], "date": day_start_iso(day)},
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
            params={"service_ids": [service_id], "date": day_start_iso(day)},
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
                params={"service_ids": [service_id], "date": day_start_iso(day)},
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
            params={"service_ids": [service_id], "date": day_start_iso(day)},
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
                params={"service_ids": [service_id], "date": day_start_iso(day)},
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
                params={"service_ids": [service_id], "date": day_start_iso(day)},
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
                params={"service_ids": [service_id], "date": day_start_iso(day)},
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
            params={"service_ids": [service_id], "date": day_start_iso(day)},
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
    # UI_description.md п.13 (2026-09-13): "ожидает согласования" теперь
    # осмысленный статус, а не свободно выставляемая станцией пометка — в
    # него можно войти вручную только при реальном неотвеченном предложении
    # доп. работы, и из него нельзя выйти, пока клиент не ответил (кроме
    # отмены).
    from app.services.robot_timer import _auto_advance

    client_id, car_id, service_id, booking_id = await make_booking(client, 50)
    extra_resp = await client.post(
        "/catalog", json={"name": f"Extra {uuid4().hex[:8]}", "duration_minutes": 15, "price": "900.00"}
    )
    extra_id = extra_resp.json()["id"]
    try:
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200

        resp = await client.post(
            f"/bookings/{booking_id}/additional-works",
            json={"service_id": extra_id},
        )
        work_id = resp.json()["id"]

        resp = await client.post(
            f"/bookings/{booking_id}/status", json={"status": "awaiting_approval"}
        )
        assert resp.status_code == 200, resp.json()

        # Пока клиент не ответил — дальше статус не двигается.
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "ready"})
        assert resp.status_code == 409

        # Ответ клиента на последнее неотвеченное предложение сам двигает
        # заявку дальше (UI_description.md п.13) — станции не нужно вручную
        # жать "готово" после этого. Согласованная доп. работа запускает
        # настоящий таймер выполнения (п.19) — заявка возвращается "на
        # пост", а не сразу "готова".
        resp = await client.post(f"/additional-works/{work_id}/respond", json={"status": "approved"})
        assert resp.status_code == 200

        resp = await client.get(f"/bookings/{booking_id}")
        assert resp.json()["status"] == "on_post"
        assert resp.json()["service_ends_at"] is not None

        # Не ждём реальные 15 минут — вызываем ту же функцию, что и
        # планировщик (тот же приём, что уже применялся для C2/B2).
        await _auto_advance(booking_id)
        resp = await client.get(f"/bookings/{booking_id}")
        assert resp.json()["status"] == "ready"

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "issued"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "issued"
    finally:
        # "issued" архивирует заявку (удаляет из активной таблицы, кладёт в
        # BookingArchive) и прибавляет её стоимость в общий счётчик станции —
        # cleanup(booking_id=...) безопасен на уже удалённой заявке, а
        # выручку и запись журнала убираем, чтобы прогон теста не оставлял
        # следов в реальном dev-БД. Выручка теперь включает и одобренную
        # доп. работу (500 за услугу + 900 за доп. работу, UI_description.md
        # п.14).
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)
        await client.delete(f"/catalog/{extra_id}")
        await refund_revenue(Decimal("1400.00"))
        await delete_archive_entry(booking_id)


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
        await refund_revenue(Decimal("500.00"))
        await delete_archive_entry(booking_id)


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
async def test_cancel_from_accepted_frees_the_slot(client: AsyncClient) -> None:
    # B4, перенесено вперёд: клиент отменяет заявку прямо из "accepted" —
    # слот должен тут же снова стать доступным (проверки занятости уже
    # исключают CANCELLED, отдельного "освобождения" делать не нужно).
    client_id, car_id, service_id, booking_id = await make_booking(client, 53)
    original = (await client.get(f"/bookings/{booking_id}")).json()
    rebooked_id = None
    try:
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "cancelled"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

        # Отменённая заявка архивируется и убирается из активной таблицы —
        # дальнейший запрос статуса получает 404, а не 409 (её физически
        # больше нет в bookings, только в BookingArchive).
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "accepted"})
        assert resp.status_code == 404

        # Тот же автомобиль на то же самое время снова бронируется без
        # конфликта — и car_is_free, и занятость поста уже игнорируют
        # CANCELLED-заявки, отдельно "освобождать" ничего не пришлось.
        resp = await client.post(
            "/bookings",
            json={
                "client_id": client_id,
                "car_id": car_id,
                "start_at": original["start_at"],
                "service_ids": [service_id],
            },
        )
        assert resp.status_code == 201
        rebooked_id = resp.json()["id"]
    finally:
        await cleanup(
            client,
            booking_ids=[booking_id] + ([rebooked_id] if rebooked_id else []),
            car_id=car_id,
            client_id=client_id,
            service_id=service_id,
        )
        await delete_archive_entry(booking_id)


@pytest.mark.asyncio
async def test_cancel_allowed_from_on_post_and_awaiting_approval(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 54)
    try:
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200

        # Вход в "ожидает согласования" требует реального неотвеченного
        # предложения доп. работы (UI_description.md п.13) — само предложение
        # намеренно оставляем без ответа, чтобы проверить именно отмену из
        # этого статуса, а не автопродвижение дальше.
        await client.post(
            f"/bookings/{booking_id}/additional-works",
            json={"service_id": service_id},
        )
        resp = await client.post(
            f"/bookings/{booking_id}/status", json={"status": "awaiting_approval"}
        )
        assert resp.status_code == 200

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "cancelled"})
        assert resp.status_code == 200
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)
        await delete_archive_entry(booking_id)


@pytest.mark.asyncio
async def test_cancel_not_allowed_from_issued(client: AsyncClient) -> None:
    # "issued" — полное завершение заявки: она удаляется из БД по прямой
    # просьбе пользователя (см. test_issued_deletes_booking_and_credits_revenue
    # ниже), поэтому дальнейший запрос статуса получает 404, а не 409 —
    # заявки для отмены уже физически не существует.
    client_id, car_id, service_id, booking_id = await make_booking(client, 55)
    try:
        for status in ("on_post", "ready", "issued"):
            resp = await client.post(f"/bookings/{booking_id}/status", json={"status": status})
            assert resp.status_code == 200

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "cancelled"})
        assert resp.status_code == 404
    finally:
        # booking_id уже архивирован/удалён самим переходом в issued —
        # cleanup безопасен (delete_booking проверяет существование перед
        # удалением). Переход в issued также прибавил 500.00 в общий
        # счётчик станции и создал запись в журнале — возвращаем/убираем.
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)
        await refund_revenue(Decimal("500.00"))
        await delete_archive_entry(booking_id)


@pytest.mark.asyncio
async def test_issued_archives_booking_and_credits_revenue(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 56)
    try:
        stats_before = (await client.get("/station/stats")).json()

        for status in ("on_post", "ready"):
            resp = await client.post(f"/bookings/{booking_id}/status", json={"status": status})
            assert resp.status_code == 200

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "issued"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "issued"

        # Полностью завершённая заявка исчезает из активной таблицы — не
        # просто меняет статус.
        resp = await client.get(f"/bookings/{booking_id}")
        assert resp.status_code == 404

        # ...но остаётся в журнале для просмотра при необходимости.
        archive_resp = await client.get("/station/archive", params={"client_id": client_id})
        assert archive_resp.status_code == 200
        entries = archive_resp.json()
        assert len(entries) == 1
        assert entries[0]["original_booking_id"] == booking_id
        assert entries[0]["status"] == "issued"
        assert Decimal(entries[0]["total_price"]) == Decimal("500.00")
        assert entries[0]["services_snapshot"][0]["name"].startswith("Услуга ")

        stats_after = (await client.get("/station/stats")).json()
        delta = Decimal(stats_after["total_revenue"]) - Decimal(stats_before["total_revenue"])
        assert delta == Decimal("500.00")  # цена услуги из make_service()
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id, service_id=service_id)
        await refund_revenue(Decimal("500.00"))
        await delete_archive_entry(booking_id)


@pytest.mark.asyncio
async def test_issued_updates_car_last_service_date(client: AsyncClient) -> None:
    # UI_description.md п.31 (2026-09-14): дата последнего обслуживания
    # машины должна сама обновляться на дату, когда обслуживание реально
    # прошло, а не оставаться пустой/старой после выдачи.
    client_id, car_id, service_id, booking_id = await make_booking(client, 60)
    try:
        car_before = (await client.get(f"/cars/{car_id}")).json()
        assert car_before["last_service_date"] is None

        for status in ("on_post", "ready", "issued"):
            resp = await client.post(f"/bookings/{booking_id}/status", json={"status": status})
            assert resp.status_code == 200

        car_after = (await client.get(f"/cars/{car_id}")).json()
        assert car_after["last_service_date"] == date.today().isoformat()
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id, service_id=service_id)
        await refund_revenue(Decimal("500.00"))
        await delete_archive_entry(booking_id)


@pytest.mark.asyncio
async def test_approved_additional_work_credited_only_on_issue(client: AsyncClient) -> None:
    # UI_description.md п.14 (2026-09-13): деньги за согласованную доп.
    # работу начисляются только при сдаче (issued), сверх суммы изначальной
    # услуги — не в момент согласования и не для отклонённых.
    from app.services.robot_timer import _auto_advance

    client_id, car_id, service_id, booking_id = await make_booking(client, 57)
    extra_approved = (
        await client.post(
            "/catalog", json={"name": f"Свечи {uuid4().hex[:8]}", "duration_minutes": 10, "price": "600.00"}
        )
    ).json()["id"]
    extra_declined = (
        await client.post(
            "/catalog", json={"name": f"Тюнинг {uuid4().hex[:8]}", "duration_minutes": 10, "price": "10000.00"}
        )
    ).json()["id"]
    try:
        stats_before = (await client.get("/station/stats")).json()

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200

        approved = (
            await client.post(
                f"/bookings/{booking_id}/additional-works",
                json={"service_id": extra_approved},
            )
        ).json()
        declined = (
            await client.post(
                f"/bookings/{booking_id}/additional-works",
                json={"service_id": extra_declined},
            )
        ).json()

        resp = await client.post(
            f"/bookings/{booking_id}/status", json={"status": "awaiting_approval"}
        )
        assert resp.status_code == 200

        # Ответ на "declined" не последний pending (approved ещё висит) —
        # заявка остаётся awaiting_approval, деньги ещё не начислены.
        await client.post(f"/additional-works/{declined['id']}/respond", json={"status": "declined"})
        stats_mid = (await client.get("/station/stats")).json()
        assert stats_mid["total_revenue"] == stats_before["total_revenue"]

        # Ответ на последнее pending-предложение сам доводит заявку дальше
        # (п.13) — но т.к. работа одобрена, дальше значит "на пост" на
        # длительность этой работы (п.19), не сразу "готова". Выручка всё
        # ещё не начислена — это происходит только при выдаче.
        resp = await client.post(
            f"/additional-works/{approved['id']}/respond", json={"status": "approved"}
        )
        assert resp.status_code == 200
        assert (await client.get(f"/bookings/{booking_id}")).json()["status"] == "on_post"
        stats_mid2 = (await client.get("/station/stats")).json()
        assert stats_mid2["total_revenue"] == stats_before["total_revenue"]

        await _auto_advance(booking_id)
        assert (await client.get(f"/bookings/{booking_id}")).json()["status"] == "ready"

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "issued"})
        assert resp.status_code == 200

        archive = (
            await client.get("/station/archive", params={"client_id": client_id})
        ).json()
        # Услуга (500.00) + одобренная доп. работа (600.00), отклонённая
        # (10000.00) в сумму не входит.
        assert Decimal(archive[0]["total_price"]) == Decimal("1100.00")

        stats_after = (await client.get("/station/stats")).json()
        delta = Decimal(stats_after["total_revenue"]) - Decimal(stats_before["total_revenue"])
        assert delta == Decimal("1100.00")
    finally:
        await cleanup(client, car_id=car_id, client_id=client_id, service_id=service_id)
        await client.delete(f"/catalog/{extra_approved}")
        await client.delete(f"/catalog/{extra_declined}")
        await refund_revenue(Decimal("1100.00"))
        await delete_archive_entry(booking_id)


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


@pytest.mark.asyncio
async def test_concurrent_cancel_vs_advance_never_corrupts_state(client: AsyncClient) -> None:
    # B8: "гонка при одновременном переносе/отмене". Клиент отменяет, станция
    # одновременно продвигает on_post -> ready. Оба перехода по отдельности
    # легитимны (ready тоже допускает cancelled), поэтому здесь НЕТ единого
    # правильного исхода — итог зависит от того, чья транзакция закоммитится
    # первой (обнаружено на практике 2026-09-13, воспроизводится не всегда).
    # Инвариант, который должен держаться всегда: ни одного 500/неожиданного
    # кода, и заявка в итоге архивируется ровно один раз со статусом, который
    # реально был последним применённым переходом.
    client_id, car_id, service_id, booking_id = await make_booking(client, 57)
    try:
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200

        cancel_resp, ready_resp = await asyncio.gather(
            client.post(f"/bookings/{booking_id}/status", json={"status": "cancelled"}),
            client.post(f"/bookings/{booking_id}/status", json={"status": "ready"}),
        )
        codes = sorted([cancel_resp.status_code, ready_resp.status_code])
        # Либо отмена прошла первой (второй запрос находит заявку уже
        # архивированной -> 404), либо ready прошёл первой, а отмена —
        # вторым легитимным переходом уже из ready (оба 200).
        assert codes in ([200, 404], [200, 200])

        archive = await client.get("/station/archive", params={"client_id": client_id})
        entries = archive.json()
        assert len(entries) == 1  # заархивирована ровно один раз, не дважды
        # Финальный статус в архиве всегда совпадает с тем запросом, который
        # реально закоммитился последним (то есть вернул 200 последним по
        # порядку выполнения на сервере) — здесь просто проверяем, что это
        # один из двух ожидаемых статусов, без падения/рассинхрона.
        assert entries[0]["status"] in ("cancelled", "ready")
    finally:
        # Ни cancelled, ни ready не начисляют выручку — refund_revenue не нужен.
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)
        await delete_archive_entry(booking_id)


@pytest.mark.asyncio
async def test_concurrent_double_issue_credits_revenue_exactly_once(client: AsyncClient) -> None:
    # B8: двойной клик "Выдать" на станции не должен задвоить выручку —
    # FOR UPDATE должен сериализовать так, что второй запрос либо получает
    # 404 (заявка уже архивирована и удалена первым), но никогда не 200
    # дважды и никогда не начисляет revenue дважды.
    client_id, car_id, service_id, booking_id = await make_booking(client, 58)
    try:
        for status in ("on_post", "ready"):
            resp = await client.post(f"/bookings/{booking_id}/status", json={"status": status})
            assert resp.status_code == 200

        stats_before = (await client.get("/station/stats")).json()

        r1, r2 = await asyncio.gather(
            client.post(f"/bookings/{booking_id}/status", json={"status": "issued"}),
            client.post(f"/bookings/{booking_id}/status", json={"status": "issued"}),
        )
        codes = sorted([r1.status_code, r2.status_code])
        assert codes == [200, 404]  # ровно один успех, второй — уже нет заявки

        stats_after = (await client.get("/station/stats")).json()
        delta = Decimal(stats_after["total_revenue"]) - Decimal(stats_before["total_revenue"])
        assert delta == Decimal("500.00")  # не задвоилось до 1000.00
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)
        await refund_revenue(Decimal("500.00"))
        await delete_archive_entry(booking_id)


@pytest.mark.asyncio
async def test_reschedule_moves_booking_to_new_slot(client: AsyncClient) -> None:
    # B4: перенос вместо отмены+повторной записи — тот же набор услуг и
    # машина, новое время.
    client_id, car_id, service_id, booking_id = await make_booking(client, 59)
    try:
        new_day = date.today() + timedelta(days=60)
        new_slot = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [service_id], "date": day_start_iso(new_day)},
            )
        ).json()[0]

        resp = await client.post(
            f"/bookings/{booking_id}/reschedule", json={"start_at": new_slot["start_at"]}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["start_at"] == new_slot["start_at"]
        assert body["status"] == "accepted"

        # Старое время реально свободно — можно записать туда другую машину.
        old_day = date.today() + timedelta(days=59)
        old_slots = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [service_id], "date": day_start_iso(old_day)},
            )
        ).json()
        assert len(old_slots) > 0
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_reschedule_excludes_own_old_slot_from_car_conflict(client: AsyncClient) -> None:
    # exclude_booking_id должен позволять "перенести" заявку на СВОЁ же
    # текущее время (например, просто чтобы поменять пост/проверить) без
    # ложного 409 "машина уже записана" от самой себя.
    client_id, car_id, service_id, booking_id = await make_booking(client, 61)
    try:
        booking = (await client.get(f"/bookings/{booking_id}")).json()
        resp = await client.post(
            f"/bookings/{booking_id}/reschedule", json={"start_at": booking["start_at"]}
        )
        assert resp.status_code == 200
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_reschedule_blocked_once_on_post(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 62)
    try:
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200

        new_day = date.today() + timedelta(days=63)
        new_slot = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [service_id], "date": day_start_iso(new_day)},
            )
        ).json()[0]
        resp = await client.post(
            f"/bookings/{booking_id}/reschedule", json={"start_at": new_slot["start_at"]}
        )
        assert resp.status_code == 409
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_reschedule_to_slot_used_by_different_car_succeeds(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 64)
    client_id2, car_id2, service_id2, booking_id2 = await make_booking(client, 65)
    try:
        booking2 = (await client.get(f"/bookings/{booking_id2}")).json()
        resp = await client.post(
            f"/bookings/{booking_id}/reschedule", json={"start_at": booking2["start_at"]}
        )
        # Разные машины/клиенты — конфликта по машине нет, но если это тот
        # же слот и на нём заняты все посты, ожидаем 409 "Все посты заняты".
        # В тестовой конфигурации 3 поста и всего одна другая заявка — слот
        # должен пройти без конфликта.
        assert resp.status_code == 200
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)
        await cleanup(
            client, booking_id=booking_id2, car_id=car_id2, client_id=client_id2, service_id=service_id2
        )


@pytest.mark.asyncio
async def test_reschedule_nonexistent_booking_returns_404(client: AsyncClient) -> None:
    future_day = date.today() + timedelta(days=90)
    grid_aligned = datetime(future_day.year, future_day.month, future_day.day, 9, 0, tzinfo=timezone.utc)
    resp = await client.post(
        "/bookings/999999999/reschedule",
        json={"start_at": grid_aligned.isoformat()},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_station_actionable_count_reflects_bookings_needing_a_decision(client: AsyncClient) -> None:
    # UI_description.md п.22 (2026-09-14): красная точка у "Станция" должна
    # держаться на реальном количестве заявок, ждущих решения station'а
    # (accepted -> принять на пост; ready -> выдать), а не гаснуть просто
    # от захода на страницу.
    client_id, car_id, service_id, booking_id = await make_booking(client, 66)
    try:
        before = (await client.get("/station/actionable-count")).json()["count"]
        assert before >= 1  # свежая заявка в "accepted" уже требует решения

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200
        mid = (await client.get("/station/actionable-count")).json()["count"]
        assert mid == before - 1  # ушла из "accepted", в "ready" ещё не пришла

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "ready"})
        assert resp.status_code == 200
        after = (await client.get("/station/actionable-count")).json()["count"]
        assert after == before  # снова требует решения — теперь "выдать"
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)
