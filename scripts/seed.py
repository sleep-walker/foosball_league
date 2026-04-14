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
        ],
    },
    {
        "name": "Everpure League",
        "scoring_type": "elo",
        "players": ["Sleepy"],
    },
]


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
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        print("✓ Tables recreated")

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

        # --- Tournament ---
        from league_app.api.tournaments.model import (
            Tournament, TournamentRegistration,
        )

        TOURNAMENT_NAME = "Vacuum 16.4.2026"
        et = (await session.execute(
            sa_select(Tournament).filter(Tournament.name == TOURNAMENT_NAME)
        )).scalar_one_or_none()

        if et:
            print(f"  Tournament '{TOURNAMENT_NAME}' already exists")
        else:
            # Find Vacuum league
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

            # Register 15 players (all Vacuum except Zlatan)
            vacuum_players = [
                "Sleepy", "Sváča", "Pablo", "Steve", "Martinka",
                "Kája", "Dejv", "Gawlis", "Láďa", "Marp", "Osky",
                "Tereza", "Vilém", "Davajhlavoláma", "Jordy",
            ]
            for nick in vacuum_players:
                p = user_player_map.get(nick)
                if p:
                    reg = TournamentRegistration(
                        tournament_id=tournament.uuid,
                        player_id=p.uuid,
                    )
                    session.add(reg)

            # Zlatan as applicant (pre-registered via QR)
            zlatan = user_player_map.get("Zlatan")
            if zlatan:
                from league_app.api.tournaments.model import tournament_applicants
                await session.execute(
                    tournament_applicants.insert().prefix_with("OR IGNORE").values(
                        tournament_id=tournament.uuid, player_id=zlatan.uuid,
                    )
                )

            await session.flush()
            print(f"✓ Tournament '{TOURNAMENT_NAME}' created")
            print(f"   15 players registered, Zlatan pre-registered")

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
