from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from league_app.database import get_session_for_api
from league_app.api.users.model import User as UserModel
from fastapi import APIRouter, Depends, HTTPException
from .users import (
    auth_backend,
    current_active_verified_user,
    current_superuser,
    fastapi_users,
)
from .schema import UserCreate, UserSchema, UserUpdate
from .model import User
from uuid import UUID
from fastapi_users import BaseUserManager
from fastapi import Response

router = APIRouter()


@router.delete("/me", status_code=204, tags=["users"])
async def delete_me(
    user: User = Depends(current_active_verified_user),
    user_manager: BaseUserManager[User, UUID] = Depends(fastapi_users.get_user_manager),
):
    if user.is_superuser:
        raise HTTPException(status_code=403, detail="Operation forbidden for superuser")
    await user_manager.delete(user)
    return Response(status_code=204)


@router.get("/search", response_model=list[UserSchema], tags=["users"])
async def search_users(
    email: str | None = None,
    is_active: bool | None = None,
    is_verified: bool | None = None,
    is_superuser: bool | None = None,
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_superuser),
) -> list[UserSchema]:
    if not user.is_superuser:
        raise HTTPException(
            status_code=401, detail="Administrator permissions required"
        )
    stmt = select(UserModel)

    # typing.TYPE_CHECKING is not available in runtime, so we use type: ignore
    if email is not None:
        stmt = stmt.where(UserModel.email == email)  # type: ignore
    if is_active is not None:
        stmt = stmt.where(UserModel.is_active == is_active)  # type: ignore
    if is_verified is not None:
        stmt = stmt.where(UserModel.is_verified == is_verified)  # type: ignore
    if is_superuser is not None:
        stmt = stmt.where(UserModel.is_superuser == is_superuser)  # type: ignore
    stmt = stmt.offset(skip).limit(limit)
    result = await session.execute(stmt)
    users = result.scalars().all()
    return [UserSchema.model_validate(u) for u in users]


@router.get("/", response_model=list[UserSchema], tags=["users"])
async def list_users(
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_superuser),
) -> list[UserSchema]:
    # Only superusers can list all users
    if not user.is_superuser:
        raise HTTPException(
            status_code=403, detail="Administrator permissions required"
        )
    result = await session.execute(select(UserModel))
    users = result.scalars().all()
    return [UserSchema.model_validate(u) for u in users]


@router.get("/authenticated-route")
async def authenticated_route(user: User = Depends(current_active_verified_user)):
    return {"message": f"Hello {user.id}!"}


router.include_router(fastapi_users.get_auth_router(auth_backend), tags=["auth"])
router.include_router(
    fastapi_users.get_register_router(UserSchema, UserCreate),
    tags=["auth"],
)
router.include_router(
    fastapi_users.get_reset_password_router(),
    tags=["auth"],
)
router.include_router(
    fastapi_users.get_verify_router(UserSchema),
    tags=["auth"],
)
router.include_router(
    fastapi_users.get_users_router(UserSchema, UserUpdate),
    tags=["users"],
)
