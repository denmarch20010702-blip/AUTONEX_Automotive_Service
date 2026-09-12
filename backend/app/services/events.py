from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

# Узкий интерфейс (publish/subscribe) — намеренно не завязан на конкретную
# реализацию. Сейчас это in-process asyncio.Queue на подписчика: работает
# только в пределах одного процесса (см. buisness/ARCHITECTURE.md, строка
# "Шина realtime-событий" — там же путь на LISTEN/NOTIFY в Postgres, если
# когда-нибудь понадобится несколько воркеров backend).
_subscribers: set[asyncio.Queue[dict[str, Any]]] = set()


def publish(event_type: str, data: dict[str, Any]) -> None:
    event = {"type": event_type, "data": data}
    for queue in _subscribers:
        queue.put_nowait(event)


async def subscribe() -> AsyncIterator[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    _subscribers.add(queue)
    try:
        while True:
            yield await queue.get()
    finally:
        _subscribers.discard(queue)


def subscriber_count() -> int:
    return len(_subscribers)
