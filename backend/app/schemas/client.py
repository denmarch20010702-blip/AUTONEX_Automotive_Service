from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ClientCreate(BaseModel):
    email: str
    name: str


class ClientUpdate(BaseModel):
    email: str | None = None
    name: str | None = None


class ClientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
