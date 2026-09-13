from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator


class ClientCreate(BaseModel):
    email: str
    name: str

    # Найдено на практике (2026-09-13): без нормализации "Test@Example.com"
    # и "test@example.com" считались разными клиентами — и уникальностью в
    # БД (регистрозависимой), и поиском при входе — что позволяло случайно
    # завести дубликат аккаунта с той же почтой в другом регистре.
    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class ClientUpdate(BaseModel):
    email: str | None = None
    name: str | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else value


class ClientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
