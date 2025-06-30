import uuid
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (AuthenticationBackend,
                                          BearerTransport, JWTStrategy)
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import \
    SQLAlchemyAccessTokenDatabase
from league_app.database import get_session_for_api
from sqlalchemy.ext.asyncio import AsyncSession

from .model import AccessToken, User, Role

SECRET = "SECRET"


from collections.abc import AsyncGenerator

async def get_user_db(session: AsyncSession = Depends(get_session_for_api)) -> AsyncGenerator[SQLAlchemyUserDatabase[User, uuid.UUID], None]:
    yield SQLAlchemyUserDatabase(session, User)


async def get_access_token_db(
    session: AsyncSession = Depends(get_session_for_api),
):
    yield SQLAlchemyAccessTokenDatabase(session, AccessToken)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        print(f"User {user.id} has registered.")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        print(f"User {user.id} has forgot their password. Reset token: {token}")

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        print(f"Verification requested for user {user.id}. Verification token: {token}")


async def get_user_manager(user_db: SQLAlchemyUserDatabase[User, uuid.UUID] = Depends(get_user_db)):
    yield UserManager(user_db)


bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy[User, uuid.UUID]:
    return JWTStrategy[User, uuid.UUID](secret=SECRET, lifetime_seconds=3600)


auth_backend = AuthenticationBackend[User, uuid.UUID](
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
current_active_verified_user = fastapi_users.current_user(active=True, verified=True)


async def current_active_verified_administrator():
    user = await current_active_verified_user()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if user.role != Role("admin"):
        raise HTTPException(
            status_code=401, detail="Administrator permissions required"
        )
    return user


async def current_active_verified_tournament_organizer():
    user = await current_active_verified_user()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if user.role not in (Role("admin"), Role("tournament_organizer"), Role("league_organizer")):
        raise HTTPException(
            status_code=401, detail="Tournament organizer permissions required"
        )
    return user


async def current_active_verified_league_organizer():
    user = await current_active_verified_user()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if user.role not in (Role("admin"), Role("league_organizer")):
        raise HTTPException(
            status_code=401, detail="Tournament organizer permissions required"
        )
    return user


current_superuser = fastapi_users.current_user(active=True, superuser=True)
