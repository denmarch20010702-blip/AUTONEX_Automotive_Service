from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.models import Client, OutboxEmail
from app.services.outbox_email import send_stub_email

# B6 (2026-09-15, уточнено вопросом пользователю): это НЕ напоминание только
# тем, кто уже хранит шины — это промо-приглашение ВСЕМ зарегистрированным
# клиентам, даже тем, кто никогда не сдавал шины и не пользовался услугами.
# Цель — рассказать про саму услугу сезонного хранения и мягко подтолкнуть
# добавить машину/записаться, если клиент этого ещё не делал (прямая
# формулировка пользователя).
#
# "Сезон" для этой фичи — не 4 календарных, а 2 момента в году, совпадающие
# с реальной сезонной переобувкой (решение пользователя): 15 апреля — пора
# сдавать зимнюю резину на хранение (переобулись в летнюю); 15 октября —
# пора забирать её обратно (переобулись в зимнюю).
SPRING_TRIGGER = (4, 15)
AUTUMN_TRIGGER = (10, 15)


def current_tire_season_label(today: date) -> str:
    """Определяет, какой сезонный триггер был последним ПЕРЕД (или в)
    сегодняшний день — именно он определяет текущее "окно" напоминания.
    Год у "осень" может быть предыдущим относительно `today`, если сейчас
    ещё не наступило 15 апреля этого года (тогда последний реальный триггер —
    осень прошлого года, ещё не сброшенная новым сезоном)."""
    spring = date(today.year, *SPRING_TRIGGER)
    autumn = date(today.year, *AUTUMN_TRIGGER)
    if today >= autumn:
        return f"осень {today.year}"
    if today >= spring:
        return f"весна {today.year}"
    return f"осень {today.year - 1}"


async def send_seasonal_tire_reminders(session: AsyncSession) -> int:
    """Отправляет ровно одно приглашение за текущий сезон каждому клиенту,
    которому его ещё не отправляли. Идемпотентность — без отдельного флага
    или таблицы: тема письма содержит сезон+год, и клиент, у которого уже
    есть в `outbox_emails` письмо с ТОЧНО такой темой, пропускается. Тот же
    принцип защиты от дублей, что и у B3 (`Booking.reminder_sent`), но
    сезонное напоминание не привязано к одной записи, поэтому естественнее
    держать признак "уже отправлено" на самом письме, а не заводить новую
    таблицу/колонку только под это."""
    today = datetime.now(timezone.utc).date()
    season_label = current_tire_season_label(today)
    subject = f"Сезонное напоминание: хранение шин — {season_label}"

    already_notified = set(
        (
            await session.execute(select(OutboxEmail.to).where(OutboxEmail.subject == subject))
        )
        .scalars()
        .all()
    )

    clients = (await session.execute(select(Client))).scalars().all()
    sent = 0
    for client in clients:
        if client.email in already_notified:
            continue
        await send_stub_email(
            session,
            to=client.email,
            subject=subject,
            body=(
                "Напоминаем: наша станция принимает шины на сезонное хранение — "
                "можно освободить место в гараже или багажнике на весь сезон. "
                "Если вы ещё не привозили к нам машину — отличный повод "
                "познакомиться с сервисом: добавьте автомобиль и запишитесь "
                "на любую услугу в личном кабинете."
            ),
        )
        sent += 1
    await session.commit()
    return sent


async def _tire_season_sweep() -> None:
    async with async_session() as session:
        await send_seasonal_tire_reminders(session)


def schedule_tire_season_sweep(scheduler) -> None:
    # Раз в сутки достаточно (см. buisness/ARCHITECTURE.md: "фоновая задача
    # APScheduler ежедневно проверяет... сезон замены шин") — идемпотентность
    # по теме письма делает частые повторные срабатывания безопасными (в
    # отличие от overdue_bookings.py, здесь повторная отправка невозможна по
    # конструкции, а не только "статистически редка"), поэтому мгновенный
    # первый запуск не опасен.
    scheduler.add_job(
        _tire_season_sweep,
        "interval",
        hours=24,
        id="tire-season-reminder-sweep",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),
    )
