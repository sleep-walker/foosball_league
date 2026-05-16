#!/usr/bin/env python3
"""Seed the database with demo data.

Usage:
    python scripts/seed.py          # or: make venv-seed
    python scripts/seed.py --reset  # drop + recreate tables first
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Make sure the project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.database import get_async_engine, get_async_session_maker, Base

# Single engine instance shared between create_all and session maker
_engine = get_async_engine()
_session_maker = get_async_session_maker(_engine)

# --- Data definition ---

USERS = [
    {"email": "froser@gmail.com", "password": "veverka007", "nickname": "Sleepy"},
    {"email": "zlatan@devnull.com", "password": "zlatanjede", "nickname": "Zlatan"},
]

LEAGUES = [
    {
        "name": "Vacuum Old-School",
        "scoring_type": "placement_points",
        "players": [
            "Sleepy", "Sváča", "Zlatan", "Pablo", "Steve", "Martinka",
            "Kája", "Dejv", "Gawlis", "Láďa", "Marp", "Osky",
            "Tereza", "Vilém", "Davajhlavoláma", "Jordy",
            "Beny", "Honzík", "Kuba", "Mára", "Petr", "Radek",
            "Vašek", "Žaba", "Filip", "Tom",
        ],
    },
    {
        "name": "Everpure League",
        "scoring_type": "elo",
        "players": ["Sleepy"],
    },
]


async def _seed_running_tournament(session: AsyncSession, player_map: dict, name: str):
    """Create a singles tournament with 12 players, 6 rounds played."""
    import random
    from league_app.api.tournaments.model import Tournament, TournamentRegistration
    from league_app.api.stages.model import Stage
    from league_app.api.matches.model import Match, Game
    from league_app.api.leagues.model import League
    from sqlalchemy import select as sa_select

    random.seed(42)  # reproducible results

    vacuum = (await session.execute(
        sa_select(League).filter(League.name == "Vacuum Old-School")
    )).scalar_one_or_none()

    owner = player_map["Sleepy"]
    t_id = uuid4()
    tournament = Tournament(
        uuid=t_id, name=name, date="2026-04-23",
        player_mode="singles", status="running",
        owner_id=owner.user_id,
        league_id=vacuum.uuid if vacuum else None,
        is_registration_open=False,
        settings={"table_count": 2},
    )
    session.add(tournament)
    await session.flush()

    # Register 19 players (odd → 1 bye per round)
    nicknames = [
        "Sleepy", "Sváča", "Pablo", "Steve", "Martinka", "Kája",
        "Dejv", "Gawlis", "Láďa", "Marp", "Osky", "Tereza",
        "Vilém", "Jordy", "Beny", "Honzík", "Kuba", "Petr", "Radek",
    ]
    player_ids = []
    for nick in nicknames:
        p = player_map.get(nick)
        if p:
            session.add(TournamentRegistration(tournament_id=t_id, player_id=p.uuid))
            player_ids.append(p.uuid)
    await session.flush()

    # Group stage — active, 6 rounds played
    stage_id = uuid4()
    stage = Stage(
        uuid=stage_id, tournament_id=t_id, name="Group",
        stage_type="group", ordering=0, status="active",
        rules={
            "points_per_game": 6, "draw_allowed": True,
            "points_for_win": 2, "points_for_draw": 1, "points_for_loss": 0,
            "table_count": 2,
        },
    )
    session.add(stage)

    await session.flush()

    # Generate 6 rounds of matches with realistic scores
    n = len(player_ids)
    used_pairings = set()

    for round_num in range(1, 7):
        # Pair players (simple: rotate list, avoid repeats)
        shuffled = player_ids[:]
        random.shuffle(shuffled)
        pairs = []
        for i in range(0, n - 1, 2):
            a, b = shuffled[i], shuffled[i + 1]
            key = (min(a, b), max(a, b))
            pairs.append((a, b))
            used_pairings.add(key)

        table_num = 1
        for a, b in pairs:
            # Generate realistic score
            winner_score = 6
            loser_score = random.choice([0, 1, 2, 3, 4, 5])
            # ~20% draws (5:5)
            if random.random() < 0.2:
                winner_score, loser_score = 5, 5
            # Random side wins
            if random.random() < 0.5:
                sa, sb = winner_score, loser_score
            else:
                sa, sb = loser_score, winner_score

            m_id = uuid4()
            winner_side = None
            if sa > sb:
                winner_side = "a"
            elif sb > sa:
                winner_side = "b"

            match = Match(
                uuid=m_id, tournament_id=t_id, stage_id=stage_id,
                player_a_id=a, player_b_id=b,
                round_number=round_num, table_number=table_num,
                best_of=1, status="finished",
                winner_side=winner_side,
            )
            game = Game(
                uuid=uuid4(), match_id=m_id, game_number=1,
                score_a=sa, score_b=sb, is_finished=True,
            )
            session.add(match)
            session.add(game)
            table_num = (table_num % 2) + 1

    await session.flush()
    rounds_played = 6
    matches_per_round = len(player_ids) // 2
    total = rounds_played * matches_per_round
    print(f"✓ Tournament '{name}' created "
          f"({len(player_ids)} players, {rounds_played} rounds, {total} matches)")
    print(f"   Group stage: active")
    print(f"   Ready to test: finish group → add elimination stage → generate bracket")


async def _seed_running_doubles_tournament(
    session: AsyncSession, player_map: dict, name: str,
):
    """Create a doubles (DYP) tournament with 23 players, 6 rounds played."""
    import random
    from league_app.api.tournaments.model import Tournament, TournamentRegistration
    from league_app.api.stages.model import Stage
    from league_app.api.matches.model import Match, Game
    from league_app.api.teams.model import Team
    from league_app.api.leagues.model import League
    from sqlalchemy import select as sa_select

    random.seed(43)  # reproducible, different from singles

    vacuum = (await session.execute(
        sa_select(League).filter(League.name == "Vacuum Old-School")
    )).scalar_one_or_none()

    owner = player_map["Sleepy"]
    t_id = uuid4()
    tournament = Tournament(
        uuid=t_id, name=name, date="2026-04-30",
        player_mode="doubles", status="running",
        owner_id=owner.user_id,
        league_id=vacuum.uuid if vacuum else None,
        is_registration_open=False,
        settings={"table_count": 2},
    )
    session.add(tournament)
    await session.flush()

    # Register 23 players (odd → 1 player bye + odd # of teams → 1 team bye)
    nicknames = [
        "Sleepy", "Sváča", "Pablo", "Steve", "Martinka", "Kája",
        "Dejv", "Gawlis", "Láďa", "Marp", "Osky", "Tereza",
        "Vilém", "Davajhlavoláma", "Jordy", "Beny", "Honzík",
        "Kuba", "Mára", "Vašek", "Žaba", "Filip", "Tom",
    ]
    player_ids = []
    for nick in nicknames:
        p = player_map.get(nick)
        if p:
            session.add(TournamentRegistration(tournament_id=t_id, player_id=p.uuid))
            player_ids.append(p.uuid)
    await session.flush()

    # Group stage — active, 6 rounds played (DYP: new random teams every round)
    stage_id = uuid4()
    stage = Stage(
        uuid=stage_id, tournament_id=t_id, name="Group",
        stage_type="group", ordering=0, status="active",
        rules={
            "points_per_game": 6, "draw_allowed": True,
            "points_for_win": 2, "points_for_draw": 1, "points_for_loss": 0,
            "table_count": 2, "team_formation": "random",
        },
    )
    session.add(stage)
    await session.flush()

    matches_total = 0
    for round_num in range(1, 7):
        # DYP: shuffle players, pair sequentially into teams of 2.
        # Odd player count → last player sits out (bye).
        shuffled = player_ids[:]
        random.shuffle(shuffled)
        teams: list[Team] = []
        for i in range(0, len(shuffled) - 1, 2):
            t = Team(
                uuid=uuid4(), tournament_id=t_id,
                player_1_id=shuffled[i], player_2_id=shuffled[i + 1],
            )
            session.add(t)
            teams.append(t)
        await session.flush()

        # Pair teams sequentially → odd team count → last team sits out (bye)
        table_num = 1
        for i in range(0, len(teams) - 1, 2):
            ta, tb = teams[i], teams[i + 1]
            winner_score = 6
            loser_score = random.choice([0, 1, 2, 3, 4, 5])
            if random.random() < 0.2:
                winner_score, loser_score = 5, 5
            if random.random() < 0.5:
                sa, sb = winner_score, loser_score
            else:
                sa, sb = loser_score, winner_score

            m_id = uuid4()
            winner_side = None
            if sa > sb:
                winner_side = "a"
            elif sb > sa:
                winner_side = "b"

            match = Match(
                uuid=m_id, tournament_id=t_id, stage_id=stage_id,
                team_a_id=ta.uuid, team_b_id=tb.uuid,
                round_number=round_num, table_number=table_num,
                best_of=1, status="finished",
                winner_side=winner_side,
            )
            game = Game(
                uuid=uuid4(), match_id=m_id, game_number=1,
                score_a=sa, score_b=sb, is_finished=True,
            )
            session.add(match)
            session.add(game)
            matches_total += 1
            table_num = (table_num % 2) + 1

    await session.flush()
    rounds_played = 6
    print(f"✓ Tournament '{name}' created "
          f"({len(player_ids)} players, doubles DYP, {rounds_played} rounds, "
          f"{matches_total} matches)")
    print(f"   Group stage: active")
    print(f"   Ready to test: finish group → add elimination stage → generate bracket")


async def seed(reset: bool = False):
    # Import all models so Base.metadata knows about every table
    import league_app.api.users.model  # noqa: F401
    import league_app.api.players.model  # noqa: F401
    import league_app.api.leagues.model  # noqa: F401
    import league_app.api.tournaments.model  # noqa: F401
    import league_app.api.matches.model  # noqa: F401
    import league_app.api.teams.model  # noqa: F401
    import league_app.api.stages.model  # noqa: F401

    if reset:
        # Preserve existing user accounts (and their linked players) across reset
        # so the operator doesn't have to re-login after re-seeding.
        from league_app.api.users.model import User
        from league_app.api.players.model import Player
        from sqlalchemy import select as sa_select, inspect as sa_inspect

        preserved_users: list[dict] = []
        preserved_players: list[dict] = []
        async with _session_maker() as snap:
            def _has_table(sync_conn, name):
                return sa_inspect(sync_conn).has_table(name)
            conn = await snap.connection()
            user_exists = await conn.run_sync(_has_table, "user")
            players_exists = await conn.run_sync(_has_table, "players")
            if user_exists:
                rows = (await snap.execute(sa_select(User))).scalars().all()
                for u in rows:
                    preserved_users.append({
                        c.name: getattr(u, c.name) for c in User.__table__.columns
                    })
            if players_exists and preserved_users:
                user_ids = {u["id"] for u in preserved_users}
                rows = (await snap.execute(
                    sa_select(Player).filter(Player.user_id.in_(user_ids))
                )).scalars().all()
                for p in rows:
                    preserved_players.append({
                        c.name: getattr(p, c.name) for c in Player.__table__.columns
                    })

        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        print("✓ Tables recreated")

        # Restore preserved users & linked players
        if preserved_users:
            async with _session_maker() as restore:
                await restore.execute(User.__table__.insert(), preserved_users)
                if preserved_players:
                    await restore.execute(Player.__table__.insert(), preserved_players)
                await restore.commit()
            print(f"✓ Preserved {len(preserved_users)} user(s) "
                  f"and {len(preserved_players)} linked player(s) across reset")

    async with _session_maker() as session:
        # --- Users & linked Players ---
        user_player_map: dict[str, object] = {}  # nickname → player ORM

        from league_app.api.users.model import User
        from league_app.api.players.model import Player
        from league_app.api.users.users import UserManager
        from league_app.api.users.schema import UserCreate
        from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
        from sqlalchemy import select as sa_select

        for u in USERS:
            existing = (await session.execute(
                sa_select(User).filter(User.email == u["email"])
            )).scalar_one_or_none()
            if existing:
                print(f"  User {u['email']} already exists, skipping")
                user_id = existing.id
            else:
                user_db = SQLAlchemyUserDatabase(session, User)
                um = UserManager(user_db)
                user = await um.create(UserCreate(
                    email=u["email"], password=u["password"],
                    is_verified=True,
                ))
                user_id = user.id
                print(f"✓ User {u['email']} created")

            # Create linked player
            ep = (await session.execute(
                sa_select(Player).filter(Player.user_id == user_id)
            )).scalar_one_or_none()
            if ep:
                p = ep
            else:
                p = Player(uuid=uuid4(), nickname=u["nickname"], user_id=user_id)
                session.add(p)
                await session.flush()
                print(f"  ✓ Player '{u['nickname']}' linked to user")
            user_player_map[u["nickname"]] = p

        # --- All players (create unregistered ones) ---
        all_nicknames = set()
        for lg in LEAGUES:
            all_nicknames.update(lg["players"])

        for nick in sorted(all_nicknames):
            if nick in user_player_map:
                continue
            ep = (await session.execute(
                sa_select(Player).filter(Player.nickname == nick)
            )).scalar_one_or_none()
            if ep:
                user_player_map[nick] = ep
            else:
                p = Player(uuid=uuid4(), nickname=nick)
                session.add(p)
                await session.flush()
                user_player_map[nick] = p
                print(f"  ✓ Player '{nick}' created (unregistered)")

        # --- Leagues ---
        from league_app.api.leagues.model import League
        for lg_def in LEAGUES:
            el = (await session.execute(
                sa_select(League).filter(League.name == lg_def["name"])
            )).scalar_one_or_none()
            if el:
                league = el
                print(f"  League '{lg_def['name']}' already exists")
            else:
                # Owner = first registered user (Sleepy)
                owner_player = user_player_map.get("Sleepy")
                owner_uid = owner_player.user_id if owner_player else None
                league = League(
                    uuid=uuid4(), name=lg_def["name"],
                    scoring_type=lg_def["scoring_type"],
                    owner_id=owner_uid,
                )
                session.add(league)
                await session.flush()
                print(f"✓ League '{lg_def['name']}' created")

            # Add members via direct insert (avoid async lazy-load issue)
            from league_app.api.leagues.model import league_members
            for nick in lg_def["players"]:
                p = user_player_map.get(nick)
                if p:
                    await session.execute(
                        league_members.insert().prefix_with("OR IGNORE").values(
                            league_id=league.uuid, player_id=p.uuid
                        )
                    )

        # --- Tournament 1: Registration example (existing) ---
        from league_app.api.tournaments.model import (
            Tournament, TournamentRegistration, tournament_applicants,
        )

        TOURNAMENT_NAME = "Vacuum 16.4.2026"
        et = (await session.execute(
            sa_select(Tournament).filter(Tournament.name == TOURNAMENT_NAME)
        )).scalar_one_or_none()

        if et:
            print(f"  Tournament '{TOURNAMENT_NAME}' already exists")
        else:
            vacuum = (await session.execute(
                sa_select(League).filter(League.name == "Vacuum Old-School")
            )).scalar_one_or_none()

            owner_player = user_player_map["Sleepy"]
            tournament = Tournament(
                uuid=uuid4(),
                name=TOURNAMENT_NAME,
                date="2026-04-16",
                player_mode="doubles",
                owner_id=owner_player.user_id,
                league_id=vacuum.uuid if vacuum else None,
                settings={"table_count": 4},
            )
            session.add(tournament)
            await session.flush()

            vacuum_players = [
                "Sleepy", "Sváča", "Pablo", "Steve", "Martinka",
                "Kája", "Dejv", "Gawlis", "Láďa", "Marp", "Osky",
                "Tereza", "Vilém", "Davajhlavoláma", "Jordy",
            ]
            for nick in vacuum_players:
                p = user_player_map.get(nick)
                if p:
                    session.add(TournamentRegistration(
                        tournament_id=tournament.uuid, player_id=p.uuid,
                    ))

            zlatan = user_player_map.get("Zlatan")
            if zlatan:
                await session.execute(
                    tournament_applicants.insert().prefix_with("OR IGNORE").values(
                        tournament_id=tournament.uuid, player_id=zlatan.uuid,
                    )
                )
            await session.flush()
            print(f"✓ Tournament '{TOURNAMENT_NAME}' created (registration example)")

        # --- Tournament 2: In-progress after 6 rounds of singles ---
        RUNNING_NAME = "Vacuum jedničky 23.4.2026"
        et2 = (await session.execute(
            sa_select(Tournament).filter(Tournament.name == RUNNING_NAME)
        )).scalar_one_or_none()

        if et2:
            print(f"  Tournament '{RUNNING_NAME}' already exists")
        else:
            await _seed_running_tournament(session, user_player_map, RUNNING_NAME)

        # --- Tournament 3: In-progress after 6 rounds of doubles (DYP) ---
        RUNNING_DOUBLES_NAME = "Vacuum dvojíčky 30.4.2026"
        et3 = (await session.execute(
            sa_select(Tournament).filter(Tournament.name == RUNNING_DOUBLES_NAME)
        )).scalar_one_or_none()

        if et3:
            print(f"  Tournament '{RUNNING_DOUBLES_NAME}' already exists")
        else:
            await _seed_running_doubles_tournament(
                session, user_player_map, RUNNING_DOUBLES_NAME,
            )

        await session.commit()
        print("\n🎉 Seed complete!")
        print(f"   {len(user_player_map)} players, {len(LEAGUES)} leagues")
        for u in USERS:
            print(f"   Login: {u['email']} / {u['password']}")


def main():
    parser = argparse.ArgumentParser(description="Seed the database")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate tables")
    args = parser.parse_args()
    asyncio.run(seed(reset=args.reset))


if __name__ == "__main__":
    main()
