from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.additional_work import AdditionalWorkStatus, ProposedBy


class AdditionalWorkCreate(BaseModel):
    # UI_description.md п.19: доп. работа выбирается кликом из каталога
    # услуг, а не вводится вручную — эндпоинт сам берёт название/цену/
    # длительность из выбранной услуги (см. app/api/additional_works.py).
    service_id: int
    proposed_by: ProposedBy = ProposedBy.MECHANIC


class AdditionalWorkRespond(BaseModel):
    status: AdditionalWorkStatus


class AdditionalWorkSchedule(BaseModel):
    # UI_description.md п.37: клиент выбрал слот из мини-календаря для
    # отдельного визита именно на эту доп. работу.
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
    created_at: datetime
