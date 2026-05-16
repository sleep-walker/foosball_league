from uuid import UUID

import pytest
from league_app.api.players.model import Player
from league_app.api.players.schema import PlayerCreate, PlayerOutput, PlayerUpdate
from league_app.api.users.model import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .conftest import PlayerFactoryType
from .testlib import assert_response_code
from fastapi.encoders import jsonable_encoder


# * /api/v1/players/


@pytest.mark.asyncio
async def test_admin_can_list_all_players(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    session: AsyncSession,
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that an admin can list all players in the system.
    """
    db_user1 = db_user1_with_pass[0]
    # Create players for different users
    player1 = await player_factory(PlayerCreate(user_id=None, nickname="p1"))
    player2 = await player_factory(PlayerCreate(user_id=db_user1.id, nickname="p2"))

    print(f"Created players: {player1.uuid}, {player2.uuid}")
    # Override current user as admin
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.get("/api/v1/players/")
    assert_response_code(response, 200)

    returned_players = [PlayerOutput(**p) for p in response.json()]
    assert PlayerOutput.model_validate(player1) in returned_players
    assert PlayerOutput.model_validate(player2) in returned_players


@pytest.mark.asyncio
async def test_create_player(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    player1: dict[str, str],
):
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post("/api/v1/players/", json=player1)
    print(response.json())
    assert_response_code(response, 200)
    data = response.json()
    stmt = select(Player).filter(Player.uuid == UUID(data["uuid"]))
    db_player = await session.scalar(stmt)

    assert db_player is not None
    assert PlayerOutput.model_validate(db_player) == PlayerOutput(**data)

    # test cleanup
    await session.delete(db_player)
    await session.commit()


@pytest.mark.asyncio
async def test_create_player_existing_email(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    player1: dict[str, str],
    db_player1: Player,
    db_user1_with_pass: tuple[User, str],
):
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post(
            "/api/v1/players/",
            json=player1,
        )
    assert response.json() == {"detail": "Email already registered"}
    assert_response_code(response, 400)


@pytest.mark.asyncio
async def test_create_player_existing_nickname(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    player1: dict[str, str],
    db_player1: Player,
    db_user1_with_pass: tuple[User, str],
):
    player1["email"] = "different_" + player1["email"]
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post(
            "/api/v1/players/",
            json=player1,
        )
    assert response.json() == {"detail": "Nickname already registered"}
    assert_response_code(response, 400)


# * /api/v1/players/{uuid}


@pytest.mark.asyncio
async def test_get_player_details(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    db_user2_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that a user can get details of a player linked to their user_id.
    """
    db_user1 = db_user1_with_pass[0]
    player = await player_factory(
        PlayerCreate(user_id=db_user1.id, nickname="test_player")
    )
    async with logged_client(*db_user2_with_pass) as client:
        response = await client.get(f"/api/v1/players/{player.uuid}")
    assert_response_code(response, 200)
    data = response.json()
    assert PlayerOutput.model_validate(player) == PlayerOutput(**data)


@pytest.mark.asyncio
async def test_user_can_update_own_player(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that a user can update a player linked to their user_id.
    """
    db_user1 = db_user1_with_pass[0]
    player = await player_factory(
        PlayerCreate(user_id=db_user1.id, nickname="editable_player")
    )
    update_data = {"uuid": str(player.uuid), "nickname": "updated_nickname"}
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.put(f"/api/v1/players/{player.uuid}", json=update_data)
    assert_response_code(response, 200)
    assert response.json()["nickname"] == "updated_nickname"
    await session.refresh(player)
    assert player.nickname == "updated_nickname"


@pytest.mark.asyncio
async def test_admin_can_update_any_player(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    session: AsyncSession,
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that an admin can update any player's details.
    """
    db_user1 = db_user1_with_pass[0]
    db_player = await player_factory(
        PlayerCreate(nickname="admin_editable_player", user_id=db_user1.id)
    )
    updated_data = {"uuid": str(db_player.uuid), "nickname": "admin_updated_nickname"}

    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.put(
            f"/api/v1/players/{db_player.uuid}", json=updated_data
        )
    assert_response_code(response, 200)
    assert response.json()["nickname"] == "admin_updated_nickname"
    await session.refresh(db_player)
    assert db_player.nickname == "admin_updated_nickname"


@pytest.mark.asyncio
async def test_user_cannot_update_player_of_another_user(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    db_user2_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that a user cannot update a player not linked to their user_id.
    """
    db_user2 = db_user2_with_pass[0]
    player = await player_factory(
        PlayerCreate(user_id=db_user2.id, nickname="not_my_player")
    )
    updated_player = PlayerUpdate.model_validate(player)
    updated_player.nickname = "hacker_attempt"
    updated_payload = jsonable_encoder(updated_player)

    async with logged_client(*db_user1_with_pass) as client:
        # Attempt to update a player not linked to the user
        response = await client.put(
            f"/api/v1/players/{player.uuid}", json=updated_payload
        )
    assert_response_code(response, 403)


@pytest.mark.asyncio
async def test_update_email_of_existing_player(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    db_user1 = db_user1_with_pass[0]
    db_player = await player_factory(
        PlayerCreate(
            user_id=db_user1.id,
            nickname="player_a",
            email="foo@example.com",
            first_name="Player",
            last_name="A",
        )
    )
    updated_player = PlayerUpdate.model_validate(db_player)
    updated_player.email = "foo@baz.com"
    updated_payload = jsonable_encoder(updated_player)

    async with logged_client(*db_user1_with_pass) as client:
        response = await client.put(
            f"/api/v1/players/{db_player.uuid}", json=updated_payload
        )
    print(response.json())
    assert_response_code(response, 200)
    await session.refresh(db_player)
    assert updated_payload["email"] == response.json()["email"]
    assert PlayerOutput(**response.json()) == PlayerOutput.model_validate(db_player)


@pytest.mark.asyncio
async def test_update_uuid_of_existing_player(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    db_user1 = db_user1_with_pass[0]
    db_player = await player_factory(
        PlayerCreate(
            user_id=db_user1.id,
            nickname="player_a",
            email="foo@example.com",
            first_name="Player",
            last_name="A",
        )
    )
    updated_player = PlayerUpdate.model_validate(db_player)
    updated_player.uuid = UUID("12345678-1234-abcd-abcd-1234567890ab")
    updated_payload = jsonable_encoder(updated_player)
    uuid = str(db_player.uuid)
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.put(f"/api/v1/players/{uuid}", json=updated_payload)
    assert_response_code(response, 403)
    assert response.json() == {"detail": "User cannot change his UUID"}


# * Test self /api/v1/players/self


@pytest.mark.asyncio
async def test_user_with_no_linked_players_gets_empty_list(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
):
    """
    Test that a user with no linked players gets an empty list.
    """
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/players/self")
    assert_response_code(response, 200)
    assert response.json() == []


@pytest.mark.asyncio
async def test_player_with_null_user_id_not_returned(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that players with user_id=None are not returned in /players/self.
    """
    await player_factory(PlayerCreate(user_id=None, nickname="orphan_player"))
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/players/self")
    assert_response_code(response, 200)
    data = response.json()
    assert all(p["nickname"] != "orphan_player" for p in data)


@pytest.mark.asyncio
async def test_list_players_linked_to_user(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that a user can list all players linked to their user_id.
    """
    db_user1 = db_user1_with_pass[0]
    # Create two players linked to the same user
    player_a = await player_factory(
        PlayerCreate(
            user_id=db_user1.id,
            nickname="player_a",
            email="player_a@example.com",
            first_name="Player",
            last_name="A",
        )
    )
    player_b = await player_factory(
        PlayerCreate(
            user_id=db_user1.id, nickname="player_b", email="player_b@example.com"
        )
    )

    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/players/self")
    assert_response_code(response, 200)
    data = response.json()
    returned_uuids = {p["uuid"] for p in data}
    assert {str(player_a.uuid), str(player_b.uuid)}.issubset(returned_uuids)


@pytest.mark.asyncio
async def test_user_cannot_list_players_of_another_user(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
    db_user2_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that a user cannot see players linked to another user.
    """
    db_user1 = db_user1_with_pass[0]
    db_user2 = db_user2_with_pass[0]
    await player_factory(PlayerCreate(user_id=db_user1.id, nickname="my_player"))  # type: ignore
    # Create a player for another user
    player_other = await player_factory(
        PlayerCreate(user_id=db_user2.id, nickname="other_player")
    )

    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/players/self")
    assert_response_code(response, 200)
    data = response.json()
    # Ensure the other user's player is not in the list
    assert all(p["uuid"] != str(player_other.uuid) for p in data)


# * /api/v1/players/search?nickname={nickname}


@pytest.mark.asyncio
async def test_user_search_players_by_nickname(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
    session: AsyncSession,
):
    """
    Test that a user can search for players by nickname.
    """
    db_player = await player_factory(
        PlayerCreate(
            user_id=None,
            nickname="searched player",
            email="searched_player@example.com",
        )
    )
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/players/search?nickname=searched%20player")
    assert_response_code(response, 200)
    data = response.json()
    assert len(data) == 1
    output_player = PlayerOutput(**(data[0]))
    output_db_player = PlayerOutput.model_validate(db_player)
    assert output_player.email is None, "Email should not be visible to regular users"
    output_db_player.email = None  # Ensure email is not compared
    assert output_player == output_db_player


@pytest.mark.asyncio
async def test_user_search_players_by_email(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that a user can search for players by email.
    """
    db_player = await player_factory(  # type: ignore
        PlayerCreate(
            user_id=None,
            nickname="searched player",
            email="searched_player@example.com",
        )
    )
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get(
            "/api/v1/players/search?email=searched_player@example.com"
        )
    assert_response_code(response, 200)
    data = response.json()
    assert len(data) == 1
    output_player = PlayerOutput(**(data[0]))
    output_db_player = PlayerOutput.model_validate(db_player)
    # FIXME: check e-mail visibility based on user role
    assert output_player == output_db_player
    assert (
        output_player.email == output_db_player.email
    ), "Email should be visible to regular users if searched by email"


@pytest.mark.asyncio
async def test_admin_search_players_by_nickname(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_administrator1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """
    Test that an admin can search for players by nickname.
    """
    db_player = await player_factory(  # type: ignore
        PlayerCreate(
            user_id=None,
            nickname="searched player",
            email="searched_player@example.com",
        )
    )
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.get("/api/v1/players/search?nickname=searched%20player")
    assert_response_code(response, 200)
    data = response.json()
    assert len(data) == 1
    output_player = PlayerOutput(**(data[0]))
    output_db_player = PlayerOutput.model_validate(db_player)
    assert output_player == output_db_player
    assert output_player.email is not None, "Email should be visible to admins"


# ---------------------------------------------------------------------------
# Claim — admin-only Player → User linking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_can_claim_unclaimed_player(
    logged_client,
    session: AsyncSession,
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """Admin links an unclaimed Player to a User account."""
    target_user = db_user1_with_pass[0]
    player = await player_factory(PlayerCreate(user_id=None, nickname="unclaimed_alice"))

    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{player.uuid}/claim",
            json={"user_id": str(target_user.id)},
        )
    assert_response_code(response, 200)
    assert response.json()["user_id"] == str(target_user.id)

    # Verify persisted
    await session.refresh(player)
    assert player.user_id == target_user.id


@pytest.mark.asyncio
async def test_admin_claim_is_idempotent(
    logged_client,
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """Claiming a Player for the same User twice returns the same record."""
    target_user = db_user1_with_pass[0]
    player = await player_factory(
        PlayerCreate(user_id=target_user.id, nickname="alice_already_claimed")
    )

    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{player.uuid}/claim",
            json={"user_id": str(target_user.id)},
        )
    assert_response_code(response, 200)
    assert response.json()["user_id"] == str(target_user.id)


@pytest.mark.asyncio
async def test_admin_cannot_steal_claimed_player(
    logged_client,
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
    db_user2_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """A claimed Player must not be reassigned to a different User."""
    owner = db_user1_with_pass[0]
    attacker = db_user2_with_pass[0]
    player = await player_factory(
        PlayerCreate(user_id=owner.id, nickname="alice_owned")
    )

    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{player.uuid}/claim",
            json={"user_id": str(attacker.id)},
        )
    assert response.status_code == 409
    assert "different user" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_non_admin_cannot_claim_player(
    logged_client,
    db_user1_with_pass: tuple[User, str],
    db_user2_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """Regular users can't claim players — admin-only by design."""
    target_user = db_user2_with_pass[0]
    player = await player_factory(PlayerCreate(user_id=None, nickname="orphan"))

    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{player.uuid}/claim",
            json={"user_id": str(target_user.id)},
        )
    # fastapi-users returns 401 for non-superuser hitting a superuser-only route
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_claim_unknown_player_returns_404(
    logged_client,
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
):
    from uuid import uuid4 as _uuid4
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{_uuid4()}/claim",
            json={"user_id": str(db_user1_with_pass[0].id)},
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_claim_unknown_user_returns_404(
    logged_client,
    db_administrator1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    from uuid import uuid4 as _uuid4
    player = await player_factory(PlayerCreate(user_id=None, nickname="no_user"))
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{player.uuid}/claim",
            json={"user_id": str(_uuid4())},
        )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Merge — combine two Player records
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_can_merge_two_unclaimed_players(
    logged_client,
    session: AsyncSession,
    db_administrator1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """Two unclaimed Players merge into one; source is soft-deleted."""
    source = await player_factory(PlayerCreate(user_id=None, nickname="honza_typo"))
    target = await player_factory(PlayerCreate(user_id=None, nickname="honza"))

    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{source.uuid}/merge?into={target.uuid}"
        )
    assert_response_code(response, 200)
    assert response.json()["uuid"] == str(target.uuid)

    await session.refresh(source)
    assert source.is_deleted is True


@pytest.mark.asyncio
async def test_admin_merge_rejects_self(
    logged_client,
    db_administrator1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    player = await player_factory(PlayerCreate(user_id=None, nickname="lonely"))
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{player.uuid}/merge?into={player.uuid}"
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_admin_merge_unknown_player_returns_404(
    logged_client,
    db_administrator1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    from uuid import uuid4 as _uuid4
    target = await player_factory(PlayerCreate(user_id=None, nickname="alive"))
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{_uuid4()}/merge?into={target.uuid}"
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_merge_claimed_to_same_user_allowed(
    logged_client,
    session: AsyncSession,
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """Two Players claimed by the SAME User can be merged (e.g. consolidation)."""
    user = db_user1_with_pass[0]
    source = await player_factory(PlayerCreate(user_id=user.id, nickname="alt_nick"))
    target = await player_factory(PlayerCreate(user_id=user.id, nickname="main_nick"))

    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{source.uuid}/merge?into={target.uuid}"
        )
    assert_response_code(response, 200)


@pytest.mark.asyncio
async def test_admin_merge_claimed_to_different_user_rejected(
    logged_client,
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
    db_user2_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """Even admin cannot merge Players linked to different Users."""
    u1, u2 = db_user1_with_pass[0], db_user2_with_pass[0]
    source = await player_factory(PlayerCreate(user_id=u1.id, nickname="p_u1"))
    target = await player_factory(PlayerCreate(user_id=u2.id, nickname="p_u2"))

    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{source.uuid}/merge?into={target.uuid}"
        )
    assert response.status_code == 409
    assert "different users" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_non_organizer_cannot_merge(
    logged_client,
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """A user with no organiser role over either Player gets 403."""
    source = await player_factory(PlayerCreate(user_id=None, nickname="x"))
    target = await player_factory(PlayerCreate(user_id=None, nickname="y"))

    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{source.uuid}/merge?into={target.uuid}"
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_tournament_organizer_can_merge_unclaimed_in_scope(
    logged_client,
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """Tournament organiser can merge two unclaimed Players who are both
    applicants/registrations in a tournament they own."""
    from league_app.api.tournaments.model import Tournament, TournamentRegistration
    organiser = db_user1_with_pass[0]
    source = await player_factory(PlayerCreate(user_id=None, nickname="honza_x"))
    target = await player_factory(PlayerCreate(user_id=None, nickname="honza"))

    # Create a tournament owned by the organiser with both players registered
    tournament = Tournament(owner_id=organiser.id, date="2026-04-30", name="Mergecup")
    session.add(tournament)
    await session.flush()
    session.add_all([
        TournamentRegistration(tournament_id=tournament.uuid, player_id=source.uuid),
        TournamentRegistration(tournament_id=tournament.uuid, player_id=target.uuid),
    ])
    await session.commit()

    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{source.uuid}/merge?into={target.uuid}"
        )
    # Conflict expected: both registered in same tournament
    assert response.status_code == 409
    assert "registered in tournament" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_tournament_organizer_merges_applicant_into_registered(
    logged_client,
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """A typo-applicant is merged into the real registered Player."""
    from league_app.api.tournaments.model import (
        Tournament, TournamentRegistration, tournament_applicants,
    )
    from sqlalchemy import insert as sa_insert
    organiser = db_user1_with_pass[0]
    typo = await player_factory(PlayerCreate(user_id=None, nickname="honaz"))
    real = await player_factory(PlayerCreate(user_id=None, nickname="honza"))

    tournament = Tournament(owner_id=organiser.id, date="2026-05-01", name="Cup")
    session.add(tournament)
    await session.flush()
    session.add(TournamentRegistration(
        tournament_id=tournament.uuid, player_id=real.uuid
    ))
    await session.execute(
        sa_insert(tournament_applicants).values(
            tournament_id=tournament.uuid, player_id=typo.uuid
        )
    )
    await session.commit()

    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{typo.uuid}/merge?into={real.uuid}"
        )
    assert_response_code(response, 200)

    await session.refresh(typo)
    assert typo.is_deleted is True


# ---------------------------------------------------------------------------
# Self-claim by e-mail token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_claim_logs_token_for_unclaimed_player(
    logged_client,
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
    caplog,
):
    """request-claim emits a log line containing the token (stand-in for SMTP)."""
    import logging
    player = await player_factory(
        PlayerCreate(user_id=None, nickname="ghost", email="ghost@example.com")
    )
    async with logged_client(*db_user1_with_pass) as client:
        with caplog.at_level(logging.WARNING, logger="players"):
            response = await client.post(
                f"/api/v1/players/{player.uuid}/request-claim"
            )
    assert_response_code(response, 200)
    # Token format: "<b64>.<b64>"
    assert any("Token=" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_request_claim_rejects_player_without_email(
    logged_client,
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
):
    """Bypass the factory (which auto-fills fake e-mails) to test the
    truly e-mail-less Player case."""
    from uuid import uuid4 as _uuid4
    player = Player(uuid=_uuid4(), user_id=None, nickname="noemail", email=None)
    session.add(player)
    await session.commit()

    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post(f"/api/v1/players/{player.uuid}/request-claim")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_request_claim_rejects_already_claimed_player(
    logged_client,
    db_user1_with_pass: tuple[User, str],
    db_user2_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """Player already linked to a different user — no point sending claim mail."""
    owner = db_user1_with_pass[0]
    player = await player_factory(
        PlayerCreate(user_id=owner.id, nickname="taken", email="t@example.com")
    )
    async with logged_client(*db_user2_with_pass) as client:
        response = await client.post(f"/api/v1/players/{player.uuid}/request-claim")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_confirm_claim_happy_path(
    logged_client,
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """Mint a token directly (would normally come from e-mail) and confirm."""
    from league_app.api.players.router import _make_claim_token
    import time

    user = db_user1_with_pass[0]
    player = await player_factory(
        PlayerCreate(user_id=None, nickname="claimme", email="c@example.com")
    )
    token = _make_claim_token(player.uuid, user.id, int(time.time()) + 600)

    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{player.uuid}/confirm-claim",
            json={"token": token},
        )
    assert_response_code(response, 200)
    assert response.json()["user_id"] == str(user.id)

    await session.refresh(player)
    assert player.user_id == user.id


@pytest.mark.asyncio
async def test_confirm_claim_is_idempotent(
    logged_client,
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    from league_app.api.players.router import _make_claim_token
    import time

    user = db_user1_with_pass[0]
    player = await player_factory(
        PlayerCreate(user_id=None, nickname="claim2", email="c2@example.com")
    )
    token = _make_claim_token(player.uuid, user.id, int(time.time()) + 600)

    async with logged_client(*db_user1_with_pass) as client:
        r1 = await client.post(
            f"/api/v1/players/{player.uuid}/confirm-claim",
            json={"token": token},
        )
        r2 = await client.post(
            f"/api/v1/players/{player.uuid}/confirm-claim",
            json={"token": token},
        )
    assert_response_code(r1, 200)
    assert_response_code(r2, 200)


@pytest.mark.asyncio
async def test_confirm_claim_rejects_invalid_token(
    logged_client,
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    player = await player_factory(
        PlayerCreate(user_id=None, nickname="bad_tok", email="b@example.com")
    )
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{player.uuid}/confirm-claim",
            json={"token": "not-a-real-token"},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_confirm_claim_rejects_expired_token(
    logged_client,
    db_user1_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    from league_app.api.players.router import _make_claim_token
    user = db_user1_with_pass[0]
    player = await player_factory(
        PlayerCreate(user_id=None, nickname="exp", email="e@example.com")
    )
    # exp in the past
    token = _make_claim_token(player.uuid, user.id, 1)

    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{player.uuid}/confirm-claim",
            json={"token": token},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_confirm_claim_rejects_token_for_different_user(
    logged_client,
    db_user1_with_pass: tuple[User, str],
    db_user2_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """A token issued to user1 cannot be redeemed by user2."""
    from league_app.api.players.router import _make_claim_token
    import time

    user1 = db_user1_with_pass[0]
    player = await player_factory(
        PlayerCreate(user_id=None, nickname="cross", email="x@example.com")
    )
    # token was minted for user1 …
    token = _make_claim_token(player.uuid, user1.id, int(time.time()) + 600)

    # … but user2 tries to redeem it
    async with logged_client(*db_user2_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{player.uuid}/confirm-claim",
            json={"token": token},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_confirm_claim_rejects_player_already_claimed_by_other(
    logged_client,
    session: AsyncSession,
    db_user1_with_pass: tuple[User, str],
    db_user2_with_pass: tuple[User, str],
    player_factory: PlayerFactoryType,
):
    """If someone else claimed the Player between request and confirm — 409."""
    from league_app.api.players.router import _make_claim_token
    import time

    user1, user2 = db_user1_with_pass[0], db_user2_with_pass[0]
    player = await player_factory(
        PlayerCreate(user_id=None, nickname="race", email="r@example.com")
    )
    token = _make_claim_token(player.uuid, user1.id, int(time.time()) + 600)
    # Simulate someone else (user2) winning the race
    player.user_id = user2.id
    await session.commit()

    async with logged_client(*db_user1_with_pass) as client:
        response = await client.post(
            f"/api/v1/players/{player.uuid}/confirm-claim",
            json={"token": token},
        )
    assert response.status_code == 409
