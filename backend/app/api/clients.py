from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Client
from app.schemas.client import ClientCreate, ClientRead, ClientUpdate

router = APIRouter(prefix="/clients", tags=["clients"])


@router.post("", response_model=ClientRead, status_code=201)
async def create_client(
    data: ClientCreate, session: AsyncSession = Depends(get_session)
) -> Client:
    client = Client(**data.model_dump())
    session.add(client)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Клиент с таким email уже существует")
    await session.refresh(client)
    return client


@router.get("", response_model=list[ClientRead])
async def list_clients(session: AsyncSession = Depends(get_session)) -> list[Client]:
    result = await session.execute(select(Client))
    return list(result.scalars().all())


@router.get("/{client_id}", response_model=ClientRead)
async def get_client(client_id: int, session: AsyncSession = Depends(get_session)) -> Client:
    client = await session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    return client


@router.patch("/{client_id}", response_model=ClientRead)
async def update_client(
    client_id: int, data: ClientUpdate, session: AsyncSession = Depends(get_session)
) -> Client:
    client = await session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Клиент с таким email уже существует")
    await session.refresh(client)
    return client


@router.delete("/{client_id}", status_code=204, response_model=None)
async def delete_client(client_id: int, session: AsyncSession = Depends(get_session)) -> None:
    client = await session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    await session.delete(client)
    await session.commit()
