from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from helpers import make_startable_now


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


async def make_booking(client: AsyncClient, days_offset: int) -> tuple[int, int, int, int]:
    # Тот же класс бага, что и в make_booking() в test_reminders.py и
    # test_api_bookings.py (2026-09-14, замечено пользователем — тестовые
    # клиенты/машины/услуги навсегда остаются в живой БД): раньше
    # client_id/car_id/service_id создавались здесь до входа вызывающего
    # теста в его собственный `try`, и если следующий шаг (поиск слота)
    # кидал исключение — уже созданные записи никто не подчищал. Хелпер
    # теперь сам чистит за собой при любой ошибке внутри себя.
    client_id = car_id = service_id = None
    try:
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
        slots = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [service_id], "date": window_start},
            )
        ).json()
        if not slots:
            pytest.skip(f"на день +{days_offset} не осталось свободных слотов — занято живыми данными")
        booking_resp = await client.post(
            "/bookings",
            json={
                "client_id": client_id,
                "car_id": car_id,
                "start_at": slots[0]["start_at"],
                "service_ids": [service_id],
            },
        )
        return client_id, car_id, service_id, booking_resp.json()["id"]
    except BaseException:
        if car_id is not None:
            await client.delete(f"/cars/{car_id}")
        if client_id is not None:
            await client.delete(f"/clients/{client_id}")
        if service_id is not None:
            await client.delete(f"/catalog/{service_id}")
        raise


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
    extra_booking_ids: list[int] | None = None,
) -> None:
    from sqlalchemy import delete as sa_delete

    from app.db.session import async_session
    from app.models import AdditionalWork, Booking

    async with async_session() as session:
        await session.execute(sa_delete(AdditionalWork).where(AdditionalWork.booking_id == booking_id))
        for extra_booking_id in extra_booking_ids or []:
            extra_booking = await session.get(Booking, extra_booking_id)
            if extra_booking is not None:
                await session.delete(extra_booking)
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
        await make_startable_now(booking_id)
        await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
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
        await make_startable_now(booking_id)
        await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
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
        await make_startable_now(booking_id)
        await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
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
        await make_startable_now(booking_id)
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
        await make_startable_now(booking_id)
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
        await make_startable_now(booking_id)
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
        await make_startable_now(booking_id)
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
async def test_execution_timer_extends_occupancy_and_blocks_double_booking(client: AsyncClient) -> None:
    # UI_description.md п.35 (2026-09-14): реальный найденный баг — доп.
    # работа продлевала `service_ends_at`, но не `end_at`, а именно `end_at`
    # используют все проверки занятости (EXCLUDE-ограничения A4,
    # `car_is_free`) — значит пока доп. работа реально выполнялась на посту,
    # система бронирования считала машину/пост уже свободными сразу после
    # ИЗНАЧАЛЬНОГО (короткого) конца услуги. Итог на практике: одна и та же
    # машина могла получить две активные заявки одновременно, а число
    # реально занятых постов превышало физическое количество постов.
    from datetime import datetime, timedelta, timezone

    client_id, car_id, service_id, booking_id = await make_booking(client, 311)
    extra_id = await make_extra_service(client, price="400.00", duration_minutes=30)
    try:
        # Сдвигаем запланированный интервал в недавнее прошлое (как будто
        # станция реально приняла и закончила основную услугу только что) —
        # без этого тестовый far-future слот (нужен, чтобы не пересекаться с
        # другими тестами) не даёт детерминированно проверить продление
        # "сейчас"-таймера относительно исходного `end_at`. Заодно
        # пересаживает на реально свободный пост на это время (2026-09-14:
        # с проверкой "не раньше start_at" при приёме на пост жёстко
        # заданный старый post_id мог столкнуться с чужой живой занятостью).
        await make_startable_now(booking_id)
        old_end = datetime.fromisoformat(
            (await client.get(f"/bookings/{booking_id}")).json()["end_at"].replace("Z", "+00:00")
        )

        for status in ("on_post", "ready"):
            resp = await client.post(f"/bookings/{booking_id}/status", json={"status": status})
            assert resp.status_code == 200

        work = (await propose(client, booking_id, extra_id)).json()
        resp = await client.post(f"/additional-works/{work['id']}/respond", json={"status": "approved"})
        assert resp.status_code == 200

        booking_after = (await client.get(f"/bookings/{booking_id}")).json()
        assert booking_after["status"] == "on_post"
        new_end_at = datetime.fromisoformat(booking_after["end_at"].replace("Z", "+00:00"))
        # `end_at` должен реально продлиться вместе с `service_ends_at`, а
        # не остаться на исходном (коротком, уже прошедшем) значении.
        assert new_end_at > old_end
        service_ends_at = datetime.fromisoformat(booking_after["service_ends_at"].replace("Z", "+00:00"))
        assert new_end_at == service_ends_at

        # Пока доп. работа "выполняется" (окно [old_end, new_end_at) уже
        # наступило по факту), эта же машина не должна получить вторую
        # активную заявку на пересекающееся время — раньше система считала
        # её уже свободной сразу после (уже прошедшего) old_end. Берём
        # ближайший grid-aligned момент от "сейчас" (15-минутная сетка,
        # см. is_on_slot_grid в slots.py) — он обязан попасть внутрь окна
        # продлённой занятости (~30 минут от момента согласования).
        soon = datetime.now(timezone.utc)
        minutes_to_next_grid = (15 - soon.minute % 15) % 15 or 15
        next_grid_moment = soon.replace(second=0, microsecond=0) + timedelta(minutes=minutes_to_next_grid)
        assert next_grid_moment < new_end_at  # иначе тест сам по себе бессмысленен

        resp = await client.post(
            "/bookings",
            json={
                "client_id": client_id,
                "car_id": car_id,
                "start_at": next_grid_moment.isoformat(),
                "service_ids": [service_id],
            },
        )
        assert resp.status_code == 409
        assert "уже записан" in resp.json()["detail"]
    finally:
        await cleanup(
            client, booking_id=booking_id, car_id=car_id, client_id=client_id, service_id=service_id,
            extra_service_ids=[extra_id],
        )


@pytest.mark.asyncio
async def test_approve_without_room_offers_separate_visit_via_schedule(client: AsyncClient) -> None:
    # UI_description.md п.37 (2026-09-14): раньше, если продление occupancy
    # для одобренной доп. работы пересекалось со следующей заявкой на том же
    # посту (см. п.35 выше — тот же механизм), клиент утыкался в голый 409
    # без выхода. Теперь в этой ситуации предложение остаётся `pending`, а
    # ответ несёт `needs_separate_visit` — клиент выбирает время отдельного
    # визита через новый /schedule (тот же принцип, что и у переноса B4), не
    # трогая текущую заявку и её таймер.
    from app.db.session import async_session
    from app.models import Booking, BookingStatus

    client_id, car_id, service_id, booking_id = await make_booking(client, 340)
    # Длительность доп. работы (45 мин) сознательно БОЛЬШЕ длительности
    # основной услуги (30 мин, см. make_booking) — иначе продление
    # `end_at` от "сейчас" не выйдет за пределы уже существующего (более
    # длинного) окна и коллизии просто не будет, тест ничего не докажет.
    extra_id = await make_extra_service(client, price="300.00", duration_minutes=45)
    other_client_id = other_car_id = blocking_id = scheduled_id = None
    try:
        await make_startable_now(booking_id)

        # Приём на пост сам пересчитывает `end_at` от РЕАЛЬНОГО момента
        # клика (см. app/api/bookings.py, п.35) — а не от запланированного
        # `start_at`. Поэтому "следующую" заявку строим ПОСЛЕ этого перехода,
        # от уже фактического `end_at`, а не от значения до него: иначе даже
        # небольшая разница в секундах между `make_startable_now` и самим
        # кликом сама создаёт лишнее (и тут нежелательное) пересечение.
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200
        booking = resp.json()
        post_id = booking["post_id"]
        end_at = datetime.fromisoformat(booking["end_at"].replace("Z", "+00:00"))

        other_client_resp = await client.post(
            "/clients", json={"email": unique_email(), "name": "AW Blocker"}
        )
        other_client_id = other_client_resp.json()["id"]
        other_car_resp = await client.post(
            "/cars", json={"client_id": other_client_id, "make": "Kia", "model": "Rio"}
        )
        other_car_id = other_car_resp.json()["id"]

        # Реальная заявка на ТОТ ЖЕ пост, начинающаяся сразу после конца
        # основной услуги — имитирует "мест для доп. работы сейчас нет".
        async with async_session() as session:
            blocking = Booking(
                client_id=other_client_id,
                car_id=other_car_id,
                post_id=post_id,
                start_at=end_at,
                end_at=end_at + timedelta(minutes=30),
                status=BookingStatus.ACCEPTED,
            )
            session.add(blocking)
            await session.commit()
            await session.refresh(blocking)
            blocking_id = blocking.id

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "ready"})
        assert resp.status_code == 200

        work = (await propose(client, booking_id, extra_id)).json()
        resp = await client.post(f"/additional-works/{work['id']}/respond", json={"status": "approved"})
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["needs_separate_visit"] is True
        assert detail["service_id"] == extra_id

        # Предложение осталось PENDING — с ним ещё можно взаимодействовать.
        works = (await client.get(f"/bookings/{booking_id}/additional-works")).json()
        assert next(w for w in works if w["id"] == work["id"])["status"] == "pending"

        day = date.today() + timedelta(days=341)
        window_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat()
        slot = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [extra_id], "date": window_start},
            )
        ).json()[0]

        resp = await client.post(
            f"/additional-works/{work['id']}/schedule", json={"start_at": slot["start_at"]}
        )
        assert resp.status_code == 200
        scheduled = resp.json()
        assert scheduled["status"] == "approved"
        scheduled_id = scheduled["scheduled_booking_id"]
        assert scheduled_id is not None

        new_booking = (await client.get(f"/bookings/{scheduled_id}")).json()
        assert new_booking["client_id"] == client_id
        assert new_booking["car_id"] == car_id
        assert new_booking["services"][0]["id"] == extra_id
        assert new_booking["start_at"] == slot["start_at"]

        # Исходная заявка не тронута этим отдельным визитом — осталась
        # "готова", как и была после основной услуги.
        original_after = (await client.get(f"/bookings/{booking_id}")).json()
        assert original_after["status"] == "ready"
    finally:
        await cleanup(
            client,
            booking_id=booking_id,
            car_id=car_id,
            client_id=client_id,
            service_id=service_id,
            extra_service_ids=[extra_id],
            extra_booking_ids=[b for b in (blocking_id, scheduled_id) if b],
        )
        if other_car_id:
            await client.delete(f"/cars/{other_car_id}")
        if other_client_id:
            await client.delete(f"/clients/{other_client_id}")


@pytest.mark.asyncio
async def test_approve_while_still_on_post_with_queued_next_booking_offers_separate_visit(
    client: AsyncClient,
) -> None:
    # UI_description.md п.38 (2026-09-14, найденный пользователем реальный
    # баг по итогам тест-кейса с очередью из машин): проактивная проверка
    # выше (см. respond_additional_work) добавлена именно из-за этого —
    # раньше конфликт занятости проверялся ТОЛЬКО когда occupancy реально
    # продлевалась (заявка уже `awaiting_approval`/`ready`, см. предыдущий
    # тест выше). Пока машина ещё активно на посту (`on_post`) — САМЫЙ
    # частый на практике момент для согласования доп. работы, прямо во
    # время диагностики — проверки не было вообще: клиент мог одобрить
    # работу, которую физически невозможно будет выполнить, когда придёт её
    # время. Этот тест — именно про `on_post`, не про `ready`.
    #
    # `on_post` пересчитывает `end_at` от РЕАЛЬНОГО "сейчас" независимо от
    # того, насколько в прошлом стоял `start_at` (см. п.35) — попытка
    # подставить искусственную дату в далёком прошлом только раздувает
    # итоговый диапазон занятости (start_at остаётся старым, а end_at
    # прыгает на "сейчас + длительность"), не помогая избежать реальной
    # занятости постов. Поэтому, как и в предыдущем тесте, используем
    # `make_startable_now` — он сам находит реально свободный на "сейчас"
    # пост, вместо того чтобы гадать с фиксированной датой.
    from app.db.session import async_session
    from app.models import Booking, BookingStatus

    client_id, car_id, service_id, booking_id = await make_booking(client, 350)
    extra_id = await make_extra_service(client, price="300.00", duration_minutes=45)
    other_client_id = other_car_id = blocking_id = None
    try:
        await make_startable_now(booking_id)

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200
        booking_now = resp.json()
        assert booking_now["status"] == "on_post"
        post_id = booking_now["post_id"]
        # on_post пересчитывает end_at от реального "сейчас" (см. п.35) — не
        # от fixed_end, поэтому читаем фактическое значение отсюда же.
        actual_end_at = datetime.fromisoformat(booking_now["end_at"].replace("Z", "+00:00"))

        other_client_resp = await client.post(
            "/clients", json={"email": unique_email(), "name": "AW Blocker"}
        )
        other_client_id = other_client_resp.json()["id"]
        other_car_resp = await client.post(
            "/cars", json={"client_id": other_client_id, "make": "Kia", "model": "Rio"}
        )
        other_car_id = other_car_resp.json()["id"]

        # Следующая (реальная) заявка в очереди на ТОТ ЖЕ пост — имитирует
        # "уже есть очередь из других", как в тест-кейсе пользователя.
        async with async_session() as session:
            blocking = Booking(
                client_id=other_client_id,
                car_id=other_car_id,
                post_id=post_id,
                start_at=actual_end_at,
                end_at=actual_end_at + timedelta(minutes=30),
                status=BookingStatus.ACCEPTED,
            )
            session.add(blocking)
            await session.commit()
            await session.refresh(blocking)
            blocking_id = blocking.id

        work = (await propose(client, booking_id, extra_id)).json()
        resp = await client.post(f"/additional-works/{work['id']}/respond", json={"status": "approved"})
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["needs_separate_visit"] is True
        assert detail["service_id"] == extra_id

        # Предложение осталось PENDING — согласовать "прямо сейчас" правда
        # невозможно, но с ним ещё можно взаимодействовать (см. /schedule).
        works = (await client.get(f"/bookings/{booking_id}/additional-works")).json()
        assert next(w for w in works if w["id"] == work["id"])["status"] == "pending"

        # Исходная заявка всё ещё на посту — согласование не тронуло её.
        original_after = (await client.get(f"/bookings/{booking_id}")).json()
        assert original_after["status"] == "on_post"
    finally:
        await cleanup(
            client,
            booking_id=booking_id,
            car_id=car_id,
            client_id=client_id,
            service_id=service_id,
            extra_service_ids=[extra_id],
            extra_booking_ids=[b for b in (blocking_id,) if b],
        )
        if other_car_id:
            await client.delete(f"/cars/{other_car_id}")
        if other_client_id:
            await client.delete(f"/clients/{other_client_id}")


@pytest.mark.asyncio
async def test_schedule_batch_combines_multiple_works_into_one_visit(client: AsyncClient) -> None:
    # Найдено пользователем на практике (2026-09-17): когда на посту уже
    # очередь (следующая заявка блокирует продление), НЕСКОЛЬКИМ доп.
    # работам по одной заявке одновременно может не хватить места — раньше
    # это означало отдельный визит (и отдельный выбор времени в мини-
    # календаре) на КАЖДУЮ из них. Проверяем, что теперь клиент может
    # выбрать время ОДИН раз и записать обе сразу в ОДНУ новую заявку.
    from app.db.session import async_session
    from app.models import Booking, BookingStatus

    client_id, car_id, service_id, booking_id = await make_booking(client, 351)
    extra_a = await make_extra_service(client, price="300.00", duration_minutes=20)
    extra_b = await make_extra_service(client, price="450.00", duration_minutes=15)
    other_client_id = other_car_id = blocking_id = scheduled_id = None
    try:
        await make_startable_now(booking_id)
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200
        booking_now = resp.json()
        post_id = booking_now["post_id"]
        actual_end_at = datetime.fromisoformat(booking_now["end_at"].replace("Z", "+00:00"))

        other_client_resp = await client.post(
            "/clients", json={"email": unique_email(), "name": "AW Batch Blocker"}
        )
        other_client_id = other_client_resp.json()["id"]
        other_car_resp = await client.post(
            "/cars", json={"client_id": other_client_id, "make": "Kia", "model": "Rio"}
        )
        other_car_id = other_car_resp.json()["id"]

        # Та же самая очередь, что и в тесте выше — блокирует продление
        # occupancy для ЛЮБОЙ одобренной доп. работы на этом посту.
        async with async_session() as session:
            blocking = Booking(
                client_id=other_client_id,
                car_id=other_car_id,
                post_id=post_id,
                start_at=actual_end_at,
                end_at=actual_end_at + timedelta(minutes=30),
                status=BookingStatus.ACCEPTED,
            )
            session.add(blocking)
            await session.commit()
            await session.refresh(blocking)
            blocking_id = blocking.id

        work_a = (await propose(client, booking_id, extra_a)).json()
        resp = await client.post(f"/additional-works/{work_a['id']}/respond", json={"status": "approved"})
        assert resp.status_code == 409
        assert resp.json()["detail"]["needs_separate_visit"] is True

        work_b = (await propose(client, booking_id, extra_b)).json()
        resp = await client.post(f"/additional-works/{work_b['id']}/respond", json={"status": "approved"})
        assert resp.status_code == 409
        assert resp.json()["detail"]["needs_separate_visit"] is True

        # Один общий визит на ОБЕ работы сразу — не два отдельных.
        day = date.today() + timedelta(days=500)
        slot = (
            await client.get(
                "/bookings/available-slots",
                params={
                    "service_ids": [extra_a, extra_b],
                    "date": datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat(),
                },
            )
        ).json()[0]
        resp = await client.post(
            "/additional-works/schedule-batch",
            json={"work_ids": [work_a["id"], work_b["id"]], "start_at": slot["start_at"]},
        )
        assert resp.status_code == 200
        scheduled = resp.json()
        assert len(scheduled) == 2
        scheduled_booking_ids = {w["scheduled_booking_id"] for w in scheduled}
        assert len(scheduled_booking_ids) == 1  # обе работы указывают на ОДНУ и ту же новую заявку
        assert all(w["status"] == "approved" for w in scheduled)
        scheduled_id = scheduled_booking_ids.pop()

        new_booking = (await client.get(f"/bookings/{scheduled_id}")).json()
        new_service_ids = {s["id"] for s in new_booking["services"]}
        assert new_service_ids == {extra_a, extra_b}
    finally:
        await cleanup(
            client,
            booking_id=booking_id,
            car_id=car_id,
            client_id=client_id,
            service_id=service_id,
            extra_service_ids=[extra_a, extra_b],
            extra_booking_ids=[b for b in (blocking_id, scheduled_id) if b],
        )
        if other_car_id:
            await client.delete(f"/cars/{other_car_id}")
        if other_client_id:
            await client.delete(f"/clients/{other_client_id}")


async def refund_revenue(booking_id: int, amount) -> None:
    # Тот же честный приём, что уже применён в test_api_bookings.py
    # (2026-09-15): вычитаем только если в архиве реально есть ISSUED-запись
    # именно этой заявки — иначе счётчик станции на общей dev-БД уходит в
    # минус, если тест упал раньше настоящего начисления.
    from sqlalchemy import select, update

    from app.db.session import async_session
    from app.models import STATION_STATS_ROW_ID, BookingArchive, BookingStatus, StationStats

    async with async_session() as session:
        archived = (
            await session.execute(
                select(BookingArchive.id).where(
                    BookingArchive.original_booking_id == booking_id,
                    BookingArchive.status == BookingStatus.ISSUED,
                )
            )
        ).first()
        if archived is None:
            return
        await session.execute(
            update(StationStats)
            .where(StationStats.id == STATION_STATS_ROW_ID)
            .values(total_revenue=StationStats.total_revenue - amount)
        )
        await session.commit()


async def delete_archive_entry(booking_id: int) -> None:
    from sqlalchemy import delete as sa_delete

    from app.db.session import async_session
    from app.models import BookingArchive

    async with async_session() as session:
        await session.execute(
            sa_delete(BookingArchive).where(BookingArchive.original_booking_id == booking_id)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_deferred_additional_work_not_charged_until_its_own_visit_is_issued(
    client: AsyncClient,
) -> None:
    # Найденный пользователем реальный баг (2026-09-15): доп. работа,
    # одобренная, но перенесённая на отдельный визит (п.37, см. тест выше —
    # "needs_separate_visit"), ещё НЕ выполнена. Если машина по основной
    # заявке уезжает (issued) раньше, чем прошёл этот отдельный визит, её
    # цена не должна попадать в выручку/архив сейчас — а должна начислиться
    # ровно один раз, когда реально пройдёт (и будет выдана) сама отдельная
    # заявка на эту работу. Без фикса цена доп. работы начислялась ДВАЖДЫ:
    # сразу при выдаче основной машины и повторно при выдаче отдельного визита.
    from decimal import Decimal

    from app.db.session import async_session
    from app.models import Booking, BookingStatus

    client_id, car_id, service_id, booking_id = await make_booking(client, 360)
    extra_id = await make_extra_service(client, price="300.00", duration_minutes=45)
    other_client_id = other_car_id = blocking_id = scheduled_id = None
    try:
        await make_startable_now(booking_id)
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        assert resp.status_code == 200
        booking_now = resp.json()
        post_id = booking_now["post_id"]
        end_at = datetime.fromisoformat(booking_now["end_at"].replace("Z", "+00:00"))

        other_client_resp = await client.post(
            "/clients", json={"email": unique_email(), "name": "AW Blocker"}
        )
        other_client_id = other_client_resp.json()["id"]
        other_car_resp = await client.post(
            "/cars", json={"client_id": other_client_id, "make": "Kia", "model": "Rio"}
        )
        other_car_id = other_car_resp.json()["id"]

        async with async_session() as session:
            blocking = Booking(
                client_id=other_client_id,
                car_id=other_car_id,
                post_id=post_id,
                start_at=end_at,
                end_at=end_at + timedelta(minutes=30),
                status=BookingStatus.ACCEPTED,
            )
            session.add(blocking)
            await session.commit()
            await session.refresh(blocking)
            blocking_id = blocking.id

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "ready"})
        assert resp.status_code == 200

        work = (await propose(client, booking_id, extra_id)).json()
        resp = await client.post(f"/additional-works/{work['id']}/respond", json={"status": "approved"})
        assert resp.status_code == 409  # нет места сейчас — только отдельный визит

        day = date.today() + timedelta(days=361)
        window_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat()
        slot = (
            await client.get(
                "/bookings/available-slots",
                params={"service_ids": [extra_id], "date": window_start},
            )
        ).json()[0]
        resp = await client.post(
            f"/additional-works/{work['id']}/schedule", json={"start_at": slot["start_at"]}
        )
        assert resp.status_code == 200
        scheduled_id = resp.json()["scheduled_booking_id"]

        # Основная заявка уезжает БЕЗ выполненной доп. работы — только
        # стоимость основной услуги (500.00 из make_booking) должна начислиться.
        stats_before = (await client.get("/station/stats")).json()
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "issued"})
        assert resp.status_code == 200
        stats_after_main = (await client.get("/station/stats")).json()
        delta_main = Decimal(stats_after_main["total_revenue"]) - Decimal(stats_before["total_revenue"])
        assert delta_main == Decimal("500.00")  # НЕ 800.00 — доп. работа ещё не выполнена

        archive = (await client.get("/station/archive", params={"client_id": client_id})).json()["items"]
        main_entry = next(a for a in archive if a["original_booking_id"] == booking_id)
        assert Decimal(main_entry["total_price"]) == Decimal("500.00")
        aw_snapshot = next(w for w in main_entry["additional_works_snapshot"] if w["id"] == work["id"])
        assert aw_snapshot["status"] == "approved"
        assert aw_snapshot["scheduled_booking_id"] == scheduled_id

        # Теперь реально проходит и выдаётся отдельный визит — вот тут деньги
        # за доп. работу должны начислиться, и ровно один раз (не задвоить).
        await make_startable_now(scheduled_id)
        for status in ("on_post", "ready", "issued"):
            resp = await client.post(f"/bookings/{scheduled_id}/status", json={"status": status})
            assert resp.status_code == 200
        stats_after_extra = (await client.get("/station/stats")).json()
        delta_extra = Decimal(stats_after_extra["total_revenue"]) - Decimal(stats_after_main["total_revenue"])
        assert delta_extra == Decimal("300.00")

        total_delta = Decimal(stats_after_extra["total_revenue"]) - Decimal(stats_before["total_revenue"])
        assert total_delta == Decimal("800.00")  # 500 + 300, ровно один раз каждая
    finally:
        await cleanup(
            client,
            booking_id=booking_id,
            car_id=car_id,
            client_id=client_id,
            service_id=service_id,
            extra_service_ids=[extra_id],
            extra_booking_ids=[b for b in (blocking_id,) if b],
        )
        if other_car_id:
            await client.delete(f"/cars/{other_car_id}")
        if other_client_id:
            await client.delete(f"/clients/{other_client_id}")
        await refund_revenue(booking_id, Decimal("500.00"))
        await delete_archive_entry(booking_id)
        if scheduled_id:
            await refund_revenue(scheduled_id, Decimal("300.00"))
            await delete_archive_entry(scheduled_id)


@pytest.mark.asyncio
async def test_pending_count_drops_after_response(client: AsyncClient) -> None:
    # UI_description.md п.17: красная точка у "Личный кабинет" держится на
    # этом счётчике — должен расти при новом предложении и падать до 0
    # после ответа клиента.
    client_id, car_id, service_id, booking_id = await make_booking(client, 308)
    extra_id = await make_extra_service(client)
    try:
        await make_startable_now(booking_id)
        await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
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
        await make_startable_now(booking_id)
        await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
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
        await make_startable_now(booking_id)
        await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        resp = await propose(client, booking_id, extra_id)
        assert resp.status_code == 201
        work_id = resp.json()["id"]
        await client.post(f"/additional-works/{work_id}/respond", json={"status": "approved"})

        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "cancelled"})
        assert resp.status_code == 200  # раньше здесь был 500

        archive = await client.get("/station/archive", params={"client_id": client_id})
        entries = archive.json()["items"]
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
