from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from league_app.database import get_session_for_api
from league_app.api.users.model import User as UserModel
from fastapi import APIRouter, Depends, HTTPException
from .users import auth_backend, current_active_verified_user, current_superuser, fastapi_users
from .schema import UserCreate, UserRead, UserUpdate
from .model import User

router = APIRouter()

router.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
)
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)
router.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/auth",
    tags=["auth"],
)
router.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/auth",
    tags=["auth"],
)
router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)

@router.get("/search", response_model=list[UserRead], tags=["users"])
async def search_users(
    email: str | None = None,
    is_active: bool | None = None,
    is_verified: bool | None = None,
    is_superuser: bool | None = None,
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session_for_api),
    user: User = Depends(current_superuser),
) -> list[UserRead]:
    if not user.is_superuser:
        raise HTTPException(status_code=401, detail="Administrator permissions required")
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
    return [UserRead.model_validate(u) for u in users]

@router.get("/authenticated-route")
async def authenticated_route(user: User = Depends(current_active_verified_user)):
    return {"message": f"Hello {user.id}!"}
