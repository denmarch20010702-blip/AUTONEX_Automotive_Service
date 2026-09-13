from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.additional_work import AdditionalWorkStatus, ProposedBy


class AdditionalWorkCreate(BaseModel):
    description: str = Field(min_length=1)
    price: Decimal = Field(gt=0)
    proposed_by: ProposedBy = ProposedBy.MECHANIC


class AdditionalWorkRespond(BaseModel):
    status: AdditionalWorkStatus


class AdditionalWorkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    booking_id: int
    description: str
    price: Decimal
    proposed_by: ProposedBy
    status: AdditionalWorkStatus
    created_at: datetime
