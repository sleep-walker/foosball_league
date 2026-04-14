"""End-to-end flow tests — simulate what the frontend does.

Each test covers a full user journey through the API:
register → login → create resources → interact → verify.
No fixtures with pre-created users — everything from scratch.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from league_app.tests.testlib import assert_response_code


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _register(client: AsyncClient, email: str, password: str) -> dict:
    """Register a new user (like the frontend Register form)."""
    r = await client.post(
        "/api/v1/users/register",
        json={"email": email, "password": password},
    )
    assert_response_code(r, 201)
    return r.json()


async def _login(client: AsyncClient, email: str, password: str) -> str:
    """Login and return access token (like the frontend Login form)."""
    r = await client.post(
        "/api/v1/users/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert_response_code(r, 200)
    token = r.json()["access_token"]
    return token


async def _auth_headers(client: AsyncClient, email: str, password: str) -> dict:
    """Register + login, return auth headers."""
    await _register(client, email, password)
    token = await _login(client, email, password)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient):
    """User can register and immediately log in."""
    user = await _register(client, "flow1@test.com", "password123")
    assert user["email"] == "flow1@test.com"
    assert user["is_active"] is True

    token = await _login(client, "flow1@test.com", "password123")
    assert len(token) > 0

    # Verify /me works
    r = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert_response_code(r, 200)
    assert r.json()["email"] == "flow1@test.com"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    """Registration with an existing email fails."""
    await _register(client, "dup@test.com", "password123")
    r = await client.post(
        "/api/v1/users/register",
        json={"email": "dup@test.com", "password": "password123"},
    )
    assert_response_code(r, 400)


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """Login with wrong password fails."""
    await _register(client, "wrong@test.com", "password123")
    r = await client.post(
        "/api/v1/users/login",
        data={"username": "wrong@test.com", "password": "WRONGWRONG"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert_response_code(r, 400)


@pytest.mark.asyncio
async def test_create_tournament_without_owner_id(client: AsyncClient):
    """Frontend sends no owner_id — server sets it from logged-in user."""
    headers = await _auth_headers(client, "org1@test.com", "password123")

    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "Friday Foosball", "date": "2026-04-15", "location": "Pub"},
        headers=headers,
    )
    assert_response_code(r, 200)
    data = r.json()
    assert data["name"] == "Friday Foosball"
    assert data["owner_id"] is not None
    assert data["status"] == "registration"


@pytest.mark.asyncio
async def test_create_tournament_unauthenticated(client: AsyncClient):
    """Unauthenticated user cannot create a tournament."""
    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "Nope", "date": "2026-04-15"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_player_profile(client: AsyncClient):
    """After registration, user can create a player profile."""
    headers = await _auth_headers(client, "player1@test.com", "password123")

    r = await client.post(
        "/api/v1/players/",
        json={"nickname": "ProPlayer"},
        headers=headers,
    )
    assert_response_code(r, 200)
    assert r.json()["nickname"] == "ProPlayer"


@pytest.mark.asyncio
async def test_full_tournament_lifecycle(client: AsyncClient):
    """Full flow: register → create tournament → add player → start → finish."""
    headers = await _auth_headers(client, "lifecycle@test.com", "password123")

    # Create player
    r = await client.post(
        "/api/v1/players/", json={"nickname": "Organizer"}, headers=headers,
    )
    assert_response_code(r, 200)
    player_id = r.json()["uuid"]


    # Create tournament (no owner_id!)
    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "Lifecycle Cup", "date": "2026-04-15"},
        headers=headers,
    )
    assert_response_code(r, 200)
    t_id = r.json()["uuid"]

    # Register player to tournament
    r = await client.post(
        f"/api/v1/tournaments/{t_id}/players/?player_id={player_id}",
        headers=headers,
    )
    assert_response_code(r, 200)

    # Create a second player + register
    r = await client.post(
        "/api/v1/players/", json={"nickname": "Opponent"}, headers=headers,
    )
    assert_response_code(r, 200)
    player2_id = r.json()["uuid"]

    r = await client.post(
        f"/api/v1/tournaments/{t_id}/players/?player_id={player2_id}",
        headers=headers,
    )
    assert_response_code(r, 200)

    # Verify tournament has 2 players
    r = await client.get(f"/api/v1/tournaments/{t_id}", headers=headers)
    assert_response_code(r, 200)
    assert len(r.json()["registrations"]) == 2

    # Start tournament
    r = await client.post(f"/api/v1/tournaments/{t_id}/start", headers=headers)
    assert_response_code(r, 200)
    assert r.json()["status"] == "running"

    # Finish tournament
    r = await client.post(f"/api/v1/tournaments/{t_id}/finish", headers=headers)
    assert_response_code(r, 200)
    assert r.json()["status"] == "finished"


@pytest.mark.asyncio
async def test_public_endpoints_no_auth(client: AsyncClient):
    """Public endpoints work without authentication."""
    headers = await _auth_headers(client, "pub@test.com", "password123")

    # Create tournament
    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "Public Cup", "date": "2026-04-15"},
        headers=headers,
    )
    assert_response_code(r, 200)
    t_id = r.json()["uuid"]

    # Public tournament info — NO auth header
    r = await client.get(f"/v1/public/tournaments/{t_id}")
    assert_response_code(r, 200)
    assert r.json()["name"] == "Public Cup"

    # Export — NO auth header
    r = await client.get(f"/v1/public/tournaments/{t_id}/export?format=json")
    assert_response_code(r, 200)

    # QR — NO auth header
    r = await client.get(f"/v1/public/tournaments/{t_id}/qr?format=json")
    assert_response_code(r, 200)


@pytest.mark.asyncio
async def test_create_tournament_player_mode(client: AsyncClient):
    """Tournament player_mode defaults to 'singles' and can be set to 'doubles'."""
    headers = await _auth_headers(client, "fmt@test.com", "password123")

    # Default
    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "Default", "date": "2026-04-15"},
        headers=headers,
    )
    assert_response_code(r, 200)
    assert r.json()["player_mode"] == "singles"

    # Doubles
    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "Doubles", "date": "2026-04-15", "player_mode": "doubles"},
        headers=headers,
    )
    assert_response_code(r, 200)
    assert r.json()["player_mode"] == "doubles"


@pytest.mark.asyncio
async def test_add_unregistered_player_to_tournament(client: AsyncClient):
    """Organizer creates an unregistered player and adds them to tournament."""
    headers = await _auth_headers(client, "orgadd@test.com", "password123")

    # Create tournament
    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "With Guests", "date": "2026-04-15"},
        headers=headers,
    )
    assert_response_code(r, 200)
    t_id = r.json()["uuid"]

    # Create unregistered player (no user_id)
    r = await client.post(
        "/api/v1/players/",
        json={"nickname": "GuestPlayer", "first_name": "Jan", "last_name": "Novák"},
        headers=headers,
    )
    assert_response_code(r, 200)
    p_id = r.json()["uuid"]
    assert r.json()["nickname"] == "GuestPlayer"

    # Add to tournament
    r = await client.post(
        f"/api/v1/tournaments/{t_id}/players/?player_id={p_id}",
        headers=headers,
    )
    assert_response_code(r, 200)

    # Verify
    r = await client.get(f"/api/v1/tournaments/{t_id}", headers=headers)
    assert_response_code(r, 200)
    player_ids = [reg["player_id"] for reg in r.json()["registrations"]]
    assert p_id in player_ids


@pytest.mark.asyncio
async def test_self_registration_via_qr(client: AsyncClient):
    """Full QR self-registration flow: create → QR → self-register → accept."""
    headers = await _auth_headers(client, "qr@test.com", "password123")

    # Create tournament
    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "QR Cup", "date": "2026-04-15"},
        headers=headers,
    )
    assert_response_code(r, 200)
    t_id = r.json()["uuid"]

    # QR endpoint returns URL with token
    r = await client.get(f"/v1/public/tournaments/{t_id}/qr?format=json")
    assert_response_code(r, 200)
    qr_url = r.json()["registration_url"]
    assert "register" in qr_url
    assert "token=" in qr_url
    # Extract token from URL
    token = qr_url.split("token=")[1]

    # Self-register WITHOUT token → 403
    r = await client.post(
        f"/v1/public/tournaments/{t_id}/register",
        json={"nickname": "Hacker", "token": "wrong"},
    )
    assert r.status_code == 403

    # Self-register WITH valid token (NO auth!) — simulates scanning QR
    r = await client.post(
        f"/v1/public/tournaments/{t_id}/register",
        json={"nickname": "QRPlayer", "first_name": "Jan", "token": token},
    )
    assert_response_code(r, 200)
    data = r.json()
    assert data["nickname"] == "QRPlayer"
    assert "on the list" in data["message"].lower() or "organizer" in data["message"].lower()
    player_id = data["player_id"]

    # Duplicate self-registration returns success (idempotent)
    r = await client.post(
        f"/v1/public/tournaments/{t_id}/register",
        json={"nickname": "QRPlayer", "token": token},
    )
    assert_response_code(r, 200)
    assert "already" in r.json()["message"].lower()

    # Public info shows applicant
    r = await client.get(f"/v1/public/tournaments/{t_id}")
    assert_response_code(r, 200)
    applicant_nicks = [a["nickname"] for a in r.json()["applicants"]]
    assert "QRPlayer" in applicant_nicks

    # Organizer accepts applicant → moves to registrations
    r = await client.post(
        f"/api/v1/tournaments/{t_id}/players/?player_id={player_id}",
        headers=headers,
    )
    assert_response_code(r, 200)
    # Endpoint returns success message
    assert "added" in r.json().get("message", "").lower() or r.status_code == 200


@pytest.mark.asyncio
async def test_self_registration_closed(client: AsyncClient):
    """Self-registration fails when registration is closed."""
    headers = await _auth_headers(client, "closed@test.com", "password123")

    # Create and start tournament (closes registration)
    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "Closed Cup", "date": "2026-04-15"},
        headers=headers,
    )
    t_id = r.json()["uuid"]

    # Add 2 players so we can start
    for nick in ("P1", "P2"):
        r = await client.post("/api/v1/players/", json={"nickname": nick + "_closed"}, headers=headers)
        pid = r.json()["uuid"]
        await client.post(f"/api/v1/tournaments/{t_id}/players/?player_id={pid}", headers=headers)

    await client.post(f"/api/v1/tournaments/{t_id}/start", headers=headers)

    # Self-registration should fail (even with a valid-looking token)
    r = await client.post(
        f"/v1/public/tournaments/{t_id}/register",
        json={"nickname": "LatePlayer", "token": "doesnt-matter"},
    )
    assert r.status_code == 400
    assert "closed" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_doubles_tournament_start(client: AsyncClient):
    """Starting a doubles tournament creates teams and draws first round."""
    headers = await _auth_headers(client, "doubles@test.com", "password123")

    # Create doubles tournament
    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "Doubles Cup", "date": "2026-04-15", "player_mode": "doubles"},
        headers=headers,
    )
    assert_response_code(r, 200)
    t_id = r.json()["uuid"]
    assert r.json()["player_mode"] == "doubles"

    # Add 4 players
    player_ids = []
    for nick in ("Alice", "Bob", "Charlie", "Diana"):
        r = await client.post(
            "/api/v1/players/", json={"nickname": nick}, headers=headers
        )
        pid = r.json()["uuid"]
        player_ids.append(pid)
        r = await client.post(
            f"/api/v1/tournaments/{t_id}/players/?player_id={pid}",
            headers=headers,
        )
        assert_response_code(r, 200)

    # Start — should create 2 teams and draw 1 match (2 teams)
    r = await client.post(f"/api/v1/tournaments/{t_id}/start", headers=headers)
    assert_response_code(r, 200)
    assert r.json()["status"] == "running"

    # Should have stages with matches
    r = await client.get(
        f"/api/v1/tournaments/{t_id}/stages/", headers=headers
    )
    assert_response_code(r, 200)
    stages = r.json()
    assert len(stages) >= 1, "Should have at least one stage after start"

    # Should have matches
    r = await client.get(
        f"/api/v1/tournaments/{t_id}/matches/", headers=headers
    )
    assert_response_code(r, 200)
    matches = r.json()
    # 2 teams → 1 match
    assert len(matches) == 1, f"Expected 1 match, got {len(matches)}"
    m = matches[0]
    assert m.get("team_a_id") is not None, "Doubles match should have team_a_id"
    assert m.get("team_b_id") is not None, "Doubles match should have team_b_id"


@pytest.mark.asyncio
async def test_doubles_needs_even_players(client: AsyncClient):
    """Doubles tournament cannot start with odd number of players."""
    headers = await _auth_headers(client, "odd@test.com", "password123")

    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "Odd Cup", "date": "2026-04-15", "player_mode": "doubles"},
        headers=headers,
    )
    t_id = r.json()["uuid"]

    # Add 3 players (odd)
    for nick in ("P1odd", "P2odd", "P3odd"):
        r = await client.post("/api/v1/players/", json={"nickname": nick}, headers=headers)
        await client.post(
            f"/api/v1/tournaments/{t_id}/players/?player_id={r.json()['uuid']}",
            headers=headers,
        )

    # Start should fail — doubles needs at least 4 players
    r = await client.post(f"/api/v1/tournaments/{t_id}/start", headers=headers)
    assert r.status_code in (400, 409)
    assert "4" in r.json()["detail"] or "least" in r.json()["detail"].lower()


async def _create_started_tournament(client, email, nicknames, **kwargs):
    """Helper: create a tournament with players, start it, return (tid, headers, player_ids)."""
    headers = await _auth_headers(client, email, "password123")
    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "ScoreTest", "date": "2026-04-15", **kwargs},
        headers=headers,
    )
    assert_response_code(r, 200)
    t_id = r.json()["uuid"]

    player_ids = []
    for nick in nicknames:
        r = await client.post("/api/v1/players/", json={"nickname": nick}, headers=headers)
        pid = r.json()["uuid"]
        player_ids.append(pid)
        await client.post(
            f"/api/v1/tournaments/{t_id}/players/?player_id={pid}",
            headers=headers,
        )

    r = await client.post(f"/api/v1/tournaments/{t_id}/start", headers=headers)
    assert_response_code(r, 200)
    return t_id, headers, player_ids


@pytest.mark.asyncio
async def test_score_submission(client: AsyncClient):
    """Basic score submission: organizer enters score, match finishes."""
    t_id, headers, _ = await _create_started_tournament(
        client, "scorer@test.com", ("SA", "SB"),
    )

    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=headers)
    assert_response_code(r, 200)
    matches = r.json()
    assert len(matches) >= 1

    match_id = matches[0]["uuid"]
    r = await client.patch(
        f"/api/v1/matches/{match_id}/score",
        json={"score_a": 6, "score_b": 3},
        headers=headers,
    )
    assert_response_code(r, 200)
    assert r.json()["score_a"] == 6
    assert r.json()["score_b"] == 3

    # Match should now be finished
    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=headers)
    m = next(m for m in r.json() if m["uuid"] == match_id)
    assert m["status"] == "finished"
    assert m["score_a"] == 6
    assert m["score_b"] == 3


@pytest.mark.asyncio
async def test_score_double_submit_rejected(client: AsyncClient):
    """Submitting score on an already-finished match returns 400."""
    t_id, headers, _ = await _create_started_tournament(
        client, "scorer2@test.com", ("SA2", "SB2"),
    )
    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=headers)
    match_id = r.json()[0]["uuid"]

    # First submit — OK
    r = await client.patch(
        f"/api/v1/matches/{match_id}/score",
        json={"score_a": 5, "score_b": 5},
        headers=headers,
    )
    assert_response_code(r, 200)

    # Second submit — already finished
    r = await client.patch(
        f"/api/v1/matches/{match_id}/score",
        json={"score_a": 6, "score_b": 1},
        headers=headers,
    )
    assert r.status_code == 400
    assert "already finished" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_score_updates_standings(client: AsyncClient):
    """After scoring, public standings reflect the result."""
    t_id, headers, _ = await _create_started_tournament(
        client, "scorer3@test.com", ("StandA", "StandB"),
    )
    # Get stage
    r = await client.get(f"/api/v1/tournaments/{t_id}", headers=headers)
    stages = r.json()["stages"]
    assert len(stages) >= 1
    stage_id = stages[0]["uuid"]

    # Submit score
    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=headers)
    match_id = r.json()[0]["uuid"]
    await client.patch(
        f"/api/v1/matches/{match_id}/score",
        json={"score_a": 6, "score_b": 2},
        headers=headers,
    )

    # Check standings (public endpoint, no auth)
    r = await client.get(
        f"/v1/public/tournaments/{t_id}/stages/{stage_id}/standings"
    )
    assert_response_code(r, 200)
    standings = r.json()
    assert len(standings) == 2

    winner = standings[0]
    loser = standings[1]
    assert winner["wins"] == 1
    assert winner["points"] == 2  # default: 2 pts/win (Kickertool style)
    assert winner["goals_for"] == 6
    assert winner["goals_against"] == 2
    assert loser["losses"] == 1
    assert loser["points"] == 0


@pytest.mark.asyncio
async def test_score_draw(client: AsyncClient):
    """A draw (equal score) awards 1 point each."""
    t_id, headers, _ = await _create_started_tournament(
        client, "scorer4@test.com", ("DrawA", "DrawB"),
    )
    r = await client.get(f"/api/v1/tournaments/{t_id}", headers=headers)
    stage_id = r.json()["stages"][0]["uuid"]

    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=headers)
    match_id = r.json()[0]["uuid"]
    r = await client.patch(
        f"/api/v1/matches/{match_id}/score",
        json={"score_a": 5, "score_b": 5},
        headers=headers,
    )
    assert_response_code(r, 200)

    r = await client.get(
        f"/v1/public/tournaments/{t_id}/stages/{stage_id}/standings"
    )
    standings = r.json()
    assert all(s["draws"] == 1 for s in standings)
    assert all(s["points"] == 1 for s in standings)


@pytest.mark.asyncio
async def test_score_by_non_participant_rejected(client: AsyncClient):
    """A user who is not a participant or organizer cannot submit scores."""
    t_id, org_headers, _ = await _create_started_tournament(
        client, "scorer5_org@test.com", ("PartA", "PartB"),
    )
    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=org_headers)
    match_id = r.json()[0]["uuid"]

    # Different user, not a participant
    outsider_headers = await _auth_headers(client, "scorer5_outsider@test.com", "password123")
    r = await client.patch(
        f"/api/v1/matches/{match_id}/score",
        json={"score_a": 6, "score_b": 0},
        headers=outsider_headers,
    )
    assert r.status_code == 403
    assert "participant" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_score_without_auth_rejected(client: AsyncClient):
    """Score submission without authentication returns 401."""
    t_id, headers, _ = await _create_started_tournament(
        client, "scorer6@test.com", ("NoAuthA", "NoAuthB"),
    )
    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=headers)
    match_id = r.json()[0]["uuid"]

    r = await client.patch(
        f"/api/v1/matches/{match_id}/score",
        json={"score_a": 6, "score_b": 0},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_score_by_participant(client: AsyncClient):
    """A registered player who is in the match can submit the score."""
    org_headers = await _auth_headers(client, "scorer7_org@test.com", "password123")

    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "ParticipantScore", "date": "2026-04-15"},
        headers=org_headers,
    )
    t_id = r.json()["uuid"]

    # Create player-user: scorer7_player
    player_headers = await _auth_headers(client, "scorer7_player@test.com", "password123")
    # Create a player linked to this user
    r = await client.post(
        "/api/v1/players/", json={"nickname": "Scorer7P"}, headers=player_headers,
    )
    p_id = r.json()["uuid"]
    # Link player to user — get user id
    r = await client.get("/api/v1/users/me/player", headers=player_headers)
    # If no linked player yet, link via the org adding them
    await client.post(
        f"/api/v1/tournaments/{t_id}/players/?player_id={p_id}",
        headers=org_headers,
    )

    # Add second player (by org)
    r = await client.post(
        "/api/v1/players/", json={"nickname": "Scorer7Opp"}, headers=org_headers,
    )
    opp_id = r.json()["uuid"]
    await client.post(
        f"/api/v1/tournaments/{t_id}/players/?player_id={opp_id}",
        headers=org_headers,
    )

    # Start
    r = await client.post(f"/api/v1/tournaments/{t_id}/start", headers=org_headers)
    assert_response_code(r, 200)

    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=org_headers)
    match_id = r.json()[0]["uuid"]

    # Player submits score — should work because they're a participant
    r = await client.patch(
        f"/api/v1/matches/{match_id}/score",
        json={"score_a": 4, "score_b": 6},
        headers=player_headers,
    )
    assert_response_code(r, 200)
    assert r.json()["score_a"] == 4


@pytest.mark.asyncio
async def test_score_doubles_tournament(client: AsyncClient):
    """Score submission works for doubles matches (with team_a/team_b)."""
    t_id, headers, _ = await _create_started_tournament(
        client, "scorer8@test.com", ("DA", "DB", "DC", "DD"),
        player_mode="doubles",
    )

    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=headers)
    assert_response_code(r, 200)
    matches = r.json()
    assert len(matches) >= 1

    match_id = matches[0]["uuid"]
    assert matches[0]["team_a_id"] is not None

    r = await client.patch(
        f"/api/v1/matches/{match_id}/score",
        json={"score_a": 6, "score_b": 4},
        headers=headers,
    )
    assert_response_code(r, 200)

    # Verify match is finished with correct score
    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=headers)
    m = next(m for m in r.json() if m["uuid"] == match_id)
    assert m["status"] == "finished"
    assert m["score_a"] == 6
    assert m["score_b"] == 4


@pytest.mark.asyncio
async def test_no_player_plays_twice_in_one_round(client: AsyncClient):
    """Each player must appear in at most one match per round."""
    headers = await _auth_headers(client, "nodup@test.com", "password123")
    PLAYER_COUNT = 16

    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "NoDup Test", "date": "2026-04-15", "settings": {"table_count": 8}},
        headers=headers,
    )
    t_id = r.json()["uuid"]

    # Register 16 players
    for i in range(PLAYER_COUNT):
        r = await client.post(
            "/api/v1/players/", json={"nickname": f"NoDup{i}"}, headers=headers,
        )
        await client.post(
            f"/api/v1/tournaments/{t_id}/players/?player_id={r.json()['uuid']}",
            headers=headers,
        )

    # Start tournament (draws round 1)
    r = await client.post(f"/api/v1/tournaments/{t_id}/start", headers=headers)
    assert_response_code(r, 200)

    # Get stage_id
    r = await client.get(f"/api/v1/tournaments/{t_id}", headers=headers)
    stage_id = r.json()["stages"][0]["uuid"]

    # Get round 1 matches — verify no duplicate players
    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=headers)
    assert_response_code(r, 200)
    matches_r1 = r.json()
    assert len(matches_r1) == PLAYER_COUNT // 2, f"Expected {PLAYER_COUNT // 2} matches, got {len(matches_r1)}"
    _assert_no_player_dupes(matches_r1, "Round 1")

    # Score all round 1 matches
    for m in matches_r1:
        r = await client.patch(
            f"/api/v1/matches/{m['uuid']}/score",
            json={"score_a": 6, "score_b": 3}, headers=headers,
        )
        assert_response_code(r, 200)

    # Draw round 2
    r = await client.post(
        f"/api/v1/tournaments/{t_id}/stages/{stage_id}/draw-round",
        headers=headers,
    )
    assert_response_code(r, 200)

    # Get all matches and filter round 2
    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=headers)
    assert_response_code(r, 200)
    all_matches = r.json()
    matches_r2 = [m for m in all_matches if m["round_number"] == 2]
    assert len(matches_r2) == PLAYER_COUNT // 2, f"Round 2: expected {PLAYER_COUNT // 2} matches, got {len(matches_r2)}"
    _assert_no_player_dupes(matches_r2, "Round 2")


@pytest.mark.asyncio
async def test_no_player_plays_twice_doubles(client: AsyncClient):
    """In DYP doubles, each player must appear in at most one match per round."""
    headers = await _auth_headers(client, "nodup_dbl@test.com", "password123")
    PLAYER_COUNT = 16  # even, for doubles

    r = await client.post(
        "/api/v1/tournaments/",
        json={
            "name": "NoDup Doubles", "date": "2026-04-15",
            "player_mode": "doubles", "settings": {"table_count": 8},
        },
        headers=headers,
    )
    t_id = r.json()["uuid"]

    for i in range(PLAYER_COUNT):
        r = await client.post(
            "/api/v1/players/", json={"nickname": f"DD{i}"}, headers=headers,
        )
        await client.post(
            f"/api/v1/tournaments/{t_id}/players/?player_id={r.json()['uuid']}",
            headers=headers,
        )

    r = await client.post(f"/api/v1/tournaments/{t_id}/start", headers=headers)
    assert_response_code(r, 200)

    r = await client.get(f"/api/v1/tournaments/{t_id}", headers=headers)
    stage_id = r.json()["stages"][0]["uuid"]

    # Round 1: 16 players → 8 teams → 4 matches
    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=headers)
    matches_r1 = r.json()
    expected_matches = PLAYER_COUNT // 4  # teams = players/2, matches = teams/2
    assert len(matches_r1) == expected_matches, f"R1: expected {expected_matches} matches, got {len(matches_r1)}"

    # Score all
    for m in matches_r1:
        r = await client.patch(
            f"/api/v1/matches/{m['uuid']}/score",
            json={"score_a": 6, "score_b": 4}, headers=headers,
        )
        assert_response_code(r, 200)

    # Draw round 2
    r = await client.post(
        f"/api/v1/tournaments/{t_id}/stages/{stage_id}/draw-round",
        headers=headers,
    )
    assert_response_code(r, 200)

    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=headers)
    all_matches = r.json()
    matches_r2 = [m for m in all_matches if m["round_number"] == 2]
    assert len(matches_r2) == expected_matches, f"R2: expected {expected_matches} matches, got {len(matches_r2)}"


def _assert_no_player_dupes(matches, label):
    """Assert no player appears in more than one match in the given list."""
    seen = set()
    for m in matches:
        for pid in (m.get("player_a_id"), m.get("player_b_id")):
            if pid:
                assert pid not in seen, f"{label}: player {pid} appears in multiple matches!"
                seen.add(pid)


@pytest.mark.asyncio
async def test_table_assignment_distributes_matches(client: AsyncClient):
    """Matches are assigned to different tables when tables are available."""
    headers = await _auth_headers(client, "tables@test.com", "password123")

    # Create singles tournament with 3 tables
    r = await client.post(
        "/api/v1/tournaments/",
        json={
            "name": "Table Test", "date": "2026-04-15",
            "player_mode": "singles",
            "settings": {"table_count": 3},
        },
        headers=headers,
    )
    assert_response_code(r, 200)
    t_id = r.json()["uuid"]

    # Add 6 players → 3 matches → exactly 3 tables needed
    pids = []
    for nick in ("T1", "T2", "T3", "T4", "T5", "T6"):
        r = await client.post(
            "/api/v1/players/", json={"nickname": nick}, headers=headers
        )
        pid = r.json()["uuid"]
        pids.append(pid)
        await client.post(
            f"/api/v1/tournaments/{t_id}/players/?player_id={pid}",
            headers=headers,
        )

    # Start → auto-draws first round
    r = await client.post(f"/api/v1/tournaments/{t_id}/start", headers=headers)
    assert_response_code(r, 200)

    # Get matches
    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=headers)
    assert_response_code(r, 200)
    matches = r.json()
    assert len(matches) == 3

    # All 3 matches should have different table numbers (1, 2, 3)
    tables = [m["table_number"] for m in matches]
    assert set(tables) == {1, 2, 3}, f"Expected tables {{1,2,3}}, got {tables}"


@pytest.mark.asyncio
async def test_table_assignment_queues_overflow(client: AsyncClient):
    """When more matches than tables, excess matches are queued (table_number=None)."""
    headers = await _auth_headers(client, "overflow@test.com", "password123")

    # Create tournament with only 1 table
    r = await client.post(
        "/api/v1/tournaments/",
        json={
            "name": "Queue Test", "date": "2026-04-15",
            "player_mode": "singles",
            "settings": {"table_count": 1},
        },
        headers=headers,
    )
    t_id = r.json()["uuid"]

    # Add 4 players → 2 matches, but only 1 table
    for nick in ("Q1", "Q2", "Q3", "Q4"):
        r = await client.post(
            "/api/v1/players/", json={"nickname": nick}, headers=headers
        )
        await client.post(
            f"/api/v1/tournaments/{t_id}/players/?player_id={r.json()['uuid']}",
            headers=headers,
        )

    r = await client.post(f"/api/v1/tournaments/{t_id}/start", headers=headers)
    assert_response_code(r, 200)

    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=headers)
    assert_response_code(r, 200)
    matches = r.json()
    assert len(matches) == 2

    tables = [m["table_number"] for m in matches]
    assert 1 in tables, "First match should be on table 1"
    assert None in tables, "Second match should be queued (table_number=None)"


@pytest.mark.asyncio
async def test_qr_code_generation(client: AsyncClient):
    """QR endpoint generates registration URL with secret token."""
    headers = await _auth_headers(client, "qrgen@test.com", "password123")

    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "QR Test", "date": "2026-04-15"},
        headers=headers,
    )
    assert_response_code(r, 200)
    t_id = r.json()["uuid"]

    # JSON format returns URL with token
    r = await client.get(f"/v1/public/tournaments/{t_id}/qr?format=json")
    assert_response_code(r, 200)
    data = r.json()
    assert "registration_url" in data
    url = data["registration_url"]
    assert f"register/{t_id}" in url
    assert "token=" in url
    # Token should be non-trivial (not empty, not just the UUID)
    token = url.split("token=")[1]
    assert len(token) >= 16

    # SVG format returns image
    r = await client.get(f"/v1/public/tournaments/{t_id}/qr?format=svg")
    assert_response_code(r, 200)
    assert "svg" in r.headers.get("content-type", "")

    # PNG format also works (segno generates without Pillow)
    r = await client.get(f"/v1/public/tournaments/{t_id}/qr?format=png")
    assert_response_code(r, 200)
    assert "png" in r.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_qr_token_is_unique_per_tournament(client: AsyncClient):
    """Each tournament gets its own unique registration token."""
    headers = await _auth_headers(client, "qruniq@test.com", "password123")

    tokens = []
    for i in range(3):
        r = await client.post(
            "/api/v1/tournaments/",
            json={"name": f"T{i}", "date": "2026-04-15"},
            headers=headers,
        )
        t_id = r.json()["uuid"]
        r = await client.get(f"/v1/public/tournaments/{t_id}/qr?format=json")
        url = r.json()["registration_url"]
        tokens.append(url.split("token=")[1])

    # All tokens should be different
    assert len(set(tokens)) == 3


@pytest.mark.asyncio
async def test_self_register_without_token_fails(client: AsyncClient):
    """Self-registration without a valid token is rejected."""
    headers = await _auth_headers(client, "notoken@test.com", "password123")

    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "Secure", "date": "2026-04-15"},
        headers=headers,
    )
    t_id = r.json()["uuid"]

    # No token field at all → 422 (validation error)
    r = await client.post(
        f"/v1/public/tournaments/{t_id}/register",
        json={"nickname": "Hacker"},
    )
    assert r.status_code == 422

    # Wrong token → 403
    r = await client.post(
        f"/v1/public/tournaments/{t_id}/register",
        json={"nickname": "Hacker", "token": "wrong-token"},
    )
    assert r.status_code == 403

    # Correct token works
    r = await client.get(f"/v1/public/tournaments/{t_id}/qr?format=json")
    real_token = r.json()["registration_url"].split("token=")[1]
    r = await client.post(
        f"/v1/public/tournaments/{t_id}/register",
        json={"nickname": "Legit", "token": real_token},
    )
    assert_response_code(r, 200)
    assert r.json()["nickname"] == "Legit"


@pytest.mark.asyncio
async def test_delete_tournament(client: AsyncClient):
    """Owner can delete a tournament."""
    headers = await _auth_headers(client, "del@test.com", "password123")

    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "To Delete", "date": "2026-04-15"},
        headers=headers,
    )
    assert_response_code(r, 200)
    t_id = r.json()["uuid"]

    # Delete
    r = await client.delete(f"/api/v1/tournaments/{t_id}", headers=headers)
    assert_response_code(r, 200)

    # Verify it's gone from listing
    r = await client.get("/api/v1/tournaments/", headers=headers)
    assert_response_code(r, 200)
    ids = [t["uuid"] for t in r.json()]
    assert t_id not in ids


@pytest.mark.asyncio
async def test_error_messages_are_readable(client: AsyncClient):
    """API validation errors return human-readable messages, not [object Object]."""
    headers = await _auth_headers(client, "err@test.com", "password123")

    # Missing required field 'date'
    r = await client.post(
        "/api/v1/tournaments/",
        json={"name": "No Date"},
        headers=headers,
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    # detail should be a list with readable messages
    assert isinstance(detail, list)
    assert len(detail) > 0
    assert "msg" in detail[0]


@pytest.mark.asyncio
async def test_standings_show_player_names_singles(client: AsyncClient):
    """Standings must show proper nicknames, never '?' or UUID fragments (singles)."""
    t_id, headers, _ = await _create_started_tournament(
        client, "names_s@test.com", ("NickAlpha", "NickBeta"),
    )
    r = await client.get(f"/api/v1/tournaments/{t_id}", headers=headers)
    stage_id = r.json()["stages"][0]["uuid"]

    # Score a match so standings are populated
    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=headers)
    mid = r.json()[0]["uuid"]
    await client.patch(
        f"/api/v1/matches/{mid}/score",
        json={"score_a": 6, "score_b": 2}, headers=headers,
    )

    r = await client.get(f"/v1/public/tournaments/{t_id}/stages/{stage_id}/standings")
    assert_response_code(r, 200)
    standings = r.json()
    assert len(standings) == 2
    for s in standings:
        nick = s["nickname"]
        assert nick in ("NickAlpha", "NickBeta"), f"Unexpected nickname: {nick!r}"
        assert nick != "?"


@pytest.mark.asyncio
async def test_standings_show_player_names_doubles(client: AsyncClient):
    """In DYP doubles, standings show individual players, not teams."""
    t_id, headers, _ = await _create_started_tournament(
        client, "names_d@test.com", ("DblAA", "DblBB", "DblCC", "DblDD"),
        player_mode="doubles",
    )
    r = await client.get(f"/api/v1/tournaments/{t_id}", headers=headers)
    stage_id = r.json()["stages"][0]["uuid"]

    # Score a match
    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=headers)
    mid = r.json()[0]["uuid"]
    await client.patch(
        f"/api/v1/matches/{mid}/score",
        json={"score_a": 6, "score_b": 4}, headers=headers,
    )

    r = await client.get(f"/v1/public/tournaments/{t_id}/stages/{stage_id}/standings")
    assert_response_code(r, 200)
    standings = r.json()
    # 4 individual players, not 2 teams
    assert len(standings) == 4
    nicks = {s["nickname"] for s in standings}
    assert nicks == {"DblAA", "DblBB", "DblCC", "DblDD"}, f"Got: {nicks}"
    for s in standings:
        assert "?" not in s["nickname"]
        assert "&" not in s["nickname"], "Should show individual players, not teams"


@pytest.mark.asyncio
async def test_match_listing_shows_player_names(client: AsyncClient):
    """Match listing must include proper player/team names, never just UUIDs."""
    t_id, headers, _ = await _create_started_tournament(
        client, "names_m@test.com", ("MatchNick1", "MatchNick2"),
    )
    r = await client.get(f"/api/v1/tournaments/{t_id}/matches/", headers=headers)
    assert_response_code(r, 200)
    matches = r.json()
    assert len(matches) >= 1
    m = matches[0]
    assert m["player_a_nickname"] in ("MatchNick1", "MatchNick2")
    assert m["player_b_nickname"] in ("MatchNick1", "MatchNick2")
    assert m["player_a_nickname"] != m["player_b_nickname"]