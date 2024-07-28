from sqlalchemy.orm import Session
from uuid import UUID

from . import models, schemas


# * Players


def get_player(db: Session, uuid: UUID):
    return db.query(models.Player).filter(models.Player.uuid == uuid).first()


def get_players(
    db: Session, skip: int = 0, limit: int = 100, include_deleted: bool = False
) -> list[models.Player]:
    query = db.query(models.Player).offset(skip)

    if limit:
        query = query.limit(limit)

    if include_deleted:
        query = query.filter(models.Player.deleted == False)

    return query.all()


def get_player_by_email(db: Session, email: str):
    return db.query(models.Player).filter(models.Player.email == email).first()


def get_player_by_nickname(db: Session, nickname: str):
    return db.query(models.Player).filter(models.Player.nickname == nickname).first()


def create_player(db: Session, player: schemas.PlayerCreate):
    db_player = models.Player(**player.model_dump())
    db.add(db_player)
    db.commit()
    db.refresh(db_player)
    return db_player


def update_player(db: Session, player: schemas.PlayerUpdate):
    db.query(models.Player).filter(models.Player.uuid == player.uuid).update(
        player.model_dump()
    )
    db.commit()
    return db.query(models.Player).filter(models.Player.uuid == player.uuid).first()


def delete_player(db: Session, uuid: UUID):
    db_player = db.query(models.Player).filter(models.Player.uuid == uuid) #.first()
    db_player.update(deleted=True)
    db.commit()
    return db.query(models.Player).filter(models.Player.uuid == player.uuid).first()


# * Matches



def get_matches(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Match).offset(skip).limit(limit).all()


def get_match(db: Session, uuid: int):
    return db.query(models.Match).filter(models.Match.uuid == uuid).first()


def create_match(db: Session, match: schemas.MatchCreate):
    db_match = models.Match(**match.model_dump(), owner_id=user_id)
    db.add(db_match)
    db.commit()
    db.refresh(db_match)
    return db_match


def update_match(db: Session, match: schemas.MatchUpdate):
    db.query(models.Match).filter(models.Match.uuid == match.uuid).update(match.model_dump())
    db.commit()
    return db.query(models.Match).filter(models.Match.uuid == match.uuid).first()


# * Teams


def get_teams(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Team).offset(skip).limit(limit).all()


def get_team(db: Session, uuid: int):
    return db.query(models.Team).filter(models.Team.uuid == uuid).first()


def update_team(db: Session, team: schemas.TeamUpdate):
    db.query(models.Team).filter(models.Team.uuid == team.uuid).update(team.model_dump())
    db.commit()
    return db.query(models.Team).filter(models.Team.uuid == team.uuid).first()


def create_team(db: Session, team: schemas.TeamCreate):
    db_team = models.Team(**team.model_dump())
    db.add(db_team)
    db.commit()
    db.refresh(db_team)
    return db_team


# * Stages


def get_stage(db: Session, uuid: int):
    return db.query(models.Stage).filter(models.Stage.uuid == uuid).first()


def get_stages(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Stage).offset(skip).limit(limit).all()


def create_stage(db: Session, stage: schemas.TournamentStageCreate):
    db_stage = models.Stage(**stage.model_dump())
    db.add(db_stage)
    db.commit()
    db.refresh(db_stage)
    return db_stage


def update_stage(db: Session, stage: schemas.TournamentStageUpdate):
    db.query(models.Stage).filter(models.Stage.uuid == stage.uuid).update(stage.model_dump())
    db.commit()
    return db.query(models.Stage).filter(models.Stage.uuid == stage.uuid).first()


# * Tournaments


def get_tournament(db: Session, uuid: int):
    return db.query(models.Tournament).filter(models.Stage.uuid == uuid).first()


def get_tournaments(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Tournament).offset(skip).limit(limit).all()


def create_tournament(db: Session, stage: schemas.TournamentCreate):
    db_stage = models.Tournament(**stage.model_dump())
    db.add(db_tournament)
    db.commit()
    db.refresh(db_tournament)
    return db_tournament


def update_tournament(db: Session, tournament: schemas.TournamentUpdate):
    db.query(models.Stage).filter(models.Tournament.uuid == tournament.uuid).update(
        stage.model_dump()
    )
    db.commit()
    return (
        db.query(models.Stage).filter(models.Tournament.uuid == tournament.uuid).first()
    )


# * Leagues


def get_league(db: Session, uuid: int):
    return db.query(models.League).filter(models.League.uuid == uuid).first()


def get_leagues(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.League).offset(skip).limit(limit).all()


def create_league(db: Session, league: schemas.LeagueCreate):
    db_league = models.League(**league.model_dump())
    db.add(db_league)
    db.commit()
    db.refresh(db_league)
    return db_league


def update_league(db: Session, league: schemas.LeagueUpdate):
    db.query(models.League).filter(models.League.uuid == league.uuid).update(
        league.model_dump()
    )
    db.commit()
    return db.query(models.League).filter(models.League.uuid == league.uuid).first()
