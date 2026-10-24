"""Tests for league_app.realtime.hub — in-memory pub/sub."""

import asyncio
import json
from uuid import uuid4

import pytest

from league_app.realtime.hub import DEFAULT_QUEUE_MAXSIZE, Event, EventHub

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


@pytest.mark.asyncio
class TestEventHubDisconnectDuringPublish:
    """Regression: a client disconnecting mid-publish must not break publish.

    ``publish()`` used to iterate the live subscriber set while
    ``unsubscribe()`` mutated it, raising
    ``RuntimeError: Set changed size during iteration`` — which 500'd the
    HTTP request that happened to trigger the event.
    """

    async def test_unsubscribe_during_publish_does_not_raise(self):
        hub = EventHub()

        class DisconnectingQueue(asyncio.Queue):
            """Simulates a WS client that drops while events are delivered."""

            def put_nowait(self, item):
                for other in list(hub._channels.get(T1, ())):
                    hub.unsubscribe(T1, other)
                super().put_nowait(item)

        queues = [DisconnectingQueue() for _ in range(4)]
        for q in queues:
            hub._channels[T1].add(q)

        # Must not raise, and every subscriber present when publishing
        # started still gets the event (delivery runs off a snapshot).
        await hub.publish(Event("round_drawn", T1))

        assert [q.get_nowait().type for q in queues] == ["round_drawn"] * 4
        assert hub.subscriber_count == 0

    async def test_unsubscribe_twice_is_harmless(self):
        hub = EventHub()
        q = hub.subscribe(T1)
        hub.unsubscribe(T1, q)
        hub.unsubscribe(T1, q)
        assert hub.subscriber_count == 0


@pytest.mark.asyncio
class TestEventHubBoundedQueues:
    """Subscriber queues are bounded — a stuck client cannot grow forever."""

    async def test_queue_has_maxsize(self):
        hub = EventHub()
        q = hub.subscribe(T1)
        assert q.maxsize == DEFAULT_QUEUE_MAXSIZE

    async def test_full_queue_drops_oldest_event(self):
        hub = EventHub(queue_maxsize=3)
        q = hub.subscribe(T1)
        for i in range(5):
            await hub.publish(Event(f"e{i}", T1))

        # Oldest events are dropped, the newest ones survive.
        assert q.qsize() == 3
        assert [q.get_nowait().type for _ in range(3)] == ["e2", "e3", "e4"]

    async def test_slow_client_does_not_block_other_subscribers(self):
        hub = EventHub(queue_maxsize=1)
        slow = hub.subscribe(T1)
        fast = hub.subscribe(T1)
        await hub.publish(Event("first", T1))
        fast.get_nowait()                      # fast client keeps up
        await hub.publish(Event("second", T1))  # slow client is already full

        assert fast.get_nowait().type == "second"
        assert slow.get_nowait().type == "second"
        assert slow.empty()


@pytest.mark.asyncio
class TestEventHubDeferredPublishing:
    """Events published inside a transaction are held until it commits."""

    async def test_deferred_events_are_invisible_until_flush(self):
        hub = EventHub()
        q = hub.subscribe(T1)
        pending = hub.begin_deferred()
        try:
            await hub.publish(Event("score_updated", T1))
            assert q.empty(), "event leaked before the transaction committed"
            assert len(pending) == 1
            hub.flush_deferred(pending)
            assert q.get_nowait().type == "score_updated"
        finally:
            hub.discard_deferred(pending)
            hub.unsubscribe(T1, q)

    async def test_discarded_events_are_never_delivered(self):
        hub = EventHub()
        q = hub.subscribe(T1)
        pending = hub.begin_deferred()
        await hub.publish(Event("round_drawn", T1))
        hub.discard_deferred(pending)
        assert q.empty()

        # Deferral is over — later publishes go out immediately again.
        await hub.publish(Event("after_rollback", T1))
        assert q.get_nowait().type == "after_rollback"
        hub.unsubscribe(T1, q)
