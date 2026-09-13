from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Car, Client, TireSet
from app.schemas.tire_set import TireSetCreate, TireSetRead

router = APIRouter(prefix="/tire-sets", tags=["tire-sets"])


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

    tire_set.issued_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(tire_set)
    return tire_set
