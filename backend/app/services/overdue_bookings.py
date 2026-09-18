from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import async_session
from app.models import Booking, BookingStatus
from app.schemas.booking import BookingStatusUpdate
from app.services.outbox_email import send_stub_email
from app.services.slots import get_bookings_overlapping, post_is_free

# Найденный пользователем реальный баг (2026-09-15): заявки, которые
# пропустили своё время приёма на пост (`start_at` в прошлом, никто не
# нажал "Принять на пост" — например, за ночь) просто зависали в статусе
# "принята" навсегда. Когда их всё же пытались принять, `on_post`
# пересчитывает занятость от РЕАЛЬНОГО "сейчас" (см. п.35 в DECISIONS_LOG),
# а не от исходного `start_at` — и если к этому моменту на том же посту уже
# стоит следующая заявка, продлённый интервал старой заявки с ней
# пересекается, и принять её нельзя, пока не обработана следующая. Внешне
# это выглядело как необходимость принимать заявки на посту в "неправильном"
# порядке (сначала более новую, потом старую) — пользователь счёл это
# нелогичным и попросил вместо этого автоматически отменять заявку, как
# только становится ясно, что дальше ждать — значит рисковать существующей
# следующей записью на этом посту.
#
# Ключевое решение (по прямой формулировке пользователя): порог для отмены —
# не фиксированное время ожидания, а именно момент, когда заявку УЖЕ нельзя
# принять прямо сейчас без пересечения с чем-то другим на её посту. До этого
# момента заявка может висеть просроченной сколько угодно — если она никому
# не мешает, спешить с отменой незачем.
#
# MIN_OVERDUE_GRACE — небольшая защитная задержка (2 минуты) ПЕРЕД тем, как
# заявка вообще попадает под эту проверку: без неё, например, тестовый
# хелпер `make_startable_now` (сдвигает `start_at` на "сейчас минус 5 секунд"
# — обычная техника во всём тест-сьюте, не ошибка) рисковал бы попасть под
# отмену этим же джобом, который крутится в живом backend-процессе
# (`--reload`, тот же контейнер, та же БД, что и у pytest) — найдено на
# практике 2026-09-15: джоб отменил заявки прямо посреди прогона тестов.
# Для реального использования 2 минуты — совершенно не спешка (станция
# нажимает "принять" вручную намного быстрее).
MIN_OVERDUE_GRACE = timedelta(minutes=2)
# 5 минут (первое значение) оказались слишком грубыми на практике
# (2026-09-15): пользователь тестирует сценариями с услугами длиной в
# 1-2 минуты, и за 5 минут между прогонами джоба уже проходило несколько
# полных циклов — просроченная заявка успевала стать проблемой (и её
# пытались принять вручную) задолго до того, как джоб успевал её убрать.
# 30 секунд — с запасом меньше, чем `MIN_OVERDUE_GRACE`, так что тестовый
# приём `make_startable_now` ("сейчас минус 5 секунд") всё равно защищён.
SWEEP_INTERVAL_SECONDS = 30

logger = logging.getLogger(__name__)


async def cancel_bookings_that_would_delay_the_queue(session: AsyncSession) -> int:
    """Находит просроченные (`accepted`, `start_at` в прошлом) заявки, приём
    которых прямо сейчас пересёкся бы с другой активной заявкой на том же
    посту, и отменяет их — тем же переходом статуса, что и ручная отмена
    (с архивацией, снятием доп. работ и т.п., см. update_booking_status)."""
    now = datetime.now(timezone.utc)
    overdue = (
        await session.execute(
            select(Booking)
            .options(selectinload(Booking.services), selectinload(Booking.client))
            .where(
                Booking.status == BookingStatus.ACCEPTED,
                Booking.start_at < now - MIN_OVERDUE_GRACE,
            )
        )
    ).scalars().all()

    to_cancel: list[tuple[int, str | None]] = []
    for booking in overdue:
        duration_minutes = sum(s.duration_minutes for s in booking.services)
        # Та же формула, что и у самого приёма на пост (см. ON_POST в
        # update_booking_status) — "как если бы эту заявку приняли прямо
        # сейчас", и только расширяя исходный интервал, никогда не сужая.
        candidate_end = max(booking.end_at, now + timedelta(minutes=duration_minutes))
        bookings_by_post = await get_bookings_overlapping(
            session, booking.start_at, candidate_end, exclude_booking_id=booking.id
        )
        if not post_is_free(bookings_by_post.get(booking.post_id, []), booking.start_at, candidate_end):
            to_cancel.append((booking.id, booking.client.email if booking.client else None))

    # Импорт внутри функции — избегаем цикла модулей на верхнем уровне
    # (bookings.py не импортирует этот файл, но лучше не рисковать порядком
    # загрузки при старте приложения).
    from app.api.bookings import update_booking_status

    cancelled = 0
    for booking_id, client_email in to_cancel:
        try:
            await update_booking_status(booking_id, BookingStatusUpdate(status=BookingStatus.CANCELLED), session)
        except Exception:
            # Гонка (заявку уже приняли/отменили вручную между выборкой и
            # этим циклом) — пропускаем, не роняем весь sweep из-за одной.
            # Явный rollback (D3, 2026-09-18, тот же приём, что и в
            # parking.py::run_parking_sweep, найденный код-ревью 2026-09-18) —
            # без него "грязное" состояние объекта заявки из неудачной
            # попытки осталось бы в сессии до следующего autoflush, рискуя
            # закоммититься случайно вместе со следующей успешной итерацией.
            await session.rollback()
            logger.debug("Skipped overdue booking %s (race or conflict)", booking_id, exc_info=True)
            continue
        cancelled += 1
        if client_email:
            await send_stub_email(
                session,
                to=client_email,
                subject=f"Заявка №{booking_id} отменена автоматически",
                body=(
                    "Вы не успели приехать на приём вовремя, а пост уже "
                    "нужен для следующей записи — заявка отменена автоматически. "
                    "Пожалуйста, запишитесь на новое время."
                ),
            )
            await session.commit()
    if cancelled:
        logger.info("Overdue sweep cancelled %s booking(s)", cancelled)
    return cancelled


async def _overdue_sweep() -> None:
    async with async_session() as session:
        await cancel_bookings_that_would_delay_the_queue(session)


def schedule_overdue_sweep(scheduler) -> None:
    # Без `next_run_time=now()` (в отличие от напоминаний, B3) — этот джоб
    # реально ОТМЕНЯЕТ заявки, и мгновенный первый запуск прямо на старте
    # backend'а (в т.ч. на каждый `--reload` в dev-режиме) слишком легко
    # зацепляет что-то, что в этот момент готовит другой процесс (найдено на
    # практике — см. MIN_OVERDUE_GRACE выше). Первый реальный прогон — через
    # штатный интервал после старта.
    scheduler.add_job(
        _overdue_sweep,
        "interval",
        seconds=SWEEP_INTERVAL_SECONDS,
        id="overdue-bookings-sweep",
        replace_existing=True,
    )
