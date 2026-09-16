from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models import Booking, BookingStatus, Car, Client, Service, TireSet, TireSetArchive
from app.schemas.tire_set import TireSetArchiveRead, TireSetCreate, TireSetRead

router = APIRouter(prefix="/tire-sets", tags=["tire-sets"])

# UI_description.md п.47 (2026-09-16): хранение шин больше не голая кнопка —
# и сдача, и выдача возможны только пока клиент физически на посту по одной
# из этих двух услуг (см. миграцию 151f2fa88e1c, где они заведены и защищены
# от переименования — сопоставление по имени ниже иначе бы сломалось).
SEASONAL_TIRE_SWAP_SERVICE_NAME = "Сезонная замена шин"
TIRE_VISIT_SERVICE_NAME = "Получить/сдать шины"


async def _find_on_post_booking_for_service(
    session: AsyncSession, car_id: int, service_names: set[str]
) -> Booking | None:
    return (
        await session.execute(
            select(Booking)
            .join(Booking.services)
            .where(
                Booking.car_id == car_id,
                Booking.status == BookingStatus.ON_POST,
                Service.name.in_(service_names),
            )
            .options(selectinload(Booking.services))
        )
    ).scalars().first()


@router.post("", response_model=TireSetRead, status_code=201)
async def store_tire_set(
    data: TireSetCreate, session: AsyncSession = Depends(get_session)
) -> TireSet:
    if await session.get(Client, data.client_id) is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")

    car = await session.get(Car, data.car_id)
    if car is None:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")
    if car.client_id != data.client_id:
        raise HTTPException(status_code=403, detail="Автомобиль не принадлежит этому клиенту")

    booking = await _find_on_post_booking_for_service(
        session, data.car_id, {SEASONAL_TIRE_SWAP_SERVICE_NAME, TIRE_VISIT_SERVICE_NAME}
    )
    if booking is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Сдать шины на хранение можно только во время визита на "
                f"«{SEASONAL_TIRE_SWAP_SERVICE_NAME}» или «{TIRE_VISIT_SERVICE_NAME}», "
                "пока машина на посту"
            ),
        )

    tire_set = TireSet(client_id=data.client_id, car_id=data.car_id)
    session.add(tire_set)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="У этой машины уже есть комплект шин на хранении — сначала выдайте его",
        )
    await session.refresh(tire_set)
    return tire_set


@router.get("", response_model=list[TireSetRead])
async def list_tire_sets(
    client_id: int | None = None,
    car_id: int | None = None,
    active_only: bool = False,
    session: AsyncSession = Depends(get_session),
) -> list[TireSet]:
    query = select(TireSet).order_by(TireSet.stored_at.desc())
    if client_id is not None:
        query = query.where(TireSet.client_id == client_id)
    if car_id is not None:
        query = query.where(TireSet.car_id == car_id)
    if active_only:
        query = query.where(TireSet.issued_at.is_(None))
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/archive")
async def list_tire_set_archive(
    client_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # UI_description.md п.40 (2026-09-15): постранично, по 50 строк по
    # умолчанию — тот же принцип, что и у журнала заявок (station.py).
    query = select(TireSetArchive).order_by(TireSetArchive.archived_at.desc())
    if client_id is not None:
        query = query.where(TireSetArchive.client_id == client_id)
    total = (
        await session.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    result = await session.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = [TireSetArchiveRead.model_validate(row) for row in result.scalars().all()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/{tire_set_id}/issue", response_model=TireSetRead)
async def issue_tire_set(
    tire_set_id: int, session: AsyncSession = Depends(get_session)
) -> TireSet:
    # Блокировка строки — тот же принцип, что и у заявок/постов/машин
    # (A4/A5): два одновременных запроса на выдачу одного и того же
    # комплекта встают в очередь, а не гонятся друг с другом.
    tire_set = (
        await session.execute(
            select(TireSet).where(TireSet.id == tire_set_id).with_for_update()
        )
    ).scalar_one_or_none()
    if tire_set is None:
        raise HTTPException(status_code=404, detail="Комплект шин не найден")
    if tire_set.issued_at is not None:
        raise HTTPException(status_code=409, detail="Комплект уже выдан")

    # UI_description.md п.47: получить шины обратно можно только визитом на
    # "Получить/сдать шины" — не через "Сезонная замена шин" (та только про
    # сдачу) и не голым кликом без визита вообще.
    booking = await _find_on_post_booking_for_service(
        session, tire_set.car_id, {TIRE_VISIT_SERVICE_NAME}
    )
    if booking is None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Забрать шины можно только во время визита на «{TIRE_VISIT_SERVICE_NAME}», "
                "пока машина на посту"
            ),
        )

    issued_at = datetime.now(timezone.utc)

    # UI_description.md п.28: раньше выданный комплект оставался в живой
    # таблице навсегда — внешний ключ на car_id/client_id блокировал
    # удаление машины/клиента даже без единой реально активной сдачи.
    # Теперь, как и заявки (BookingArchive), выданный комплект переезжает в
    # денормализованный журнал и удаляется из живой таблицы.
    client = await session.get(Client, tire_set.client_id)
    car = await session.get(Car, tire_set.car_id)
    session.add(
        TireSetArchive(
            original_tire_set_id=tire_set.id,
            client_id=tire_set.client_id,
            client_name=client.name if client else "?",
            client_email=client.email if client else "?",
            car_id=tire_set.car_id,
            car_make=car.make if car else "?",
            car_model=car.model if car else "?",
            stored_at=tire_set.stored_at,
            issued_at=issued_at,
        )
    )
    archived_snapshot = TireSetRead(
        id=tire_set.id,
        client_id=tire_set.client_id,
        car_id=tire_set.car_id,
        stored_at=tire_set.stored_at,
        issued_at=issued_at,
    )
    await session.delete(tire_set)
    await session.commit()
    return archived_snapshot
