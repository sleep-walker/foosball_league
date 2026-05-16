"""In-process event hub for real-time notifications.

Services call ``hub.publish(...)`` when something interesting happens.
WebSocket/SSE clients subscribe to a tournament channel and receive
JSON messages.

This is a simple in-memory pub/sub — sufficient for a single-process
deployment.  For multi-process (e.g. behind gunicorn with multiple
workers), replace with Redis pub/sub or similar.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass
class Event:
    """A real-time event."""

    type: str          # e.g. "round_drawn", "score_updated", "match_finished"
    tournament_id: UUID
    data: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        d = {"type": self.type, "tournament_id": str(self.tournament_id), "data": self.data}
        return json.dumps(d, default=str)


class EventHub:
    """Simple in-memory pub/sub hub, keyed by tournament_id."""

    def __init__(self) -> None:
        self._channels: dict[UUID, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, tournament_id: UUID) -> asyncio.Queue:
        """Subscribe to events for a tournament. Returns a Queue to read from."""
        q: asyncio.Queue = asyncio.Queue()
        self._channels[tournament_id].add(q)
        return q

    def unsubscribe(self, tournament_id: UUID, q: asyncio.Queue) -> None:
        """Unsubscribe from a tournament channel."""
        self._channels[tournament_id].discard(q)
        if not self._channels[tournament_id]:
            del self._channels[tournament_id]

    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers of the tournament."""
        for q in self._channels.get(event.tournament_id, set()):
            await q.put(event)

    @property
    def subscriber_count(self) -> int:
        return sum(len(subs) for subs in self._channels.values())


# Global singleton — used by services and WebSocket endpoint
event_hub = EventHub()
