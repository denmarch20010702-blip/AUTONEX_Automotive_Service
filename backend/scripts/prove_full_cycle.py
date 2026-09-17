"""C6 — скрипт-доказательство полного цикла заявки: запись -> робот
принимает машину и запускает и себя, и ИИ-диагностику -> ИИ находит доп.
работу -> клиент подтверждает -> робот доводит доп. работу -> готова ->
выдана.

Как и A10 (`scripts/prove_concurrency.py`), бьёт по-настоящему поднятому
backend по HTTP, а не через httpx.ASGITransport и не через мок ИИ/таймера:
и автотаймер (C2, `AsyncIOScheduler`), и ИИ-диагностика (C4, реальный вызов
`run_ai_diagnostic`), и письма-заглушки (C5) — всё настоящее, без подделки
того, что сценарий должен доказать.

Два оправданных прямых обращения к БД (не через REST) — по той же причине,
что и у `tests/helpers.py::make_startable_now`/`set_service_history`,
которыми весь тест-сьют пользуется десятки раз: не заставлять сценарий
реально ждать до 15 минут выравнивания по слот-сетке и гонять отдельный
"пустой" визит только ради системного поля `mileage_at_last_service`
(у него нет и не должно быть публичного setter'а — оно выставляется только
при реальной выдаче заявки, см. ARCHITECTURE.md). Обе подделки — только
формальность подготовки данных, НЕ то, что сценарий проверяет: реальную
работу робота/ИИ/писем ни в одном месте не подделываем.

Длительности услуг взяты короткими (1 минута) специально, чтобы дождаться
настоящего срабатывания автотаймера за разумное время, а не имитировать это.

Запуск (backend должен быть поднят, `docker compose up -d`; именно `-m`, а
не `python scripts/prove_full_cycle.py` напрямую — иначе `/app` не попадает
в sys.path и `from app...` ниже не находит пакет):
    docker compose exec backend python -m scripts.prove_full_cycle
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import httpx
from sqlalchemy import select, update

from app.db.session import async_session
from app.models import Booking, Car, OutboxEmail, Post

BASE_URL = "http://localhost:8000"
MAIN_SERVICE_DURATION_MINUTES = 1
EXTRA_SERVICE_DURATION_MINUTES = 1
MILEAGE_THRESHOLD_KM = 10_000  # см. ai_diagnostics.py


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


async def shift_to_startable_now(booking_id: int) -> None:
    """Тот же приём, что и tests/helpers.py::make_startable_now — сдвигает
    start_at/end_at (сохраняя длительность) в ближайшее прошлое и подбирает
    пост, реально свободный на это новое время, вместо того чтобы ждать
    реально до 15 минут выравнивания по слот-сетке. Не через REST, потому
    что в публичном API намеренно нет и не должно быть эндпоинта "притворись,
    что время прошло" — это была бы дыра в бизнес-логике."""
    async with async_session() as session:
        booking = await session.get(Booking, booking_id)
        duration = booking.end_at - booking.start_at
        start_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        end_at = start_at + duration

        posts = (await session.execute(select(Post.id))).scalars().all()
        occupied = (
            await session.execute(
                select(Booking.post_id).where(
                    Booking.id != booking_id,
                    Booking.status != "CANCELLED",
                    Booking.start_at < end_at,
                    Booking.end_at > start_at,
                )
            )
        ).scalars().all()
        free_post_id = next((p for p in posts if p not in occupied), None)
        if free_post_id is None:
            raise SystemExit(
                "Все посты реально заняты живыми заявками прямо сейчас — "
                "повторите запуск, когда станция свободнее."
            )

        await session.execute(
            update(Booking)
            .where(Booking.id == booking_id)
            .values(start_at=start_at, end_at=end_at, post_id=free_post_id)
        )
        await session.commit()


async def set_service_history(car_id: int, mileage_at_last_service: int) -> None:
    """`mileage_at_last_service` — системное поле без публичного setter'а по
    дизайну (выставляется только при реальной выдаче заявки) — тот же приём,
    что и в tests/test_ai_diagnostics.py::set_service_history, чтобы не
    гонять отдельный "пустой" визит только ради истории ТО."""
    async with async_session() as session:
        car = await session.get(Car, car_id)
        car.mileage_at_last_service = mileage_at_last_service
        await session.commit()


async def latest_outbox_subject(to: str) -> str | None:
    async with async_session() as session:
        row = (
            await session.execute(
                select(OutboxEmail.subject)
                .where(OutboxEmail.to == to)
                .order_by(OutboxEmail.id.desc())
                .limit(1)
            )
        ).first()
        return row[0] if row else None


async def wait_for_status_change(
    client: httpx.AsyncClient, booking_id: int, *, away_from: str, timeout_seconds: int = 100
) -> dict:
    deadline = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)
    while datetime.now(timezone.utc) < deadline:
        booking = (await client.get(f"/bookings/{booking_id}")).json()
        if booking["status"] != away_from:
            return booking
        await asyncio.sleep(3)
    raise SystemExit(f"Заявка №{booking_id} не вышла из статуса '{away_from}' за {timeout_seconds}с — таймер не сработал?")


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10) as client:
        print("=== C6: доказательство полного цикла запись -> робот -> ИИ -> клиент -> готово ===\n")

        # 1. Клиент и машина с пробегом, достаточным для срабатывания ИИ.
        client_resp = await client.post("/clients", json={"email": unique_email(), "name": "C6 Proof"})
        client_resp.raise_for_status()
        client_id = client_resp.json()["id"]
        car_resp = await client.post(
            "/cars", json={"client_id": client_id, "make": "Kia", "model": "Rio", "mileage": 25_000}
        )
        car_resp.raise_for_status()
        car_id = car_resp.json()["id"]
        await set_service_history(car_id, mileage_at_last_service=25_000 - 2 * MILEAGE_THRESHOLD_KM)
        print(f"Клиент id={client_id}, машина id={car_id} — пробег с последнего ТО далеко за порогом ИИ.")

        # 2. Основная услуга + услуга-кандидат для ИИ ("ТО" в названии).
        main_service_resp = await client.post(
            "/catalog",
            json={
                "name": f"C6 Диагностика {uuid4().hex[:6]}",
                "duration_minutes": MAIN_SERVICE_DURATION_MINUTES,
                "price": "500.00",
            },
        )
        main_service_resp.raise_for_status()
        main_service_id = main_service_resp.json()["id"]
        to_service_name = f"ТО-проверка {uuid4().hex[:6]}"
        to_service_resp = await client.post(
            "/catalog",
            json={
                "name": to_service_name,
                "duration_minutes": EXTRA_SERVICE_DURATION_MINUTES,
                "price": "900.00",
            },
        )
        to_service_resp.raise_for_status()
        to_service_id = to_service_resp.json()["id"]
        print(f"Основная услуга id={main_service_id}, услуга-кандидат для ИИ id={to_service_id}.\n")

        # 3. Запись — далеко в будущем (как и в A10), чтобы не столкнуться с
        #    живыми данными станции, затем сдвиг в "сейчас" (см. docstring).
        day = date.today() + timedelta(days=950)
        slots_resp = await client.get(
            "/bookings/available-slots",
            params={
                "service_ids": [main_service_id],
                "date": datetime(day.year, day.month, day.day, tzinfo=timezone.utc).isoformat(),
            },
        )
        slots_resp.raise_for_status()
        target_slot = slots_resp.json()[0]["start_at"]
        booking_resp = await client.post(
            "/bookings",
            json={
                "client_id": client_id,
                "car_id": car_id,
                "start_at": target_slot,
                "service_ids": [main_service_id],
            },
        )
        booking_resp.raise_for_status()
        booking_id = booking_resp.json()["id"]
        print(f"ЗАПИСЬ: заявка №{booking_id} создана на {target_slot}.")
        await shift_to_startable_now(booking_id)
        print("Время визита формально уже наступило (см. docstring про сдвиг).\n")

        # 4. РОБОТ принимает машину на пост — синхронно в этом же запросе
        #    запускается настоящий автотаймер (C2) И настоящая ИИ-диагностика (C4).
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "on_post"})
        resp.raise_for_status()
        print(f"РОБОТ: машина принята на пост {resp.json()['post_id']}, автотаймер на {MAIN_SERVICE_DURATION_MINUTES} мин запущен.")

        works = (await client.get(f"/bookings/{booking_id}/additional-works")).json()
        ai_works = [w for w in works if w["proposed_by"] == "ai"]
        if not ai_works:
            raise SystemExit("ИИ не предложил ни одной доп. работы — ожидался хотя бы 'ТО-проверка'.")
        # Живой каталог станции мог накопить и другие услуги с "ТО" в
        # названии от прошлых ручных проверок — ИИ честно предложит их все
        # для этой машины, не только нашу "ТО-проверку" (найдено на
        # практике при первом прогоне: суммарная длительность НЕСКОЛЬКИХ
        # таких старых услуг раздула occupancy настолько, что она
        # столкнулась с чем-то ещё на живой станции — 409 вместо ожидаемого
        # согласования). Сценарий поэтому взаимодействует только со СВОИМ
        # предложением (по точному имени услуги), а остальные, случайно
        # найденные по совпадению "ТО" в названии, честно отклоняет — это
        # чужой побочный эффект живого каталога, не то, что C6 проверяет.
        for w in ai_works:
            print(f"ИИ: предложена доп. работа «{w['description']}» ({w['price']} ₽), уверенность {w['ai_confidence']}.")
        our_work = next((w for w in ai_works if w["description"] == to_service_name), None)
        if our_work is None:
            raise SystemExit(f"ИИ не предложил именно нашу услугу «{to_service_name}» — не найдена среди предложений.")
        other_ai_works = [w for w in ai_works if w["id"] != our_work["id"]]
        for w in other_ai_works:
            resp = await client.post(f"/additional-works/{w['id']}/respond", json={"status": "declined"})
            resp.raise_for_status()
            print(f"(побочный эффект живого каталога станции — «{w['description']}» отклонена, к сценарию C6 не относится)")

        subject = await latest_outbox_subject(client_resp.json()["email"])
        if subject is None or "требуют вашего решения" not in subject:
            raise SystemExit(f"Ожидалось письмо клиенту про доп. работы, письмо не найдено (тема: {subject!r}).")
        print(f"ПИСЬМО: клиенту отправлено «{subject}» (email-заглушка, outbox_emails).\n")

        # 5. Ждём, пока робот САМ доработает основную услугу (реальный таймер).
        print(f"Ждём реального срабатывания автотаймера основной услуги (до {MAIN_SERVICE_DURATION_MINUTES + 1} мин)...")
        booking_now = await wait_for_status_change(client, booking_id, away_from="on_post")
        if booking_now["status"] != "awaiting_approval":
            raise SystemExit(f"Ожидался статус 'awaiting_approval' (есть неотвеченное предложение ИИ), получили {booking_now['status']!r}.")
        print("РОБОТ: основная услуга готова, заявка сама перешла в 'ожидает согласования' — доп. работа от ИИ ещё не отвечена.\n")

        # 6. КЛИЕНТ подтверждает предложение ИИ (как в реальном кабинете —
        #    ответ на конкретное предложение, см. B2).
        resp = await client.post(f"/additional-works/{our_work['id']}/respond", json={"status": "approved"})
        resp.raise_for_status()
        print(f"КЛИЕНТ: доп. работа «{our_work['description']}» подтверждена — {resp.json()['status']}.")

        booking_now = (await client.get(f"/bookings/{booking_id}")).json()
        if booking_now["status"] != "on_post":
            raise SystemExit(f"Ожидался статус 'on_post' (робот сам вернулся отрабатывать доп. работу), получили {booking_now['status']!r}.")
        print(f"РОБОТ: сам вернулся на пост отрабатывать доп. работу (таймер на {EXTRA_SERVICE_DURATION_MINUTES} мин).\n")

        # 7. Ждём, пока робот САМ доработает и доп. работу.
        print(f"Ждём реального срабатывания автотаймера доп. работы (до {EXTRA_SERVICE_DURATION_MINUTES + 1} мин)...")
        booking_now = await wait_for_status_change(client, booking_id, away_from="on_post")
        if booking_now["status"] != "ready":
            raise SystemExit(f"Ожидался статус 'ready', получили {booking_now['status']!r}.")
        print("РОБОТ: доп. работа готова — заявка сама перешла в 'готова'.")

        ready_subject = await latest_outbox_subject(client_resp.json()["email"])
        if ready_subject is None or "машина готова" not in ready_subject:
            raise SystemExit(f"Ожидалось письмо 'машина готова', получили: {ready_subject!r}.")
        print(f"ПИСЬМО: клиенту отправлено «{ready_subject}».\n")

        # 8. Станция выдаёт машину — финал цикла.
        resp = await client.post(f"/bookings/{booking_id}/status", json={"status": "issued"})
        resp.raise_for_status()
        print("СТАНЦИЯ: машина выдана — 'issued'. Полный цикл пройден целиком, без единого мока.\n")

        # 9. Уборка — только штатные REST-эндпоинты (заявка уже архивирована
        #    сама, отдельно её убирать не нужно).
        await client.delete(f"/cars/{car_id}")
        await client.delete(f"/clients/{client_id}")
        await client.delete(f"/catalog/{main_service_id}")
        await client.delete(f"/catalog/{to_service_id}")
        print("Временные данные сценария удалены.")

        print("\nРЕЗУЛЬТАТ: запись -> робот принял и запустил ИИ -> ИИ нашёл доп. работу -> письмо ушло ->")
        print("робот сам закончил основную услугу -> клиент подтвердил -> робот сам отработал доп. работу ->")
        print("письмо о готовности ушло -> заявка выдана. Все шаги — через настоящий API реально поднятого backend.")


if __name__ == "__main__":
    asyncio.run(main())
