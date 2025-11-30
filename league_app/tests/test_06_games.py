from typing import AsyncContextManager, Callable
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.api.games.model import Game
from league_app.api.games.schema import GameCreate, GameOutput, GameUpdate
from league_app.api.players.model import Player
from league_app.api.tournaments.model import Tournament
from league_app.api.users.model import User

from .testlib import assert_response_code
from fastapi.encoders import jsonable_encoder


@pytest.mark.asyncio
async def test_admin_can_list_all_games(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    session: AsyncSession,
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
    player_factory,
    tournament_factory,
    game_factory,
):
    # prepare players, tournament and games
    creator = db_user1_with_pass[0]
    p1 = await player_factory({"nickname": "p1", "user_id": creator.id})
    p2 = await player_factory({"nickname": "p2", "user_id": creator.id})
    tournament = await tournament_factory(
        GameCreate(
            name="ListTestTournament", date="2025-07-20", location="Hall", owner_id=creator.id
        )
    )  # tournament_factory may accept TournamentCreate-like dict
    g1 = await game_factory(GameCreate(player_a_id=p1.uuid, player_b_id=p2.uuid, tournament_id=tournament.uuid))
    g2 = await game_factory(GameCreate(player_a_id=p2.uuid, player_b_id=p1.uuid, tournament_id=tournament.uuid))

    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.get("/api/v1/games/")
    assert_response_code(response, 200)
    returned = [GameOutput(**g) for g in response.json()]
    assert GameOutput.model_validate(g1) in returned
    assert GameOutput.model_validate(g2) in returned


@pytest.mark.asyncio
async def test_create_game(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    db_player1,
    db_player2,
):
    user = db_user1_with_pass[0]
    p1 = db_player1
    p2 = db_player2
    payload = jsonable_encoder(
        {
            "player_a_id": str(p1.uuid),
            "player_b_id": str(p2.uuid),
            "score_a": 0,
            "score_b": 0,
            "tournament_id": None,
        }
    )
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post("/api/v1/games/", json=payload)
    assert_response_code(response, 200)
    data = response.json()
    stmt = select(Game).filter(Game.uuid == UUID(data["uuid"]))
    db_game = await session.scalar(stmt)
    assert db_game is not None
    assert GameOutput.model_validate(db_game) == GameOutput(**data)
    # cleanup
    await session.delete(db_game)
    await session.commit()


@pytest.mark.asyncio
async def test_get_game_details(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    game_factory,
):
    creator = db_user1_with_pass[0]
    g = await game_factory(GameCreate(player_a_id=None, player_b_id=None, score_a=0, score_b=0, tournament_id=None))
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get(f"/api/v1/games/{g.uuid}")
    assert_response_code(response, 200)
    assert GameOutput.model_validate(g) == GameOutput(**response.json())


@pytest.mark.asyncio
async def test_update_game_result(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    game_factory,
):
    user = db_user1_with_pass[0]
    g = await game_factory(GameCreate(player_a_id=None, player_b_id=None, score_a=0, score_b=0, tournament_id=None))
    update = {"uuid": str(g.uuid), "score_a": 10, "score_b": 8, "is_finished": True}
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.patch(f"/api/v1/games/{g.uuid}", json=update)
    assert_response_code(response, 200)
    data = response.json()
    assert data["score_a"] == 10
    assert data["score_b"] == 8
    await session.refresh(g)
    assert getattr(g, "is_finished", False)


@pytest.mark.asyncio
async def test_delete_game_by_owner(
    logged_client: Callable[[User, str], AsyncContextManager[AsyncClient]],
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    game_factory,
):
    user = db_user1_with_pass[0]
    g = await game_factory(GameCreate(player_a_id=None, player_b_id=None, score_a=0, score_b=0, tournament_id=None))
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.delete(f"/api/v1/games/{g.uuid}")
    assert_response_code(response, 200)
    await session.refresh(g)
    assert getattr(g, "is_deleted", False) or not getattr(g, "is_active", True)