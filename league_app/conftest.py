from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest

from .database import Base
from .main import app, get_db
from . import models

SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


Base.metadata.create_all(bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session")
def client():
    yield TestClient(app)


@pytest.fixture(scope="function")
def player1():
    yield {
        "first_name": "foo",
        "last_name": "bar",
        "nickname": "foobar",
        "email": "foo@bar.com",
    }


@pytest.fixture(scope="session")
def db():
    yield TestingSessionLocal()


@pytest.fixture(scope="function")
def db_player1(db, player1):
    db_player = models.Player(**player1)

    db.add(db_player)
    db.commit()
    db.refresh(db_player)

    yield db_player

    db.delete(db_player)
    db.commit()
