from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Car, Client
from app.schemas.car import CarCreate, CarRead, CarUpdate

router = APIRouter(prefix="/cars", tags=["cars"])


@router.post("", response_model=CarRead, status_code=201)
async def create_car(data: CarCreate, session: AsyncSession = Depends(get_session)) -> Car:
    client = await session.get(Client, data.client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    car = Car(**data.model_dump())
    session.add(car)
    await session.commit()
    await session.refresh(car)
    return car


@router.get("", response_model=list[CarRead])
async def list_cars(
    client_id: int | None = None, session: AsyncSession = Depends(get_session)
) -> list[Car]:
    query = select(Car)
    if client_id is not None:
        query = query.where(Car.client_id == client_id)
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/{car_id}", response_model=CarRead)
async def get_car(car_id: int, session: AsyncSession = Depends(get_session)) -> Car:
    car = await session.get(Car, car_id)
    if car is None:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")
    return car


@router.patch("/{car_id}", response_model=CarRead)
async def update_car(
    car_id: int, data: CarUpdate, session: AsyncSession = Depends(get_session)
) -> Car:
    car = await session.get(Car, car_id)
    if car is None:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(car, field, value)
    await session.commit()
    await session.refresh(car)
    return car


@router.delete("/{car_id}", status_code=204, response_model=None)
async def delete_car(car_id: int, session: AsyncSession = Depends(get_session)) -> None:
    car = await session.get(Car, car_id)
    if car is None:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")
    await session.delete(car)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="Нельзя удалить автомобиль — на него есть заявки"
        )
