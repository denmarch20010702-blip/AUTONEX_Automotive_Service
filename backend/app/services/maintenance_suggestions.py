from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Car, Service
from app.services.slots import get_available_slots

# B5 (проактивное предложение записи по пробегу/сроку ТО, плюс по остатку
# мест — пометка пользователя 2026-09-11: "если остаётся ≤3 свободных мест
# и клиенту подходит срок, предложить запись заранее, т.к. позже мест может
# не быть"). Точные бизнес-пороги "когда пора на ТО" в задании не заданы —
# решение AI, стандартные ориентиры для большинства легковых авто:
MONTHS_SINCE_SERVICE_THRESHOLD = 6
KM_SINCE_SERVICE_THRESHOLD = 10_000
SCARCE_SLOTS_THRESHOLD = 3


async def get_maintenance_suggestions(session: AsyncSession, client_id: int) -> list[dict]:
    """Для каждой машины клиента — предложение записаться на ТО, если по
    времени (>= 6 месяцев с последнего ТО) или по пробегу (>= 10 000 км с
    последнего ТО) подошёл срок. Машины без единого ТО в истории не
    предлагаются — нет базы для сравнения (решение AI: лучше молчать, чем
    гадать по машине без данных)."""
    cars = (await session.execute(select(Car).where(Car.client_id == client_id))).scalars().all()
    today = datetime.now(timezone.utc).date()
    suggestions: list[dict] = []
    for car in cars:
        if car.last_service_date is None:
            continue
        months_since = (today.year - car.last_service_date.year) * 12 + (
            today.month - car.last_service_date.month
        )
        if months_since >= MONTHS_SINCE_SERVICE_THRESHOLD:
            suggestions.append(
                {
                    "car_id": car.id,
                    "make": car.make,
                    "model": car.model,
                    "reason": "time",
                    "months_since_service": months_since,
                }
            )
            continue
        if car.mileage_at_last_service is not None:
            km_since = car.mileage - car.mileage_at_last_service
            if km_since >= KM_SINCE_SERVICE_THRESHOLD:
                suggestions.append(
                    {
                        "car_id": car.id,
                        "make": car.make,
                        "model": car.model,
                        "reason": "mileage",
                        "km_since_service": km_since,
                    }
                )
    return suggestions


async def slots_are_scarce(session: AsyncSession) -> bool:
    """Мест мало — грубая оценка: свободных слотов на завтра для самой
    короткой услуги в каталоге (её проще всего куда-то вписать, поэтому это
    "оптимистичный" ориентир общей загрузки станции) не больше порога.
    Пустой каталог/нет услуг — считаем, что мест достаточно (не пугаем
    клиента без данных)."""
    shortest = (
        await session.execute(select(Service).order_by(Service.duration_minutes).limit(1))
    ).scalar_one_or_none()
    if shortest is None:
        return False
    tomorrow_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)
    slots = await get_available_slots(session, [shortest.id], tomorrow_start)
    return len(slots) <= SCARCE_SLOTS_THRESHOLD
