from uuid import UUID
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

app = FastAPI()


# * Prelude
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# FIXME: properly mount favicon
app.mount("/static", StaticFiles(directory="static"), name="static")

# * /api/v1/players


@app.post("/api/v1/players/", response_model=schemas.PlayerOutput)
def create_player(player: schemas.PlayerCreate, db: Session = Depends(get_db)):
    db_player = crud.get_player_by_email(db, email=player.email)
    if db_player:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_player = crud.get_player_by_nickname(db, nickname=player.nickname)
    if db_player:
        raise HTTPException(status_code=400, detail="Nickname already registered")
    return crud.create_player(db=db, player=player)


@app.get("/api/v1/players/", response_model=list[schemas.PlayerOutput])
def read_players(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    players = crud.get_players(db, skip=skip, limit=limit)
    return players


@app.get("/api/v1/players/{uuid}", response_model=schemas.PlayerOutput)
def read_player(uuid: UUID, db: Session = Depends(get_db)):
    db_player = crud.get_player(db, uuid=uuid)
    if db_player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return db_player


@app.put("/api/v1/players/{uuid}", response_model=schemas.PlayerOutput)
def update_player(
    uuid: UUID, player: schemas.PlayerUpdate, db: Session = Depends(get_db)
):
    if uuid != player.uuid:
        raise HTTPException(status_code=403, detail="User cannot change his UUID")
    player = crud.update_player(db, player=player)
    return player


@app.delete("/api/v1/players/{uuid}", response_model=schemas.PlayerOutput)
def delete_player(uuid: UUID, db: Session = Depends(get_db)):
    # FIXME: ensure required permissions
    return crud.delete_player(db, uuid=uuid)


# * /api/v1/matches


@app.post("/api/v1/matches", response_model=schemas.MatchBase)
def create_match(match: schemas.MatchCreate, db: Session = Depends(get_db)):
    return crud.create_match(db=db, match=match)


@app.get("/api/v1/matches", response_model=list[schemas.MatchBase])
def read_matches(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    matches = crud.get_matches(db, skip=skip, limit=limit)
    return matches


@app.get("/api/v1/matches/{uuid}", response_model=schemas.MatchBase)
def read_match(uuid: UUID, db: Session = Depends(get_db)):
    db_match = crud.get_match(db, uuid=uuid)
    if db_match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return db_match


@app.put("/api/v1/matches/{uuid}", response_model=schemas.MatchBase)
def update_match(uuid: UUID, match: schemas.MatchUpdate, db: Session = Depends(get_db)):
    match = crud.update_match(db, match=match)
    return match


# * /api/v1/tournaments


@app.post("/api/v1/tournaments", response_model=schemas.TournamentBase)
def create_tournament(match: schemas.TournamentCreate, db: Session = Depends(get_db)):
    return crud.create_match(db=db, match=match)


@app.get("/api/v1/tournaments", response_model=list[schemas.TournamentBase])
def read_tournaments(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    matches = crud.get_tournaments(db, skip=skip, limit=limit)
    return matches


@app.get("/api/v1/tournaments/{uuid}", response_model=schemas.TournamentBase)
def read_tournament(uuid: UUID, db: Session = Depends(get_db)):
    db_match = crud.get_tournament(db, uuid=uuid)
    if db_match is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return db_match


@app.put("/api/v1/tournaments/{uuid}", response_model=schemas.TournamentBase)
def update_tournament(
    uuid: UUID, match: schemas.TournamentUpdate, db: Session = Depends(get_db)
):
    match = crud.update_tournament(db, match=match)
    return match


# * /api/v1/teams


@app.post("/api/v1/teams", response_model=schemas.TeamBase)
def create_team(team: schemas.TeamCreate, db: Session = Depends(get_db)):
    return crud.create_team(db=db, team=team)


@app.get("/api/v1/teams", response_model=list[schemas.TeamBase])
def read_teams(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    teams = crud.get_teams(db, skip=skip, limit=limit)
    return teams


@app.get("/api/v1/teams/{uuid}", response_model=schemas.TeamBase)
def read_team(uuid: UUID, db: Session = Depends(get_db)):
    db_team = crud.get_team(db, uuid=uuid)
    if db_team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return db_team


@app.put("/api/v1/teams/{uuid}", response_model=schemas.TeamBase)
def update_team(uuid: UUID, team: schemas.TeamUpdate, db: Session = Depends(get_db)):
    team = crud.update_team(db, team=team)
    return team


# * /api/v1/stages


@app.post("/api/v1/stages", response_model=schemas.TournamentStageBase)
def create_stage(stage: schemas.TournamentStageCreate, db: Session = Depends(get_db)):
    return crud.create_stage(db=db, stage=stage)


@app.get("/api/v1/stages", response_model=list[schemas.TournamentStageBase])
def read_stages(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    stages = crud.get_stages(db, skip=skip, limit=limit)
    return stages


@app.get("/api/v1/stages/{uuid}", response_model=schemas.TournamentStageBase)
def read_stage(uuid: UUID, db: Session = Depends(get_db)):
    db_stage = crud.get_stage(db, uuid=uuid)
    if db_stage is None:
        raise HTTPException(status_code=404, detail="Stage not found")
    return db_stage


@app.put("/api/v1/stages/{uuid}", response_model=schemas.TournamentStageBase)
def update_stage(
    uuid: UUID, stage: schemas.TournamentStageUpdate, db: Session = Depends(get_db)
):
    stage = crud.update_stage(db, stage=stage)
    return stage


# * /api/v1/leagues


@app.post("/api/v1/leagues", response_model=schemas.LeagueBase)
def create_league(league: schemas.LeagueCreate, db: Session = Depends(get_db)):
    return crud.create_league(db=db, league=league)


@app.get("/api/v1/leagues", response_model=list[schemas.LeagueBase])
def read_leagues(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    leagues = crud.get_leagues(db, skip=skip, limit=limit)
    return leagues


@app.get("/api/v1/leagues/{uuid}", response_model=schemas.LeagueBase)
def read_league(uuid: UUID, db: Session = Depends(get_db)):
    db_league = crud.get_league(db, uuid=uuid)
    if db_league is None:
        raise HTTPException(status_code=404, detail="League not found")
    return db_league


@app.put("/api/v1/leagues/{uuid}", response_model=schemas.LeagueBase)
def update_league(
    uuid: UUID, league: schemas.LeagueUpdate, db: Session = Depends(get_db)
):
    league = crud.update_league(db, league=league)
    return league
