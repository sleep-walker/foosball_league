"""Tests for league_app.realtime.hub — in-memory pub/sub."""

import json
from uuid import uuid4

import pytest

from league_app.realtime.hub import Event, EventHub

T1, T2 = uuid4(), uuid4()


@pytest.mark.asyncio
class TestEventHub:
    async def test_subscribe_and_publish(self):
        hub = EventHub()
        q = hub.subscribe(T1)
        await hub.publish(Event("test_event", T1, {"key": "value"}))
        event = q.get_nowait()
        assert event.type == "test_event"
        assert event.tournament_id == T1
        assert event.data == {"key": "value"}
        hub.unsubscribe(T1, q)

    async def test_multiple_subscribers(self):
        hub = EventHub()
        q1 = hub.subscribe(T1)
        q2 = hub.subscribe(T1)
        await hub.publish(Event("hello", T1))
        assert q1.get_nowait().type == "hello"
        assert q2.get_nowait().type == "hello"
        hub.unsubscribe(T1, q1)
        hub.unsubscribe(T1, q2)

    async def test_different_tournaments_isolated(self):
        hub = EventHub()
        q1 = hub.subscribe(T1)
        q2 = hub.subscribe(T2)
        await hub.publish(Event("only_t1", T1))
        assert q2.empty() is not True or q2.qsize() == 0
        assert q1.get_nowait().type == "only_t1"
        assert q2.empty()
        hub.unsubscribe(T1, q1)
        hub.unsubscribe(T2, q2)

    async def test_unsubscribe(self):
        hub = EventHub()
        q = hub.subscribe(T1)
        hub.unsubscribe(T1, q)
        await hub.publish(Event("gone", T1))
        assert q.empty()

    async def test_event_to_json(self):
        event = Event("score_updated", T1, {"match_id": "abc", "score": 6})
        j = json.loads(event.to_json())
        assert j["type"] == "score_updated"
        assert j["tournament_id"] == str(T1)
        assert j["data"]["score"] == 6

    async def test_subscriber_count(self):
        hub = EventHub()
        assert hub.subscriber_count == 0
        q1 = hub.subscribe(T1)
        q2 = hub.subscribe(T1)
        q3 = hub.subscribe(T2)
        assert hub.subscriber_count == 3
        hub.unsubscribe(T1, q1)
        assert hub.subscriber_count == 2
        hub.unsubscribe(T1, q2)
        hub.unsubscribe(T2, q3)
        assert hub.subscriber_count == 0
