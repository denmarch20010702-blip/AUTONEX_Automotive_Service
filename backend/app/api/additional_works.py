from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models import (
    AdditionalWork,
    AdditionalWorkStatus,
    Booking,
    BookingStatus,
    Client,
    ProposedBy,
    Service,
)
from app.schemas.additional_work import (
    AdditionalWorkCreate,
    AdditionalWorkRead,
    AdditionalWorkRespond,
    AdditionalWorkSchedule,
    AdditionalWorkScheduleBatch,
)
from app.schemas.booking import BookingCreate, BookingRead
from app.services.events import publish
from app.services.outbox_email import notify_pending_additional_works
from app.services.robot_timer import resolve_next_step
from app.services.slots import get_bookings_overlapping, post_is_free

# bookings.py ничего не импортирует из additional_works.py, цикла нет —
# переиспользуем сам эндпоинт создания заявки напрямую (та же конкурентно-
# безопасная логика A4: блокировки авто/постов, EXCLUDE-ограничения), а не
# копируем её для отдельного визита ниже (см. schedule_additional_work).
from app.api.bookings import create_booking

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

    # Найденный на практике реальный баг (2026-09-17, аудит проекта):
    # мастер мог предложить доп. работу на заявку, которая ещё даже не
    # принята на пост (`accepted` — машина физически не приехала). Это не
    # просто нелогично ("нашёл что-то ещё" подразумевает, что машина уже
    # обслуживается) — это создавало тупик: неотвеченное предложение сразу
    # блокировало сам переход `accepted -> on_post` (см. guard в
    # update_booking_status), заявка зависала в "принята" до ответа клиента
    # по машине, которую он даже не привёз.
    if booking.status == BookingStatus.ACCEPTED:
        raise HTTPException(
            status_code=409,
            detail="Машина ещё не принята на пост — сначала примите заявку",
        )

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
        # UI_description.md п.37: нужна настоящая ссылка на каталог (не
        # только снимок имени/цены выше), чтобы при нехватке места можно
        # было предложить отдельный визит именно на эту услугу — см.
        # schedule_additional_work_separately.
        service_id=service.id,
        # C5 (2026-09-16): этот публичный эндпоинт — только для мастера;
        # `proposed_by=ai` возможно только через внутренний вызов
        # run_ai_diagnostic, не через API (см. AdditionalWorkCreate).
        proposed_by=ProposedBy.MECHANIC,
    )
    session.add(work)

    # Пометка пользователя (B2): доп. работа предлагается клиенту сразу при
    # обнаружении — не дожидаясь, пока станция закончит уже согласованное.
    # Сама эта работа не начинается, пока клиент не ответит (см. respond
    # ниже) — но статус заявки этим переходом сознательно не трогаем: если
    # что-то ещё согласовано и делается, работа над этим продолжается
    # параллельно (тоже прямая пометка пользователя).
    #
    # C5: одно письмо на ВЕСЬ текущий список неотвеченных предложений по
    # заявке (не только это) — тот же путь, что и для предложений от ИИ
    # (см. ai_diagnostics.py), клиенту не важно, кто предложил.
    await notify_pending_additional_works(
        session, booking_id, client.email if client else "unknown"
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

    if data.status == AdditionalWorkStatus.APPROVED:
        # UI_description.md п.38 (2026-09-14, найденный пользователем реальный
        # баг): предыдущая проверка (см. п.37 ниже, в блоке try/except)
        # срабатывала только В МОМЕНТ, когда occupancy РЕАЛЬНО продлевалась —
        # то есть только если заявка уже была `awaiting_approval`/`ready`,
        # или позже, когда доходил автотаймер. Пока машина ещё активно на
        # посту (`on_post`) — самый частый на практике момент для
        # согласования доп. работы, прямо во время диагностики — эта функция
        # occupancy вообще не трогала и ничего не проверяла: клиент спокойно
        # соглашался на работу, которую физически невозможно будет выполнить,
        # когда придёт её время (пост уже занят следующей заявкой в очереди).
        # Теперь проверяем ЗАРАНЕЕ и всегда, независимо от текущего статуса
        # заявки: влезет ли эта работа (плюс все уже одобренные, но ещё не
        # отработанные) после ТЕКУЩЕГО запланированного конца занятости
        # (`booking.end_at`), а не после "сейчас" — на момент согласования
        # настоящая работа может ещё даже не начаться.
        booking_for_check = (
            await session.execute(select(Booking).where(Booking.id == work.booking_id))
        ).scalar_one_or_none()
        if booking_for_check is None:
            raise HTTPException(status_code=404, detail="Заявка не найдена")

        other_approved_unexecuted_minutes = (
            await session.execute(
                select(func.coalesce(func.sum(AdditionalWork.duration_minutes), 0)).where(
                    AdditionalWork.booking_id == work.booking_id,
                    AdditionalWork.status == AdditionalWorkStatus.APPROVED,
                    AdditionalWork.execution_started.is_(False),
                )
            )
        ).scalar_one()
        total_extra_minutes = other_approved_unexecuted_minutes + work.duration_minutes
        prospective_end = booking_for_check.end_at + timedelta(minutes=total_extra_minutes)

        bookings_by_post = await get_bookings_overlapping(
            session, booking_for_check.end_at, prospective_end, exclude_booking_id=booking_for_check.id
        )
        if not post_is_free(
            bookings_by_post.get(booking_for_check.post_id, []), booking_for_check.end_at, prospective_end
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        "Сейчас нет места для этой работы — пост занят следующей заявкой. "
                        "Выберите время для отдельного визита."
                    ),
                    "needs_separate_visit": True,
                    "service_id": work.service_id,
                    "duration_minutes": work.duration_minutes,
                },
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
        # UI_description.md п.20/25 (2026-09-14): раньше сюда заходили только
        # если заявка в этот момент была РОВНО в 'awaiting_approval' — если
        # клиент отвечал уже после того, как основная услуга закончилась
        # (заявка 'ready'), таймер одобренной доп. работы вообще не
        # запускался, и она считалась выполненной просто по факту ответа.
        # Добавлено 'ready' к условию. 'accepted' сознательно не включаем —
        # машина ещё не на посту вообще, финализировать заявку было бы
        # неверно; 'on_post' тоже не включаем — там уже идёт другой таймер,
        # который сам подхватит эту работу, когда закончится (см.
        # resolve_next_step).
        resolved_booking = booking if booking is not None and booking.status in (
            BookingStatus.AWAITING_APPROVAL,
            BookingStatus.READY,
        ) else None
        if resolved_booking is not None:
            await resolve_next_step(session, resolved_booking)
    else:
        resolved_booking = None

    # Снимок нужен ДО commit/rollback: после rollback SQLAlchemy "протухает"
    # атрибуты объектов в этой сессии, а обращение к ним ниже потребовало бы
    # нового запроса, чего в async-сессии нельзя сделать синхронно.
    work_service_id = work.service_id
    work_duration_minutes = work.duration_minutes

    try:
        # Найденный баг (2026-09-14, всплыл при разработке п.37): раньше
        # `flush()` после `resolve_next_step` стоял ДО этого `try` — если
        # продление occupancy пересекалось с чужой заявкой, EXCLUDE-
        # ограничение падало прямо на flush() необработанным 500 вместо
        # честного 409 ниже (существующий тест этот путь не проверял, т.к.
        # проверял конфликт отдельным запросом ПОСЛЕ успешного ответа, а не
        # сам момент продления). Теперь flush — часть защищённого блока.
        await session.flush()
        if resolved_booking is not None:
            booking_snapshot = BookingRead.model_validate(resolved_booking).model_dump(mode="json")
        await session.commit()
    except IntegrityError:
        # Продление occupancy (п.35, см. resolve_next_step) в редком случае
        # может пересечься с чужой заявкой.
        await session.rollback()
        if data.status == AdditionalWorkStatus.APPROVED:
            # UI_description.md п.37 (2026-09-14): раньше это был тупик —
            # клиент не мог ни согласовать (пост занят следующей заявкой),
            # ни понять, что делать. Теперь предложение остаётся PENDING
            # (согласовать "прямо сейчас" правда невозможно), а фронтенд по
            # `needs_separate_visit` показывает мини-календарь и вызывает
            # POST /additional-works/{id}/schedule с выбранным временем —
            # отдельным визитом именно на эту работу, не трогая текущую
            # заявку и её таймер.
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        "Сейчас нет места для этой работы — пост занят следующей заявкой. "
                        "Выберите время для отдельного визита."
                    ),
                    "needs_separate_visit": True,
                    "service_id": work_service_id,
                    "duration_minutes": work_duration_minutes,
                },
            )
        raise HTTPException(status_code=409, detail="Пост или машина заняты на продлённое время")
    await session.refresh(work)
    publish("additional_work_responded", AdditionalWorkRead.model_validate(work).model_dump(mode="json"))
    if booking_snapshot is not None:
        publish("booking_status_changed", booking_snapshot)
    return work


@router.post("/additional-works/{work_id}/schedule", response_model=AdditionalWorkRead)
async def schedule_additional_work(
    work_id: int, data: AdditionalWorkSchedule, session: AsyncSession = Depends(get_session)
) -> AdditionalWork:
    """UI_description.md п.37 (2026-09-14): когда пост занят следующей
    заявкой и доп. работу нельзя выполнить сразу, клиент вместо тупика
    выбирает время для ОТДЕЛЬНОГО визита именно на эту работу — тот же
    компонент выбора слота, что и у переноса записи (B4). Создаёт новую
    самостоятельную заявку (та же машина/клиент, только время и услуга —
    снятая с этой доп. работы) и помечает предложение согласованным."""
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
    if work.service_id is None:
        raise HTTPException(
            status_code=409,
            detail="Услуга для этой доп. работы больше не существует в каталоге — отдельный визит невозможен, можно только отклонить",
        )

    booking = await session.get(Booking, work.booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    # Переиспользуем сам эндпоинт создания заявки — та же конкурентно-
    # безопасная проверка слота/поста/машины, что и у обычной записи (A4).
    # Если слот уже занят кем-то другим к моменту клика — get_available_slots
    # для этой услуги на фронтенде мог устареть, поэтому это НЕ баг, а
    # честный 409 от create_booking, который дойдёт до клиента как обычно.
    new_booking = await create_booking(
        BookingCreate(
            client_id=booking.client_id,
            car_id=booking.car_id,
            start_at=data.start_at,
            service_ids=[work.service_id],
        ),
        session,
    )

    # create_booking() выше сам коммитит — блокировка `work` от FOR UPDATE
    # снята вместе с этим commit'ом раньше, чем мы успели пометить работу
    # согласованной. Перепроверяем статус заново под новой блокировкой,
    # чтобы не задвоить визит, если кто-то параллельно успел ответить на то
    # же предложение в этом узком окне.
    work = (
        await session.execute(
            select(AdditionalWork).where(AdditionalWork.id == work_id).with_for_update()
        )
    ).scalar_one_or_none()
    if work is None or work.status != AdditionalWorkStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail="Предложение уже обработано в другом запросе — новый визит создан, но не привязан",
        )

    work.status = AdditionalWorkStatus.APPROVED
    work.scheduled_booking_id = new_booking.id
    await session.commit()
    await session.refresh(work)
    publish("additional_work_responded", AdditionalWorkRead.model_validate(work).model_dump(mode="json"))
    return work


@router.post("/additional-works/schedule-batch", response_model=list[AdditionalWorkRead])
async def schedule_additional_works_batch(
    data: AdditionalWorkScheduleBatch, session: AsyncSession = Depends(get_session)
) -> list[AdditionalWork]:
    """Найдено пользователем на практике (2026-09-17): когда на посту уже
    очередь, НЕСКОЛЬКИМ доп. работам по одной заявке одновременно может не
    хватить места — раньше клиенту приходилось выбирать время отдельно для
    КАЖДОЙ (см. schedule_additional_work выше). Здесь — тот же принцип, но
    сразу для группы работ: одна новая заявка со всеми их услугами разом,
    один выбор времени."""
    if not data.work_ids:
        raise HTTPException(status_code=422, detail="Список работ пуст")

    works = (
        await session.execute(
            select(AdditionalWork).where(AdditionalWork.id.in_(data.work_ids)).with_for_update()
        )
    ).scalars().all()
    if len(works) != len(set(data.work_ids)):
        raise HTTPException(status_code=404, detail="Одно или несколько предложений не найдены")
    if len({w.booking_id for w in works}) != 1:
        raise HTTPException(status_code=409, detail="Все работы в одном визите должны относиться к одной заявке")
    for w in works:
        if w.status != AdditionalWorkStatus.PENDING:
            raise HTTPException(
                status_code=409, detail=f"На предложение №{w.id} уже есть ответ: '{w.status.value}'"
            )
        if w.service_id is None:
            raise HTTPException(
                status_code=409,
                detail=f"Услуга для предложения №{w.id} больше не существует в каталоге — отдельный визит невозможен",
            )

    booking = await session.get(Booking, works[0].booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    # Переиспользуем сам эндпоинт создания заявки — та же конкурентно-
    # безопасная проверка слота/поста/машины (A4), что и у обычной записи;
    # длительность нового визита складывается из ВСЕХ переданных услуг сразу.
    new_booking = await create_booking(
        BookingCreate(
            client_id=booking.client_id,
            car_id=booking.car_id,
            start_at=data.start_at,
            service_ids=[w.service_id for w in works],
        ),
        session,
    )

    # create_booking() выше сам коммитит — блокировка от FOR UPDATE снята
    # вместе с этим commit'ом раньше, чем мы успели пометить работы
    # согласованными. Перепроверяем заново под новой блокировкой (тот же
    # приём, что и в schedule_additional_work) — если кто-то параллельно
    # успел ответить хоть на одну из них в этом узком окне, не задваиваем
    # визит для остальных молча.
    works = (
        await session.execute(
            select(AdditionalWork).where(AdditionalWork.id.in_(data.work_ids)).with_for_update()
        )
    ).scalars().all()
    if any(w.status != AdditionalWorkStatus.PENDING for w in works):
        raise HTTPException(
            status_code=409,
            detail="Одно из предложений уже обработано в другом запросе — новый визит создан, но не привязан",
        )

    for w in works:
        w.status = AdditionalWorkStatus.APPROVED
        w.scheduled_booking_id = new_booking.id
    await session.commit()
    for w in works:
        await session.refresh(w)
    for w in works:
        publish("additional_work_responded", AdditionalWorkRead.model_validate(w).model_dump(mode="json"))
    return works
