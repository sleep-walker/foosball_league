"""Mappers between SQLAlchemy ORM models and domain entities."""

from __future__ import annotations

from league_app.domain import entities as e
from league_app.domain.entities_league import League as LeagueEntity
from league_app.api.players import model as player_orm
from league_app.api.teams import model as team_orm
from league_app.api.matches import model as match_orm
from league_app.api.tables import model as table_orm
from league_app.api.stages import model as stage_orm
from league_app.api.tournaments import model as tournament_orm
from league_app.api.leagues import model as league_orm


# --- Player ---

def player_to_entity(m: player_orm.Player) -> e.Player:
    return e.Player(
        uuid=m.uuid, nickname=m.nickname, first_name=m.first_name,
        last_name=m.last_name, email=m.email, user_id=m.user_id,
        is_deleted=m.is_deleted,
    )

def player_to_orm(p: e.Player) -> player_orm.Player:
    return player_orm.Player(
        uuid=p.uuid, nickname=p.nickname, first_name=p.first_name,
        last_name=p.last_name, email=p.email, user_id=p.user_id,
        is_deleted=p.is_deleted,
    )


# --- Team ---

def team_to_entity(m: team_orm.Team) -> e.Team:
    return e.Team(
        uuid=m.uuid, player_1_id=m.player_1_id,
        player_2_id=m.player_2_id, tournament_id=m.tournament_id,
    )

def team_to_orm(t: e.Team) -> team_orm.Team:
    return team_orm.Team(
        uuid=t.uuid, player_1_id=t.player_1_id,
        player_2_id=t.player_2_id, tournament_id=t.tournament_id,
    )


# --- Game ---

def game_to_entity(m: match_orm.Game) -> e.Game:
    return e.Game(
        uuid=m.uuid, match_id=m.match_id, game_number=m.game_number,
        score_a=m.score_a, score_b=m.score_b, is_finished=m.is_finished,
    )

def game_to_orm(g: e.Game) -> match_orm.Game:
    return match_orm.Game(
        uuid=g.uuid, match_id=g.match_id, game_number=g.game_number,
        score_a=g.score_a, score_b=g.score_b, is_finished=g.is_finished,
    )


# --- Match ---

def match_to_entity(m: match_orm.Match) -> e.Match:
    return e.Match(
        uuid=m.uuid, tournament_id=m.tournament_id, stage_id=m.stage_id,
        owner_id=m.owner_id, round_number=m.round_number,
        table_number=m.table_number, bracket_position=m.bracket_position,
        best_of=m.best_of, player_a_id=m.player_a_id,
        player_b_id=m.player_b_id, team_a_id=m.team_a_id,
        team_b_id=m.team_b_id, status=m.status,
        winner_side=m.winner_side, is_deleted=m.is_deleted,
        games=[game_to_entity(g) for g in (m.games or [])],
    )


# --- Stage ---

def stage_to_entity(m: stage_orm.Stage) -> e.Stage:
    return e.Stage(
        uuid=m.uuid, tournament_id=m.tournament_id, name=m.name,
        stage_type=m.stage_type, ordering=m.ordering,
        advancement_count=m.advancement_count, rules=m.rules,
        is_deleted=m.is_deleted,
    )


# --- TournamentRegistration ---

def registration_to_entity(m: tournament_orm.TournamentRegistration) -> e.TournamentRegistration:
    return e.TournamentRegistration(
        tournament_id=m.tournament_id, player_id=m.player_id,
        paid=m.paid, seed=m.seed,
        is_paused=m.is_paused,
    )


# --- Tournament ---

def tournament_to_entity(m: tournament_orm.Tournament) -> e.Tournament:
    return e.Tournament(
        uuid=m.uuid, owner_id=m.owner_id, date=m.date, name=m.name,
        location=m.location, league_id=m.league_id, format=m.format,
        entry_fee=float(m.entry_fee) if m.entry_fee is not None else None,
        status=m.status, settings=m.settings,
        is_deleted=m.is_deleted, is_open=m.is_open,
        is_registration_open=m.is_registration_open,
        registrations=[registration_to_entity(r) for r in (m.registrations or [])],
        stages=[stage_to_entity(s) for s in (m.stages or [])],
    )


# --- League ---

def league_to_entity(m: league_orm.League) -> LeagueEntity:
    return LeagueEntity(
        uuid=m.uuid, owner_id=m.owner_id, name=m.name,
        description=m.description, registration_type=m.registration_type,
        scoring_type=m.scoring_type, scoring_config=m.scoring_config,
        is_deleted=m.is_deleted, is_open=m.is_open,
        is_registration_open=m.is_registration_open,
    )



# --- GameTable ---

def table_to_entity(m: table_orm.GameTable) -> e.GameTable:
    return e.GameTable(
        uuid=m.uuid, tournament_id=m.tournament_id, name=m.name,
        number=m.number, table_type=m.table_type, status=m.status,
    )