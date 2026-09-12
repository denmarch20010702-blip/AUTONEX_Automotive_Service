from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import STATION_STATS_ROW_ID, BookingArchive, StationStats
from app.schemas.booking_archive import BookingArchiveRead
from app.schemas.station import StationStatsRead

router = APIRouter(prefix="/station", tags=["station"])


@router.get("/stats", response_model=StationStatsRead)
async def get_station_stats(session: AsyncSession = Depends(get_session)) -> StationStats:
    return await session.get(StationStats, STATION_STATS_ROW_ID)


@router.get("/archive", response_model=list[BookingArchiveRead])
async def list_archive(
    client_id: int | None = None, session: AsyncSession = Depends(get_session)
) -> list[BookingArchive]:
    # Журнал завершённых/отменённых заявок — по прямой просьбе пользователя
    # (см. buisness/ARCHITECTURE.md). client_id — для "Моей истории" в
    # личном кабинете клиента; без параметра — полный журнал станции.
    query = select(BookingArchive).order_by(BookingArchive.archived_at.desc())
    if client_id is not None:
        query = query.where(BookingArchive.client_id == client_id)
    result = await session.execute(query)
    return list(result.scalars().all())
