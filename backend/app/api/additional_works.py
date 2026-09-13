from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models import (
    AdditionalWork,
    AdditionalWorkStatus,
    Booking,
    BookingStatus,
    Client,
    Service,
)
from app.schemas.additional_work import (
    AdditionalWorkCreate,
    AdditionalWorkRead,
    AdditionalWorkRespond,
)
from app.schemas.booking import BookingRead
from app.services.events import publish
from app.services.outbox_email import send_stub_email
from app.services.robot_timer import schedule_auto_advance

router = APIRouter(tags=["additional-works"])


@router.post(
    "/bookings/{booking_id}/additional-works", response_model=AdditionalWorkRead, status_code=201
)
async def propose_additional_work(
    booking_id: int, data: AdditionalWorkCreate, session: AsyncSession = Depends(get_session)
) -> AdditionalWork:
    booking = await session.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    client = await session.get(Client, booking.client_id)

    # UI_description.md п.19: доп. работа выбирается кликом из каталога
    # услуг, а не вводится вручную — название/цена/длительность снимаются с
    # выбранной услуги на момент предложения (снимок, как и services_snapshot
    # в архиве: каталог мог измениться позже, а предложение — нет).
    service = await session.get(Service, data.service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="Услуга не найдена в каталоге")

    work = AdditionalWork(
        booking_id=booking_id,
        description=service.name,
        price=service.price,
        duration_minutes=service.duration_minutes,
        proposed_by=data.proposed_by,
    )
    session.add(work)

    # Пометка пользователя (B2): доп. работа предлагается клиенту сразу при
    # обнаружении — не дожидаясь, пока станция закончит уже согласованное.
    # Сама эта работа не начинается, пока клиент не ответит (см. respond
    # ниже) — но статус заявки этим переходом сознательно не трогаем: если
    # что-то ещё согласовано и делается, работа над этим продолжается
    # параллельно (тоже прямая пометка пользователя).
    await send_stub_email(
        session,
        to=client.email if client else "unknown",
        subject=f"Заявка №{booking_id}: предложена дополнительная работа",
        body=f"{service.name} — {service.price} ₽. Подтвердите или отклоните в личном кабинете.",
    )

    await session.commit()
    await session.refresh(work)
    publish("additional_work_proposed", AdditionalWorkRead.model_validate(work).model_dump(mode="json"))
    return work


@router.get("/bookings/{booking_id}/additional-works", response_model=list[AdditionalWorkRead])
async def list_additional_works(
    booking_id: int, session: AsyncSession = Depends(get_session)
) -> list[AdditionalWork]:
    result = await session.execute(
        select(AdditionalWork)
        .where(AdditionalWork.booking_id == booking_id)
        .order_by(AdditionalWork.created_at)
    )
    return list(result.scalars().all())


@router.get("/clients/{client_id}/additional-works/pending-count")
async def count_pending_additional_works(
    client_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    # UI_description.md п.17: красная точка у "Личный кабинет" в шапке,
    # пока у клиента есть хоть одно неотвеченное предложение доп. работы —
    # один лёгкий запрос вместо того, чтобы фронтенду тянуть все брони
    # клиента и по каждой отдельно запрашивать список доп. работ.
    count = (
        await session.execute(
            select(func.count(AdditionalWork.id))
            .select_from(AdditionalWork)
            .join(Booking, Booking.id == AdditionalWork.booking_id)
            .where(Booking.client_id == client_id, AdditionalWork.status == AdditionalWorkStatus.PENDING)
        )
    ).scalar_one()
    return {"count": count}


@router.post("/additional-works/{work_id}/respond", response_model=AdditionalWorkRead)
async def respond_additional_work(
    work_id: int, data: AdditionalWorkRespond, session: AsyncSession = Depends(get_session)
) -> AdditionalWork:
    if data.status not in (AdditionalWorkStatus.APPROVED, AdditionalWorkStatus.DECLINED):
        raise HTTPException(status_code=422, detail="Ответ должен быть 'approved' или 'declined'")

    work = (
        await session.execute(
            select(AdditionalWork).where(AdditionalWork.id == work_id).with_for_update()
        )
    ).scalar_one_or_none()
    if work is None:
        raise HTTPException(status_code=404, detail="Предложение не найдено")
    if work.status != AdditionalWorkStatus.PENDING:
        raise HTTPException(
            status_code=409, detail=f"На это предложение уже есть ответ: '{work.status.value}'"
        )

    work.status = data.status

    # UI_description.md п.13: раньше станция сама вручную отмечала
    # "согласовано"/"отклонено" — непонятно было, зачем это, если реальный
    # ответ даёт клиент в кабинете (B2). Теперь ответ клиента — не просто
    # пометка на AdditionalWork: если это было последнее неотвеченное
    # предложение по заявке и она всё ещё ждёт согласования, заявка сама
    # едет дальше сама, без единого клика со стороны станции.
    booking_snapshot: dict | None = None
    remaining_pending = (
        await session.execute(
            select(AdditionalWork.id)
            .where(
                AdditionalWork.booking_id == work.booking_id,
                AdditionalWork.status == AdditionalWorkStatus.PENDING,
                AdditionalWork.id != work.id,
            )
            .limit(1)
        )
    ).first()
    if remaining_pending is None:
        booking = (
            await session.execute(
                select(Booking)
                .options(selectinload(Booking.services))
                .where(Booking.id == work.booking_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if booking is not None and booking.status == BookingStatus.AWAITING_APPROVAL:
            # UI_description.md п.19: согласованная доп. работа — это ещё
            # работа, которую нужно физически сделать, а не просто пометка.
            # Берём все одобренные работы, длительность которых ещё не
            # попадала ни в один таймер (execution_started=False, чтобы не
            # задвоить уже отработанную длительность, если позже предложат
            # ещё одну доп. работу), и едем на пост ещё на эту длительность —
            # тем же автотаймером, что и основная услуга (C2).
            newly_approved = (
                await session.execute(
                    select(AdditionalWork).where(
                        AdditionalWork.booking_id == work.booking_id,
                        AdditionalWork.status == AdditionalWorkStatus.APPROVED,
                        AdditionalWork.execution_started.is_(False),
                    )
                )
            ).scalars().all()
            extra_minutes = sum(w.duration_minutes for w in newly_approved)

            if extra_minutes > 0:
                for w in newly_approved:
                    w.execution_started = True
                booking.status = BookingStatus.ON_POST
                booking.service_ends_at = datetime.now(timezone.utc) + timedelta(minutes=extra_minutes)
                await session.flush()
                schedule_auto_advance(booking.id, timedelta(minutes=extra_minutes))
            else:
                # Все ответы по этому раунду — "отклонено", делать больше
                # нечего сверх изначальной услуги.
                booking.status = BookingStatus.READY

            booking_snapshot = BookingRead.model_validate(booking).model_dump(mode="json")

    await session.commit()
    await session.refresh(work)
    publish("additional_work_responded", AdditionalWorkRead.model_validate(work).model_dump(mode="json"))
    if booking_snapshot is not None:
        publish("booking_status_changed", booking_snapshot)
    return work
