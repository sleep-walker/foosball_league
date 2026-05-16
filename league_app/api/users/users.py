import uuid
from typing import Optional

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from league_app.database import get_session_for_api
from sqlalchemy.ext.asyncio import AsyncSession

from .model import AccessToken, User
from league_app.config import get_settings, Settings

from collections.abc import AsyncGenerator


async def get_user_db(
    session: AsyncSession = Depends(get_session_for_api),
) -> AsyncGenerator[SQLAlchemyUserDatabase[User, uuid.UUID], None]:
    yield SQLAlchemyUserDatabase(session, User)


async def get_access_token_db(
    session: AsyncSession = Depends(get_session_for_api),
):
    yield SQLAlchemyAccessTokenDatabase(session, AccessToken)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = get_settings().SECRET_KEY
    verification_token_secret = get_settings().SECRET_KEY

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        settings = get_settings()
        updates = {}

        # Auto-promote admin
        admin_email = settings.ADMIN_EMAIL.strip().lower()
        if admin_email and user.email.lower() == admin_email:
            updates["is_superuser"] = True
            updates["is_verified"] = True
            print(f"User {user.email} promoted to superuser (ADMIN_EMAIL match).")

        # Auto-verify (dev mode)
        if settings.AUTO_VERIFY_USERS and not user.is_verified:
            updates["is_verified"] = True

        if updates:
            user = await self.user_db.update(user, updates)

        print(f"User {user.id} ({user.email}) has registered.")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        print(f"User {user.id} has forgot their password. Reset token: {token}")

    async def on_after_request_verify(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        print(f"Verification requested for user {user.id}. Verification token: {token}")


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[User, uuid.UUID] = Depends(get_user_db),
):
    yield UserManager(user_db)


bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy(
    settings: Settings = Depends(get_settings),
) -> JWTStrategy[User, uuid.UUID]:
    return JWTStrategy[User, uuid.UUID](
        secret=settings.SECRET_KEY, lifetime_seconds=settings.TOKEN_LIFETIME
    )


auth_backend = AuthenticationBackend[User, uuid.UUID](
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
current_active_verified_user = fastapi_users.current_user(active=True, verified=True)
current_superuser = fastapi_users.current_user(
    active=True, superuser=True, verified=True
)
# Optional auth: returns None if no/invalid token. Used by public endpoints
# that adapt their behaviour for logged-in users (e.g. self-registration
# binding the new Player to the authenticated User).
current_user_optional = fastapi_users.current_user(optional=True)
