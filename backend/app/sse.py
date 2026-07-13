from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, campaign_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues[campaign_id].append(q)
        return q

    def unsubscribe(self, campaign_id: str, q: asyncio.Queue) -> None:
        if campaign_id in self._queues and q in self._queues[campaign_id]:
            self._queues[campaign_id].remove(q)

    async def publish(self, campaign_id: str, event: str, data: dict[str, Any]) -> None:
        payload = {"event": event, "data": data}
        for q in list(self._queues.get(campaign_id, [])):
            await q.put(payload)

    def publish_threadsafe(
        self, loop: asyncio.AbstractEventLoop, campaign_id: str, event: str, data: dict
    ) -> None:
        asyncio.run_coroutine_threadsafe(self.publish(campaign_id, event, data), loop)


bus = EventBus()


def format_sse(payload: dict) -> str:
    event = payload.get("event", "message")
    data = json.dumps(payload.get("data", {}))
    return f"event: {event}\ndata: {data}\n\n"
