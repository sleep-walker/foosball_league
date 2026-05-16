from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from . import model, schema
from sqlalchemy import delete, select, update


async def get_player(session: AsyncSession, uuid: UUID) -> model.Player | None:
    stmt = select(model.Player).filter(model.Player.uuid == uuid)
    assert isinstance(session, AsyncSession)
    return await session.scalar(stmt)


async def get_players(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    filter_deleted: bool = True,
) -> list[model.Player]:
    stmt = select(model.Player).offset(skip)

    if limit != 0:
        stmt = stmt.limit(limit)

    result = await session.scalars(stmt.order_by(model.Player.uuid))
    return list(result)


async def create_player(session: AsyncSession, player: schema.PlayerCreate):
    db_player = model.Player(**player.model_dump())
    session.add(db_player)
    await session.commit()
    await session.refresh(db_player)
    return db_player


async def get_player_by_email(session: AsyncSession, email: str):
    stmt = select(model.Player).filter(model.Player.email == email)
    return await session.scalar(stmt)


async def get_player_by_nickname(session: AsyncSession, nickname: str):
    stmt = select(model.Player).filter(model.Player.nickname == nickname)
    return await session.scalar(stmt)


async def get_player_by_uuid(session: AsyncSession, uuid: UUID):
    stmt = select(model.Player).filter(model.Player.uuid == uuid)
    return await session.scalar(stmt)


async def get_players_by_user_id(
    session: AsyncSession, user_id: UUID
) -> list[model.Player]:
    stmt = (
        select(model.Player)
        .filter(model.Player.user_id == user_id)
        .order_by(model.Player.uuid)
    )
    result = await session.scalars(stmt)
    return list(result)


async def update_player(session: AsyncSession, player: schema.PlayerUpdate):
    stmt = (
        update(model.Player)
        .filter(model.Player.uuid == player.uuid)
        .values(**player.model_dump())
    )
    await session.execute(stmt)
    stmt = select(model.Player).filter(model.Player.uuid == player.uuid)
    return await session.scalar(stmt)


async def delete_player(session: AsyncSession, uuid: UUID):
    stmt = update(model.Player).filter(model.Player.uuid == uuid).values(is_deleted=True)
    await session.execute(stmt)
    await session.commit()
    return await session.scalar(
        select(model.Player).filter(model.Player.uuid == uuid)
    )


# ---------------------------------------------------------------------------
# Merge — replace all references to ``source_id`` with ``target_id`` and mark
# the source as deleted.  Touches every table that holds a foreign key to
# ``players.uuid``.  Returns a list of human-readable conflict descriptions
# if the merge would create duplicate rows in a many-to-many association; in
# that case nothing is changed and the caller should surface a 409.
# ---------------------------------------------------------------------------


async def merge_players(
    session: AsyncSession, source_id: UUID, target_id: UUID
) -> list[str]:
    """Merge ``source`` into ``target``. Returns conflicts (empty on success).

    Conflicts occur when both Players are linked to the same tournament as
    distinct participants — for instance both registered in the same
    tournament, or paired as teammates in the same Team.  Resolving such
    conflicts requires manual intervention (delete one match, swap a team
    member, etc.) so we bail out with a description rather than silently
    losing data.
    """
    from league_app.api.matches import model as match_orm
    from league_app.api.teams import model as team_orm
    from league_app.api.tournaments import model as tournament_orm
    from league_app.api.leagues import model as league_orm

    if source_id == target_id:
        return ["Source and target must differ"]

    conflicts: list[str] = []

    # --- M2M conflicts (composite PK would clash) ---

    # tournament_applicants(tournament_id, player_id): overlap is fine,
    # we just drop the source row.  Load both sides separately.
    src_app_tids = {
        r for (r,) in await session.execute(
            select(tournament_orm.tournament_applicants.c.tournament_id).where(
                tournament_orm.tournament_applicants.c.player_id == source_id
            )
        )
    }
    tgt_app_tids = {
        r for (r,) in await session.execute(
            select(tournament_orm.tournament_applicants.c.tournament_id).where(
                tournament_orm.tournament_applicants.c.player_id == target_id
            )
        )
    }
    overlap_app = src_app_tids & tgt_app_tids
    # Overlap in applicants is fine — we simply drop the source row.

    # TournamentRegistration: both registered in same tournament → conflict
    src_reg_tids = {
        r for (r,) in await session.execute(
            select(tournament_orm.TournamentRegistration.tournament_id).where(
                tournament_orm.TournamentRegistration.player_id == source_id
            )
        )
    }
    tgt_reg_tids = {
        r for (r,) in await session.execute(
            select(tournament_orm.TournamentRegistration.tournament_id).where(
                tournament_orm.TournamentRegistration.player_id == target_id
            )
        )
    }
    overlap_reg = src_reg_tids & tgt_reg_tids
    for tid in overlap_reg:
        conflicts.append(
            f"Both players are registered in tournament {tid} — "
            f"unregister one before merging"
        )

    # league_members: overlap is fine (just drop the source row)

    # Team conflict: source and target on the same team (would self-pair)
    same_team = await session.scalar(
        select(team_orm.Team.uuid).where(
            ((team_orm.Team.player_1_id == source_id) & (team_orm.Team.player_2_id == target_id))
            | ((team_orm.Team.player_1_id == target_id) & (team_orm.Team.player_2_id == source_id))
        )
    )
    if same_team is not None:
        conflicts.append(
            f"Players already form team {same_team} together — merging would "
            f"create a self-paired team"
        )

    # Match conflict: source and target as opposing participants in the same match
    same_match = await session.scalar(
        select(match_orm.Match.uuid).where(
            match_orm.Match.is_deleted == False,  # noqa: E712
            ((match_orm.Match.player_a_id == source_id) & (match_orm.Match.player_b_id == target_id))
            | ((match_orm.Match.player_a_id == target_id) & (match_orm.Match.player_b_id == source_id)),
        )
    )
    if same_match is not None:
        conflicts.append(
            f"Players faced each other in match {same_match} — merge would "
            f"make the match self-play"
        )

    if conflicts:
        return conflicts

    # --- Rewrite singular FK columns: simple updates ---

    await session.execute(
        update(match_orm.Match)
        .where(match_orm.Match.player_a_id == source_id)
        .values(player_a_id=target_id)
    )
    await session.execute(
        update(match_orm.Match)
        .where(match_orm.Match.player_b_id == source_id)
        .values(player_b_id=target_id)
    )
    await session.execute(
        update(team_orm.Team)
        .where(team_orm.Team.player_1_id == source_id)
        .values(player_1_id=target_id)
    )
    await session.execute(
        update(team_orm.Team)
        .where(team_orm.Team.player_2_id == source_id)
        .values(player_2_id=target_id)
    )

    # --- M2M tables: drop source row where target already exists, otherwise rewrite ---

    # tournament_applicants
    if overlap_app:
        await session.execute(
            delete(tournament_orm.tournament_applicants).where(
                tournament_orm.tournament_applicants.c.player_id == source_id,
                tournament_orm.tournament_applicants.c.tournament_id.in_(overlap_app),
            )
        )
    await session.execute(
        update(tournament_orm.tournament_applicants)
        .where(tournament_orm.tournament_applicants.c.player_id == source_id)
        .values(player_id=target_id)
    )

    # TournamentRegistration: overlap was rejected above, safe to rewrite
    await session.execute(
        update(tournament_orm.TournamentRegistration)
        .where(tournament_orm.TournamentRegistration.player_id == source_id)
        .values(player_id=target_id)
    )

    # league_members
    src_league_ids = {
        r for (r,) in await session.execute(
            select(league_orm.league_members.c.league_id).where(
                league_orm.league_members.c.player_id == source_id
            )
        )
    }
    tgt_league_ids = {
        r for (r,) in await session.execute(
            select(league_orm.league_members.c.league_id).where(
                league_orm.league_members.c.player_id == target_id
            )
        )
    }
    overlap_lg = src_league_ids & tgt_league_ids
    if overlap_lg:
        await session.execute(
            delete(league_orm.league_members).where(
                league_orm.league_members.c.player_id == source_id,
                league_orm.league_members.c.league_id.in_(overlap_lg),
            )
        )
    await session.execute(
        update(league_orm.league_members)
        .where(league_orm.league_members.c.player_id == source_id)
        .values(player_id=target_id)
    )

    # Soft-delete the source Player
    await session.execute(
        update(model.Player)
        .where(model.Player.uuid == source_id)
        .values(is_deleted=True)
    )

    await session.commit()
    return []


async def search_players(
    session: AsyncSession,
    nickname: str | None = None,
    email: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[model.Player]:
    stmt = select(model.Player)

    if nickname is not None:
        # FIXME: consider security implications of using ilike
        stmt = stmt.where(model.Player.nickname.ilike(f"%{nickname}%"))
    if email is not None:
        stmt = stmt.where(model.Player.email.ilike(f"%{email}%"))

    stmt = stmt.offset(skip).limit(limit)
    result = await session.scalars(stmt)
    return list(result)
