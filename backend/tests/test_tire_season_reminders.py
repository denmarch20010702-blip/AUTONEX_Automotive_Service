"""B6 (2026-09-15) — сезонное промо-приглашение про хранение шин. Не
напоминание существующим клиентам хранилища — прямая уточнённая просьба
пользователя: рассылка ВСЕМ зарегистрированным клиентам (даже тем, кто
никогда не хранил шины), дважды в год (весна/осень), ровно одно письмо за
сезон на клиента. Тестируем логику напрямую (как send_due_reminders в B3),
не через реальный APScheduler — см. helpers.py и test_reminders.py."""

from datetime import date
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from app.db.session import async_session
from app.models import OutboxEmail
from app.services.tire_season_reminders import (
    current_tire_season_label,
    send_seasonal_tire_reminders,
)


def unique_email() -> str:
    return f"{uuid4().hex}@example.com"


async def outbox_subjects_for(to: str) -> list[str]:
    async with async_session() as session:
        result = await session.execute(select(OutboxEmail.subject).where(OutboxEmail.to == to))
        return list(result.scalars().all())


async def delete_outbox(to: str) -> None:
    async with async_session() as session:
        await session.execute(sa_delete(OutboxEmail).where(OutboxEmail.to == to))
        await session.commit()


@pytest.mark.parametrize(
    "today, expected",
    [
        (date(2027, 4, 15), "весна 2027"),
        (date(2027, 4, 14), "осень 2026"),
        (date(2027, 10, 15), "осень 2027"),
        (date(2027, 10, 14), "весна 2027"),
        (date(2027, 1, 1), "осень 2026"),
        (date(2027, 12, 31), "осень 2027"),
    ],
)
def test_current_tire_season_label(today: date, expected: str) -> None:
    assert current_tire_season_label(today) == expected


@pytest.mark.asyncio
async def test_seasonal_reminder_sent_to_every_client_including_those_without_history(
    client: AsyncClient,
) -> None:
    # Прямая просьба пользователя: приглашение получают ВСЕ, включая тех, у
    # кого нет ни одной машины/заявки/комплекта шин в истории — это промо,
    # а не сервисное напоминание существующему клиенту хранилища.
    email = unique_email()
    client_resp = await client.post("/clients", json={"email": email, "name": "Без истории"})
    client_id = client_resp.json()["id"]
    try:
        async with async_session() as session:
            sent = await send_seasonal_tire_reminders(session)
        assert sent >= 1

        subjects = await outbox_subjects_for(email)
        assert len(subjects) == 1
        assert subjects[0].startswith("Сезонное напоминание: хранение шин — ")
    finally:
        await delete_outbox(email)
        await client.delete(f"/clients/{client_id}")


@pytest.mark.asyncio
async def test_seasonal_reminder_is_sent_only_once_per_season(client: AsyncClient) -> None:
    email = unique_email()
    client_resp = await client.post("/clients", json={"email": email, "name": "Дважды за сезон"})
    client_id = client_resp.json()["id"]
    try:
        async with async_session() as session:
            first = await send_seasonal_tire_reminders(session)
        async with async_session() as session:
            await send_seasonal_tire_reminders(session)

        assert first >= 1
        # Общий счётчик второго вызова не проверяем напрямую — в общей БД
        # мог за это мгновение появиться другой новый клиент (реальный
        # пользователь), которому это же письмо ещё не отправлялось, и это
        # не баг. Важно только про НАШЕГО клиента — ему письмо не задвоилось.
        subjects = await outbox_subjects_for(email)
        assert len(subjects) == 1
    finally:
        await delete_outbox(email)
        await client.delete(f"/clients/{client_id}")


@pytest.mark.asyncio
async def test_tire_season_reminder_endpoint_reflects_outbox_state(client: AsyncClient) -> None:
    # UI_description.md (2026-09-15, найденный пользователем пробел): раньше
    # приглашение уходило ТОЛЬКО в email-заглушку — в кабинете клиента (в
    # отличие от B3/B5) этого не было видно вообще. Источник истины для
    # этого эндпоинта — та же строка в outbox_emails, что пишет
    # send_seasonal_tire_reminders(), без отдельного флага.
    email = unique_email()
    client_resp = await client.post("/clients", json={"email": email, "name": "Проверка баннера"})
    client_id = client_resp.json()["id"]
    try:
        before = (await client.get(f"/clients/{client_id}/tire-season-reminder")).json()
        assert before["active"] is False

        async with async_session() as session:
            await send_seasonal_tire_reminders(session)

        after = (await client.get(f"/clients/{client_id}/tire-season-reminder")).json()
        assert after["active"] is True
        assert after["season_label"] == before["season_label"]
    finally:
        await delete_outbox(email)
        await client.delete(f"/clients/{client_id}")


@pytest.mark.asyncio
async def test_dismissing_tire_season_reminder_hides_it_until_next_season(client: AsyncClient) -> None:
    # UI_description.md п.44 (2026-09-15): баннер закрывается крестиком и не
    # должен вернуться до конца ТЕКУЩЕГО сезона — письмо в почте при этом
    # никуда не пропадает, закрытие касается только баннера в кабинете.
    email = unique_email()
    client_resp = await client.post("/clients", json={"email": email, "name": "Закрываю баннер"})
    client_id = client_resp.json()["id"]
    try:
        async with async_session() as session:
            await send_seasonal_tire_reminders(session)

        before = (await client.get(f"/clients/{client_id}/tire-season-reminder")).json()
        assert before["active"] is True

        resp = await client.post(f"/clients/{client_id}/tire-season-reminder/dismiss")
        assert resp.status_code == 204

        after = (await client.get(f"/clients/{client_id}/tire-season-reminder")).json()
        assert after["active"] is False

        # Письмо осталось на месте — закрытие баннера его не трогает.
        assert len(await outbox_subjects_for(email)) == 1
    finally:
        await delete_outbox(email)
        await client.delete(f"/clients/{client_id}")
