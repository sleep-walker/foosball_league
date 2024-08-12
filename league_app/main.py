from fastapi import FastAPI

from fastapi.responses import FileResponse

from .database import engine, Base
from .api import router

FAVICON_PATH = "static/favicon.ico"

Base.metadata.create_all(bind=engine)
app = FastAPI()


# * Prelude


# async_engine = create_async_engine(
#     settings.DB_URI,
#     pool_pre_ping=True,
#     echo=settings.ECHO_SQL,
# )
# AsyncSessionLocal = async_sessionmaker(
#     bind=async_engine,
#     autoflush=False,
#     future=True,
# )


app.include_router(router)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(FAVICON_PATH)


# * Users


# * /api/v1/players


# * /api/v1/matches


# @app.post("/api/v1/matches", response_model=schemas.MatchBase)
# def create_match(match: schemas.MatchCreate, db: Session = Depends(get_db)):
#     return crud.create_match(db=db, match=match)


# @app.get("/api/v1/matches", response_model=list[schemas.MatchBase])
# def read_matches(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
#     matches = crud.get_matches(db, skip=skip, limit=limit)
#     return matches


# @app.get("/api/v1/matches/{uuid}", response_model=schemas.MatchBase)
# def read_match(uuid: UUID, db: Session = Depends(get_db)):
#     db_match = crud.get_match(db, uuid=uuid)
#     if db_match is None:
#         raise HTTPException(status_code=404, detail="Match not found")
#     return db_match


# @app.put("/api/v1/matches/{uuid}", response_model=schemas.MatchBase)
# def update_match(uuid: UUID, match: schemas.MatchUpdate, db: Session = Depends(get_db)):
#     match = crud.update_match(db, match=match)
#     return match


# * /api/v1/tournaments


# @app.post("/api/v1/tournaments", response_model=schemas.TournamentBase)
# def create_tournament(match: schemas.TournamentCreate, db: Session = Depends(get_db)):
#     return crud.create_match(db=db, match=match)


# @app.get("/api/v1/tournaments", response_model=list[schemas.TournamentBase])
# def read_tournaments(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
#     matches = crud.get_tournaments(db, skip=skip, limit=limit)
#     return matches


# @app.get("/api/v1/tournaments/{uuid}", response_model=schemas.TournamentBase)
# def read_tournament(uuid: UUID, db: Session = Depends(get_db)):
#     db_match = crud.get_tournament(db, uuid=uuid)
#     if db_match is None:
#         raise HTTPException(status_code=404, detail="Tournament not found")
#     return db_match


# @app.put("/api/v1/tournaments/{uuid}", response_model=schemas.TournamentBase)
# def update_tournament(
#     uuid: UUID, match: schemas.TournamentUpdate, db: Session = Depends(get_db)
# ):
#     match = crud.update_tournament(db, match=match)
#     return match


# * /api/v1/teams


# @app.post("/api/v1/teams", response_model=schemas.TeamBase)
# def create_team(team: schemas.TeamCreate, db: Session = Depends(get_db)):
#     return crud.create_team(db=db, team=team)


# @app.get("/api/v1/teams", response_model=list[schemas.TeamBase])
# def read_teams(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
#     teams = crud.get_teams(db, skip=skip, limit=limit)
#     return teams


# @app.get("/api/v1/teams/{uuid}", response_model=schemas.TeamBase)
# def read_team(uuid: UUID, db: Session = Depends(get_db)):
#     db_team = crud.get_team(db, uuid=uuid)
#     if db_team is None:
#         raise HTTPException(status_code=404, detail="Team not found")
#     return db_team


# @app.put("/api/v1/teams/{uuid}", response_model=schemas.TeamBase)
# def update_team(uuid: UUID, team: schemas.TeamUpdate, db: Session = Depends(get_db)):
#     team = crud.update_team(db, team=team)
#     return team


# * /api/v1/stages


# @app.post("/api/v1/stages", response_model=schemas.TournamentStageBase)
# def create_stage(stage: schemas.TournamentStageCreate, db: Session = Depends(get_db)):
#     return crud.create_stage(db=db, stage=stage)


# @app.get("/api/v1/stages", response_model=list[schemas.TournamentStageBase])
# def read_stages(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
#     stages = crud.get_stages(db, skip=skip, limit=limit)
#     return stages


# @app.get("/api/v1/stages/{uuid}", response_model=schemas.TournamentStageBase)
# def read_stage(uuid: UUID, db: Session = Depends(get_db)):
#     db_stage = crud.get_stage(db, uuid=uuid)
#     if db_stage is None:
#         raise HTTPException(status_code=404, detail="Stage not found")
#     return db_stage


# @app.put("/api/v1/stages/{uuid}", response_model=schemas.TournamentStageBase)
# def update_stage(
#     uuid: UUID, stage: schemas.TournamentStageUpdate, db: Session = Depends(get_db)
# ):
#     stage = crud.update_stage(db, stage=stage)
#     return stage


# * /api/v1/leagues


# @app.post("/api/v1/leagues", response_model=schemas.LeagueBase)
# def create_league(league: schemas.LeagueCreate, db: Session = Depends(get_db)):
#     return crud.create_league(db=db, league=league)


# @app.get("/api/v1/leagues", response_model=list[schemas.LeagueBase])
# def read_leagues(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
#     leagues = crud.get_leagues(db, skip=skip, limit=limit)
#     return leagues


# @app.get("/api/v1/leagues/{uuid}", response_model=schemas.LeagueBase)
# def read_league(uuid: UUID, db: Session = Depends(get_db)):
#     db_league = crud.get_league(db, uuid=uuid)
#     if db_league is None:
#         raise HTTPException(status_code=404, detail="League not found")
#     return db_league


# @app.put("/api/v1/leagues/{uuid}", response_model=schemas.LeagueBase)
# def update_league(
#     uuid: UUID, league: schemas.LeagueUpdate, db: Session = Depends(get_db)
# ):
#     league = crud.update_league(db, league=league)
#     return league
