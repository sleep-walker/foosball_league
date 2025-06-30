from httpx import AsyncClient
import pytest
from league_app.api.users import model
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


@pytest.mark.asyncio
async def test_auth_user_register(
    client: AsyncClient, session: AsyncSession, user1: dict[str, str]
) -> None:
    response = await client.post(
        "/auth/register",
        json=user1,
    )
    print(response.json())
    assert response.status_code == 201, f"Response code {response.status_code}: {response.json()}"

    # cleanup
    # typing.TYPE_CHECKING is not available in runtime, so we use type: ignore
    stmt = select(model.User).where(model.User.email == user1["email"])  # type: ignore
    db_user = await session.scalar(stmt)
    await session.delete(db_user)
    await session.commit()


@pytest.mark.asyncio
async def test_auth_user_register_existing_username(
    client: AsyncClient, session: AsyncSession, user1: dict[str, str], db_user1: model.User
) -> None:
    response = await client.post(
        "/auth/register",
        json=user1,
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "REGISTER_USER_ALREADY_EXISTS"}
