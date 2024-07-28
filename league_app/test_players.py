from uuid import uuid4, UUID
from fastapi.testclient import TestClient
from . import models
from . import schemas

# ** Test /api/v1/players/


def test_read_player(client, db_player1):
    response = client.get("/api/v1/players/")
    data = response.json()
    # data["uuid"] = UUID(data["uuid"])
    assert response.status_code == 200
    p1data = schemas.PlayerOutput.from_orm(db_player1).model_dump()
    p1data["uuid"] = str(p1data["uuid"])
    assert data == [p1data]


def test_create_player(client, player1, db):
    response = client.post(
        "/api/v1/players/",
        json=player1,
    )
    assert response.status_code == 200
    data = response.json()
    db_player = (
        db.query(models.Player).filter(models.Player.uuid == UUID(data["uuid"])).first()
    )
    player1["uuid"] = UUID(data["uuid"])
    for field in ("first_name", "last_name", "nickname", "email", "uuid"):
        assert getattr(db_player, field) == player1[field]

    db.delete(db_player)
    db.commit()


def test_create_player_existing_email(client, player1, db_player1):
    response = client.post(
        "/api/v1/players/",
        json=player1,
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Email already registered"}


def test_create_player_existing_nickname(client, player1, db_player1):
    player1["email"] = "different_" + player1["email"]
    response = client.post(
        "/api/v1/players/",
        json=player1,
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Nickname already registered"}


def test_update_existing_player_as_the_user_himself(client, player1, db, db_player1):
    player1["last_name"] = "baz"
    player1["uuid"] = str(db_player1.uuid)
    response = client.put(f"/api/v1/players/{str(db_player1.uuid)}", json=player1)
    p1_data = {k: v for k, v in player1.items() if k not in ("email")}
    assert response.status_code == 200
    assert response.json() == p1_data
    db.refresh(db_player1)
    assert db_player1.last_name == "baz"


def test_update_existing_player_as_admin(client, player1, db, db_player1):
    player1["last_name"] = "baz"
    player1["uuid"] = str(db_player1.uuid)
    response = client.put(f"/api/v1/players/{str(db_player1.uuid)}", json=player1)
    p1_data = {k: v for k, v in player1.items() if k not in ("email")}
    assert response.status_code == 200
    assert response.json() == p1_data
    db.refresh(db_player1)
    assert db_player1.last_name == "baz"


def test_update_existing_player_as_another_player(client, player1, db, db_player1):
    response = client.put(f"/api/v1/players/{str(db_player1.uuid)}", json=player1)
    p1_data = {k: v for k, v in player1.items() if k not in ("email")}
    assert response.status_code == 403
    assert response.json() == {"detail": "User not authorized to modify someone else."}


def test_update_email_of_existing_player(client, player1, db, db_player1):
    uuid = str(db_player1.uuid)
    player1["email"] = "foo@baz.com"
    player1["uuid"] = uuid
    response = client.put(f"/api/v1/players/{uuid}", json=player1)
    p1_data = {k: v for k, v in player1.items() if k not in ("email")}
    assert response.status_code == 200
    db.refresh(db_player1)
    assert db_player1.email == "foo@baz.com"


def test_update_uuid_of_existing_player(client, player1, db_player1):
    uuid = str(db_player1.uuid)
    player1["uuid"] = "12345678-1234-abcd-abcd-1234567890ab"
    response = client.put(f"/api/v1/players/{uuid}", json=player1)
    assert response.status_code == 403
    assert response.json() == {"detail": "User cannot change his UUID"}


# ** Test self /api/v1/players/self


def test_get_self_player(client, db_player1):
    response = client.get("/api/v1/players/self")
    data = response.json()
    # data["uuid"] = UUID(data["uuid"])
    assert response.status_code == 200
    p1data = schemas.PlayerOutput.from_orm(db_player1).model_dump()
    p1data["uuid"] = str(p1data["uuid"])
    assert data == [p1data]


def test_update_self_player(client, player1, db, db_player1):
    player1["last_name"] = "baz"
    player1["uuid"] = str(db_player1.uuid)
    response = client.put(f"/api/v1/players/self", json=player1)
    p1_data = {k: v for k, v in player1.items() if k not in ("email")}
    assert response.status_code == 200
    assert response.json() == p1_data
    db.refresh(db_player1)
    assert db_player1.last_name == "baz"


# def test_read_item():
#     response = client.get("/items/foo", headers={"X-Token": "coneofsilence"})
#     assert response.status_code == 200
#     assert response.json() == {
#         "id": "foo",
#         "title": "Foo",
#         "description": "There goes my hero",
#     }


# def test_read_item_bad_token():
#     response = client.get("/items/foo", headers={"X-Token": "hailhydra"})
#     assert response.status_code == 400
#     assert response.json() == {"detail": "Invalid X-Token header"}


# def test_read_nonexistent_item():
#     response = client.get("/items/baz", headers={"X-Token": "coneofsilence"})
#     assert response.status_code == 404
#     assert response.json() == {"detail": "Item not found"}


# def test_create_item():
#     response = client.post(
#         "/items/",
#         headers={"X-Token": "coneofsilence"},
#         json={"id": "foobar", "title": "Foo Bar", "description": "The Foo Barters"},
#     )
#     assert response.status_code == 200
#     assert response.json() == {
#         "id": "foobar",
#         "title": "Foo Bar",
#         "description": "The Foo Barters",
#     }


# def test_create_item_bad_token():
#     response = client.post(
#         "/items/",
#         headers={"X-Token": "hailhydra"},
#         json={"id": "bazz", "title": "Bazz", "description": "Drop the bazz"},
#     )
#     assert response.status_code == 400
#     assert response.json() == {"detail": "Invalid X-Token header"}


# def test_create_existing_item():
#     response = client.post(
#         "/items/",
#         headers={"X-Token": "coneofsilence"},
#         json={
#             "id": "foo",
#             "title": "The Foo ID Stealers",
#             "description": "There goes my stealer",
#         },
#     )
#     assert response.status_code == 409
#     assert response.json() == {"detail": "Item already exists"}
