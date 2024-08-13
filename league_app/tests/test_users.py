import pytest
from league_app.api.users import model


@pytest.mark.asyncio
async def test_auth_user_register(client):
    response = await client.post(
        "/auth/register",
        json={"email": "foo1@bar.com", "password": "foobar"},
    )
    print(response.json())
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_auth_user_register_existing_username(client, db_user1: model.User):
    response = await client.post(
        "/auth/register",
        json={"email": db_user1.email, "password": db_user1.password},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Email already registered"}
