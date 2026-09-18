from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import (
    STATION_SETTINGS_ROW_ID,
    Booking,
    BookingArchive,
    BookingStatus,
    StationSettings,
)
from app.schemas.booking_archive import BookingArchiveRead
from app.schemas.station import StationSettingsRead, StationSettingsUpdate, StationStatsRead

router = APIRouter(prefix="/station", tags=["station"])


@router.get("/settings", response_model=StationSettingsRead)
async def get_station_settings(session: AsyncSession = Depends(get_session)) -> StationSettings:
    return await session.get(StationSettings, STATION_SETTINGS_ROW_ID)


@router.patch("/settings", response_model=StationSettingsRead)
async def update_station_settings(
    data: StationSettingsUpdate, session: AsyncSession = Depends(get_session)
) -> StationSettings:
    # C7 (buisness.md): "тариф который можно менять в личном кабинете
    # станции" — единственная сейчас редактируемая настройка станции.
    settings_row = await session.get(StationSettings, STATION_SETTINGS_ROW_ID)
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(settings_row, field, value)
    await session.commit()
    await session.refresh(settings_row)
    return settings_row


@router.get("/stats", response_model=StationStatsRead)
async def get_station_stats(session: AsyncSession = Depends(get_session)) -> dict:
    # The archive is the immutable financial source of truth.  `station_stats`
    # is retained only as a backwards-compatible cache; reading it here once
    # allowed failed/old live-db test clean-up to display a negative revenue.
    total_revenue = (
        await session.execute(
            select(func.coalesce(func.sum(BookingArchive.total_price), 0)).where(
                BookingArchive.status == BookingStatus.ISSUED
            )
        )
    ).scalar_one()

    # UI_description.md п.45 (2026-09-15): компактный счётчик в правом верхнем
    # углу — выручка "за сегодня" отдельно от "за всё время". Честное
    # упрощение: "сегодня" — сутки по UTC (та же логика, что и везде в
    # проекте про часовой пояс слотов, см. ARCHITECTURE.md), не по локальному
    # времени станции/клиента.
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_revenue = (
        await session.execute(
            select(func.coalesce(func.sum(BookingArchive.total_price), 0)).where(
                BookingArchive.status == BookingStatus.ISSUED,
                BookingArchive.archived_at >= today_start,
            )
        )
    ).scalar_one()

    average_check = (
        await session.execute(
            select(func.avg(BookingArchive.total_price)).where(
                BookingArchive.status == BookingStatus.ISSUED
            )
        )
    ).scalar_one()

    issued_count = (
        await session.execute(
            select(func.count()).where(BookingArchive.status == BookingStatus.ISSUED)
        )
    ).scalar_one()
    cancelled_count = (
        await session.execute(
            select(func.count()).where(BookingArchive.status == BookingStatus.CANCELLED)
        )
    ).scalar_one()
    completion_rate_percent = (
        round(issued_count / (issued_count + cancelled_count) * 100, 1)
        if (issued_count + cancelled_count) > 0
        else None
    )

    # Конверсия по доп. работам: доля одобренных среди реально отвеченных
    # (approved+declined, без ещё не отвеченных — тех тут и не может быть,
    # заявка не архивируется с pending-предложением). Снимок хранится
    # JSON-массивом на каждой архивной заявке — агрегируем в Python: объём
    # для демо-проекта небольшой, а структура вложенная, не стоит городить
    # SQL по JSON ради этого.
    snapshots = (
        await session.execute(select(BookingArchive.additional_works_snapshot))
    ).scalars().all()
    approved = 0
    answered = 0
    for snapshot in snapshots:
        for work in snapshot:
            if work["status"] == "approved":
                approved += 1
                answered += 1
            elif work["status"] == "declined":
                answered += 1
    additional_work_conversion_percent = round(approved / answered * 100, 1) if answered > 0 else None

    return {
        "total_revenue": total_revenue,
        "today_revenue": today_revenue,
        "average_check": average_check,
        "issued_count": issued_count,
        "cancelled_count": cancelled_count,
        "completion_rate_percent": completion_rate_percent,
        "additional_work_conversion_percent": additional_work_conversion_percent,
    }


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
