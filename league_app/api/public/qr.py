"""QR code generation for tournament registration.

Uses the `qrcode` library if available, otherwise returns a JSON
response with the URL for the client to generate the QR code itself.

The endpoint produces a registration URL that players can scan to
sign up for a tournament.
"""

from __future__ import annotations

import io
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.database import get_session_for_api
from league_app.api.tournaments import crud as tournaments_crud

router = APIRouter(tags=["public"])

# Base URL — in production, this would come from settings/env
_BASE_URL = "http://localhost:8000"


def _registration_url(tournament_id: UUID) -> str:
    return f"{_BASE_URL}/v1/public/tournaments/{tournament_id}/register"


@router.get("/tournaments/{tournament_id}/qr")
async def get_tournament_qr(
    tournament_id: UUID,
    format: str = "json",
    session: AsyncSession = Depends(get_session_for_api),
):
    """Generate a QR code (or URL) for tournament registration.

    Query params:
    - ``format=json`` (default) — returns ``{"url": "...", "tournament_id": "..."}``
    - ``format=svg`` — returns an SVG QR code image (requires ``qrcode`` library)
    - ``format=png`` — returns a PNG QR code image (requires ``qrcode[pil]``)
    """
    t = await tournaments_crud.get_tournament(session, tournament_id)
    if t is None or t.is_deleted:
        raise HTTPException(status_code=404, detail="Tournament not found")

    url = _registration_url(tournament_id)

    if format == "json":
        return {
            "tournament_id": str(tournament_id),
            "tournament_name": t.name,
            "registration_url": url,
            "is_registration_open": t.is_registration_open,
        }

    # Try to use qrcode library for SVG/PNG
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="QR code image generation requires the 'qrcode' package. "
                   "Use format=json instead, or install: pip install qrcode[pil]",
        )

    if format == "svg":
        factory = qrcode.image.svg.SvgPathImage
        img = qrcode.make(url, image_factory=factory)
        buf = io.BytesIO()
        img.save(buf)
        return Response(content=buf.getvalue(), media_type="image/svg+xml")

    if format == "png":
        try:
            img = qrcode.make(url)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return Response(content=buf.getvalue(), media_type="image/png")
        except Exception:
            raise HTTPException(
                status_code=501,
                detail="PNG generation requires 'pillow'. Install: pip install qrcode[pil]",
            )

    raise HTTPException(status_code=400, detail="Invalid format. Use 'json', 'svg', or 'png'.")
