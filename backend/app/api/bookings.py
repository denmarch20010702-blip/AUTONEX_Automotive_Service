from __future__ import annotations

from datetime import datetime, timedelta, timezone

from decimal import Decimal

from asyncpg.exceptions import DeadlockDetectedError
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models import (
    STATION_STATS_ROW_ID,
    AdditionalWork,
    AdditionalWorkStatus,
    Booking,
    BookingArchive,
    BookingStatus,
    Car,
    Client,
    Post,
    Service,
    StationStats,
)
from app.models.booking import booking_services
from app.schemas.booking import BookingCreate, BookingReschedule, BookingRead, BookingStatusUpdate, SlotOption
from app.services.ai_diagnostics import run_ai_diagnostic
from app.services.booking_status import is_transition_allowed
from app.services.events import publish
from app.services.robot_timer import schedule_auto_advance
from app.services.slots import (
    car_is_free,
    get_available_slots,
    get_bookings_overlapping,
    is_on_slot_grid,
    post_is_free,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("/available-slots", response_model=list[SlotOption])
async def available_slots(
    service_ids: list[int] = Query(...),
    # Точный момент начала "суток", которые хочет видеть клиент (обязательно
    # со смещением часового пояса в строке) — не календарная дата без
    # контекста. См. подробное объяснение в services/slots.py: интерпретация
    # голой даты как UTC-суток рвёт выдачу слотов на границах часового пояса
    # клиента (обнаружено на практике 2026-09-13).
    day_start: datetime = Query(..., alias="date"),
    # B4 (перенос): при выборе нового времени для УЖЕ существующей заявки
    # её собственный старый интервал не должен считаться "занятостью" —
    # иначе заявка вечно конфликтовала бы сама с собой.
    exclude_booking_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    if day_start.tzinfo is None:
        raise HTTPException(status_code=422, detail="date должен содержать часовой пояс")
    return await get_available_slots(
        session, service_ids, day_start, exclude_booking_id=exclude_booking_id
    )


@router.post("", response_model=BookingRead, status_code=201)
async def create_booking(
    data: BookingCreate, session: AsyncSession = Depends(get_session)
) -> Booking:
    # start_at — не то, что клиент вводит руками, а то, что он кликнул в
    # списке available-slots. Значит оно обязано лежать на 15-минутной
    # сетке; всё остальное — либо чужой клиент API, либо баг фронтенда.
    if data.start_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="start_at должен содержать часовой пояс")
    if not is_on_slot_grid(data.start_at):
        raise HTTPException(
            status_code=422,
            detail="start_at должен совпадать с одним из предложенных available-slots",
        )
    if data.start_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Нельзя записаться в прошлое")

    if await session.get(Client, data.client_id) is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")

    # Блокируем строку авто ДО поиска поста и в том же порядке всегда (авто,
    # затем посты) — той же техникой, что и посты ниже, и по той же причине:
    # чтобы две заявки на одну и ту же машину встали в очередь на этой
    # блокировке, а не гонялись друг с другом за диапазоном в GiST-индексе.
    car = (
        await session.execute(select(Car).where(Car.id == data.car_id).with_for_update())
    ).scalar_one_or_none()
    if car is None:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")
    if car.client_id != data.client_id:
        # Реальный пользователь не может записать машину, которую он сам не
        # добавил себе в аккаунт — только свои автомобили.
        raise HTTPException(status_code=403, detail="Автомобиль не принадлежит этому клиенту")

    services_result = await session.execute(
        select(Service).where(Service.id.in_(data.service_ids))
    )
    services = list(services_result.scalars().all())
    if len(services) != len(set(data.service_ids)):
        raise HTTPException(status_code=404, detail="Одна или несколько услуг не найдены")

    # Конец слота — не то, что вводит клиент, а прямое следствие выбранных
    # услуг: клиент называет только желаемое время начала.
    duration = timedelta(minutes=sum(s.duration_minutes for s in services))
    if duration <= timedelta(0):
        raise HTTPException(status_code=422, detail="Список услуг пуст или некорректен")
    end_at = data.start_at + duration

    # Найдено вручную: одна и та же машина физически не может обслуживаться
    # на нескольких постах одновременно — эту проверку нельзя выразить как
    # "хотя бы один пост свободен", в отличие от постов, поэтому она отдельно.
    if not await car_is_free(session, data.car_id, data.start_at, end_at):
        raise HTTPException(status_code=409, detail="Автомобиль уже записан на это время")

    # Клиенту не важно, на каком посту его обслужат — пост подбирается
    # автоматически. Блокируем строки ВСЕХ постов в одном, всегда одинаковом
    # порядке (по id): конкурентные заявки на одно и то же время встают в
    # очередь на этой блокировке, а не гоняются друг с другом за диапазоном
    # в GiST-индексе EXCLUDE-ограничения — иначе Postgres иногда обнаруживает
    # deadlock между такими транзакциями вместо чистой ошибки ограничения
    # (проверено на практике при разработке A4).
    posts = (
        (await session.execute(select(Post).order_by(Post.id).with_for_update()))
        .scalars()
        .all()
    )
    bookings_by_post = await get_bookings_overlapping(session, data.start_at, end_at)
    free_post = next(
        (p for p in posts if post_is_free(bookings_by_post.get(p.id, []), data.start_at, end_at)),
        None,
    )
    if free_post is None:
        raise HTTPException(status_code=409, detail="Все посты заняты в это время")

    booking = Booking(
        client_id=data.client_id,
        car_id=data.car_id,
        post_id=free_post.id,
        start_at=data.start_at,
        end_at=end_at,
        services=services,
    )
    session.add(booking)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Слот уже занят")
    except DBAPIError as exc:
        await session.rollback()
        # Defense in depth: если блокировка поста выше почему-то не спасла
        # (например, будущий код обойдёт её) — распознаём deadlock именно
        # как проигранную гонку за слот, а не маскируем случайную ошибку БД.
        if isinstance(exc.orig, DeadlockDetectedError):
            raise HTTPException(status_code=409, detail="Слот уже занят")
        raise
    # Обычный `refresh()` не подгружает `services` (relationship "протухает"
    # после commit) — без явного eager-load ниже Pydantic упал бы на попытке
    # лениво дочитать её в асинхронной сессии (MissingGreenlet).
    booking = (
        await session.execute(
            select(Booking).options(selectinload(Booking.services)).where(Booking.id == booking.id)
        )
    ).scalar_one()
    publish("booking_created", BookingRead.model_validate(booking).model_dump(mode="json"))
    return booking


@router.post("/{booking_id}/reschedule", response_model=BookingRead)
async def reschedule_booking(
    booking_id: int, data: BookingReschedule, session: AsyncSession = Depends(get_session)
) -> Booking:
    # B4: перенос вместо отмены+повторной записи — тот же набор услуг и
    # машины, только новое время. Разрешён только пока заявка ещё не
    # принята на пост: перенести уже начатое/законченное обслуживание
    # физически не имеет смысла.
    if data.start_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="start_at должен содержать часовой пояс")
    if not is_on_slot_grid(data.start_at):
        raise HTTPException(
            status_code=422,
            detail="start_at должен совпадать с одним из предложенных available-slots",
        )
    if data.start_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Нельзя перенести запись в прошлое")

    # Тот же порядок блокировок, что и в create_booking (авто → посты), по
    # той же причине — избежать deadlock между конкурентными операциями.
    booking = (
        await session.execute(
            select(Booking)
            .options(selectinload(Booking.services))
            .where(Booking.id == booking_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if booking is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if booking.status != BookingStatus.ACCEPTED:
        raise HTTPException(
            status_code=409,
            detail=f"Перенос возможен только для заявки в статусе 'accepted', сейчас '{booking.status.value}'",
        )

    car = (
        await session.execute(select(Car).where(Car.id == booking.car_id).with_for_update())
    ).scalar_one()

    duration = timedelta(minutes=sum(s.duration_minutes for s in booking.services))
    new_end_at = data.start_at + duration

    if not await car_is_free(
        session, car.id, data.start_at, new_end_at, exclude_booking_id=booking.id
    ):
        raise HTTPException(status_code=409, detail="Автомобиль уже записан на это время")

    posts = (
        (await session.execute(select(Post).order_by(Post.id).with_for_update()))
        .scalars()
        .all()
    )
    bookings_by_post = await get_bookings_overlapping(
        session, data.start_at, new_end_at, exclude_booking_id=booking.id
    )
    free_post = next(
        (p for p in posts if post_is_free(bookings_by_post.get(p.id, []), data.start_at, new_end_at)),
        None,
    )
    if free_post is None:
        raise HTTPException(status_code=409, detail="Все посты заняты в это время")

    booking.start_at = data.start_at
    booking.end_at = new_end_at
    booking.post_id = free_post.id
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Слот уже занят")
    except DBAPIError as exc:
        await session.rollback()
        if isinstance(exc.orig, DeadlockDetectedError):
            raise HTTPException(status_code=409, detail="Слот уже занят")
        raise

    booking = (
        await session.execute(
            select(Booking).options(selectinload(Booking.services)).where(Booking.id == booking.id)
        )
    ).scalar_one()
    snapshot = BookingRead.model_validate(booking).model_dump(mode="json")
    publish("booking_rescheduled", snapshot)
    return booking


@router.get("", response_model=list[BookingRead])
async def list_bookings(
    client_id: int | None = None, session: AsyncSession = Depends(get_session)
) -> list[Booking]:
    query = (
        select(Booking).options(selectinload(Booking.services)).order_by(Booking.start_at)
    )
    if client_id is not None:
        query = query.where(Booking.client_id == client_id)
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/{booking_id}", response_model=BookingRead)
async def get_booking(booking_id: int, session: AsyncSession = Depends(get_session)) -> Booking:
    booking = (
        await session.execute(
            select(Booking)
            .options(selectinload(Booking.services))
            .where(Booking.id == booking_id)
        )
    ).scalar_one_or_none()
    if booking is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return booking


@router.post("/{booking_id}/status", response_model=BookingRead)
async def update_booking_status(
    booking_id: int, data: BookingStatusUpdate, session: AsyncSession = Depends(get_session)
) -> BookingRead:
    # Блокируем строку заявки — та же техника, что уже дважды сработала в
    # A4 (пост, авто): два одновременных запроса сменить статус одной и той
    # же заявки встают в очередь на этой блокировке, а не гонятся друг с
    # другом. Второй запрос увидит уже обновлённый статус первого и получит
    # честный 409, если повторный/недопустимый переход.
    booking = (
        await session.execute(
            select(Booking)
            .options(
                selectinload(Booking.services),
                selectinload(Booking.client),
                selectinload(Booking.car),
            )
            .where(Booking.id == booking_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if booking is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    if not is_transition_allowed(booking.status, data.status):
        raise HTTPException(
            status_code=409,
            detail=f"Нельзя перейти из статуса '{booking.status.value}' в '{data.status.value}'",
        )

    # Снимаем ДО перезаписи ниже — нужно, чтобы отличить настоящий "заезд"
    # машины (accepted -> on_post) от возврата на пост для отработки уже
    # согласованной доп. работы (см. resolve_next_step в robot_timer.py,
    # который трогает on_post иначе, не через этот эндпоинт) — ИИ-диагностика
    # (C4) должна запускаться только один раз, при первом заезде.
    previous_status = booking.status

    # Реальный найденный баг (2026-09-14): ничто не мешало принять машину на
    # пост (и запустить автотаймер обслуживания, п.7/C2) намного раньше
    # назначенного `start_at` — таймер отталкивается от момента нажатия
    # кнопки, а не от расписания, поэтому заявка "работала" ещё до
    # назначенного времени визита. Машина физически не может быть принята в
    # обслуживание до того, как настало её время.
    if data.status == BookingStatus.ON_POST and datetime.now(timezone.utc) < booking.start_at:
        raise HTTPException(
            status_code=409,
            detail=(
                "Нельзя принять на пост раньше назначенного времени "
                f"({booking.start_at.isoformat()})"
            ),
        )

    # Заметка пользователя (B2, уточнение 2026-09-13): пока клиент не принял
    # или не отклонил предложенную доп. работу, статус заявки дальше не
    # меняется — кроме отмены самой заявки (в любой момент) и входа в само
    # "ожидает согласования" (это как раз и означает "ждём ответа клиента",
    # а не обход его решения).
    if data.status != BookingStatus.CANCELLED:
        has_pending = (
            await session.execute(
                select(AdditionalWork.id)
                .where(
                    AdditionalWork.booking_id == booking.id,
                    AdditionalWork.status == AdditionalWorkStatus.PENDING,
                )
                .limit(1)
            )
        ).first()
        if has_pending is not None and data.status != BookingStatus.AWAITING_APPROVAL:
            raise HTTPException(
                status_code=409,
                detail="Есть неотвеченное предложение доп. работы — статус не меняется, пока клиент не ответит",
            )

        # UI_description.md п.13: раньше "ожидает согласования" можно было
        # выставить вручную без единого реального предложения доп. работы —
        # ровно то, что запутывало пользователя ("непонятно, зачем нужно
        # согласование, если оно не отправляется клиенту"). Теперь входить в
        # этот статус вручную бессмысленно и запрещено, если согласовывать
        # реально нечего.
        if has_pending is None and data.status == BookingStatus.AWAITING_APPROVAL:
            raise HTTPException(
                status_code=409,
                detail="Нет неотвеченных предложений доп. работы — нечего согласовывать",
            )

    booking.status = data.status

    # UI_description.md п.11: таймер до завершения должен быть виден и
    # станции, и клиенту — точку отсчёта фиксируем на самой заявке в момент
    # приёма на пост (тот же момент, что запускает автотаймер ниже), а не
    # только внутри задачи планировщика.
    on_post_duration_minutes = sum(s.duration_minutes for s in booking.services)
    if data.status == BookingStatus.ON_POST:
        new_ends_at = datetime.now(timezone.utc) + timedelta(minutes=on_post_duration_minutes)
        booking.service_ends_at = new_ends_at
        # UI_description.md п.35 (2026-09-14): если станция принимает машину
        # на пост позже запланированного `start_at` (реальная задержка), то
        # реальное занятие поста заканчивается позже, чем `end_at`,
        # рассчитанный при создании заявки — а именно `end_at` проверяют
        # EXCLUDE-ограничения A4/`car_is_free`/`get_available_slots`. Без
        # этой синхронизации новая заявка могла бы занять тот же пост или ту
        # же машину на время, которое по факту ещё занято. Сужать `end_at`
        # никогда не нужно — только расширять.
        if new_ends_at > booking.end_at:
            booking.end_at = new_ends_at

    # Оба терминальных статуса (issued/cancelled) убирают заявку из
    # активного списка — слот освобождается, как и раньше, но сама заявка
    # не пропадает: переезжает в BookingArchive для просмотра при
    # необходимости (по прямой просьбе пользователя, 2026-09-12). Выручка
    # начисляется только за реально выполненную работу (issued), не за
    # отменённую.
    completing = data.status == BookingStatus.ISSUED
    archiving = data.status in (BookingStatus.ISSUED, BookingStatus.CANCELLED)

    try:
        # Найденный баг (2026-09-15, всплыл на реальном тест-кейсе п.39):
        # этот `flush()` раньше стоял ДО защищённого `try` ниже — если
        # продление occupancy при приёме на пост (п.35 выше) пересекалось с
        # чужой заявкой, EXCLUDE-ограничение падало прямо здесь необработанным
        # 500, а не доходило до честного 409. Тот же класс бага, что уже
        # чинился в respond_additional_work (см. app/api/additional_works.py,
        # п.37) — здесь этот путь никто не проверял отдельным тестом, потому
        # что обычно до него просто не доходило дело при штатном приёме на
        # пост вовремя.
        await session.flush()
        # Снимок для ответа/события снимаем ДО удаления ниже — после удаления
        # обращаться к атрибутам ORM-объекта уже нельзя.
        snapshot = BookingRead.model_validate(booking).model_dump(mode="json")

        if archiving:
            total = sum((service.price for service in booking.services), start=Decimal("0"))

            # additional_works имеет FK на bookings без каскада — без явного
            # удаления его строк здесь DELETE FROM bookings падал с
            # IntegrityError (500), если у заявки было хоть одно предложение
            # доп. работы (найдено на практике 2026-09-13). Сохраняем снимком в
            # архив по той же логике, что и services_snapshot, а не молча теряем.
            additional_works = (
                await session.execute(
                    select(AdditionalWork).where(AdditionalWork.booking_id == booking.id)
                )
            ).scalars().all()
            additional_works_snapshot = [
                {
                    "id": w.id,
                    "description": w.description,
                    "price": str(w.price),
                    "proposed_by": w.proposed_by.value,
                    "status": w.status.value,
                    # Явно видно в архиве, почему одобренная работа не вошла в
                    # total_price этой заявки — перенесена на отдельный визит
                    # (см. фильтр по scheduled_booking_id ниже).
                    "scheduled_booking_id": w.scheduled_booking_id,
                }
                for w in additional_works
            ]

            # UI_description.md п.14: деньги за согласованные доп. работы
            # начисляются только при сдаче машины (issued), сверх суммы за
            # изначальную услугу — не в момент согласования. Отклонённые/ещё не
            # отвеченные (последних тут уже быть не может — см. guard выше) в
            # сумму не входят.
            if completing:
                # Найденный пользователем реальный баг (2026-09-15): работа,
                # одобренная, но перенесённая на ОТДЕЛЬНЫЙ будущий визит
                # (п.37/38 — `scheduled_booking_id` заполнен, см.
                # schedule_additional_work в additional_works.py), ещё не
                # выполнена — деньги за неё не должны попадать в счётчик
                # выручки СЕЙЧАС, при выдаче основной машины. Иначе клиент
                # платит за услугу, которую фактически ещё не оказали, а
                # когда отдельный визит реально пройдёт и будет выдан — эта
                # же сумма начислится ЕЩЁ РАЗ (через total_price его
                # собственной услуги), то есть без этого фильтра деньги
                # задваивались бы.
                total += sum(
                    (
                        w.price
                        for w in additional_works
                        if w.status == AdditionalWorkStatus.APPROVED and w.scheduled_booking_id is None
                    ),
                    start=Decimal("0"),
                )
                await session.execute(
                    update(StationStats)
                    .where(StationStats.id == STATION_STATS_ROW_ID)
                    .values(total_revenue=StationStats.total_revenue + total)
                )
                # UI_description.md п.31 (2026-09-14): "дата последнего
                # обслуживания" на машине должна сама обновляться на дату, когда
                # обслуживание реально прошло — `service_ends_at` — момент,
                # рассчитанный автотаймером (C2), точнее отражает это, чем
                # "сейчас" (когда станция нажала "выдать", может быть позже).
                booking.car.last_service_date = (booking.service_ends_at or booking.end_at).date()
                # B5: пробег на момент ЭТОГО ТО — основа для расчёта "пробег с
                # последнего ТО" в проактивном предложении записи.
                booking.car.mileage_at_last_service = booking.car.mileage
            session.add(
                BookingArchive(
                    original_booking_id=booking.id,
                    client_id=booking.client_id,
                    client_name=booking.client.name,
                    client_email=booking.client.email,
                    car_id=booking.car_id,
                    car_make=booking.car.make,
                    car_model=booking.car.model,
                    post_id=booking.post_id,
                    start_at=booking.start_at,
                    end_at=booking.end_at,
                    status=booking.status,
                    total_price=total,
                    services_snapshot=[
                        {
                            "id": s.id,
                            "name": s.name,
                            "price": str(s.price),
                            "duration_minutes": s.duration_minutes,
                        }
                        for s in booking.services
                    ],
                    additional_works_snapshot=additional_works_snapshot,
                    created_at=booking.created_at,
                )
            )
            await session.execute(
                delete(booking_services).where(booking_services.c.booking_id == booking.id)
            )
            await session.execute(delete(AdditionalWork).where(AdditionalWork.booking_id == booking.id))
            await session.delete(booking)

        await session.commit()
    except IntegrityError:
        # Расширение `end_at` выше (п.35) в редком случае может пересечься
        # с чужой заявкой, которая успела встать в промежуток раньше —
        # честный 409 вместо 500, тот же принцип, что и в create_booking.
        await session.rollback()
        raise HTTPException(status_code=409, detail="Пост или машина заняты на продлённое время")

    publish("booking_status_changed", snapshot)
    if completing:
        publish("booking_completed", snapshot)

    # Заметка пользователя: после приёма машины на пост обслуживание должно
    # само пойти по таймеру — длительность = сумма длительностей выбранных
    # услуг. Пилотная часть C2 (без очереди/симуляции сбоев).
    if data.status == BookingStatus.ON_POST:
        schedule_auto_advance(booking.id, timedelta(minutes=on_post_duration_minutes))

        # C4 (2026-09-15) — "AI Diagnostic Assistant" из buisness.md:
        # запускается сразу после заезда машины, параллельно с началом
        # основной услуги — но только при настоящем заезде (accepted ->
        # on_post), не при возврате на пост ради уже согласованной доп.
        # работы. Обёрнут в try/except намеренно: диагностика необязательна
        # для приёма машины на пост — её сбой (БД, сеть до LLM) не должен
        # превращать успешный приём в 500 клиенту станции.
        if previous_status == BookingStatus.ACCEPTED:
            try:
                await run_ai_diagnostic(session, booking.id)
            except Exception:
                pass

    return BookingRead(**snapshot)
