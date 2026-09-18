from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# UI_description.md п.24/30 (2026-09-14): реальные найденные баги — можно
# было сохранить услугу с пустым названием при редактировании (create уже
# требовал непустое), и слишком длинное название расползалось за пределы
# плитки 150px в каталоге. max_length подобран так, чтобы типичное название
# укладывалось в 2-3 строки плитки без переполнения.
NAME_MAX_LENGTH = 60


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    duration_minutes: int = Field(gt=0)
    price: Decimal = Field(gt=0)


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    duration_minutes: int | None = Field(default=None, gt=0)
    price: Decimal | None = Field(default=None, gt=0)


class ServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    duration_minutes: int
    price: Decimal
    # UI_description.md п.47: проводник к обязательному функционалу (B1) —
    # каталог не даёт переименовать/удалить, только менять время/цену.
    protected: bool
