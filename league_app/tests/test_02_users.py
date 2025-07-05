from httpx import AsyncClient
import pytest
from league_app.api.users import model
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Callable, AsyncContextManager
from sqlalchemy import select
from league_app.api.users.schema import UserCreate, UserRead
from league_app.api.users.model import User

from .conftest import UserFactoryType
from .testlib import assert_response_code

@pytest.mark.asyncio
async def test_auth_user_register(
    client: AsyncClient, session: AsyncSession, user1: UserCreate
) -> None:
    response = await client.post(
        "/api/v1/users/auth/register",
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
async def test_auth_user_register_existing_username(
    client: AsyncClient, session: AsyncSession, user1: UserCreate, db_user1: model.User
) -> None:
    response = await client.post(
        "/api/v1/users/auth/register",
        json=user1.model_dump(),
    )
    assert_response_code(response, 400)
    assert response.json() == {"detail": "REGISTER_USER_ALREADY_EXISTS"}

@pytest.mark.asyncio
async def test_user_search_requires_admin(
    logged_client,  # type: Callable[[User], AsyncContextManager[AsyncClient]]
    db_user1: User):
    # db_user1 is a regular user, not a superuser
    async with logged_client(db_user1) as client:
        response = await client.get("/api/v1/users/search")
    assert_response_code(response, 401)


@pytest.mark.asyncio
async def test_user_search_returns_users(
        logged_client,  # type: Callable[[User], AsyncContextManager[AsyncClient]]
        db_administrator1: User, db_user1: User, session: AsyncSession):
    # Authenticate as admin (db_administrator1)

    async with logged_client(db_administrator1) as client:
        response = await client.get("/api/v1/users/search")
    assert_response_code(response, 200)
    users = response.json()
    assert isinstance(users, list)
    # Should contain at least the admin user
    assert any(UserRead(**u) == UserRead.model_validate(db_administrator1) for u in response.json())
    assert any(UserRead(**u) == UserRead.model_validate(db_user1) for u in response.json())


@pytest.mark.asyncio
async def test_user_search_filters(
    logged_client,  # type: Callable[[User], AsyncContextManager[AsyncClient]]
    user_factory: UserFactoryType,  # type: Callable[[UserCreate], Awaitable[User]]
    db_administrator1: User, session: AsyncSession):
    """Test that user search can filter by email, is_active, is_verified, and is_superuser."""
    email = "unique_search@example.com"
    uniq_user = await user_factory(UserCreate(email=email, password="x", is_active=True, is_verified=True, is_superuser=False))

    async with logged_client(db_administrator1) as client:
        email_response = await client.get(f"/api/v1/users/search?email={email}")
        active_response = await client.get("/api/v1/users/search?is_active=true")
        verified_response = await client.get("/api/v1/users/search?is_verified=true")

    assert_response_code(email_response, 200)
    assert_response_code(active_response, 200)
    assert_response_code(verified_response, 200)

    assert any(UserRead(**u) == UserRead.model_validate(uniq_user) for u in email_response.json())

    assert any(UserRead(**u) == UserRead.model_validate(db_administrator1) for u in active_response.json())
    assert any(UserRead(**u) == UserRead.model_validate(uniq_user) for u in active_response.json())

    assert any(UserRead(**u) == UserRead.model_validate(uniq_user) for u in verified_response.json())
    assert any(UserRead(**u) == UserRead.model_validate(db_administrator1) for u in verified_response.json())

