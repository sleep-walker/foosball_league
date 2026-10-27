"""Regression tests for review finding M4 — unplayed matches are not draws.

``build_match_history`` used to convert *every* match of a stage into a
``MatchResult``, regardless of status.  A match that has only been drawn but
not played yet carries no games, and the standings engine reads "no games"
as ``wins_a == wins_b == 0`` — a 0-0 draw.  Both sides therefore collected a
point for a match nobody had played, which corrupted the standings that the
Swiss engine uses to pair the *next* round.

The fix filters on ``status == "finished"`` inside ``build_match_history``.
Because the Swiss engine also uses the history to avoid repeat matchups,
pairings that are merely scheduled are now passed separately via
``build_pair_history`` / ``avoid_pairs`` — remembered as "already drawn"
without being scored.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.api.tournaments.router import _get_tournament_service
from league_app.domain import entities as e
from league_app.domain.tournament_helpers import (
    build_match_history,
    build_pair_history,
)
from league_app.engine import swiss as swiss_engine
from league_app.engine.standings import compute_standings
from league_app.tests.testlib import (
    API,
    assert_response_code,
    create_running_tournament,
    register_and_login,
)

P1, P2, P3, P4 = (UUID(int=i) for i in range(1, 5))


def _match(a: UUID, b: UUID, status: str, games: list[e.Game] | None = None) -> e.Match:
    return e.Match(
        uuid=uuid4(), player_a_id=a, player_b_id=b,
        status=status, games=games or [],
    )


def _game(score_a: int, score_b: int) -> e.Game:
    return e.Game(
        uuid=uuid4(), match_id=uuid4(), score_a=score_a, score_b=score_b,
        is_finished=True,
    )


# ---------------------------------------------------------------------------
# domain/tournament_helpers.py — pure functions
# ---------------------------------------------------------------------------


class TestBuildMatchHistory:
    def test_scheduled_match_is_not_history(self):
        assert build_match_history([_match(P1, P2, "scheduled")]) == []

    def test_in_progress_match_is_not_history(self):
        assert build_match_history([_match(P1, P2, "in_progress")]) == []

    def test_finished_match_is_history(self):
        history = build_match_history(
            [_match(P1, P2, "finished", [_game(6, 3)])]
        )
        assert len(history) == 1
        assert history[0].participant_a_id == P1
        assert history[0].participant_b_id == P2

    def test_only_the_finished_match_of_a_mixed_round_counts(self):
        matches = [
            _match(P1, P2, "finished", [_game(6, 3)]),
            _match(P3, P4, "scheduled"),
        ]
        history = build_match_history(matches)
        assert [
            (h.participant_a_id, h.participant_b_id) for h in history
        ] == [(P1, P2)]

    def test_unplayed_match_no_longer_scores_as_a_draw(self):
        """The bug, expressed in the standings the Swiss engine consumes."""
        matches = [
            _match(P1, P2, "finished", [_game(6, 3)]),
            _match(P3, P4, "scheduled"),
        ]
        rows = {
            r.participant_id: r
            for r in compute_standings(build_match_history(matches))
        }
        assert rows[P1].wins == 1 and rows[P1].points == 2
        assert rows[P2].losses == 1
        # P3/P4 never played — they must not appear with a free draw point.
        assert P3 not in rows and P4 not in rows

    def test_team_keyed_finished_match_still_counts(self):
        team_a, team_b = uuid4(), uuid4()
        match = e.Match(
            uuid=uuid4(), team_a_id=team_a, team_b_id=team_b,
            status="finished", games=[_game(6, 1)],
        )
        history = build_match_history([match])
        assert len(history) == 1
        assert history[0].participant_a_id == team_a


class TestBuildPairHistory:
    def test_scheduled_pairings_are_remembered(self):
        pairs = build_pair_history([
            _match(P1, P2, "finished", [_game(6, 3)]),
            _match(P3, P4, "scheduled"),
        ])
        assert {frozenset(p) for p in pairs} == {
            frozenset((P1, P2)), frozenset((P3, P4)),
        }

    def test_match_without_both_sides_is_skipped(self):
        half_filled = e.Match(uuid=uuid4(), player_a_id=P1, status="scheduled")
        assert build_pair_history([half_filled]) == []


class TestSwissAvoidPairs:
    def test_scheduled_pair_is_not_drawn_again(self):
        """4 players, round 1 drawn but unplayed → round 2 must re-pair."""
        pairings = swiss_engine.generate_swiss_round(
            [P1, P2, P3, P4], [],
            avoid_pairs=[(P1, P2), (P3, P4)],
        )
        assert len(pairings) == 2
        drawn = {frozenset((p.participant_a_id, p.participant_b_id)) for p in pairings}
        assert frozenset((P1, P2)) not in drawn
        assert frozenset((P3, P4)) not in drawn


# ---------------------------------------------------------------------------
# TournamentService — what the Swiss engine actually receives
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_next_round_is_paired_from_finished_matches_only(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """Round 1 half-played; the round-2 draw must only score what was played.

    Spies on the Swiss engine call so the assertion is about the data the
    pairing algorithm is handed — the exact thing M4 corrupted — rather than
    about a pairing outcome that could coincidentally match.
    """
    headers, org_id = await register_and_login(client, "m4_org@test.com")
    t = await create_running_tournament(client, headers, "M4Swiss", players=4)

    r = await client.get(
        f"{API}/tournaments/{t['tournament_id']}/matches/", headers=headers,
    )
    assert_response_code(r, 200)
    round_1 = r.json()
    assert len(round_1) == 2, "4 players → 2 matches in round 1"

    # Play exactly one of the two matches; the other stays `scheduled`.
    played, unplayed = round_1[0], round_1[1]
    r = await client.patch(
        f"{API}/matches/{played['uuid']}/score",
        json={"score_a": 6, "score_b": 1}, headers=headers,
    )
    assert_response_code(r, 200)

    captured: dict = {}
    real = swiss_engine.generate_swiss_round

    def _spy(participant_ids, match_history, rules=None, rng=None, **kwargs):
        captured["history"] = list(match_history)
        captured["avoid_pairs"] = list(kwargs.get("avoid_pairs") or [])
        return real(participant_ids, match_history, rules, rng, **kwargs)

    monkeypatch.setattr(swiss_engine, "generate_swiss_round", _spy)

    svc = _get_tournament_service(session)
    await svc.draw_swiss_round(t["tournament_id"], t["stage_id"], org_id)

    # Only the played match is history...
    assert len(captured["history"]) == 1
    rows = compute_standings(captured["history"])
    assert sum(r.draws for r in rows) == 0, "an unplayed match scored as a draw"
    assert sorted(r.matches_played for r in rows) == [1, 1]

    # ...but the unplayed pairing is still remembered as already drawn.
    unplayed_pair = frozenset((
        UUID(unplayed["player_a_id"]), UUID(unplayed["player_b_id"]),
    ))
    assert unplayed_pair in {frozenset(p) for p in captured["avoid_pairs"]}


@pytest.mark.asyncio
async def test_second_round_does_not_repeat_an_unplayed_pairing(
    client: AsyncClient, session: AsyncSession,
):
    """End-to-end consequence: nobody is drawn twice against the same player."""
    headers, org_id = await register_and_login(client, "m4_repeat@test.com")
    t = await create_running_tournament(client, headers, "M4Repeat", players=4)

    svc = _get_tournament_service(session)
    round_1 = await svc._matches.list_by_stage(t["stage_id"])
    first_pairs = {frozenset((m.player_a_id, m.player_b_id)) for m in round_1}

    # Nothing is played at all — the hardest case for the pairing guard.
    round_2 = await svc.draw_swiss_round(t["tournament_id"], t["stage_id"], org_id)
    second_pairs = {frozenset((m.player_a_id, m.player_b_id)) for m in round_2}

    assert len(round_2) == 2
    assert not (first_pairs & second_pairs), "an unplayed pairing was drawn again"
