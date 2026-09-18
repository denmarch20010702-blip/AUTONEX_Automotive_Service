"""UI_description.md п.45 (2026-09-15): новые метрики станции — выручка "за
сегодня" отдельно от общей, средний чек, соотношение выполнено/отменено,
конверсия по доп. работам. Вставляем синтетические строки archive напрямую
(не через полный цикл заявки) — тестируем саму агрегацию, не бизнес-логику
архивации, которая уже покрыта в другом месте."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete as sa_delete
from sqlalchemy import update

from app.db.session import async_session
from app.models import STATION_STATS_ROW_ID, BookingArchive, BookingStatus, StationStats


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


async def insert_archive_row(
    *,
    status: BookingStatus,
    total_price: str,
    archived_at: datetime | None = None,
    additional_works_snapshot: list | None = None,
) -> int:
    async with async_session() as session:
        row = BookingArchive(
            original_booking_id=0,
            client_id=0,
            client_name="Metrics Tester",
            client_email=unique_email(),
            car_id=0,
            car_make="Test",
            car_model="Car",
            post_id=1,
            start_at=datetime.now(timezone.utc),
            end_at=datetime.now(timezone.utc),
            status=status,
            total_price=Decimal(total_price),
            services_snapshot=[],
            additional_works_snapshot=additional_works_snapshot or [],
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        row_id = row.id
    if archived_at is not None:
        async with async_session() as session:
            await session.execute(
                update(BookingArchive).where(BookingArchive.id == row_id).values(archived_at=archived_at)
            )
            await session.commit()
    return row_id


async def delete_archive_row(row_id: int) -> None:
    async with async_session() as session:
        await session.execute(sa_delete(BookingArchive).where(BookingArchive.id == row_id))
        await session.commit()


@pytest.mark.asyncio
async def test_today_revenue_excludes_older_issued_bookings(client: AsyncClient) -> None:
    old_id = await insert_archive_row(
        status=BookingStatus.ISSUED,
        total_price="500.00",
        archived_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    try:
        before = (await client.get("/station/stats")).json()
        new_id = await insert_archive_row(status=BookingStatus.ISSUED, total_price="300.00")
        try:
            after = (await client.get("/station/stats")).json()
            delta_today = Decimal(str(after["today_revenue"])) - Decimal(str(before["today_revenue"]))
            delta_total = Decimal(str(after["total_revenue"])) - Decimal(str(before["total_revenue"]))
            # Старая запись (2 дня назад) не в "сегодня" — только новая.
            assert delta_today == Decimal("300.00")
            # Общая выручка, как и "сегодня", считается из неизменяемого
            # архива выданных машин. Это защищает UI от испорченного legacy-
            # счётчика StationStats и делает прямую вставку видимой честно.
            assert delta_total == Decimal("300.00")
        finally:
            await delete_archive_row(new_id)
    finally:
        await delete_archive_row(old_id)


@pytest.mark.asyncio
async def test_completion_rate_and_average_check_present(client: AsyncClient) -> None:
    issued_id = await insert_archive_row(status=BookingStatus.ISSUED, total_price="1000.00")
    cancelled_id = await insert_archive_row(status=BookingStatus.CANCELLED, total_price="1000.00")
    try:
        stats = (await client.get("/station/stats")).json()
        assert stats["issued_count"] >= 1
        assert stats["cancelled_count"] >= 1
        assert stats["completion_rate_percent"] is not None
        assert 0 <= stats["completion_rate_percent"] <= 100
        assert stats["average_check"] is not None
        assert Decimal(str(stats["average_check"])) > 0
    finally:
        await delete_archive_row(issued_id)
        await delete_archive_row(cancelled_id)


@pytest.mark.asyncio
async def test_additional_work_conversion_percent_present_and_bounded(client: AsyncClient) -> None:
    row_id = await insert_archive_row(
        status=BookingStatus.ISSUED,
        total_price="500.00",
        additional_works_snapshot=[
            {
                "id": 1,
                "description": "X",
                "price": "100.00",
                "proposed_by": "mechanic",
                "status": "approved",
                "scheduled_booking_id": None,
            },
            {
                "id": 2,
                "description": "Y",
                "price": "100.00",
                "proposed_by": "mechanic",
                "status": "declined",
                "scheduled_booking_id": None,
            },
        ],
    )
    try:
        stats = (await client.get("/station/stats")).json()
        assert stats["additional_work_conversion_percent"] is not None
        assert 0 <= stats["additional_work_conversion_percent"] <= 100
    finally:
        await delete_archive_row(row_id)


@pytest.mark.asyncio
async def test_metrics_are_none_when_no_archive_history(client: AsyncClient) -> None:
    # Честное "нет данных", а не деление на ноль или 0.0, вводящее в
    # заблуждение как настоящий ноль.
    async with async_session() as session:
        from sqlalchemy import select

        any_row = (await session.execute(select(BookingArchive.id).limit(1))).first()
    if any_row is not None:
        pytest.skip("в архиве уже есть данные от других тестов — этот сценарий не воспроизвести изолированно")
    stats = (await client.get("/station/stats")).json()
    assert stats["average_check"] is None
    assert stats["completion_rate_percent"] is None
    assert stats["additional_work_conversion_percent"] is None


@pytest.mark.asyncio
async def test_total_revenue_ignores_corrupted_legacy_counter(client: AsyncClient) -> None:
    """Regression for the negative-revenue incident from live-db tests."""
    before = Decimal(str((await client.get("/station/stats")).json()["total_revenue"]))
    async with async_session() as session:
        legacy_counter = await session.get(StationStats, STATION_STATS_ROW_ID)
        original_value = legacy_counter.total_revenue
        legacy_counter.total_revenue = Decimal("-999999.99")
        await session.commit()
    try:
        after = Decimal(str((await client.get("/station/stats")).json()["total_revenue"]))
        assert after == before
    finally:
        async with async_session() as session:
            legacy_counter = await session.get(StationStats, STATION_STATS_ROW_ID)
            legacy_counter.total_revenue = original_value
            await session.commit()
