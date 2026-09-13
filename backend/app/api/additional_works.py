from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import AdditionalWork, AdditionalWorkStatus, Booking, Client
from app.schemas.additional_work import (
    AdditionalWorkCreate,
    AdditionalWorkRead,
    AdditionalWorkRespond,
)
from app.services.events import publish
from app.services.outbox_email import send_stub_email

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

    work = AdditionalWork(
        booking_id=booking_id,
        description=data.description,
        price=data.price,
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
        body=f"{data.description} — {data.price} ₽. Подтвердите или отклоните в личном кабинете.",
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
    await session.commit()
    await session.refresh(work)
    publish("additional_work_responded", AdditionalWorkRead.model_validate(work).model_dump(mode="json"))
    return work
