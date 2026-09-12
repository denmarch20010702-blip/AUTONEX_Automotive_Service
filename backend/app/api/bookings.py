from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from decimal import Decimal

from asyncpg.exceptions import DeadlockDetectedError
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models import (
    STATION_STATS_ROW_ID,
    Booking,
    BookingArchive,
    BookingStatus,
    Car,
    Client,
    Post,
    Service,
    StationStats,
)
from app.models.booking import booking_services
from app.schemas.booking import BookingCreate, BookingRead, BookingStatusUpdate, SlotOption
from app.services.booking_status import is_transition_allowed
from app.services.events import publish
from app.services.slots import (
    car_is_free,
    get_available_slots,
    get_bookings_overlapping,
    is_on_slot_grid,
    post_is_free,
)

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
    # start_at — не то, что клиент вводит руками, а то, что он кликнул в
    # списке available-slots. Значит оно обязано лежать на 15-минутной
    # сетке; всё остальное — либо чужой клиент API, либо баг фронтенда.
    if data.start_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="start_at должен содержать часовой пояс")
    if not is_on_slot_grid(data.start_at):
        raise HTTPException(
            status_code=422,
            detail="start_at должен совпадать с одним из предложенных available-slots",
        )
    if data.start_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Нельзя записаться в прошлое")

    if await session.get(Client, data.client_id) is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")

    # Блокируем строку авто ДО поиска поста и в том же порядке всегда (авто,
    # затем посты) — той же техникой, что и посты ниже, и по той же причине:
    # чтобы две заявки на одну и ту же машину встали в очередь на этой
    # блокировке, а не гонялись друг с другом за диапазоном в GiST-индексе.
    car = (
        await session.execute(select(Car).where(Car.id == data.car_id).with_for_update())
    ).scalar_one_or_none()
    if car is None:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")
    if car.client_id != data.client_id:
        # Реальный пользователь не может записать машину, которую он сам не
        # добавил себе в аккаунт — только свои автомобили.
        raise HTTPException(status_code=403, detail="Автомобиль не принадлежит этому клиенту")

    services_result = await session.execute(
        select(Service).where(Service.id.in_(data.service_ids))
    )
    services = list(services_result.scalars().all())
    if len(services) != len(set(data.service_ids)):
        raise HTTPException(status_code=404, detail="Одна или несколько услуг не найдены")

    # Конец слота — не то, что вводит клиент, а прямое следствие выбранных
    # услуг: клиент называет только желаемое время начала.
    duration = timedelta(minutes=sum(s.duration_minutes for s in services))
    if duration <= timedelta(0):
        raise HTTPException(status_code=422, detail="Список услуг пуст или некорректен")
    end_at = data.start_at + duration

    # Найдено вручную: одна и та же машина физически не может обслуживаться
    # на нескольких постах одновременно — эту проверку нельзя выразить как
    # "хотя бы один пост свободен", в отличие от постов, поэтому она отдельно.
    if not await car_is_free(session, data.car_id, data.start_at, end_at):
        raise HTTPException(status_code=409, detail="Автомобиль уже записан на это время")

    # Клиенту не важно, на каком посту его обслужат — пост подбирается
    # автоматически. Блокируем строки ВСЕХ постов в одном, всегда одинаковом
    # порядке (по id): конкурентные заявки на одно и то же время встают в
    # очередь на этой блокировке, а не гоняются друг с другом за диапазоном
    # в GiST-индексе EXCLUDE-ограничения — иначе Postgres иногда обнаруживает
    # deadlock между такими транзакциями вместо чистой ошибки ограничения
    # (проверено на практике при разработке A4).
    posts = (
        (await session.execute(select(Post).order_by(Post.id).with_for_update()))
        .scalars()
        .all()
    )
    bookings_by_post = await get_bookings_overlapping(session, data.start_at, end_at)
    free_post = next(
        (p for p in posts if post_is_free(bookings_by_post.get(p.id, []), data.start_at, end_at)),
        None,
    )
    if free_post is None:
        raise HTTPException(status_code=409, detail="Все посты заняты в это время")

    booking = Booking(
        client_id=data.client_id,
        car_id=data.car_id,
        post_id=free_post.id,
        start_at=data.start_at,
        end_at=end_at,
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
    publish("booking_created", BookingRead.model_validate(booking).model_dump(mode="json"))
    return booking


@router.get("", response_model=list[BookingRead])
async def list_bookings(
    client_id: int | None = None, session: AsyncSession = Depends(get_session)
) -> list[Booking]:
    query = select(Booking).order_by(Booking.start_at)
    if client_id is not None:
        query = query.where(Booking.client_id == client_id)
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/{booking_id}", response_model=BookingRead)
async def get_booking(booking_id: int, session: AsyncSession = Depends(get_session)) -> Booking:
    booking = await session.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return booking


@router.post("/{booking_id}/status", response_model=BookingRead)
async def update_booking_status(
    booking_id: int, data: BookingStatusUpdate, session: AsyncSession = Depends(get_session)
) -> BookingRead:
    # Блокируем строку заявки — та же техника, что уже дважды сработала в
    # A4 (пост, авто): два одновременных запроса сменить статус одной и той
    # же заявки встают в очередь на этой блокировке, а не гонятся друг с
    # другом. Второй запрос увидит уже обновлённый статус первого и получит
    # честный 409, если повторный/недопустимый переход.
    booking = (
        await session.execute(
            select(Booking)
            .options(
                selectinload(Booking.services),
                selectinload(Booking.client),
                selectinload(Booking.car),
            )
            .where(Booking.id == booking_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if booking is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    if not is_transition_allowed(booking.status, data.status):
        raise HTTPException(
            status_code=409,
            detail=f"Нельзя перейти из статуса '{booking.status.value}' в '{data.status.value}'",
        )

    booking.status = data.status
    await session.flush()
    # Снимок для ответа/события снимаем ДО удаления ниже — после удаления
    # обращаться к атрибутам ORM-объекта уже нельзя.
    snapshot = BookingRead.model_validate(booking).model_dump(mode="json")

    # Оба терминальных статуса (issued/cancelled) убирают заявку из
    # активного списка — слот освобождается, как и раньше, но сама заявка
    # не пропадает: переезжает в BookingArchive для просмотра при
    # необходимости (по прямой просьбе пользователя, 2026-09-12). Выручка
    # начисляется только за реально выполненную работу (issued), не за
    # отменённую.
    completing = data.status == BookingStatus.ISSUED
    archiving = data.status in (BookingStatus.ISSUED, BookingStatus.CANCELLED)
    if archiving:
        total = sum((service.price for service in booking.services), start=Decimal("0"))
        if completing:
            await session.execute(
                update(StationStats)
                .where(StationStats.id == STATION_STATS_ROW_ID)
                .values(total_revenue=StationStats.total_revenue + total)
            )
        session.add(
            BookingArchive(
                original_booking_id=booking.id,
                client_id=booking.client_id,
                client_name=booking.client.name,
                client_email=booking.client.email,
                car_id=booking.car_id,
                car_make=booking.car.make,
                car_model=booking.car.model,
                post_id=booking.post_id,
                start_at=booking.start_at,
                end_at=booking.end_at,
                status=booking.status,
                total_price=total,
                services_snapshot=[
                    {
                        "id": s.id,
                        "name": s.name,
                        "price": str(s.price),
                        "duration_minutes": s.duration_minutes,
                    }
                    for s in booking.services
                ],
                created_at=booking.created_at,
            )
        )
        await session.execute(
            delete(booking_services).where(booking_services.c.booking_id == booking.id)
        )
        await session.delete(booking)

    await session.commit()

    publish("booking_status_changed", snapshot)
    if completing:
        publish("booking_completed", snapshot)
    return BookingRead(**snapshot)
