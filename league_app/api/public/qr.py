"""QR code generation for tournament registration.

Uses `segno` — a pure-Python QR code library with zero external
dependencies.  Generates SVG and PNG natively (no Pillow needed).
"""

from __future__ import annotations

import io
from uuid import UUID

import segno
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.config import get_settings
from league_app.database import get_session_for_api
from league_app.api.tournaments import crud as tournaments_crud

router = APIRouter(tags=["public"])


def _registration_url(tournament_id: UUID, token: str) -> str:
    base = get_settings().BASE_URL.rstrip("/")
    return f"{base}/#register/{tournament_id}?token={token}"


@router.get("/tournaments/{tournament_id}/qr")
async def get_tournament_qr(
    tournament_id: UUID,
    format: str = "json",
    session: AsyncSession = Depends(get_session_for_api),
):
    """Generate a QR code for tournament registration.

    Query params:
    - ``format=json`` (default) — returns URL + metadata
    - ``format=svg`` — SVG QR image
    - ``format=png`` — PNG QR image
    """
    t = await tournaments_crud.get_tournament(session, tournament_id)
    if t is None or t.is_deleted:
        raise HTTPException(status_code=404, detail="Tournament not found")

    url = _registration_url(tournament_id, t.registration_token)

    if format == "json":
        return {
            "tournament_id": str(tournament_id),
            "tournament_name": t.name,
            "registration_url": url,
            "is_registration_open": t.is_registration_open,
        }

    qr = segno.make(url)

    if format == "svg":
        buf = io.BytesIO()
        qr.save(buf, kind="svg", scale=6, border=2)
        return Response(content=buf.getvalue(), media_type="image/svg+xml")

    if format == "png":
        buf = io.BytesIO()
        qr.save(buf, kind="png", scale=8, border=2)
        return Response(content=buf.getvalue(), media_type="image/png")

    raise HTTPException(
        status_code=400,
        detail="Invalid format. Use 'json', 'svg', or 'png'.",
    )
