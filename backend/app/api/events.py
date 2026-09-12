from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.services.events import subscribe

router = APIRouter(tags=["events"])


@router.get("/events")
async def events_stream() -> EventSourceResponse:
    async def generator() -> AsyncIterator[dict[str, str]]:
        async for event in subscribe():
            yield {"event": event["type"], "data": json.dumps(event["data"])}

    return EventSourceResponse(generator())
