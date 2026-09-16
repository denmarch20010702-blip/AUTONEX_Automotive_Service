from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Service
from app.schemas.service import ServiceCreate, ServiceRead, ServiceUpdate

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.post("", response_model=ServiceRead, status_code=201)
async def create_service(
    data: ServiceCreate, session: AsyncSession = Depends(get_session)
) -> Service:
    service = Service(**data.model_dump())
    session.add(service)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Услуга с таким названием уже существует")
    await session.refresh(service)
    return service


@router.get("", response_model=list[ServiceRead])
async def list_services(session: AsyncSession = Depends(get_session)) -> list[Service]:
    result = await session.execute(select(Service))
    return list(result.scalars().all())


@router.get("/{service_id}", response_model=ServiceRead)
async def get_service(service_id: int, session: AsyncSession = Depends(get_session)) -> Service:
    service = await session.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    return service


@router.patch("/{service_id}", response_model=ServiceRead)
async def update_service(
    service_id: int, data: ServiceUpdate, session: AsyncSession = Depends(get_session)
) -> Service:
    service = await session.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    # UI_description.md п.47 (2026-09-16): "Сезонная замена шин"/"Получить/
    # сдать шины" — проводники к обязательному функционалу (B1), их название
    # нельзя менять (иначе сломается сопоставление по имени в
    # app/api/tire_sets.py). Время/цену менять можно как обычно.
    if service.protected and data.name is not None and data.name != service.name:
        raise HTTPException(
            status_code=409,
            detail="Название этой услуги нельзя менять — она является проводником к хранению шин",
        )
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(service, field, value)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Услуга с таким названием уже существует")
    await session.refresh(service)
    return service


@router.delete("/{service_id}", status_code=204, response_model=None)
async def delete_service(service_id: int, session: AsyncSession = Depends(get_session)) -> None:
    service = await session.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    # UI_description.md п.47: см. update_service выше — то же самое для удаления.
    if service.protected:
        raise HTTPException(
            status_code=409,
            detail="Эту услугу нельзя удалить — она является проводником к хранению шин",
        )
    await session.delete(service)
    await session.commit()
