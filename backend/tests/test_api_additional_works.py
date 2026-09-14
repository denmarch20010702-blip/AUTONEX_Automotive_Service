from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


async def make_booking(client: AsyncClient, days_offset: int) -> tuple[int, int, int, int]:
    client_resp = await client.post(
        "/clients", json={"email": unique_email(), "name": "AW Tester"}
    )
    client_id = client_resp.json()["id"]
    car_resp = await client.post(
        "/cars", json={"client_id": client_id, "make": "Honda", "model": "Civic"}
    )
    car_id = car_resp.json()["id"]
    service_resp = await client.post(
        "/catalog", json={"name": f"AW Service {uuid4().hex[:8]}", "duration_minutes": 30, "price": "500.00"}
    )
    service_id = service_resp.json()["id"]
    day = date.today() + timedelta(days=days_offset)
    window_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat()
    slot = (
        await client.get(
            "/bookings/available-slots",
            params={"service_ids": [service_id], "date": window_start},
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
    return client_id, car_id, service_id, booking_resp.json()["id"]


async def make_extra_service(client: AsyncClient, *, price: str = "1000.00", duration_minutes: int = 15) -> int:
    # UI_description.md п.19: доп. работа теперь предлагается выбором из
    # каталога услуг, а не свободным текстом — тестам нужна услуга-кандидат.
    resp = await client.post(
        "/catalog",
        json={"name": f"Extra {uuid4().hex[:8]}", "duration_minutes": duration_minutes, "price": price},
    )
    return resp.json()["id"]


async def propose(client: AsyncClient, booking_id: int, service_id: int):
    return await client.post(
        f"/bookings/{booking_id}/additional-works", json={"service_id": service_id}
    )


async def cleanup(
    client: AsyncClient,
    *,
    booking_id: int,
    car_id: int,
    client_id: int,
    service_id: int,
    extra_service_ids: list[int] | None = None,
) -> None:
    from sqlalchemy import delete as sa_delete

    from app.db.session import async_session
    from app.models import AdditionalWork, Booking

    async with async_session() as session:
        await session.execute(sa_delete(AdditionalWork).where(AdditionalWork.booking_id == booking_id))
        booking = await session.get(Booking, booking_id)
        if booking is not None:
            await session.delete(booking)
        await session.commit()
    await client.delete(f"/cars/{car_id}")
    await client.delete(f"/clients/{client_id}")
    await client.delete(f"/catalog/{service_id}")
    for extra_id in extra_service_ids or []:
        await client.delete(f"/catalog/{extra_id}")


@pytest.mark.asyncio
async def test_propose_and_approve_additional_work(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 300)
    extra_id = await make_extra_service(client, price="1500.00", duration_minutes=20)
    try:
        resp = await propose(client, booking_id, extra_id)
        assert resp.status_code == 201
        work = resp.json()
        assert work["status"] == "pending"
        assert work["proposed_by"] == "mechanic"
        assert work["price"] == "1500.00"
        assert work["duration_minutes"] == 20
        work_id = work["id"]

        resp = await client.get(f"/bookings/{booking_id}/additional-works")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp = await client.post(f"/additional-works/{work_id}/respond", json={"status": "approved"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"
    finally:
        await cleanup(
            client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id,
            extra_service_ids=[extra_id],
        )


@pytest.mark.asyncio
async def test_decline_additional_work(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 301)
    extra_id = await make_extra_service(client)
    try:
        resp = await propose(client, booking_id, extra_id)
        work_id = resp.json()["id"]

        resp = await client.post(f"/additional-works/{work_id}/respond", json={"status": "declined"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "declined"
    finally:
        await cleanup(
            client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id,
            extra_service_ids=[extra_id],
        )


@pytest.mark.asyncio
async def test_cannot_respond_twice(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 302)
    extra_id = await make_extra_service(client)
    try:
        resp = await propose(client, booking_id, extra_id)
        work_id = resp.json()["id"]

        resp = await client.post(f"/additional-works/{work_id}/respond", json={"status": "approved"})
        assert resp.status_code == 200

        resp = await client.post(f"/additional-works/{work_id}/respond", json={"status": "declined"})
        assert resp.status_code == 409
    finally:
        await cleanup(
            client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id,
            extra_service_ids=[extra_id],
        )


@pytest.mark.asyncio
async def test_awaiting_approval_requires_a_real_pending_work(client: AsyncClient) -> None:
    # UI_description.md п.13 (2026-09-13): раньше станция могла вручную
    # выставить "ожидает согласования" без единого реального предложения —
    # непонятная, ничего не значащая пометка. Теперь это запрещено.
    client_id, car_id, service_id, booking_id = await make_booking(client, 304)
    try:
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200

        resp = await client.post(
            f"/bookings/{booking_id}/status", json={"status": "awaiting_approval"}
        )
        assert resp.status_code == 409
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_last_response_all_declined_moves_straight_to_ready(client: AsyncClient) -> None:
    # UI_description.md п.13: как только клиент ответил на ПОСЛЕДНЕЕ
    # неотвеченное предложение — заявка сама переходит дальше, без ручного
    # клика станции. Если всё отклонено — делать больше нечего, сразу "готова".
    client_id, car_id, service_id, booking_id = await make_booking(client, 305)
    extra_a = await make_extra_service(client, price="100.00")
    extra_b = await make_extra_service(client, price="200.00")
    try:
        await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        work_a = (await propose(client, booking_id, extra_a)).json()
        work_b = (await propose(client, booking_id, extra_b)).json()
        resp = await client.post(
            f"/bookings/{booking_id}/status", json={"status": "awaiting_approval"}
        )
        assert resp.status_code == 200

        await client.post(f"/additional-works/{work_a['id']}/respond", json={"status": "declined"})
        # Осталась ещё одна неотвеченная — заявка не двигается.
        assert (await client.get(f"/bookings/{booking_id}")).json()["status"] == "awaiting_approval"

        await client.post(f"/additional-works/{work_b['id']}/respond", json={"status": "declined"})
        # Это была последняя, и ни одна не одобрена — сразу "готова".
        booking = (await client.get(f"/bookings/{booking_id}")).json()
        assert booking["status"] == "ready"
    finally:
        await cleanup(
            client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id,
            extra_service_ids=[extra_a, extra_b],
        )


@pytest.mark.asyncio
async def test_last_response_with_approval_starts_execution_timer(client: AsyncClient) -> None:
    # UI_description.md п.19: согласованная доп. работа запускает настоящий
    # таймер выполнения (тем же механизмом, что и основная услуга, C2) —
    # заявка возвращается "на пост", а не сразу "готова".
    from app.services.robot_timer import _auto_advance

    client_id, car_id, service_id, booking_id = await make_booking(client, 306)
    extra_a = await make_extra_service(client, price="100.00", duration_minutes=25)
    extra_b = await make_extra_service(client, price="200.00", duration_minutes=10)
    try:
        await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        work_a = (await propose(client, booking_id, extra_a)).json()
        work_b = (await propose(client, booking_id, extra_b)).json()
        await client.post(f"/bookings/{booking_id}/status", json={"status": "awaiting_approval"})

        await client.post(f"/additional-works/{work_a['id']}/respond", json={"status": "approved"})
        await client.post(f"/additional-works/{work_b['id']}/respond", json={"status": "declined"})

        booking = (await client.get(f"/bookings/{booking_id}")).json()
        assert booking["status"] == "on_post"
        assert booking["service_ends_at"] is not None
        ends_at = datetime.fromisoformat(booking["service_ends_at"].replace("Z", "+00:00"))
        remaining = (ends_at - datetime.now(timezone.utc)).total_seconds()
        assert 24 * 60 - 5 <= remaining <= 25 * 60  # ~25 минут (только work_a одобрена)

        # Не ждём реальные 25 минут — вызываем ту же функцию, что и
        # планировщик, напрямую (тот же приём, что уже применялся для C2).
        await _auto_advance(booking_id)
        booking = (await client.get(f"/bookings/{booking_id}")).json()
        assert booking["status"] == "ready"
    finally:
        await cleanup(
            client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id,
            extra_service_ids=[extra_a, extra_b],
        )


@pytest.mark.asyncio
async def test_approval_after_main_service_already_ready_still_starts_timer(client: AsyncClient) -> None:
    # UI_description.md п.20/25 (2026-09-14): реальный найденный баг —
    # если доп. работу предлагали и одобряли ПОСЛЕ того, как основная
    # услуга уже завершилась (заявка уже 'ready'), таймер выполнения
    # никогда не запускался — работа считалась выполненной просто по факту
    # одобрения, без реальной отработки.
    from app.services.robot_timer import _auto_advance

    client_id, car_id, service_id, booking_id = await make_booking(client, 309)
    extra_id = await make_extra_service(client, price="300.00", duration_minutes=12)
    try:
        for status in ("on_post", "ready"):
            resp = await client.post(f"/bookings/{booking_id}/status", json={"status": status})
            assert resp.status_code == 200

        # Основная услуга уже готова — только теперь предлагаем доп. работу.
        work = (await propose(client, booking_id, extra_id)).json()
        resp = await client.post(f"/additional-works/{work['id']}/respond", json={"status": "approved"})
        assert resp.status_code == 200

        booking = (await client.get(f"/bookings/{booking_id}")).json()
        assert booking["status"] == "on_post"  # раньше здесь оставалось "ready"
        assert booking["service_ends_at"] is not None

        await _auto_advance(booking_id)
        booking = (await client.get(f"/bookings/{booking_id}")).json()
        assert booking["status"] == "ready"
    finally:
        await cleanup(
            client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id,
            extra_service_ids=[extra_id],
        )


@pytest.mark.asyncio
async def test_pending_count_drops_after_response(client: AsyncClient) -> None:
    # UI_description.md п.17: красная точка у "Личный кабинет" держится на
    # этом счётчике — должен расти при новом предложении и падать до 0
    # после ответа клиента.
    client_id, car_id, service_id, booking_id = await make_booking(client, 308)
    extra_id = await make_extra_service(client)
    try:
        count = (await client.get(f"/clients/{client_id}/additional-works/pending-count")).json()
        assert count["count"] == 0

        work = (await propose(client, booking_id, extra_id)).json()
        count = (await client.get(f"/clients/{client_id}/additional-works/pending-count")).json()
        assert count["count"] == 1

        await client.post(f"/additional-works/{work['id']}/respond", json={"status": "declined"})
        count = (await client.get(f"/clients/{client_id}/additional-works/pending-count")).json()
        assert count["count"] == 0
    finally:
        await cleanup(
            client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id,
            extra_service_ids=[extra_id],
        )


@pytest.mark.asyncio
async def test_propose_for_nonexistent_booking_returns_404(client: AsyncClient) -> None:
    resp = await client.post(
        "/bookings/999999999/additional-works",
        json={"service_id": 1},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_propose_with_nonexistent_service_returns_404(client: AsyncClient) -> None:
    client_id, car_id, service_id, booking_id = await make_booking(client, 307)
    try:
        resp = await propose(client, booking_id, 999999999)
        assert resp.status_code == 404
    finally:
        await cleanup(client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id)


@pytest.mark.asyncio
async def test_respond_to_nonexistent_work_returns_404(client: AsyncClient) -> None:
    resp = await client.post("/additional-works/999999999/respond", json={"status": "approved"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancelling_booking_with_additional_work_does_not_crash(client: AsyncClient) -> None:
    # Регресс-тест на реальный найденный баг (2026-09-13): additional_works
    # имеет FK на bookings без каскада — отмена/выдача заявки с хотя бы
    # одной доп. работой падала 500 (IntegrityError) вместо обычной
    # архивации. Проверяем оба терминальных статуса и то, что снимок доп.
    # работ сохраняется в журнале, а не молча теряется.
    client_id, car_id, service_id, booking_id = await make_booking(client, 303)
    extra_id = await make_extra_service(client, price="700.00")
    try:
        resp = await propose(client, booking_id, extra_id)
        assert resp.status_code == 201
        work_id = resp.json()["id"]
        await client.post(f"/additional-works/{work_id}/respond", json={"status": "approved"})

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "cancelled"})
        assert resp.status_code == 200  # раньше здесь был 500

        archive = await client.get("/station/archive", params={"client_id": client_id})
        entries = archive.json()
        assert len(entries) == 1
        snapshot = entries[0]["additional_works_snapshot"]
        assert len(snapshot) == 1
        assert snapshot[0]["status"] == "approved"
    finally:
        from app.db.session import async_session
        from app.models import BookingArchive

        async with async_session() as session:
            entry = (
                await session.execute(
                    select(BookingArchive).where(BookingArchive.original_booking_id == booking_id)
                )
            ).scalar_one_or_none()
            if entry is not None:
                await session.delete(entry)
                await session.commit()
        await client.delete(f"/cars/{car_id}")
        await client.delete(f"/clients/{client_id}")
        await client.delete(f"/catalog/{service_id}")
        await client.delete(f"/catalog/{extra_id}")
