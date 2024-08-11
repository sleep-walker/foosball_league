from fastapi import APIRouter

from .users.router import router as users_router
from .players.router import router as players_router

api_router = APIRouter()
api_router.include_router(players_router, prefix="/v1/players", tags=["players"])

router = APIRouter()
router.include_router(users_router)
router.include_router(api_router, prefix="/api", tags=["api"])
