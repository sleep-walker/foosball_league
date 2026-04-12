"""WebSocket endpoint for real-time tournament updates.

Clients connect to ``/ws/tournaments/{tournament_id}`` and receive
JSON messages whenever something happens (new round, score update, etc.).

No authentication required — this is a public spectator channel.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .hub import event_hub

router = APIRouter()


@router.websocket("/ws/tournaments/{tournament_id}")
async def tournament_ws(websocket: WebSocket, tournament_id: UUID):
    await websocket.accept()

    q = event_hub.subscribe(tournament_id)
    try:
        while True:
            event = await q.get()
            await websocket.send_text(event.to_json())
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        event_hub.unsubscribe(tournament_id, q)
