"""Удаление тестовых артефактов из dev-БД.

Периодически после прерванных прогонов автотестов или ручных smoke-тестов
в базе остаются "сиротские" строки, которые не мешают работе, но засоряют
интерфейс (например, попадают в список услуг на экране записи). Этот
скрипт находит и удаляет только то, что однозначно соответствует
соглашениям тестовых данных проекта — не трогая ничего, что им не
соответствует:

- Клиенты, чей email заканчивается на "@example.com" — это соглашение,
  которого придерживаются все автотесты (`unique_email()` в
  `tests/conftest.py`/`tests/test_api_crud.py`) и ручные smoke-тесты в
  этом проекте (см. `logs/DECISIONS_LOG.md`, запись про smoke-test A8).
  Реальные данные пользователя ему не соответствуют — проверено вручную
  перед первым запуском скрипта (2026-09-12): реальные клиенты используют
  явно нетестовые email вроде "email.example"/"Почта123" без "@example.com".
- Их машины и заявки (иначе внешние ключи не дадут удалить клиента).
- Услуги с автосгенерированным именем вида "Услуга <32 hex-символа>"
  (паттерн `uuid4().hex`, которым тесты заменяют захардкоженные значения,
  см. "Изменения плана" в `logs/EXECUTION_PLAN.md") — но только если такая
  услуга не привязана ни к одной существующей заявке.

По умолчанию — только показывает, что было бы удалено (dry-run).
Реальное удаление — только с флагом --apply.

Запуск (из корня проекта):
    docker compose exec backend python scripts/cleanup_test_data.py
    docker compose exec backend python scripts/cleanup_test_data.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import re

from sqlalchemy import delete, select

from app.db.session import async_session
from app.models import Booking, Car, Client, Service, booking_services

TEST_EMAIL_SUFFIX = "@example.com"
TEST_SERVICE_NAME = re.compile(r"^Услуга [0-9a-f]{32}$")


async def find_targets(session):
    clients = (
        (await session.execute(select(Client).where(Client.email.like(f"%{TEST_EMAIL_SUFFIX}"))))
        .scalars()
        .all()
    )
    client_ids = [c.id for c in clients]

    bookings: list[Booking] = []
    cars: list[Car] = []
    if client_ids:
        bookings = (
            (await session.execute(select(Booking).where(Booking.client_id.in_(client_ids))))
            .scalars()
            .all()
        )
        cars = (
            (await session.execute(select(Car).where(Car.client_id.in_(client_ids))))
            .scalars()
            .all()
        )

    all_services = (await session.execute(select(Service))).scalars().all()
    candidate_ids = [s.id for s in all_services if TEST_SERVICE_NAME.match(s.name)]
    referenced_ids: set[int] = set()
    if candidate_ids:
        rows = await session.execute(
            select(booking_services.c.service_id).where(
                booking_services.c.service_id.in_(candidate_ids)
            )
        )
        referenced_ids = {row[0] for row in rows}
    services = [s for s in all_services if s.id in candidate_ids and s.id not in referenced_ids]

    return clients, cars, bookings, services


async def main(apply: bool) -> None:
    async with async_session() as session:
        clients, cars, bookings, services = await find_targets(session)

        print(f"Клиенты ({len(clients)}):")
        for c in clients:
            print(f"  id={c.id} email={c.email!r} name={c.name!r}")
        print(f"Машины ({len(cars)}):")
        for car in cars:
            print(f"  id={car.id} client_id={car.client_id} {car.make} {car.model}")
        print(f"Заявки ({len(bookings)}):")
        for b in bookings:
            print(f"  id={b.id} client_id={b.client_id} start_at={b.start_at} status={b.status.value}")
        print(f"Сиротские услуги ({len(services)}):")
        for s in services:
            print(f"  id={s.id} name={s.name!r}")

        if not clients and not services:
            print("\nЧистить нечего.")
            return

        if not apply:
            print("\nDry-run: ничего не удалено. Запусти с --apply, чтобы реально удалить.")
            return

        booking_ids = [b.id for b in bookings]
        if booking_ids:
            await session.execute(
                delete(booking_services).where(booking_services.c.booking_id.in_(booking_ids))
            )
            await session.execute(delete(Booking).where(Booking.id.in_(booking_ids)))

        car_ids = [c.id for c in cars]
        if car_ids:
            await session.execute(delete(Car).where(Car.id.in_(car_ids)))

        client_ids = [c.id for c in clients]
        if client_ids:
            await session.execute(delete(Client).where(Client.id.in_(client_ids)))

        service_ids = [s.id for s in services]
        if service_ids:
            await session.execute(delete(Service).where(Service.id.in_(service_ids)))

        await session.commit()
        print("\nУдалено.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Реально удалить (по умолчанию — только показать)")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
