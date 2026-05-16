from httpx import AsyncClient
import pytest
from league_app.api.users import model
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from league_app.api.users.schema import UserCreate, UserSchema
from league_app.api.users.model import User
from uuid import uuid4
from .conftest import UserFactoryType
from .testlib import assert_response_code

# * /register


@pytest.mark.asyncio
async def test_auth_user_register(
    client: AsyncClient, session: AsyncSession, user1: UserCreate
) -> None:
    """Test registration of a new user."""
    response = await client.post(
        "/api/v1/users/register",
        json=user1.model_dump(),
    )
    print(response.json())
    assert_response_code(response, 201)

    # cleanup
    # typing.TYPE_CHECKING is not available in runtime, so we use type: ignore
    stmt = select(model.User).where(model.User.email == user1.email)  # type: ignore
    db_user = await session.scalar(stmt)
    await session.delete(db_user)
    await session.commit()


@pytest.mark.asyncio
async def test_auth_user_register_existing_email(
    client: AsyncClient,
    session: AsyncSession,
    user1: UserCreate,
    db_user1_with_pass: model.User,
) -> None:
    """Test registration of a user with an existing email."""
    response = await client.post(
        "/api/v1/users/register",
        json=user1.model_dump(),
    )
    assert_response_code(response, 400)
    assert response.json() == {"detail": "REGISTER_USER_ALREADY_EXISTS"}


# * /login


@pytest.mark.asyncio
async def test_auth_user_login(
    client: AsyncClient, db_user1_with_pass: model.User, user1: UserCreate
) -> None:
    response = await client.post(
        "/api/v1/users/login",
        data={
            "username": user1.email,
            "password": user1.password,
        },
    )
    assert_response_code(response, 200)
    assert "access_token" in response.json()
    assert "token_type" in response.json()
    assert response.json()["token_type"] == "bearer"

    response = await client.post(
        "/api/v1/users/logout",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_auth_user_login_invalid_credentials(
    client: AsyncClient, user1: UserCreate
) -> None:
    """Test login with invalid credentials."""
    response = await client.post(
        "/api/v1/users/login",
        data={
            "username": user1.email,
            "password": "wrongpassword",
        },
    )
    assert_response_code(response, 400)
    assert response.json() == {"detail": "LOGIN_BAD_CREDENTIALS"}


# * /me


@pytest.mark.asyncio
async def test_auth_user_me(
    user_factory: UserFactoryType,  # type: Callable[[UserCreate], Awaitable[User]]
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    user = UserCreate(
        email="some@random.org",
        password="foobar",
        is_superuser=False,
        is_active=True,
        is_verified=True,
    )
    db_user = await user_factory(user, commit=True)

    response = await client.post(
        "/api/v1/users/login",
        data={
            "username": user.email,
            "password": user.password,
        },
    )

    assert_response_code(response, 200)
    token = response.json()["access_token"]
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert UserSchema.model_validate(db_user) == UserSchema(**response.json())
    response = await client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "foo-" + user.email, "password": "bar-" + user.password},
    )
    assert_response_code(response, 200)
    assert response.json()["email"] == "foo-" + user.email

    # mark as verified so we can delete later
    await session.refresh(db_user)
    db_user.is_verified = True
    await session.commit()
    await session.refresh(db_user)
    assert db_user.is_verified is True

    # Now login with the new credentials
    response = await client.post(
        "/api/v1/users/login",
        data={
            "id": str(db_user.id),
            "username": "foo-" + user.email,
            "password": "bar-" + user.password,
        },
    )
    assert_response_code(response, 200)
    new_token = response.json()["access_token"]

    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {new_token}"},
    )
    # Now delete with the new token
    response = await client.delete(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {new_token}"},
    )
    assert_response_code(response, 204)


# * /search


@pytest.mark.asyncio
async def test_user_search_requires_admin(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
):
    # db_user1 is a regular user, not a superuser
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/users/search")
    assert_response_code(response, 403)


@pytest.mark.asyncio
async def test_user_search_returns_users(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
    session: AsyncSession,
):
    # Authenticate as admin (db_administrator1)
    db_user1 = db_user1_with_pass[0]
    db_administrator1 = db_administrator1_with_pass[0]
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.get("/api/v1/users/search")
    assert_response_code(response, 200)
    users = response.json()
    assert isinstance(users, list)
    # Should contain at least the admin user
    assert any(
        UserSchema(**u) == UserSchema.model_validate(db_administrator1)
        for u in response.json()
    )
    assert any(
        UserSchema(**u) == UserSchema.model_validate(db_user1) for u in response.json()
    )


@pytest.mark.asyncio
async def test_user_search_filters(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    user_factory: UserFactoryType,  # type: Callable[[UserCreate], Awaitable[User]]
    db_administrator1_with_pass: tuple[User, str],
    session: AsyncSession,
):
    """Test that user search can filter by email, is_active, is_verified, and is_superuser."""
    db_administrator1 = db_administrator1_with_pass[0]
    email = "unique_search@example.com"
    uniq_user = await user_factory(
        UserCreate(
            email=email,
            password="x",
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
    )

    async with logged_client(*db_administrator1_with_pass) as client:
        email_response = await client.get(f"/api/v1/users/search?email={email}")
        active_response = await client.get("/api/v1/users/search?is_active=true")
        verified_response = await client.get("/api/v1/users/search?is_verified=true")

    assert_response_code(email_response, 200)
    assert_response_code(active_response, 200)
    assert_response_code(verified_response, 200)

    assert any(
        UserSchema(**u) == UserSchema.model_validate(uniq_user)
        for u in email_response.json()
    )

    assert any(
        UserSchema(**u) == UserSchema.model_validate(db_administrator1)
        for u in active_response.json()
    )
    assert any(
        UserSchema(**u) == UserSchema.model_validate(uniq_user)
        for u in active_response.json()
    )

    assert any(
        UserSchema(**u) == UserSchema.model_validate(uniq_user)
        for u in verified_response.json()
    )
    assert any(
        UserSchema(**u) == UserSchema.model_validate(db_administrator1)
        for u in verified_response.json()
    )


# * /users/{uuid}


@pytest.mark.asyncio
async def test_get_user_requires_login(
    client: AsyncClient, db_user1_with_pass: tuple[User, str]
):
    # Not logged in
    db_user1 = db_user1_with_pass[0]
    response = await client.get(f"/api/v1/users/{db_user1.id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_user_doesnt_work_for_self(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
):
    db_user1 = db_user1_with_pass[0]
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get(f"/api/v1/users/{db_user1.id}")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_user_works_for_admin(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
):
    db_user1 = db_user1_with_pass[0]
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.get(f"/api/v1/users/{db_user1.id}")
    assert response.status_code == 200
    assert UserSchema(**response.json()).id == db_user1.id


@pytest.mark.asyncio
async def test_get_user_non_existing(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_administrator1_with_pass: tuple[User, str],
):
    non_existing_uuid = str(uuid4())
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.get(f"/api/v1/users/{non_existing_uuid}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_patch_user_requires_admin(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
):
    db_user1 = db_user1_with_pass[0]
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.patch(
            f"/api/v1/users/{db_user1.id}", json={"email": "new@email.com"}
        )
    assert response.status_code == 401 or response.status_code == 403


@pytest.mark.asyncio
async def test_patch_user_admin_success(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],
    session: AsyncSession,
):
    new_email = "changed@email.com"
    db_user1 = db_user1_with_pass[0]
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.patch(
            f"/api/v1/users/{db_user1.id}", json={"email": new_email}
        )
    assert response.status_code == 200
    assert response.json()["email"] == new_email
    # Optionally, check DB
    await session.refresh(db_user1)
    assert db_user1.email == new_email


@pytest.mark.asyncio
async def test_patch_user_non_existing(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_administrator1_with_pass: tuple[User, str],
):
    non_existing_uuid = str(uuid4())
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.patch(
            f"/api/v1/users/{non_existing_uuid}", json={"email": "x@y.com"}
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_user_requires_admin(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
):
    db_user1 = db_user1_with_pass[0]
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.delete(f"/api/v1/users/{db_user1.id}")
    assert response.status_code == 401 or response.status_code == 403


@pytest.mark.asyncio
async def test_delete_user_admin_success(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_administrator1_with_pass: tuple[User, str],
    db_user2_with_pass: tuple[User, str],
    session: AsyncSession,
):
    db_user2 = db_user2_with_pass[0]
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.delete(f"/api/v1/users/{db_user2.id}")
    assert response.status_code == 204
    # Check user is gone
    user = await session.get(type(db_user2), db_user2.id)
    assert user is None


@pytest.mark.asyncio
async def test_delete_user_non_existing(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_administrator1_with_pass: tuple[User, str],
):
    non_existing_uuid = str(uuid4())
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.delete(f"/api/v1/users/{non_existing_uuid}")
    assert response.status_code == 404


# temporary route for testing authenticated user
@pytest.mark.asyncio
async def test_authenticated_route(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
):
    db_user1 = db_user1_with_pass[0]
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/users/authenticated-route")
    assert response.status_code == 200
    assert response.json() == {"message": f"Hello {db_user1.id}!"}


# * /users


# admin can list all users
@pytest.mark.asyncio
async def test_users_get_by_admin(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_administrator1_with_pass: tuple[User, str],
    db_user1_with_pass: tuple[User, str],  # type: ignore[unused-variable]  # noqa: F841
):
    async with logged_client(*db_administrator1_with_pass) as client:
        response = await client.get("/api/v1/users/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) > 0


# non-admin cannot list all users
@pytest.mark.asyncio
async def test_users_get_by_non_admin(
    logged_client,  # type: Callable[[User, str], AsyncContextManager[AsyncClient]]
    db_user1_with_pass: tuple[User, str],
):
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/users/")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# /me/player and /me/players — Player profiles linked to the current user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_players_empty_for_user_without_profiles(
    logged_client,
    db_user1_with_pass: tuple[User, str],
):
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/users/me/players")
    assert_response_code(response, 200)
    assert response.json() == []


@pytest.mark.asyncio
async def test_me_player_null_for_user_without_profile(
    logged_client,
    db_user1_with_pass: tuple[User, str],
):
    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/users/me/player")
    assert_response_code(response, 200)
    assert response.json() == {"player_id": None}


@pytest.mark.asyncio
async def test_me_players_returns_all_linked_players_sorted(
    logged_client,
    db_user1_with_pass: tuple[User, str],
    player_factory,
):
    """User with three linked Players gets all three, ordered by nickname."""
    from league_app.api.players.schema import PlayerCreate
    user = db_user1_with_pass[0]
    await player_factory(PlayerCreate(user_id=user.id, nickname="charlie"))
    await player_factory(PlayerCreate(user_id=user.id, nickname="alpha"))
    await player_factory(PlayerCreate(user_id=user.id, nickname="bravo"))

    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/users/me/players")
    assert_response_code(response, 200)
    nicknames = [p["nickname"] for p in response.json()]
    assert nicknames == ["alpha", "bravo", "charlie"]


@pytest.mark.asyncio
async def test_me_player_returns_primary_when_multiple_linked(
    logged_client,
    db_user1_with_pass: tuple[User, str],
    player_factory,
):
    """``/me/player`` returns the first by nickname when multiple exist."""
    from league_app.api.players.schema import PlayerCreate
    user = db_user1_with_pass[0]
    await player_factory(PlayerCreate(user_id=user.id, nickname="zulu"))
    await player_factory(PlayerCreate(user_id=user.id, nickname="alpha"))

    async with logged_client(*db_user1_with_pass) as client:
        response = await client.get("/api/v1/users/me/player")
    assert_response_code(response, 200)
    assert response.json()["nickname"] == "alpha"


@pytest.mark.asyncio
async def test_me_players_isolates_users(
    logged_client,
    db_user1_with_pass: tuple[User, str],
    db_user2_with_pass: tuple[User, str],
    player_factory,
):
    """User1's Players don't leak into User2's /me/players response."""
    from league_app.api.players.schema import PlayerCreate
    u1, u2 = db_user1_with_pass[0], db_user2_with_pass[0]
    await player_factory(PlayerCreate(user_id=u1.id, nickname="user1_p"))
    await player_factory(PlayerCreate(user_id=u2.id, nickname="user2_p"))

    async with logged_client(*db_user2_with_pass) as client:
        response = await client.get("/api/v1/users/me/players")
    assert_response_code(response, 200)
    nicknames = {p["nickname"] for p in response.json()}
    assert nicknames == {"user2_p"}
