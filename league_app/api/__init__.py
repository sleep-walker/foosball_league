from fastapi import APIRouter

from .users.router import router as users_router
from .players.router import router as players_router
from .leagues.router import router as leagues_router

api_router = APIRouter()
api_router.include_router(players_router, prefix="/v1/players", tags=["players"])
api_router.include_router(users_router, prefix="/v1/users", tags=["users"])
api_router.include_router(leagues_router, prefix="/v1/leagues", tags=["leagues"])


@api_router.get("/v1/ping")
async def ping():
    """
    Simple endpoint to check if the API is running.
    """
    return {"message": "pong"}


router = APIRouter()
router.include_router(api_router, prefix="/api")
