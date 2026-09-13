from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.models import Booking, Client

# B3: напоминание клиенту за день до записи, ровно одно на заявку. Живая
# `bookings`-таблица уже не содержит issued/cancelled (они архивируются в
# том же переходе — см. app/api/bookings.py), поэтому отдельно исключать эти
# статусы здесь не нужно: если заявка ещё здесь, она ещё предстоит.
REMINDER_WINDOW = timedelta(hours=24)


async def send_due_reminders(session: AsyncSession) -> int:
    """Отправляет напоминание по каждой заявке, до которой осталось не
    больше суток и по которой напоминание ещё не отправлялось. Флаг
    `reminder_sent` делает функцию идемпотентной — периодический вызов
    (см. schedule_reminder_sweep ниже) не может отправить дубликат, даже
    если окно перекрывается между прогонами."""
    from app.services.outbox_email import send_stub_email

    now = datetime.now(timezone.utc)
    due = (
        (
            await session.execute(
                select(Booking)
                .where(
                    Booking.reminder_sent.is_(False),
                    Booking.start_at > now,
                    Booking.start_at <= now + REMINDER_WINDOW,
                )
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    for booking in due:
        client = await session.get(Client, booking.client_id)
        booking.reminder_sent = True
        await send_stub_email(
            session,
            to=client.email if client else "unknown",
            subject=f"Напоминание: заявка №{booking.id} завтра",
            body=(
                f"Ждём тебя {booking.start_at.strftime('%d.%m.%Y в %H:%M')} "
                f"(UTC) — не забудь про этот визит."
            ),
        )
    await session.commit()
    return len(due)


async def _reminder_sweep() -> None:
    async with async_session() as session:
        await send_due_reminders(session)


def schedule_reminder_sweep(scheduler) -> None:
    # Раз в 15 минут достаточно для суточного окна напоминания — не нужна
    # секундная точность, которая требуется для короткого автотаймера C2.
    scheduler.add_job(
        _reminder_sweep,
        "interval",
        minutes=15,
        id="reminder-sweep",
        replace_existing=True,
        next_run_time=datetime.now(timezone.utc),
    )
