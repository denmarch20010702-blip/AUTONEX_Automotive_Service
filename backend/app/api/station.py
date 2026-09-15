from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import STATION_STATS_ROW_ID, Booking, BookingArchive, BookingStatus, StationStats
from app.schemas.booking_archive import BookingArchiveRead
from app.schemas.station import StationStatsRead

router = APIRouter(prefix="/station", tags=["station"])


@router.get("/stats", response_model=StationStatsRead)
async def get_station_stats(session: AsyncSession = Depends(get_session)) -> StationStats:
    return await session.get(StationStats, STATION_STATS_ROW_ID)


@router.get("/actionable-count")
async def count_actionable_bookings(session: AsyncSession = Depends(get_session)) -> dict:
    # UI_description.md п.22 (2026-09-14): красная точка у "Станция" должна
    # гаснуть, когда решение реально принято — не просто при переходе на
    # страницу и обратно. "Требует решения" здесь — заявка ждёт, чтобы её
    # приняли на пост (accepted), либо чтобы её выдали (ready); реальный
    # счётчик вместо разового SSE-флага сам падает до 0, когда станция
    # обработает все такие заявки, и сам растёт, если появится новая.
    count = (
        await session.execute(
            select(func.count(Booking.id)).where(
                Booking.status.in_([BookingStatus.ACCEPTED, BookingStatus.READY])
            )
        )
    ).scalar_one()
    return {"count": count}


@router.get("/archive")
async def list_archive(
    client_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Журнал завершённых/отменённых заявок — по прямой просьбе пользователя
    # (см. buisness/ARCHITECTURE.md). client_id — для "Моей истории" в
    # личном кабинете клиента; без параметра — полный журнал станции.
    # UI_description.md п.40 (2026-09-15): журнал разросся настолько, что
    # приходилось много скроллить — постранично, по 50 строк по умолчанию,
    # а не всё сразу.
    query = select(BookingArchive).order_by(BookingArchive.archived_at.desc())
    if client_id is not None:
        query = query.where(BookingArchive.client_id == client_id)
    total = (
        await session.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    result = await session.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = [BookingArchiveRead.model_validate(row) for row in result.scalars().all()]
    return {"items": items, "total": total, "page": page, "page_size": page_size}
