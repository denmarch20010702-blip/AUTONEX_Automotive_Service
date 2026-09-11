from __future__ import annotations

from datetime import date

from asyncpg.exceptions import DeadlockDetectedError
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Booking, Car, Client, Post, Service
from app.schemas.booking import BookingCreate, BookingRead, SlotOption
from app.services.slots import get_available_slots

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("/available-slots", response_model=list[SlotOption])
async def available_slots(
    service_ids: list[int] = Query(...),
    on: date = Query(..., alias="date"),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    return await get_available_slots(session, service_ids, on)


@router.post("", response_model=BookingRead, status_code=201)
async def create_booking(
    data: BookingCreate, session: AsyncSession = Depends(get_session)
) -> Booking:
    for model, entity_id, label in (
        (Client, data.client_id, "Клиент"),
        (Car, data.car_id, "Автомобиль"),
    ):
        if await session.get(model, entity_id) is None:
            raise HTTPException(status_code=404, detail=f"{label} не найден")

    # Блокируем строку поста на время транзакции: конкурентные заявки на
    # один и тот же пост встают в очередь на этой блокировке, а не гоняются
    # друг с другом за диапазоном в GiST-индексе EXCLUDE-ограничения — иначе
    # Postgres иногда обнаруживает deadlock между двумя такими транзакциями
    # вместо чистой ошибки ограничения (проверено на практике).
    post = (
        await session.execute(select(Post).where(Post.id == data.post_id).with_for_update())
    ).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="Пост не найден")

    services_result = await session.execute(
        select(Service).where(Service.id.in_(data.service_ids))
    )
    services = list(services_result.scalars().all())
    if len(services) != len(set(data.service_ids)):
        raise HTTPException(status_code=404, detail="Одна или несколько услуг не найдены")

    booking = Booking(
        client_id=data.client_id,
        car_id=data.car_id,
        post_id=data.post_id,
        start_at=data.start_at,
        end_at=data.end_at,
        services=services,
    )
    session.add(booking)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Слот уже занят")
    except DBAPIError as exc:
        await session.rollback()
        # Defense in depth: если блокировка поста выше почему-то не спасла
        # (например, будущий код обойдёт её) — распознаём deadlock именно
        # как проигранную гонку за слот, а не маскируем случайную ошибку БД.
        if isinstance(exc.orig, DeadlockDetectedError):
            raise HTTPException(status_code=409, detail="Слот уже занят")
        raise
    await session.refresh(booking)
    return booking


@router.get("/{booking_id}", response_model=BookingRead)
async def get_booking(booking_id: int, session: AsyncSession = Depends(get_session)) -> Booking:
    booking = await session.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return booking
