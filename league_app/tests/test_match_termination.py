"""Regression tests for review finding M6 — a match always terminates.

``compute_match_status`` finished a match only when one side reached
``best_of // 2 + 1`` game wins.  Individual games may legitimately be draws
(``5:5`` under the default rules), so a best-of-3 (or longer) match in which
every game was drawn stayed at ``wins_a == wins_b == 0`` forever: it never
finished, and nothing capped how many games could be submitted — the service
just kept handing out ``game_number = len(games) + 1``.

The rule now is: a best-of-N match is at most N games.  At the cap the side
with more game wins takes the match, and if the game wins are level the
match is a draw — exactly how a drawn single game has always been reported
for ``best_of == 1``.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from league_app.engine.scoring import GameScore, compute_match_status
from league_app.tests.testlib import (
    API,
    assert_response_code,
    create_running_tournament,
    register_and_login,
)

DRAW = GameScore(5, 5)
A_WINS = GameScore(6, 2)
B_WINS = GameScore(2, 6)


# ---------------------------------------------------------------------------
# engine/scoring.py
# ---------------------------------------------------------------------------


class TestGameCap:
    def test_all_drawn_best_of_3_finishes_at_the_cap(self):
        """The M6 bug: three draws used to leave the match open forever."""
        assert not compute_match_status([DRAW], best_of=3).is_finished
        assert not compute_match_status([DRAW, DRAW], best_of=3).is_finished

        s = compute_match_status([DRAW, DRAW, DRAW], best_of=3)
        assert s.is_finished
        assert s.winner_side == "draw"
        assert (s.wins_a, s.wins_b) == (0, 0)

    def test_all_drawn_best_of_5_finishes_at_the_cap(self):
        assert not compute_match_status([DRAW] * 4, best_of=5).is_finished
        s = compute_match_status([DRAW] * 5, best_of=5)
        assert s.is_finished
        assert s.winner_side == "draw"

    def test_one_win_among_draws_wins_the_match_at_the_cap(self):
        s = compute_match_status([DRAW, A_WINS, DRAW], best_of=3)
        assert s.is_finished
        assert s.winner_side == "a"
        assert (s.wins_a, s.wins_b) == (1, 0)

    def test_even_best_of_level_on_wins_is_a_draw(self):
        s = compute_match_status([A_WINS, B_WINS], best_of=2)
        assert s.is_finished
        assert s.winner_side == "draw"

    def test_even_best_of_ahead_on_wins_takes_the_match(self):
        s = compute_match_status([DRAW, B_WINS, DRAW, DRAW], best_of=4)
        assert s.is_finished
        assert s.winner_side == "b"

    def test_cap_does_not_shorten_a_decided_match(self):
        """Reaching the required wins early still finishes immediately."""
        s = compute_match_status([A_WINS, A_WINS], best_of=3)
        assert s.is_finished
        assert s.winner_side == "a"

    def test_best_of_1_draw_unchanged(self):
        s = compute_match_status([DRAW], best_of=1)
        assert s.is_finished
        assert s.winner_side == "draw"

    def test_best_of_0_is_treated_as_a_single_game(self):
        """Defensive: a bogus best_of must not create an endless match."""
        s = compute_match_status([DRAW], best_of=0)
        assert s.is_finished


# ---------------------------------------------------------------------------
# TournamentService — the cap is enforced on submission too
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_drawn_best_of_3_match_terminates(client: AsyncClient):
    """Three 5:5 games finish the match; a fourth game is refused."""
    headers, _ = await register_and_login(client, "m6_org@test.com")
    t = await create_running_tournament(
        client, headers, "M6BestOf3", players=2, settings={"best_of": 3},
    )

    r = await client.get(
        f"{API}/tournaments/{t['tournament_id']}/matches/", headers=headers,
    )
    assert_response_code(r, 200)
    assert len(r.json()) == 1
    match_id = r.json()[0]["uuid"]
    assert r.json()[0]["best_of"] == 3

    for _ in range(3):
        r = await client.patch(
            f"{API}/matches/{match_id}/score",
            json={"score_a": 5, "score_b": 5}, headers=headers,
        )
        assert_response_code(r, 200)

    r = await client.get(f"{API}/matches/{match_id}", headers=headers)
    assert_response_code(r, 200)
    match = r.json()
    assert match["status"] == "finished"
    assert match["winner_side"] == "draw"
    assert len(match["games"]) == 3

    # A fourth game must be refused rather than silently appended.
    r = await client.patch(
        f"{API}/matches/{match_id}/score",
        json={"score_a": 5, "score_b": 5}, headers=headers,
    )
    assert r.status_code == 400

    r = await client.get(f"{API}/matches/{match_id}/games/", headers=headers)
    assert_response_code(r, 200)
    assert len(r.json()) == 3, "the match grew past its best_of cap"


@pytest.mark.asyncio
async def test_batch_submission_cannot_exceed_the_cap(client: AsyncClient):
    """Four games for a best-of-3 are rejected as a whole (no partial write)."""
    headers, _ = await register_and_login(client, "m6_batch@test.com")
    t = await create_running_tournament(
        client, headers, "M6Batch", players=2, settings={"best_of": 3},
    )
    r = await client.get(
        f"{API}/tournaments/{t['tournament_id']}/matches/", headers=headers,
    )
    match_id = r.json()[0]["uuid"]

    r = await client.patch(
        f"{API}/matches/{match_id}/scores",
        json={"scores": [{"score_a": 5, "score_b": 5}] * 4},
        headers=headers,
    )
    assert r.status_code == 400

    r = await client.get(f"{API}/matches/{match_id}/games/", headers=headers)
    assert_response_code(r, 200)
    assert r.json() == [], "a rejected batch must not write any game"
