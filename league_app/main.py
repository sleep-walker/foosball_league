from fastapi import FastAPI

from fastapi.responses import FileResponse

from .database import engine, Base
from .api import router

FAVICON_PATH = "static/favicon.ico"

Base.metadata.create_all(bind=engine)
app = FastAPI()


app.include_router(router)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(FAVICON_PATH)
