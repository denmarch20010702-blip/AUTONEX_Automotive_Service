from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import ParkingSpot
from app.schemas.parking_spot import ParkingSpotRead

router = APIRouter(prefix="/parking-spots", tags=["parking-spots"])


@router.get("", response_model=list[ParkingSpotRead])
async def list_parking_spots(session: AsyncSession = Depends(get_session)) -> list[ParkingSpot]:
    # C7 (buisness.md): 6 фиксированных мест — как и посты, не через CRUD
    # (см. миграцию-сидинг) — этот эндпоинт только читает список для
    # отображения (доска на станции, C8).
    result = await session.execute(select(ParkingSpot).order_by(ParkingSpot.id))
    return list(result.scalars().all())
