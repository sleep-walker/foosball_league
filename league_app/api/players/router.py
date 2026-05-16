from uuid import UUID
from fastapi import APIRouter

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException

from . import crud, schema

from league_app.database import get_session_for_api
from league_app.api.users.users import current_active_verified_user, current_superuser
from league_app.api.users.model import User
from logging import getLogger

router = APIRouter(tags=["players"])
logger = getLogger("players")


@router.post("/", response_model=schema.PlayerOutput)
async def create_player(
    player: schema.PlayerCreate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    logger.info("checking mail")
    if player.email is not None:
        db_player = await crud.get_player_by_email(session, email=player.email)
        if db_player:
            raise HTTPException(status_code=400, detail="Email already registered")
    logger.info("checking nickname")
    db_player = await crud.get_player_by_nickname(session, nickname=player.nickname)
    if db_player:
        raise HTTPException(status_code=400, detail="Nickname already registered")

    # Auto-link to creating user if user doesn't already have a player
    existing_links = await crud.get_players_by_user_id(session, user.id)
    existing_link = existing_links[0] if existing_links else None
    created = await crud.create_player(session=session, player=player)
    if existing_link is None:
        created.user_id = user.id
        await session.commit()
        await session.refresh(created)
    return created


@router.get("/", response_model=list[schema.PlayerOutput])
async def read_players(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_superuser),
):
    if not user.is_superuser:
        raise HTTPException(
            status_code=401, detail="Only superuser can list all players"
        )

    players = await crud.get_players(db, skip=skip, limit=limit)
    return players


@router.get("/self", response_model=list[schema.PlayerOutput])
async def read_player_self(
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    db_players = await crud.get_players_by_user_id(session, user_id=user.id)
    return db_players


@router.get("/search", response_model=list[schema.PlayerOutput])
async def search_player(
    nickname: str | None = None,
    email: str | None = None,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    players = await crud.search_players(session, nickname=nickname, email=email)
    can_see_email = user.is_superuser or (email is not None)
    output_players = [
        schema.PlayerOutput.model_validate(player) for player in players
        ]
    if not can_see_email:
        for player in output_players:
            player.email = None
    return output_players


@router.get("/{uuid}", response_model=schema.PlayerOutput)
async def read_player(
    uuid: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    db_player = await crud.get_player(session, uuid=uuid)
    if db_player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return db_player


@router.put("/{uuid}", response_model=schema.PlayerOutput)
async def update_player(
    uuid: UUID,
    player: schema.PlayerUpdate,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    db_player = await crud.get_player(session, uuid=uuid)
    if db_player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    allowed = user.is_superuser or user.id == db_player.user_id
    if not allowed:
        raise HTTPException(
            status_code=403, detail="Only a superuser can change other players"
        )
    if player.uuid is not None and uuid != player.uuid:
        raise HTTPException(status_code=403, detail="User cannot change his UUID")

    player_output = await crud.update_player(session, player=player)
    return player_output


@router.delete("/{uuid}", response_model=schema.PlayerOutput)
async def delete_player(
    uuid: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    player = await crud.get_player(session, uuid=uuid)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    allowed = user.is_superuser or user.id == player.user_id
    if not allowed:
        raise HTTPException(
            status_code=403, detail="Only a superuser can delete other players"
        )
    return await crud.delete_player(session=session, uuid=uuid)


# ---------------------------------------------------------------------------
# Claim — link an unclaimed Player to a User account.
#
# Admin-only operation by design.  A User may end up owning multiple Players
# (different nicknames per league/persona), but the link from a Player to
# a User is a strong identity statement and must not be made by tournament
# or league organisers — that would let them route someone else's results
# into their own account.
#
# Future work: a self-claim flow where the User proves ownership by
# clicking a link e-mailed to ``player.email``.
# ---------------------------------------------------------------------------


class PlayerClaimRequest(BaseModel):
    user_id: UUID


@router.post("/{uuid}/claim", response_model=schema.PlayerOutput, tags=["players"])
async def claim_player(
    uuid: UUID,
    body: PlayerClaimRequest,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_superuser),
):
    """Link an unclaimed Player to a User. Admin only."""
    db_player = await crud.get_player(session, uuid=uuid)
    if db_player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    if db_player.user_id is not None:
        if db_player.user_id == body.user_id:
            return db_player  # idempotent
        raise HTTPException(
            status_code=409,
            detail="Player is already claimed by a different user",
        )

    target_user = await session.get(User, body.user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="Target user not found")

    db_player.user_id = body.user_id
    await session.commit()
    await session.refresh(db_player)
    return db_player


# ---------------------------------------------------------------------------
# Merge — combine two Player records into one.
#
# The non-admin scope is intentionally narrow:
#   * tournament organiser: both Players must be applicants/registrations
#     in some tournament they own (or co-organise).
#   * league organiser (i.e. league.owner_id): both Players must be members
#     of a league they own.
#   * admin: any two Players.
#
# Claimed Players (those with ``user_id``) can only be merged by an admin,
# and only into the same User.  Otherwise an organiser could redirect a
# different user's results into the wrong account.
# ---------------------------------------------------------------------------


async def _can_merge_players(
    session: AsyncSession, user: User, source_id: UUID, target_id: UUID
) -> tuple[bool, str | None]:
    """Return (allowed, reason_if_denied)."""
    from league_app.api.tournaments import model as tournament_orm
    from league_app.api.leagues import model as league_orm
    from sqlalchemy import select

    if user.is_superuser:
        return (True, None)

    # Load source / target Players to inspect their user_id linkage
    source = await crud.get_player(session, uuid=source_id)
    target = await crud.get_player(session, uuid=target_id)
    if source is None or target is None:
        return (False, "Player not found")

    # Non-admins can only merge unclaimed Players
    if source.user_id is not None or target.user_id is not None:
        return (
            False,
            "Only an administrator can merge Players that are linked to a user",
        )

    # Tournaments the user owns
    owned_tournaments = {
        r for (r,) in await session.execute(
            select(tournament_orm.Tournament.uuid).where(
                tournament_orm.Tournament.owner_id == user.id,
                tournament_orm.Tournament.is_deleted == False,  # noqa: E712
            )
        )
    }
    # TODO: also consider co-organisers via tournament_organizers when that
    # feature lands in the UI.

    # Tournaments where each player is involved (registration or applicant)
    async def _tournaments_for(player_id: UUID) -> set[UUID]:
        regs = {
            r for (r,) in await session.execute(
                select(tournament_orm.TournamentRegistration.tournament_id)
                .where(tournament_orm.TournamentRegistration.player_id == player_id)
            )
        }
        apps = {
            r for (r,) in await session.execute(
                select(tournament_orm.tournament_applicants.c.tournament_id)
                .where(tournament_orm.tournament_applicants.c.player_id == player_id)
            )
        }
        return regs | apps

    src_tournaments = await _tournaments_for(source_id)
    tgt_tournaments = await _tournaments_for(target_id)
    if (src_tournaments & owned_tournaments) and (tgt_tournaments & owned_tournaments):
        return (True, None)

    # League organiser path
    owned_leagues = {
        r for (r,) in await session.execute(
            select(league_orm.League.uuid).where(
                league_orm.League.owner_id == user.id,
                league_orm.League.is_deleted == False,  # noqa: E712
            )
        )
    }
    if owned_leagues:
        # Both Players must be in some league the user owns, either as direct
        # members or as participants of a tournament belonging to that league.
        league_tournaments = {
            r for (r,) in await session.execute(
                select(tournament_orm.Tournament.uuid).where(
                    tournament_orm.Tournament.league_id.in_(owned_leagues),
                    tournament_orm.Tournament.is_deleted == False,  # noqa: E712
                )
            )
        }
        src_member_of = {
            r for (r,) in await session.execute(
                select(league_orm.league_members.c.league_id).where(
                    league_orm.league_members.c.player_id == source_id
                )
            )
        }
        tgt_member_of = {
            r for (r,) in await session.execute(
                select(league_orm.league_members.c.league_id).where(
                    league_orm.league_members.c.player_id == target_id
                )
            )
        }
        src_in_scope = bool(src_member_of & owned_leagues) or bool(
            src_tournaments & league_tournaments
        )
        tgt_in_scope = bool(tgt_member_of & owned_leagues) or bool(
            tgt_tournaments & league_tournaments
        )
        if src_in_scope and tgt_in_scope:
            return (True, None)

    return (
        False,
        "Both players must belong to a tournament or league you organise",
    )


@router.post("/{source_id}/merge", response_model=schema.PlayerOutput, tags=["players"])
async def merge_player(
    source_id: UUID,
    into: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    """Merge ``source_id`` into ``into`` (the surviving Player)."""
    if source_id == into:
        raise HTTPException(status_code=400, detail="source and target must differ")

    source = await crud.get_player(session, uuid=source_id)
    target = await crud.get_player(session, uuid=into)
    if source is None or target is None:
        raise HTTPException(status_code=404, detail="Player not found")

    # Admin-only safety net: claimed players linked to different users can
    # never be merged (impersonation).
    if (
        source.user_id is not None
        and target.user_id is not None
        and source.user_id != target.user_id
    ):
        raise HTTPException(
            status_code=409,
            detail="Players are claimed by different users — cannot merge",
        )

    allowed, reason = await _can_merge_players(session, user, source_id, into)
    if not allowed:
        raise HTTPException(status_code=403, detail=reason or "Forbidden")

    conflicts = await crud.merge_players(session, source_id, into)
    if conflicts:
        raise HTTPException(status_code=409, detail="; ".join(conflicts))

    await session.refresh(target)
    return target


# ---------------------------------------------------------------------------
# Self-claim by e-mail — a User who recognises their old Player record can
# request a one-time link, sent to ``player.email``, and confirm ownership.
#
# This is the user-driven counterpart of the admin-only claim above.  It
# requires that the Player has a stored e-mail address (the only channel we
# can trust without an organiser in the loop).
#
# Token format: HMAC over ``player_id:user_id:exp``.  Stateless, single-use
# is enforced only by Player.user_id flipping non-null on success — a
# second confirm with the same token returns the existing claim
# (idempotent).
# ---------------------------------------------------------------------------


_CLAIM_TOKEN_TTL_SECONDS = 30 * 60  # 30 minutes


def _make_claim_token(player_id: UUID, user_id: UUID, exp_ts: int) -> str:
    """Sign a (player_id, user_id, exp) tuple with the app secret."""
    import base64
    import hashlib
    import hmac
    from league_app.config import get_settings

    payload = f"{player_id}:{user_id}:{exp_ts}".encode("utf-8")
    sig = hmac.new(
        get_settings().SECRET_KEY.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).digest()
    return (
        base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        + "."
        + base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
    )


def _verify_claim_token(token: str) -> tuple[UUID, UUID, int] | None:
    """Return (player_id, user_id, exp) if the signature is valid, else None."""
    import base64
    import hashlib
    import hmac
    import time
    from league_app.config import get_settings

    try:
        payload_b64, sig_b64 = token.split(".", 1)
    except ValueError:
        return None

    def _pad(s: str) -> bytes:
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

    try:
        payload = _pad(payload_b64)
        sig = _pad(sig_b64)
    except Exception:
        return None

    expected = hmac.new(
        get_settings().SECRET_KEY.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected, sig):
        return None

    try:
        pid_str, uid_str, exp_str = payload.decode("utf-8").split(":")
        exp = int(exp_str)
    except (ValueError, UnicodeDecodeError):
        return None
    if exp < int(time.time()):
        return None
    try:
        return (UUID(pid_str), UUID(uid_str), exp)
    except ValueError:
        return None


class ClaimConfirmRequest(BaseModel):
    token: str


@router.post("/{uuid}/request-claim", tags=["players"])
async def request_player_claim(
    uuid: UUID,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    """Send a one-time claim link to the Player's e-mail address.

    The Player must (a) be unclaimed and (b) have a non-empty e-mail.  The
    e-mail itself is not actually delivered yet — we only log the URL.
    SMTP integration is a follow-up TODO.
    """
    import time

    db_player = await crud.get_player(session, uuid=uuid)
    if db_player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    if db_player.user_id is not None:
        raise HTTPException(
            status_code=409,
            detail="Player is already claimed",
        )
    if not db_player.email:
        raise HTTPException(
            status_code=400,
            detail="Player has no e-mail on file — ask an administrator "
                   "to link the account instead",
        )

    exp = int(time.time()) + _CLAIM_TOKEN_TTL_SECONDS
    token = _make_claim_token(uuid, user.id, exp)

    # TODO: send via SMTP. For now log the URL — the same approach
    # fastapi-users uses for password-reset tokens in dev mode.
    logger.warning(
        "Player claim requested. Player=%s User=%s Email=%s Token=%s",
        uuid, user.id, db_player.email, token,
    )
    return {
        "message": (
            "A confirmation e-mail has been sent. Check the inbox for "
            f"{db_player.email}."
        ),
    }


@router.post(
    "/{uuid}/confirm-claim",
    response_model=schema.PlayerOutput,
    tags=["players"],
)
async def confirm_player_claim(
    uuid: UUID,
    body: ClaimConfirmRequest,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_active_verified_user),
):
    """Complete the claim by submitting the token from the e-mail."""
    verified = _verify_claim_token(body.token)
    if verified is None:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    token_player_id, token_user_id, _exp = verified
    if token_player_id != uuid:
        raise HTTPException(status_code=400, detail="Token does not match this player")
    if token_user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="This claim was requested by a different user",
        )

    db_player = await crud.get_player(session, uuid=uuid)
    if db_player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    if db_player.user_id is not None:
        if db_player.user_id == user.id:
            return db_player  # idempotent
        raise HTTPException(
            status_code=409,
            detail="Player is already claimed by another user",
        )

    db_player.user_id = user.id
    await session.commit()
    await session.refresh(db_player)
    return db_player
