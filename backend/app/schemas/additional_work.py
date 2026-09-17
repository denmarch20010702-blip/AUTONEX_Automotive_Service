from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.additional_work import AdditionalWorkStatus, ProposedBy


class AdditionalWorkCreate(BaseModel):
    # UI_description.md п.19: доп. работа выбирается кликом из каталога
    # услуг, а не вводится вручную — эндпоинт сам берёт название/цену/
    # длительность из выбранной услуги (см. app/api/additional_works.py).
    #
    # C5 (2026-09-16): `proposed_by` раньше было полем запроса — временная
    # ручка, которую можно было дёрнуть вручную через API без реального
    # ИИ-расчёта. Убрано: этот публичный эндпоинт — только для мастера,
    # `proposed_by=ai` возможно ТОЛЬКО через внутренний вызов
    # run_ai_diagnostic (app/services/ai_diagnostics.py), не через API.
    service_id: int


class AdditionalWorkRespond(BaseModel):
    status: AdditionalWorkStatus


class AdditionalWorkSchedule(BaseModel):
    # UI_description.md п.37: клиент выбрал слот из мини-календаря для
    # отдельного визита именно на эту доп. работу.
    start_at: datetime


class AdditionalWorkScheduleBatch(BaseModel):
    # Найдено пользователем на практике (2026-09-17): при очереди на посту
    # НЕСКОЛЬКИМ доп. работам по одной заявке одновременно может не хватить
    # места — раньше это означало отдельный визит (и отдельный выбор
    # времени) на КАЖДУЮ. Один визит на все разом — один выбор времени,
    # одна новая заявка со всеми услугами сразу (см. эндпоинт /schedule-batch).
    work_ids: list[int]
    start_at: datetime


class AdditionalWorkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_id: int
    description: str
    price: Decimal
    duration_minutes: int
    service_id: int | None
    scheduled_booking_id: int | None
    proposed_by: ProposedBy
    status: AdditionalWorkStatus
    # C2 (2026-09-15): различает "согласовано, ждёт своей очереди на посту"
    # от "уже выполняется прямо сейчас" — оба раньше выглядели одинаково
    # ("согласовано") в UI, хотя это разные фазы одной и той же очереди задач.
    execution_started: bool
    # C5 (2026-09-16): видно только станции (см. AdditionalWorkPanel.tsx) —
    # клиентский кабинет эти два поля намеренно не показывает.
    ai_confidence: float | None
    ai_reason: str | None
    created_at: datetime
