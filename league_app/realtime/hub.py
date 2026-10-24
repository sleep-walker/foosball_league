"""In-process event hub for real-time notifications.

Services call ``hub.publish(...)`` when something interesting happens.
WebSocket/SSE clients subscribe to a tournament channel and receive
JSON messages.

This is a simple in-memory pub/sub — sufficient for a single-process
deployment.  For multi-process (e.g. behind gunicorn with multiple
workers), replace with Redis pub/sub or similar.

Two delivery guarantees are implemented here:

* **Publishing never breaks the publisher.**  Delivery iterates over a
  snapshot of the subscriber set (a WebSocket client disconnecting
  mid-publish used to raise ``RuntimeError: Set changed size during
  iteration`` and 500 the HTTP request that triggered the event), and
  subscriber queues are bounded so one stuck client cannot grow the
  process heap without limit.
* **Nothing is published before the data is committed.**  Inside a
  request, ``publish()`` only buffers events; ``league_app.database``
  flushes the buffer after the request's transaction commits (and drops
  it on rollback), so subscribers never see state that does not exist.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

log = logging.getLogger(__name__)

# Max events buffered per subscriber before the oldest ones are dropped.
# 100 events is several minutes of a busy tournament; a client that far
# behind has effectively lost the live feed anyway.
DEFAULT_QUEUE_MAXSIZE = 100

# Events published while a request transaction is open.  ``None`` means
# "no deferral active" — publish immediately (background jobs, tests,
# WebSocket-side code).
_deferred: ContextVar[list["Event"] | None] = ContextVar("event_hub_deferred", default=None)


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

    def __init__(self, queue_maxsize: int = DEFAULT_QUEUE_MAXSIZE) -> None:
        self._channels: dict[UUID, set[asyncio.Queue]] = defaultdict(set)
        self._queue_maxsize = queue_maxsize

    def subscribe(self, tournament_id: UUID) -> asyncio.Queue:
        """Subscribe to events for a tournament. Returns a Queue to read from."""
        q: asyncio.Queue = asyncio.Queue(maxsize=self._queue_maxsize)
        self._channels[tournament_id].add(q)
        return q

    def unsubscribe(self, tournament_id: UUID, q: asyncio.Queue) -> None:
        """Unsubscribe from a tournament channel."""
        if tournament_id not in self._channels:
            return
        self._channels[tournament_id].discard(q)
        if not self._channels[tournament_id]:
            del self._channels[tournament_id]

    async def publish(self, event: Event) -> None:
        """Publish an event — immediately, or at commit time inside a request.

        Kept ``async`` for call-site compatibility; delivery itself never
        blocks (see :meth:`deliver`).
        """
        pending = _deferred.get()
        if pending is not None:
            pending.append(event)
            return
        self.deliver(event)

    def deliver(self, event: Event) -> None:
        """Deliver an event to all current subscribers of the tournament."""
        # Iterate a snapshot: a WebSocket client that disconnects while we
        # are delivering calls unsubscribe(), which mutates this very set.
        for q in list(self._channels.get(event.tournament_id, ())):
            self._offer(q, event)

    def _offer(self, q: asyncio.Queue, event: Event) -> None:
        """Put an event on a subscriber queue, dropping the oldest if full.

        Policy: drop the OLDEST event, keep the newest.  This is a live
        scoreboard feed — the most recent state is what a client needs, and
        dropping a stale event is strictly better than either blocking the
        publisher (which runs inside an HTTP request) or disconnecting a
        client that is merely a bit slow.
        """
        while True:
            try:
                q.put_nowait(event)
                return
            except asyncio.QueueFull:
                try:
                    dropped = q.get_nowait()
                except asyncio.QueueEmpty:  # pragma: no cover — only with a concurrent reader
                    return
                log.warning(
                    "Subscriber queue full (maxsize=%d) — dropping oldest event %r",
                    self._queue_maxsize, dropped.type,
                )

    # --- Deferred (post-commit) publishing ---

    def begin_deferred(self) -> list[Event]:
        """Start buffering published events in the current context."""
        pending: list[Event] = []
        _deferred.set(pending)
        return pending

    def flush_deferred(self, pending: list[Event]) -> None:
        """Deliver buffered events (call only after a successful commit)."""
        self._end_deferred(pending)
        for event in pending:
            self.deliver(event)
        pending.clear()

    def discard_deferred(self, pending: list[Event]) -> None:
        """Throw buffered events away (the transaction did not commit)."""
        self._end_deferred(pending)
        if pending:
            log.info("Discarding %d event(s) — transaction did not commit", len(pending))
        pending.clear()

    def _end_deferred(self, pending: list[Event]) -> None:
        if _deferred.get() is pending:
            _deferred.set(None)

    @property
    def subscriber_count(self) -> int:
        return sum(len(subs) for subs in self._channels.values())


# Global singleton — used by services and WebSocket endpoint
event_hub = EventHub()
