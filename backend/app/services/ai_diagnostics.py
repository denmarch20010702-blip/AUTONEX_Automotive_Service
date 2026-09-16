from __future__ import annotations

import json
import re
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
from app.services.outbox_email import notify_pending_additional_works

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
# _rule_based_picks/_llm_picks, не в вызывающем коде.
MILEAGE_THRESHOLD_KM = 10_000

# Найдено пользователем на практике (2026-09-15): с широким списком ключевых
# слов (масло/тормоза/фильтр/...) и всего одной предлагаемой услугой на
# заезд ИИ почти всегда выбирал одну и ту же случайную дешёвую услугу —
# невзрачный результат. Решение пользователя: единый класс "регулярного ТО"
# по одному ключевому слову "ТО", и предлагать ВСЕ подходящие услуги сразу,
# а не одну. Матчим по границе слова (не голым substring) — иначе "ТО" ложно
# сработало бы внутри "авТОмобиль", "авТО" и подобных слов.
TO_KEYWORD_PATTERN = re.compile(r"(?<![а-яё])то(?![а-яё])", re.IGNORECASE)


def _matches_keyword_class(service_name: str) -> bool:
    return TO_KEYWORD_PATTERN.search(service_name) is not None


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


def _rule_based_picks(car: Car, candidates: list[Service]) -> list[DiagnosticSuggestion]:
    if car.mileage_at_last_service is None:
        return []  # нет истории ТО — нет базы для сравнения (тот же принцип, что и B5)
    km_since = car.mileage - car.mileage_at_last_service
    if km_since < MILEAGE_THRESHOLD_KM:
        return []
    matches = [s for s in candidates if _matches_keyword_class(s.name)]
    confidence = min(0.95, 0.5 + (km_since - MILEAGE_THRESHOLD_KM) / (2 * MILEAGE_THRESHOLD_KM))
    # Найдено пользователем на практике (2026-09-16): при нескольких
    # подходящих услугах сразу причина повторяла марку/модель/пробег машины
    # в КАЖДОЙ строке панели доп. работ на станции — раздувало колонку без
    # пользы (контекст заявки/машины уже виден на самой странице станции).
    # Причина станции нужна для оверсайта конкретно ЭТОЙ рекомендации, а не
    # для повторного напоминания, какая это машина.
    return [
        DiagnosticSuggestion(
            service_id=match.id,
            confidence=round(confidence, 2),
            reason=f"Плановое ТО по пробегу — рекомендуется «{match.name}».",
        )
        for match in matches
    ]


async def _llm_picks(car: Car, candidates: list[Service]) -> list[DiagnosticSuggestion]:
    if not candidates:
        return []
    catalog_text = "\n".join(
        f"- id={s.id}: {s.name} ({s.price} ₽, {s.duration_minutes} мин)" for s in candidates
    )
    prompt = (
        "Ты — диагностический ассистент автосервиса. По профилю автомобиля определи, "
        "какие дополнительные услуги из каталога стоит предложить клиенту прямо сейчас "
        "(может быть ни одной, одна или несколько).\n"
        f"Автомобиль: {car.make} {car.model}, текущий пробег {car.mileage} км, "
        f"пробег на момент последнего ТО: {car.mileage_at_last_service}.\n"
        f"Каталог доступных услуг:\n{catalog_text}\n\n"
        'Ответь СТРОГО в виде JSON-массива без пояснений вокруг: '
        '[{"service_id": <int>, "confidence": <число 0..1>, "reason": "<кратко по-русски>"}, ...]. '
        "reason — только про эту конкретную услугу, без повтора марки/модели/пробега машины "
        "(они не должны повторяться в каждой причине, если предложено несколько услуг). "
        "Если предлагать нечего — пустой массив []."
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
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response.raise_for_status()
        text = response.json()["content"][0]["text"]

    items = json.loads(text)
    by_id = {s.id: s for s in candidates}
    suggestions = []
    for item in items:
        service_id = item.get("service_id")
        if service_id in by_id:
            suggestions.append(
                DiagnosticSuggestion(
                    service_id=service_id,
                    confidence=float(item.get("confidence", 0.5)),
                    reason=str(item.get("reason", "")),
                )
            )
    return suggestions


async def generate_diagnostic_suggestions(
    session: AsyncSession, booking: Booking, car: Car
) -> list[DiagnosticSuggestion]:
    """Pluggable по конструкции (см. C1/ARCHITECTURE.md): реальный вызов LLM,
    если в `.env` задан LLM_API_KEY, иначе rule-based генератор с тем же
    контрактом. Любой сбой LLM (сеть, невалидный JSON, лимиты) — честный
    фолбэк на rule-based, а не ошибка наружу: диагностика необязательна для
    приёма машины на пост.

    Решение пользователя (2026-09-15): предлагать ВСЕ подходящие услуги
    сразу, не одну — сейчас это простое совпадение по единому классу "ТО"
    (см. TO_KEYWORD_PATTERN); в будущем здесь появится нестатическая логика
    (см. docstring _rule_based_picks и ARCHITECTURE.md, раздел про C4)."""
    candidates = await _catalog_candidates(session, booking)
    if not candidates:
        return []
    if settings.llm_api_key:
        try:
            return await _llm_picks(car, candidates)
        except Exception:
            pass
    return _rule_based_picks(car, candidates)


async def run_ai_diagnostic(session: AsyncSession, booking_id: int) -> list[AdditionalWork]:
    """Точка входа, вызываемая сразу после приёма машины на пост (см.
    app/api/bookings.py::update_booking_status). Сама коммитит свою транзакцию
    отдельно от коммита перехода в on_post — вызывающий код оборачивает
    вызов в try/except, чтобы сбой диагностики никогда не ронял сам приём
    машины на пост. Возвращает все созданные предложения (может быть
    несколько за один заезд, см. generate_diagnostic_suggestions)."""
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
        return []

    suggestions = await generate_diagnostic_suggestions(session, booking, booking.car)
    if not suggestions:
        return []

    created: list[AdditionalWork] = []
    for suggestion in suggestions:
        service = await session.get(Service, suggestion.service_id)
        if service is None:
            continue

        work = AdditionalWork(
            booking_id=booking.id,
            description=service.name,
            price=service.price,
            duration_minutes=service.duration_minutes,
            service_id=service.id,
            proposed_by=ProposedBy.AI,
            # C5 (2026-09-16): причина/уверенность — только для оверсайта
            # станции (AdditionalWorkPanel.tsx), не для клиента и не для
            # письма ниже (единое нейтральное письмо для ИИ и мастера).
            ai_confidence=suggestion.confidence,
            ai_reason=suggestion.reason,
        )
        session.add(work)
        created.append(work)

    if not created:
        return []

    # C5 (2026-09-16, прямая просьба пользователя): ОДНО письмо на весь
    # текущий список неотвеченных предложений — не по письму на каждую
    # найденную услугу, и без упоминания ИИ (клиенту не важно, кто
    # предложил, — тот же нейтральный текст, что и у предложения мастера).
    await notify_pending_additional_works(session, booking.id, booking.client.email)

    await session.commit()
    for work in created:
        await session.refresh(work)
        publish("additional_work_proposed", AdditionalWorkRead.model_validate(work).model_dump(mode="json"))
    return created
