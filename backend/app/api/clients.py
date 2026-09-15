from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Booking, BookingStatus, Car, Client, OutboxEmail, TireSet
from app.schemas.booking import BookingStatusUpdate
from app.schemas.client import ClientCreate, ClientRead, ClientUpdate
from app.services.maintenance_suggestions import get_maintenance_suggestions, slots_are_scarce
from app.services.tire_season_reminders import current_tire_season_label

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
async def list_clients(
    email: str | None = None, session: AsyncSession = Depends(get_session)
) -> list[Client]:
    query = select(Client)
    if email is not None:
        # Email хранится нормализованным (нижний регистр) с этого фикса —
        # но нормализуем и вход, чтобы старые данные/чужие клиенты API
        # тоже находились независимо от регистра запроса.
        query = query.where(Client.email == email.strip().lower())
    result = await session.execute(query)
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


@router.get("/{client_id}/maintenance-suggestions")
async def maintenance_suggestions(
    client_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    # B5: проактивное предложение записи по сроку/пробегу ТО, плюс сигнал
    # "мест мало — лучше не откладывать" (пометка пользователя 2026-09-11).
    if await session.get(Client, client_id) is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    suggestions = await get_maintenance_suggestions(session, client_id)
    scarce = await slots_are_scarce(session) if suggestions else False
    return {"suggestions": suggestions, "slots_scarce": scarce}


@router.get("/{client_id}/tire-season-reminder")
async def tire_season_reminder(client_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    # B6 (2026-09-15, найденный пользователем пробел): промо про сезонное
    # хранение шин раньше уходило ТОЛЬКО в email-заглушку — в отличие от
    # B3/B5, в кабинете клиента этого не было видно вообще. Источник истины
    # для "активно ли приглашение в этом сезоне" — та же строка в
    # `outbox_emails`, что уже пишет `send_seasonal_tire_reminders()`, а не
    # отдельный флаг: сезонный джоб рассылает письмо ВСЕМ клиентам сразу при
    # наступлении сезона, так что наличие письма с точной темой этого сезона
    # надёжно означает "приглашение уже действует", без дублирования логики.
    client = await session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")

    today = datetime.now(timezone.utc).date()
    season_label = current_tire_season_label(today)
    subject = f"Сезонное напоминание: хранение шин — {season_label}"
    already_sent = (
        await session.execute(
            select(OutboxEmail.id).where(OutboxEmail.to == client.email, OutboxEmail.subject == subject)
        )
    ).first()
    return {"active": already_sent is not None, "season_label": season_label}


@router.delete("/{client_id}", status_code=204, response_model=None)
async def delete_client(client_id: int, session: AsyncSession = Depends(get_session)) -> None:
    # UI_description.md п.32/41 (2026-09-15): раньше удаление профиля просто
    # падало 409, если у клиента были машины/заявки — клиент физически не мог
    # удалить себя, пока сам вручную не убирал их одну за одной. Теперь
    # активные заявки и машины удаляются автоматически вместе с профилем; но
    # шины на хранении — блокирующее условие (их нужно сначала забрать),
    # прямая просьба пользователя.
    client = await session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")

    has_tire_set = (
        await session.execute(select(TireSet.id).where(TireSet.client_id == client_id).limit(1))
    ).first()
    if has_tire_set is not None:
        raise HTTPException(
            status_code=409,
            detail="Нельзя удалить профиль — сначала забери шины со хранения",
        )

    # Каждую активную заявку честно отменяем (тот же путь, что у ручной
    # отмены — архивация, освобождение поста, снятие доп. работ), а не
    # удаляем в обход этой логики — иначе пост остался бы занятым в системе
    # дольше реального, а история визита пропала бы без следа.
    from app.api.bookings import update_booking_status

    active_booking_ids = (
        await session.execute(
            select(Booking.id).join(Car, Car.id == Booking.car_id).where(Car.client_id == client_id)
        )
    ).scalars().all()
    for booking_id in active_booking_ids:
        try:
            await update_booking_status(booking_id, BookingStatusUpdate(status=BookingStatus.CANCELLED), session)
        except HTTPException:
            # Найденная при код-ревью гонка (2026-09-15): в проекте теперь
            # есть фоновый джоб, который сам отменяет просроченные заявки
            # (app/services/overdue_bookings.py, каждые 30 секунд) — он мог
            # успеть отменить (и удалить из живой таблицы) ОДНУ из этих
            # заявок между выборкой списка выше и этим циклом. Без этого
            # try/except такой 404 вылетал бы необработанным прямо из
            # DELETE /clients/{id}, прерывая удаление на середине: часть
            # заявок уже отменена и закоммичена (каждый вызов коммитит сам),
            # а машины и сам клиент — ещё нет. Гонка возможна и с любым
            # другим параллельным изменением статуса той же заявки — в
            # любом случае "её тут уже нет или она уже не активна" не должно
            # останавливать удаление профиля.
            continue

    car_ids = (await session.execute(select(Car.id).where(Car.client_id == client_id))).scalars().all()
    for car_id in car_ids:
        car = await session.get(Car, car_id)
        if car is not None:
            await session.delete(car)

    await session.delete(client)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Нельзя удалить клиента — не удалось снять все связанные записи",
        )
