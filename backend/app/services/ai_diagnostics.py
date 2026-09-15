from __future__ import annotations

import json
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models import (
    AdditionalWork,
    AdditionalWorkStatus,
    Booking,
    Car,
    ProposedBy,
    Service,
)
from app.schemas.additional_work import AdditionalWorkRead
from app.services.events import publish
from app.services.outbox_email import send_stub_email

# C4 (2026-09-15) — "AI Diagnostic Assistant" из buisness.md: запускается
# сразу после приёма машины на пост, параллельно с началом основной услуги
# (см. вызов в app/api/bookings.py, тем же местом, что запускает автотаймер
# C2), и по профилю машины предлагает клиенту доп. работу — если есть повод.
# Согласование остаётся обязательным шагом клиента (B2, C1) — этот модуль
# только предлагает, как раньше делал это мастер вручную через тот же
# каталог услуг, а не решает и не выполняет что-то за клиента.
#
# Честное упрощение (нет данных для большего): buisness.md описывает анализ
# "ошибок" и "истории обслуживания" — в проекте нет отдельной сущности для
# кодов неисправностей/истории ремонтов, единственный реальный сигнал о
# состоянии машины — пробег с последнего ТО (тот же, что уже использует B5).
# Pluggable-интерфейс ниже не привязан к этому конкретному сигналу — при
# появлении новых полей на Car/Booking рефакторинг понадобится только внутри
# _rule_based_pick/_llm_pick, не в вызывающем коде.
MILEAGE_THRESHOLD_KM = 10_000
KEYWORD_HINTS = ("масл", "тормоз", "фильтр", "ремен", "диагностик", "жидкост", "свеч", "колод")


@dataclass
class DiagnosticSuggestion:
    service_id: int
    confidence: float  # 0..1 — "вероятность неисправности" из buisness.md
    reason: str


async def _catalog_candidates(session: AsyncSession, booking: Booking) -> list[Service]:
    # Не предлагаем то, что уже входит в эту заявку или уже было предложено
    # (в любом статусе, кроме отклонённого — отклонённое можно предложить
    # снова, если машина всё ещё на посту в следующий раз).
    already = {s.id for s in booking.services}
    proposed = (
        await session.execute(
            select(AdditionalWork.service_id).where(
                AdditionalWork.booking_id == booking.id,
                AdditionalWork.status != AdditionalWorkStatus.DECLINED,
            )
        )
    ).scalars().all()
    already.update(sid for sid in proposed if sid is not None)
    services = (await session.execute(select(Service))).scalars().all()
    return [s for s in services if s.id not in already]


def _rule_based_pick(car: Car, candidates: list[Service]) -> DiagnosticSuggestion | None:
    if car.mileage_at_last_service is None:
        return None  # нет истории ТО — нет базы для сравнения (тот же принцип, что и B5)
    km_since = car.mileage - car.mileage_at_last_service
    if km_since < MILEAGE_THRESHOLD_KM:
        return None
    matches = [s for s in candidates if any(k in s.name.lower() for k in KEYWORD_HINTS)]
    if not matches:
        return None
    pick = min(matches, key=lambda s: s.price)
    confidence = min(0.95, 0.5 + (km_since - MILEAGE_THRESHOLD_KM) / (2 * MILEAGE_THRESHOLD_KM))
    return DiagnosticSuggestion(
        service_id=pick.id,
        confidence=round(confidence, 2),
        reason=(
            f"{car.make} {car.model}: пробег с последнего ТО {km_since} км — "
            f"похоже, пора проверить «{pick.name}»."
        ),
    )


async def _llm_pick(car: Car, candidates: list[Service]) -> DiagnosticSuggestion | None:
    if not candidates:
        return None
    catalog_text = "\n".join(
        f"- id={s.id}: {s.name} ({s.price} ₽, {s.duration_minutes} мин)" for s in candidates
    )
    prompt = (
        "Ты — диагностический ассистент автосервиса. По профилю автомобиля определи, "
        "стоит ли предложить клиенту ровно одну дополнительную услугу из каталога прямо сейчас.\n"
        f"Автомобиль: {car.make} {car.model}, текущий пробег {car.mileage} км, "
        f"пробег на момент последнего ТО: {car.mileage_at_last_service}.\n"
        f"Каталог доступных услуг:\n{catalog_text}\n\n"
        'Ответь СТРОГО в виде JSON без пояснений вокруг: '
        '{"service_id": <int или null>, "confidence": <число 0..1>, "reason": "<кратко по-русски>"}. '
        "Если предлагать нечего — service_id: null."
    )
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        response = await http_client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.llm_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response.raise_for_status()
        text = response.json()["content"][0]["text"]

    data = json.loads(text)
    service_id = data.get("service_id")
    if service_id is None:
        return None
    match = next((s for s in candidates if s.id == service_id), None)
    if match is None:
        return None
    return DiagnosticSuggestion(
        service_id=match.id,
        confidence=float(data.get("confidence", 0.5)),
        reason=str(data.get("reason", "")),
    )


async def generate_diagnostic_suggestion(
    session: AsyncSession, booking: Booking, car: Car
) -> DiagnosticSuggestion | None:
    """Pluggable по конструкции (см. C1/ARCHITECTURE.md): реальный вызов LLM,
    если в `.env` задан LLM_API_KEY, иначе rule-based генератор с тем же
    контрактом. Любой сбой LLM (сеть, невалидный JSON, лимиты) — честный
    фолбэк на rule-based, а не ошибка наружу: диагностика необязательна для
    приёма машины на пост."""
    candidates = await _catalog_candidates(session, booking)
    if not candidates:
        return None
    if settings.llm_api_key:
        try:
            return await _llm_pick(car, candidates)
        except Exception:
            pass
    return _rule_based_pick(car, candidates)


async def run_ai_diagnostic(session: AsyncSession, booking_id: int) -> AdditionalWork | None:
    """Точка входа, вызываемая сразу после приёма машины на пост (см.
    app/api/bookings.py::update_booking_status). Сама коммитит свою транзакцию
    отдельно от коммита перехода в on_post — вызывающий код оборачивает
    вызов в try/except, чтобы сбой диагностики никогда не ронял сам приём
    машины на пост."""
    booking = (
        await session.execute(
            select(Booking)
            .options(
                selectinload(Booking.services),
                selectinload(Booking.car),
                selectinload(Booking.client),
            )
            .where(Booking.id == booking_id)
        )
    ).scalar_one_or_none()
    if booking is None:
        return None

    suggestion = await generate_diagnostic_suggestion(session, booking, booking.car)
    if suggestion is None:
        return None

    service = await session.get(Service, suggestion.service_id)
    if service is None:
        return None

    work = AdditionalWork(
        booking_id=booking.id,
        description=service.name,
        price=service.price,
        duration_minutes=service.duration_minutes,
        service_id=service.id,
        proposed_by=ProposedBy.AI,
    )
    session.add(work)

    await send_stub_email(
        session,
        to=booking.client.email,
        subject=f"Заявка №{booking.id}: ИИ-диагностика нашла повод для доп. работы",
        body=(
            f"{suggestion.reason} Предложение: {service.name} — {service.price} ₽ "
            f"(вероятность {round(suggestion.confidence * 100)}%). "
            "Подтвердите или отклоните в личном кабинете."
        ),
    )

    await session.commit()
    await session.refresh(work)
    publish("additional_work_proposed", AdditionalWorkRead.model_validate(work).model_dump(mode="json"))
    return work
