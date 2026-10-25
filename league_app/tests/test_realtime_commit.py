"""Events must not be observable before the request transaction commits.

``get_session_for_api`` is the one place where an HTTP request's
transaction is committed, so it is also the only correct place to release
real-time events.  These tests drive the dependency directly (that is the
whole unit under test) and assert both halves of the contract:

* nothing is delivered while the request is still running;
* a request that blows up (rollback) delivers nothing at all.
"""

from uuid import uuid4

import pytest

from league_app.database import get_session_for_api
from league_app.realtime.hub import Event, event_hub

T = uuid4()


@pytest.mark.asyncio
async def test_events_are_delivered_only_after_commit():
    q = event_hub.subscribe(T)
    try:
        gen = get_session_for_api()
        await gen.__anext__()  # request starts, transaction open

        await event_hub.publish(Event("score_updated", T, {"score_a": 6}))
        assert q.empty(), "event was delivered before the transaction committed"

        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()  # request ends -> commit -> flush

        event = q.get_nowait()
        assert event.type == "score_updated"
        assert q.empty()
    finally:
        event_hub.unsubscribe(T, q)


@pytest.mark.asyncio
async def test_events_are_dropped_when_the_request_fails():
    q = event_hub.subscribe(T)
    try:
        gen = get_session_for_api()
        await gen.__anext__()

        await event_hub.publish(Event("round_drawn", T))
        assert q.empty()

        with pytest.raises(RuntimeError):
            await gen.athrow(RuntimeError("boom"))  # request fails -> rollback

        assert q.empty(), "rolled-back request still announced its events"
    finally:
        event_hub.unsubscribe(T, q)


@pytest.mark.asyncio
async def test_publishing_outside_a_request_is_immediate():
    """Background/WebSocket-side publishing is unaffected by the deferral."""
    q = event_hub.subscribe(T)
    try:
        await event_hub.publish(Event("tournament_started", T))
        assert q.get_nowait().type == "tournament_started"
    finally:
        event_hub.unsubscribe(T, q)
